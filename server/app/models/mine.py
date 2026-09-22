"""我的域 ORM 模型：订单 / 优惠券 / 我的课程。

建表：python -m app.init_db
说明：这三张表都是「用户数据」，均带 uid 字段归属到具体用户。
      本期种子数据先挂在演示账号下，后续接入真实下单流程即可复用。
"""
from sqlalchemy import Index, Integer, Numeric, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    """订单表。

    ⚠️ 表名用 order_info 而非 order：
       ORDER 是 SQL 保留字，直接用会导致每次查询都必须写反引号。
    """

    __tablename__ = "order_info"
    __table_args__ = (
        Index("idx_uid", "uid"),
        {"comment": "订单表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="订单ID")
    uid: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="所属用户ID（user.id）"
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, comment="商品标题")
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="金额")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="订单状态")
    date: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="下单日期 yyyy-MM-dd")
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="course", comment="商品类型 course / vip"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class Coupon(Base):
    """优惠券表。"""

    __tablename__ = "coupon"
    __table_args__ = (
        Index("idx_uid", "uid"),
        {"comment": "优惠券表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="优惠券ID")
    uid: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="所属用户ID"
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="面额（元）")
    threshold: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="使用门槛文案")
    scope: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="适用范围")
    expire: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="到期日")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unused", comment="unused=可用 / expired=已过期"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class UserCourse(Base):
    """我的课程表（学习记录）。

    ⚠️ kind 取值：learning=在学 / finished=已学完 / collect=我的收藏
    """

    __tablename__ = "user_course"
    __table_args__ = (
        Index("idx_uid_kind", "uid", "kind"),
        {"comment": "我的课程表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="记录ID")
    uid: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="所属用户ID"
    )
    kind: Mapped[str] = mapped_column(
        String(12), nullable=False, default="learning", comment="learning / finished / collect"
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, comment="课程标题")
    teacher: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="讲师")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="学习进度(%)")
    last_lesson: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="最近学到")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
