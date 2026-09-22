"""安全与鉴权：bcrypt 密码哈希、JWT 签发/解析、当前用户依赖。

安全约定：
    - 密码只存 bcrypt 哈希，响应、日志、数据库中均不出现明文；
    - JWT 采用 HS256，载荷仅 uid/phone/iat/exp，不携带任何敏感信息；
    - 已注销（逻辑删除）的用户一律按 401 处理，不允许继续访问。
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET
from app.core.response import BizError
from app.database import get_db
from app.models import User

# auto_error=False：
#   HTTPBearer 默认在缺少 Authorization 头时直接抛 403，
#   这里关掉它，交由我们返回统一的业务错误码 40100
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希。

    ⚠️ 调用方需先校验密码长度（6~20 位），本函数不做业务校验。
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与数据库中的哈希是否匹配。

    ⚠️ 边界处理：
        1. hashed 为空串 → 表示该账号未设置密码（纯验证码账号），直接返回 False；
        2. hashed 内容损坏时 bcrypt 会抛 ValueError，此处捕获返回 False，
           避免把密码校验失败升级成 500 服务器错误。
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    """签发 JWT。

    ⚠️ 纯 CPU 计算，无 IO，因此声明为同步函数，无需 await。
    ⚠️ 载荷刻意最小化：只放 uid/phone/iat/exp，不放昵称等可变信息，
       否则用户改名后旧 token 里的信息会不一致。
    """
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user.id,
        "phone": user.phone,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """鉴权依赖：所有需要登录的端点统一写 Depends(get_current_user)。

    错误码约定：
        40100 未携带 token 或 token 无效 → HTTP 401
        40101 token 已过期               → HTTP 401
        40102 用户不存在或已注销         → HTTP 401
    """
    if cred is None:
        raise BizError(40100, "请先登录", http=401)
    return await get_user_by_token(db, cred.credentials)


async def get_user_by_token(db: AsyncSession, token: str) -> User:
    """按 token 取活跃用户。

    抽成独立函数的目的：HTTP 之外的通路（如未来接入 WebSocket）也要鉴权，
    但它们没有 HTTP 状态码，可以由调用方把 BizError 转换成各自的关闭码。
    """
    if not token:
        raise BizError(40100, "请先登录", http=401)

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise BizError(40101, "登录已过期，请重新登录", http=401)
    except jwt.InvalidTokenError:
        raise BizError(40100, "请先登录", http=401)

    uid = payload.get("uid")
    # ⚠️ 查询必须带 deleted_at IS NULL：已注销用户的旧 token 不能继续使用
    result = await db.execute(
        select(User).where(User.id == uid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise BizError(40102, "账号不存在或已注销", http=401)
    return user
