"""用户查询封装。

设计意图：
    把「逻辑删除过滤」这条纪律收敛到单一位置，避免各处业务代码
    自己拼查询时漏掉 deleted_at IS NULL 条件（这是逻辑删除方案最常见的漏洞）。

约定：
    对外查询一律使用 get_active_user_by_phone；
    get_user_any_status 仅供「注销复活」策略内部使用。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_active_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    """按手机号查询「活跃」用户（未注销）。

    参数：
        db:    数据库会话
        phone: 手机号
    返回：
        User 对象；不存在时返回 None
    """
    result = await db.execute(
        select(User).where(User.phone == phone, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_any_status(db: AsyncSession, phone: str) -> User | None:
    """按手机号查询用户，包含已注销记录。

    ⚠️ 仅供「注销复活」策略内部使用，业务代码请勿调用。
        - 返回对象 deleted_at 为 None  → 该手机号已被占用
        - 返回对象 deleted_at 非 None → 可复用该行并清除 deleted_at 实现复活
    """
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def get_active_user_by_email(db: AsyncSession, email: str) -> User | None:
    """按邮箱查询「活跃」用户（未注销）。

    说明：本期注册 / 登录账号为邮箱，这是对外查询邮箱用户的统一入口。
    """
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_any_status_by_email(db: AsyncSession, email: str) -> User | None:
    """按邮箱查询用户，包含已注销记录。

    ⚠️ 仅供「注销复活」策略内部使用，业务代码请勿调用。
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()
