"""用户域路由。

前缀：/api/v1/user
端点总表（🔒 = 需登录）：
    POST   /sms        发送验证码      （公开）
    POST   /reg        注册            （公开）
    POST   /login      登录            （公开）
    GET    /info       查询我的资料    🔒
    PUT    /info       更新我的资料    🔒
    PUT    /password   修改密码        🔒
    POST   /logout     退出登录        🔒
    DELETE ""          注销账号        🔒

本模块错误码：
    40001 手机号格式不正确
    40002 验证码错误 / 失败次数超限
    40003 验证码已过期
    40004 发送过于频繁
    40005 该手机号已注册
    40006 该手机号未注册
    40007 密码错误
    40008 未设置密码 / 原密码错误
    40009 长度或格式不合法
    40100~40102 鉴权失败（见 core/security.py）
"""
import logging
import random
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    EMAIL_CODE_LEN,
    EMAIL_DEBUG,
    EMAIL_INTERVAL,
    EMAIL_MAX_VERIFY_ATTEMPTS,
    EMAIL_TTL,
)
from app.core.mail import send_email_code
from app.core.query import (
    get_active_user_by_email,
    get_user_any_status_by_email,
)
from app.core.response import BizError, ok
from app.core.security import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import EmailCode, User
from app.schemas.user import (
    ChangePwdIn,
    EmailIn,
    LoginIn,
    RegIn,
    UpdateProfileIn,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/user", tags=["用户"])

# ---------- 常量 ----------
# 邮箱格式：基础校验（xx@yy.zz）。不追求 RFC 全量合规，真实性由验证码环节保证
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PWD_MIN, PWD_MAX = 6, 20                # 密码长度区间（与客户端校验一致）
NICK_MIN, NICK_MAX = 1, 20              # 昵称长度区间
SIGN_MAX = 60                           # 签名最大长度
DEFAULT_SIGNATURE = "这个人很懒，什么都没写"


def default_nickname(email: str) -> str:
    """生成默认昵称：取邮箱 @ 前的用户名部分。

    例如 zhangsan@qq.com → 同学zhangsan
    """
    name = (email or "").split("@")[0] or "用户"
    return "同学" + name[:12]


# ==========================================================
# 内部复用函数
# ==========================================================


async def verify_email_code(db: AsyncSession, email: str, code: str) -> None:
    """校验邮箱验证码，通过后置为已使用（单次有效）。

    ⚠️ 安全加固：增加「校验失败次数」限制。
        4 位验证码仅 1 万种组合，若不限制尝试次数，
        攻击者可在有效期内穷举成功。
        累计失败达 EMAIL_MAX_VERIFY_ATTEMPTS 次即作废该验证码。

    错误码：
        40002 验证码不存在 / 错误 / 失败次数超限
        40003 验证码已过期（过期判定优先于内容比对）
    """
    # 取该邮箱最新一条未失效的验证码
    result = await db.execute(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.used == 0)
        .order_by(EmailCode.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise BizError(40002, "验证码错误")

    # 1) 过期优先：顺手作废，避免被继续尝试
    if row.expires_at < datetime.now():
        row.used = 1
        await db.commit()
        raise BizError(40003, "验证码已过期，请重新获取")

    # 2) 失败次数已达上限：作废
    if row.verify_attempts >= EMAIL_MAX_VERIFY_ATTEMPTS:
        row.used = 1
        await db.commit()
        raise BizError(40002, "验证码错误次数过多，请重新获取")

    # 3) 内容比对失败：累计失败次数，达上限则作废并给出精确提示
    if row.code != code:
        row.verify_attempts += 1
        reached_limit = row.verify_attempts >= EMAIL_MAX_VERIFY_ATTEMPTS
        if reached_limit:
            row.used = 1
        await db.commit()
        # ⚠️ 达上限与普通错误给不同文案，否则用户无法判断是输错了还是验证码已作废
        if reached_limit:
            raise BizError(40002, "验证码错误次数过多，请重新获取")
        raise BizError(40002, "验证码错误")

    # 4) 校验通过：置为已使用（单次有效，防重放）
    row.used = 1
    await db.commit()


async def register_or_revive(db: AsyncSession, email: str, password: str | None) -> User:
    """注册或复活用户（按邮箱）。

    ⚠️ 复活策略（配合 UNIQUE(email) 硬约束）：
        邮箱注销后记录仍保留（逻辑删除），同邮箱再次注册会撞唯一键，
        因此必须复用原行：清除 deleted_at、重置资料，并保留原 created_at。

    前置条件：调用方需保证「活跃的同邮箱用户」不存在。
    """
    pwd_hash = hash_password(password) if password else ""

    user = await get_user_any_status_by_email(db, email)
    if user is not None:
        # 存在历史记录（已注销）→ 复活，注销记录作废
        user.deleted_at = None
        user.password = pwd_hash
        user.nickname = default_nickname(email)
        user.avatar = ""
        user.signature = DEFAULT_SIGNATURE
    else:
        # 全新用户
        user = User(
            email=email,
            password=pwd_hash,
            nickname=default_nickname(email),
            signature=DEFAULT_SIGNATURE,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user


async def finish_login(db: AsyncSession, user: User) -> dict:
    """登录收尾：更新最后登录时间 → 签发 token → 返回统一结构。"""
    user.last_login_at = datetime.now()
    await db.commit()
    await db.refresh(user)
    return ok({"token": create_token(user), "user": UserOut.from_model(user)})


# ==========================================================
# 公开端点（无需登录）
# ==========================================================


@router.post("/email/code", summary="发送邮箱验证码")
async def send_verify_code(body: EmailIn, db: AsyncSession = Depends(get_db)):
    """发送邮箱验证码。

    校验顺序：邮箱格式(40001) → 60 秒重发频控(40004) → 发送邮件。

    ⚠️ EMAIL_DEBUG=true  时验证码随响应以 dev_code 返回（调试用，不发邮件）；
       EMAIL_DEBUG=false 时通过 SMTP 真实发送，响应中不含验证码。
    """
    email = (body.email or "").strip().lower()

    # 参数校验：邮箱格式
    if not EMAIL_RE.match(email):
        raise BizError(40001, "邮箱格式不正确")

    # 频控：同一邮箱 60 秒内只能发一次
    last_result = await db.execute(
        select(EmailCode)
        .where(EmailCode.email == email)
        .order_by(EmailCode.id.desc())
        .limit(1)
    )
    last = last_result.scalar_one_or_none()
    if last and (datetime.now() - last.created_at).total_seconds() < EMAIL_INTERVAL:
        raise BizError(40004, "发送过于频繁，请稍后再试")

    # 生成验证码并落库
    code = "".join(random.choices("0123456789", k=EMAIL_CODE_LEN))
    db.add(
        EmailCode(
            email=email,
            code=code,
            verify_attempts=0,
            expires_at=datetime.now() + timedelta(seconds=EMAIL_TTL),
        )
    )
    await db.commit()

    # 发送邮件：调试模式为空操作；未配置 SMTP 或发送失败会抛 RuntimeError
    try:
        send_email_code(email, code, ttl_minutes=max(1, EMAIL_TTL // 60))
    except RuntimeError as e:
        # ⚠️ 开发阶段把具体原因回传给客户端（如「SMTP 未配置」），便于快速定位；
        #    正式环境建议改为统一文案，避免向外暴露服务端配置细节
        logger.error("[email] 发送失败: %s", e)
        raise BizError(50001, str(e))
    # ⚠️ 日志只记录事件与邮箱，绝不打印验证码
    logger.info("[email] email=%s 验证码已生成，有效期 %ss", email, EMAIL_TTL)

    data = {"expires_in": EMAIL_TTL}
    if EMAIL_DEBUG:
        # 调试模式：验证码随响应返回，便于本地联调
        data["dev_code"] = code
    return ok(data)


@router.post("/reg", summary="注册")
async def register(body: RegIn, db: AsyncSession = Depends(get_db)):
    """注册（邮箱验证码 + 可选密码）。

    校验顺序：邮箱格式(40001) → 密码长度(40009) → 验证码(40002/40003) → 是否已注册(40005)。
    成功后直接登录，返回 token + user。
    """
    email = (body.email or "").strip().lower()

    if not EMAIL_RE.match(email):
        raise BizError(40001, "邮箱格式不正确")
    if body.password is not None and not (PWD_MIN <= len(body.password) <= PWD_MAX):
        raise BizError(40009, f"密码需 {PWD_MIN}~{PWD_MAX} 位")

    # 先校验验证码（失败即返回，不产生任何数据变更）
    await verify_email_code(db, email, body.code)

    # 已存在活跃用户 → 拒绝
    if await get_active_user_by_email(db, email):
        raise BizError(40005, "该邮箱已注册，请直接登录")

    # ⚠️ 邀请码：本期仅接收不处理（邀请关系需单独的关系表与奖励规则，另作设计）
    if body.invite:
        logger.info("[user.reg] 收到邀请码填写，暂不处理")

    user = await register_or_revive(db, email, body.password)
    logger.info("[user.reg] 注册成功 uid=%s", user.id)
    return await finish_login(db, user)


@router.post("/login", summary="登录")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    """登录。

    mode=code：邮箱验证码登录；未注册的邮箱自动注册（密码留空）。
    mode=pwd ：密码登录；未注册(40006) / 未设密码(40008) / 密码错误(40007)。
    """
    email = (body.email or "").strip().lower()

    if not EMAIL_RE.match(email):
        raise BizError(40001, "邮箱格式不正确")

    # ---------- 验证码登录 ----------
    if body.mode == "code":
        await verify_email_code(db, email, body.code or "")
        user = await get_active_user_by_email(db, email)
        if user is None:
            # 未注册 → 自动注册（与客户端「验证码登录即注册」的交互一致）
            user = await register_or_revive(db, email, None)
            logger.info("[user.login] 验证码登录自动注册 uid=%s", user.id)
        return await finish_login(db, user)

    # ---------- 密码登录 ----------
    user = await get_active_user_by_email(db, email)
    if user is None:
        raise BizError(40006, "该邮箱未注册")
    if not user.password:
        # 纯验证码账号没有密码，引导其改用验证码登录
        raise BizError(40008, "该账号未设置密码，请用验证码登录")
    if not verify_password(body.password or "", user.password):
        raise BizError(40007, "密码错误")

    return await finish_login(db, user)


# ==========================================================
# 鉴权端点（🔒 需登录）
# ==========================================================


@router.get("/info", summary="查询我的资料")
async def get_info(user: User = Depends(get_current_user)):
    """查询当前登录用户的资料。

    用户身份从 JWT 解析（不走前端传参，避免越权查看他人资料）。
    """
    return ok({"user": UserOut.from_model(user)})


@router.put("/info", summary="更新我的资料")
async def update_info(
    body: UpdateProfileIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新资料。

    规则：字段传了才更新（未传 = 不动）。
    校验：昵称 1~20 字(40009)。
    ⚠️ 先完成全部校验再写入，避免出现「部分字段已改、部分校验失败」的半写状态。
    """
    # 统一去空白，并区分「未传(None)」与「传了空串」
    nickname = body.nickname.strip() if body.nickname is not None else None
    signature = body.signature.strip() if body.signature is not None else None
    avatar = body.avatar.strip() if body.avatar is not None else None

    # 先校验
    if nickname is not None and not (NICK_MIN <= len(nickname) <= NICK_MAX):
        raise BizError(40009, f"昵称需 {NICK_MIN}~{NICK_MAX} 字")
    if signature is not None and len(signature) > SIGN_MAX:
        raise BizError(40009, f"签名不能超过 {SIGN_MAX} 字")

    # 后写入
    if nickname is not None:
        user.nickname = nickname
    if signature is not None:
        user.signature = signature
    if avatar is not None:
        user.avatar = avatar  # 传空串 = 清除头像，回退到前端首字占位

    await db.commit()
    await db.refresh(user)
    return ok({"user": UserOut.from_model(user)})


@router.put("/password", summary="修改密码")
async def change_password(
    body: ChangePwdIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码。

    verify=old ：校验原密码；账号未设密码时返回 40008 引导改用短信方式。
    verify=code：校验邮箱验证码（用于给未设密码的账号补设密码）。
    verify=set ：已登录用户直接设置/补设密码，无需原密码、也不用再收验证码。
                 安全性由 get_current_user（JWT 鉴权）保证；主要用于
                 「验证码首次登录后顺手设密码」与「设置页给无密码账号补设」。

    ⚠️ 无论哪种方式，新密码都需满足 6~20 位。
    """
    if not (PWD_MIN <= len(body.new_password) <= PWD_MAX):
        raise BizError(40009, f"新密码需 {PWD_MIN}~{PWD_MAX} 位")

    if body.verify == "old":
        if not user.password:
            raise BizError(40008, "该账号未设置密码，请用验证码方式设置")
        if not verify_password(body.old_password or "", user.password):
            raise BizError(40008, "原密码错误")
    elif body.verify == "set":
        # 已登录上下文直接补设密码（首次验证码登录后顺手设、或无密码账号在设置页补设）
        # 不校验原密码/验证码：JWT 已证明当前用户身份，避免「再收一次验证码」的割裂体验
        pass
    else:
        # verify == "code"：邮箱验证码校验（用于给未设密码的账号补设密码）
        await verify_email_code(db, user.email or "", body.code or "")

    user.password = hash_password(body.new_password)
    await db.commit()
    logger.info("[user.pwd] 密码已修改 uid=%s verify=%s", user.id, body.verify)
    return ok({})


@router.post("/logout", summary="退出登录")
async def logout(user: User = Depends(get_current_user)):
    """退出登录。

    ⚠️ JWT 是无状态的，服务端不保存会话，因此这里无需清理任何数据，
       客户端丢弃本地 token 即完成登出。
       如需「服务端主动作废 token」，需引入 Redis 黑名单，本期不做。
    """
    return ok({})


@router.delete("", summary="注销账号")
async def delete_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """注销账号（逻辑删除）。

    ⚠️ 只置 deleted_at，绝不做物理 DELETE：
        1. 保留历史数据可追溯；
        2. 注销后该手机号可在将来重新注册（复活策略）。
    注销后该用户的旧 token 立即失效（get_current_user 会过滤 deleted_at）。
    """
    user.deleted_at = datetime.now()
    await db.commit()
    logger.info("[user.delete] 账号已注销 uid=%s", user.id)
    return ok({})
