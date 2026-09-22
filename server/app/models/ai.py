"""AI 助教域 ORM 模型：会话表 / 消息表。

建表：python -m app.init_db

设计说明：
    - 会话与消息都是用户数据，均归属到具体用户（uid）；
    - 删除会话采用「物理删除 + 级联删消息」：
      会话一旦删除，其消息不具保留价值。
      ⚠️ 这与 user 表的「逻辑删除」纪律不同，是有意区分——
         账号是主体需要可追溯，对话内容不是。
    - 图片附件（2026-09 新增）单独放在 AiMessageImage 表，见该类的说明。
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiSession(Base):
    """AI 会话表。"""

    __tablename__ = "ai_session"
    __table_args__ = (
        Index("idx_uid_updated", "uid", "updated_at"),
        {"comment": "AI 会话表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="会话ID"
    )
    uid: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属用户（user.id）"
    )
    title: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", comment="标题：取首条提问前 30 字"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间（首问时刻）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="最后活跃时间（生成收尾时由路由层显式刷新）",
    )


class AiMessage(Base):
    """AI 消息表（一问一答各占一行）。"""

    __tablename__ = "ai_message"
    __table_args__ = (
        Index("idx_session_id", "session_id", "id"),
        {"comment": "AI 消息表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="消息ID"
    )
    session_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属会话（ai_session.id）"
    )
    role: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="user=提问 / assistant=回答"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="文本内容（markdown）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="落库时间",
    )


class AiMessageImage(Base):
    """AI 消息图片附件表（一条消息可挂 0~N 张图）。

    ⚠️ 为什么单独建表，而不是给 ai_message 加一列：
        `init_db` 走的是 Base.metadata.create_all，它只创建「尚不存在」的表，
        绝不会 ALTER 已存在的表。给 ai_message 加字段在已有库上永远不会生效，
        必须先手工 ALTER 或删表重建（后者丢数据）。
        独立成新表则能被 create_all 干净地建出来，且天然支持「一条消息多张图」。

    ⚠️ 关联纪律：message_id 带真实外键 + ON DELETE CASCADE，
       与「会话/消息走物理删除」的既有策略保持一致（见 routers/ai.py:delete_session）。
       ⚠️ 但 delete_session 里仍会显式删除本表记录，不单纯依赖数据库级联：
          显式删除不依赖 MySQL 实际是否建成了这个外键，行为更可预期。

    ⚠️ 只存 URL 不存二进制：图片本体落在 server/uploads/ai/，
       由 main.py 用 StaticFiles 挂到 /uploads 对外提供。
       name 字段仅用于前端展示，绝不参与磁盘路径（防路径穿越）。
    """

    __tablename__ = "ai_message_image"
    __table_args__ = (
        Index("idx_message_id", "message_id", "sort_order"),
        {"comment": "AI 消息图片附件表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="附件ID"
    )
    message_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("ai_message.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属消息（ai_message.id）",
    )
    url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="访问路径，形如 /uploads/ai/<uuid>.jpg（客户端补上站点 origin）",
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="展示用文件名（不参与磁盘路径）"
    )
    size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="字节数"
    )
    mime: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", comment="MIME 类型（服务端按文件头判定）"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="同一条消息内的顺序，从 0 起"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="上传/关联时间",
    )
