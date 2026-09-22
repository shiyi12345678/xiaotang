"""用户域 ORM 模型。

建表方式（DDL 单源）：
    在 server/ 目录执行  python -m app.init_db

设计要点：
    - 逻辑删除：deleted_at IS NULL 表示活跃；业务上不存在物理 DELETE；
    - updated_at 交给 MySQL 的 ON UPDATE 自动维护，ORM 侧不手动赋值；
    - 用户档案字段（等级/积分/会员）对齐客户端 common/mock/index.js 的 userInfo 结构。
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """用户表。"""

    __tablename__ = "user"
    __table_args__ = (
        # 手机号与邮箱各自唯一。
        # 与「注销复活」策略配合：注销只是置 deleted_at，行仍在，
        # 因此同号复注册时必须复用原行（否则会撞唯一键）。
        # ⚠️ MySQL 的 UNIQUE 允许多行为 NULL，故可空字段加唯一约束是安全的。
        UniqueConstraint("phone", name="uk_phone"),
        UniqueConstraint("email", name="uk_email"),
        {"comment": "用户表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="用户ID"
    )
    phone: Mapped[str | None] = mapped_column(
        String(11), nullable=True, comment="手机号（本期改用邮箱登录，此字段预留）"
    )
    email: Mapped[str | None] = mapped_column(
        String(120), nullable=True, comment="邮箱（本期注册/登录账号）"
    )
    password: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        comment="bcrypt 哈希；纯验证码注册未设密码时为空串",
    )
    nickname: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="",
        comment="昵称（注册默认：同学+手机尾号4位）",
    )
    avatar: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="头像URL；空串时前端用昵称首字占位",
    )
    signature: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", comment="个人签名"
    )
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="V1 学习新人", comment="等级文案"
    )
    level_progress: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="等级进度百分比 0~100"
    )
    points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="积分"
    )
    is_vip: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="是否会员 0否/1是"
    )
    vip_expire: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="会员到期日；NULL=非会员"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后一次登录时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="注册时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),  # MySQL ON UPDATE 自动维护
        comment="更新时间（自动维护）",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="逻辑删除时间；NULL=未删除"
    )


class SmsCode(Base):
    """短信验证码流水表。

    ⚠️ 与参考资料实现的一处差异：新增 verify_attempts 失败计数字段。
       4 位验证码仅 1 万种组合，若只校验正确性而不限制失败次数，
       攻击者可在 300 秒有效期内穷举出验证码。
    """

    __tablename__ = "sms_code"
    __table_args__ = (
        Index("idx_phone_time", "phone", "created_at"),
        {"comment": "短信验证码流水（演示期小表，可定期清理已用/过期行）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="流水ID"
    )
    phone: Mapped[str] = mapped_column(
        String(11), nullable=False, comment="接收手机号"
    )
    code: Mapped[str] = mapped_column(
        String(6), nullable=False, comment="验证码（SMS_CODE_LEN 位，默认 4 位）"
    )
    used: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="是否已失效 0未用/1已用或作废"
    )
    verify_attempts: Mapped[int] = mapped_column(
        TINYINT,
        nullable=False,
        default=0,
        comment="校验失败次数；达到 SMS_MAX_VERIFY_ATTEMPTS 即作废该验证码",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="过期时间（发送时刻 + SMS_TTL）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="发送时间",
    )


class EmailCode(Base):
    """邮箱验证码流水表。

    ⚠️ 与 SmsCode 结构一致但独立成表：
       两者下发通道不同（邮件 vs 短信），分开可避免混用；
       将来接入真实短信通道时，SmsCode 可直接启用，互不影响。
    """

    __tablename__ = "email_code"
    __table_args__ = (
        Index("idx_email_time", "email", "created_at"),
        {"comment": "邮箱验证码流水（含失败计数，防暴力枚举）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="流水ID"
    )
    email: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="接收邮箱"
    )
    code: Mapped[str] = mapped_column(
        String(6), nullable=False, comment="验证码（EMAIL_CODE_LEN 位，默认 4 位）"
    )
    used: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="是否已失效 0未用/1已用或作废"
    )
    verify_attempts: Mapped[int] = mapped_column(
        TINYINT,
        nullable=False,
        default=0,
        comment="校验失败次数；达到 EMAIL_MAX_VERIFY_ATTEMPTS 即作废该验证码",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="过期时间（发送时刻 + EMAIL_TTL）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="发送时间",
    )
