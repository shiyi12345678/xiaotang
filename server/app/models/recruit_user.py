"""招聘域 · 用户角色模型（区分求职者 / 企业 HR）。

建表方式（DDL 单源）：在 server/ 目录执行  python -m app.init_db

⚠️ 为什么单独建表，而不是给旧 user 表加 role / company_id 字段：
    本次改造的约定是「旧表原封不动、随时可回滚」，所以不动 user 表结构；
    账号体系（注册 / 登录 / 邮箱验证码 / JWT）仍然完全复用 user 表，
    本表只补充「身份 + 企业归属」这一层，避免把鉴权体系再造一遍。
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(Base):
    """用户角色表：一个账号可以同时拥有求职者与企业 HR 两种身份。"""

    __tablename__ = "user_role"
    __table_args__ = (
        # 同一账号 + 同一角色只允许一条；但允许同时存在 candidate 与 hr 两条
        UniqueConstraint("user_id", "role", name="uk_user_role"),
        Index("idx_role_company", "role", "company_id"),
        {"comment": "用户角色（求职者 / 企业HR）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键"
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="用户ID（关联 user.id）"
    )
    role: Mapped[str] = mapped_column(
        String(12), nullable=False, comment="candidate=求职者 / hr=企业HR"
    )
    company_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="HR 所属公司（关联 company.id）；求职者该字段为 NULL",
    )
    hr_title: Mapped[str] = mapped_column(
        String(30), nullable=False, default="", comment="HR 职位，如「招聘经理」"
    )
    is_default: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="登录后的默认身份 0否/1是"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间（自动维护）",
    )
