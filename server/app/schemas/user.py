"""用户域 Pydantic 出入参模型。

职责边界（重要）：
    本层只保证「类型与必填」；业务格式校验（手机号正则、密码长度区间等）
    一律放在路由层做，这样才能返回业务错误码（40001/40009），
    而不是让 FastAPI 抛出 422 被统一吞成 50000。
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

# ==========================================================
# 输入模型
# ==========================================================


class EmailIn(BaseModel):
    """发送邮箱验证码入参。"""

    email: str


class RegIn(BaseModel):
    """注册入参。"""

    email: str
    code: str
    password: str | None = None   # 可省略 → 纯验证码注册（不设密码）
    invite: str | None = None     # 邀请码：本期仅记录，不做邀请关系校验


class LoginIn(BaseModel):
    """登录入参。

    mode=code → 校验邮箱验证码；mode=pwd → 校验密码。
    用 Literal 约束取值，非法值由框架拦截。
    """

    mode: Literal["code", "pwd"]
    email: str
    code: str | None = None
    password: str | None = None


class UpdateProfileIn(BaseModel):
    """更新资料入参：字段全部可选，传了才更新。"""

    nickname: str | None = None
    avatar: str | None = None
    signature: str | None = None


class ChangePwdIn(BaseModel):
    """修改密码入参。

    verify=old  → 校验 old_password（适用于已设密码的账号改密）；
    verify=code → 校验邮箱验证码（用于给未设密码的账号补设密码）；
    verify=set  → 已登录用户直接设置/补设密码，无需原密码也不用再收验证码。
                  安全性由 JWT 鉴权（get_current_user 依赖）保证：能进到这里说明已登录，
                  因此主要用于「验证码首次登录后顺手设密码」与「设置页给无密码账号补设」。
                  ⚠️ 该模式不校验旧密码，仅限已登录上下文使用，禁止在未鉴权端点复用。
    """

    verify: Literal["old", "code", "set"]
    old_password: str | None = None
    code: str | None = None
    new_password: str


# ==========================================================
# 输出模型
# ==========================================================


def _fmt_dt(value: datetime | None) -> str | None:
    """时间格式化：统一输出 yyyy-MM-dd HH:mm:ss；None 保持 None。"""
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _fmt_date(value: date | None) -> str | None:
    """日期格式化：统一输出 yyyy-MM-dd；None 保持 None。"""
    return value.strftime("%Y-%m-%d") if value else None


class UserOut(BaseModel):
    """用户信息输出结构。

    ⚠️ 字段名使用 camelCase，与客户端 common/mock/index.js 的 userInfo 保持一致，
       前端拿到即可直接使用，无需再做字段名映射。

    ⚠️ 安全：不包含 password 字段，哈希值也不外泄。
    """

    id: str
    email: str
    phone: str
    nickname: str
    avatar: str
    signature: str
    level: str
    levelProgress: int
    points: int
    isVip: bool
    hasPassword: bool            # 是否已设置密码（用于前端判断要不要引导设密码）
    vipExpire: str | None
    createdAt: str | None
    lastLoginAt: str | None

    @classmethod
    def from_model(cls, u) -> dict:
        """由 ORM 对象构造前端可直接使用的字典。

        参数：
            u: User 模型实例
        返回：
            dict（camelCase 键名），可直接放入统一响应的 data 中

        ⚠️ hasPassword 由 password 字段是否非空推导：
           bcrypt 哈希不可能为空串以外的「假值」，故 bool(u.password) 可靠。
        """
        return cls(
            id=str(u.id),
            email=u.email or "",
            phone=u.phone or "",
            nickname=u.nickname,
            avatar=u.avatar,
            signature=u.signature,
            level=u.level,
            levelProgress=u.level_progress,
            points=u.points,
            isVip=bool(u.is_vip),
            hasPassword=bool(u.password),
            vipExpire=_fmt_date(u.vip_expire),
            createdAt=_fmt_dt(u.created_at),
            lastLoginAt=_fmt_dt(u.last_login_at),
        ).model_dump()
