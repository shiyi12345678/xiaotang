"""内容域 ORM 模型：分类 / 课程 / 页面配置。

建表：python -m app.init_db
说明：Mock 中的课程类数据来源多样（普通课、精品课、直播、秒杀、免费课），
      统一收敛到 course 表并用 kind 字段区分，差异字段统一放 extra(JSON)，
      避免为每种形态各建一张结构相近的表。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Category(Base):
    """分类表（合并「分类页左侧分类」与「首页分类入口」）。

    ⚠️ 主键设计说明：
       同一个业务分类（如 ai）在分类页与首页都有配置，但展示字段不同
       （分类页用 filled 图标，首页入口额外带 color/bg），因此不能只用业务 id 做主键。
       这里用自增主键 + (kind, biz_id) 唯一约束，允许同一 id 存两条；
       接口对外仍返回 biz_id，前端无感知。
    """

    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("kind", "id", name="uk_kind_biz"),
        Index("idx_kind_sort", "kind", "sort_order"),
        {"comment": "分类表"},
    )

    pk: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="自增主键"
    )
    id: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="业务标识（接口对外返回，前端使用）"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="分类名称")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="图标名")
    description: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="副标题")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="主色（首页入口用）")
    bg: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="底色（首页入口用）")
    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default="main", comment="main=分类页 / home=首页入口"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class Course(Base):
    """课程表（统一承载普通课 / 精品课 / 直播课 / 秒杀 / 免费课）。

    ⚠️ kind 取值：
        normal  普通课程（分类列表、搜索结果、猜你喜欢）
        quality 精品课
        live    直播课
        seckill 秒杀商品
        free    免费好课
        差异字段（如精品课的 tags、直播课的 teacherTitle）统一放 extra。
    """

    __tablename__ = "course"
    __table_args__ = (
        Index("idx_kind_sort", "kind", "sort_order"),
        Index("idx_category", "category_id"),
        {"comment": "课程表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="课程ID")
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", comment="课程类型")
    category_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="归属分类")
    title: Mapped[str] = mapped_column(String(120), nullable=False, comment="课程标题")
    summary: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="简介")
    teacher: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="讲师")
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="现价")
    origin_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="原价")
    enrolled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="报名人数")
    tag: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="角标文案")
    cover: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="封面地址（本期为空，前端渐变占位）")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    extra: Mapped[dict] = mapped_column(JSON, nullable=True, comment="差异化字段（tags/lessonCount/liveTime 等）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class PageConfig(Base):
    """页面配置表（key → JSON）。

    用途：存放纯展示型数据（轮播、公告、榜单、打卡、每日一句、
          筛选条件、学习概览、功能宫格等），这类数据不是业务实体，
          单独建表会造成大量结构相似的空壳表。
    ⚠️ 若后续某个配置需要在后台逐条维护，再单独迁移为实体表。
    """

    __tablename__ = "page_config"
    __table_args__ = ({"comment": "页面展示配置"},)

    key: Mapped[str] = mapped_column(String(64), primary_key=True, comment="配置键")
    value: Mapped[dict] = mapped_column(JSON, nullable=False, comment="配置内容(JSON)")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间（自动维护）",
    )
