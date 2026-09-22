"""招聘域 · 主体模型：公司 / 城市 / 职位分类 / 职位 / 职位收藏。

建表方式（DDL 单源）：在 server/ 目录执行  python -m app.init_db

设计要点：
    - 主键统一用「业务ID字符串」（如 c1001 / j2001 / cat-ai），与前端 mock 风格一致，
      前端路由与接口都直接用它，无需再做一次 id 映射；
    - 薪资用「整数K + 几薪」两级存储，不用字符串：
        salary_min / salary_max 单位是 K（如 15 表示 15K），salary_months 表示 13/14 薪，
        展示文案（"15-25K·14薪"）由后端 schema 拼，避免前端各自拼导致口径不一；
    - 学历/经验这类枚举直接存中文文案：它们是展示字段而非可计算维度，
      存英文枚举反而要多一层翻译表；
    - 逻辑删除：deleted_at IS NULL 表示有效，业务上不做物理 DELETE。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    """公司表。

    ⚠️ logo 用「主色 + 首字占位」而不是图片：
       本项目零图片资源（沿用改造前的约定），前端 zn-company-logo 组件
       用 logo_color 做渐变底、logo_text 做首字。
    """

    __tablename__ = "company"
    __table_args__ = (
        Index("idx_industry", "industry"),
        Index("idx_city", "city"),
        {"comment": "公司表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="公司ID，如 c1001")
    name: Mapped[str] = mapped_column(String(80), nullable=False, comment="公司全称")
    short_name: Mapped[str] = mapped_column(
        String(30), nullable=False, default="", comment="公司简称（列表展示用）"
    )
    logo_text: Mapped[str] = mapped_column(
        String(4), nullable=False, default="", comment="Logo 占位首字（1~2 字）"
    )
    logo_color: Mapped[str] = mapped_column(
        String(20), nullable=False, default="#00A6A7", comment="Logo 渐变主色"
    )
    industry: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="所属行业")
    scale: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="公司规模，如「1000-9999人」"
    )
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="融资阶段，如「D轮及以上」「已上市」"
    )
    city: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="所在城市")
    address: Mapped[str] = mapped_column(String(120), nullable=False, default="", comment="办公地址")
    intro: Mapped[str] = mapped_column(Text, nullable=True, comment="公司介绍")
    benefits: Mapped[list] = mapped_column(
        JSON, nullable=True, comment="福利标签数组，如 [\"五险一金\",\"弹性工作\"]"
    )
    website: Mapped[str] = mapped_column(String(120), nullable=False, default="", comment="官网")
    job_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="在招职位数（灌库时统计写入）"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间（自动维护）",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="逻辑删除时间；NULL=有效"
    )


class City(Base):
    """城市表（搜索页 / 筛选用，含热门城市与首字母分组）。"""

    __tablename__ = "city"
    __table_args__ = (
        Index("idx_hot_sort", "is_hot", "sort_order"),
        {"comment": "城市表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="城市ID，如 city-bj")
    name: Mapped[str] = mapped_column(String(20), nullable=False, comment="城市名，如「北京」")
    province: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="所属省份")
    initial: Mapped[str] = mapped_column(
        String(2), nullable=False, default="", comment="拼音首字母（城市列表分组用）"
    )
    is_hot: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="是否热门城市 0否/1是"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class JobCategory(Base):
    """职位职能分类表（两级：level=1 大类，level=2 子类）。

    ⚠️ 与旧 category 表的区别：
       旧表是「学习端的课程分类」，本表是招聘端的职能分类，业务含义不同故独立建表；
       结构上沿用「业务ID + kind + sort」的思路，前端分类页与筛选器共用。
    """

    __tablename__ = "job_category"
    __table_args__ = (
        Index("idx_level_sort", "level", "sort_order"),
        Index("idx_parent", "parent_id"),
        {"comment": "职位职能分类表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="分类ID，如 cat-tech")
    name: Mapped[str] = mapped_column(String(30), nullable=False, comment="分类名称")
    parent_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="父分类ID；一级分类为空串"
    )
    level: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="层级 1=大类 / 2=子类"
    )
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="图标名（uni-icons type）")
    description: Mapped[str] = mapped_column(String(60), nullable=False, default="", comment="副标题")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="主色（首页入口用）")
    bg: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="底色（首页入口用）")
    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default="main", comment="main=分类页 / home=首页入口"
    )
    is_hot: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0, comment="是否热门 0否/1是")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class Job(Base):
    """职位表。

    ⚠️ kind 取值（沿用旧 course 表的 kind 收敛思路）：
        normal    普通在招职位
        urgent    急招（列表带「急」角标）
        referral  名企内推（首页内推专区）
        intern    实习
        campus    校招
        差异字段（如内推奖金、是否支持远程）统一放 extra(JSON)。
    """

    __tablename__ = "job"
    __table_args__ = (
        Index("idx_status_sort", "status", "sort_order"),
        Index("idx_category", "category_id"),
        Index("idx_city", "city_id"),
        Index("idx_company", "company_id"),
        Index("idx_hr", "hr_id"),
        {"comment": "职位表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="职位ID，如 j2001")
    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default="normal", comment="职位形态 normal/urgent/referral/intern/campus"
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False, comment="职位名称")
    company_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="所属公司")
    category_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="职能子分类")
    city_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="城市")
    city_name: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="城市名冗余（列表直出，免联表）"
    )
    district: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="区域，如「海淀区」")
    salary_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="薪资下限（单位 K）")
    salary_max: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="薪资上限（单位 K）")
    salary_months: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=12, comment="几薪，如 13/14/15/16"
    )
    experience: Mapped[str] = mapped_column(
        String(20), nullable=False, default="经验不限", comment="经验要求（中文文案）"
    )
    education: Mapped[str] = mapped_column(
        String(20), nullable=False, default="学历不限", comment="学历要求（中文文案）"
    )
    job_type: Mapped[str] = mapped_column(
        String(12), nullable=False, default="fulltime", comment="fulltime/intern/parttime"
    )
    tags: Mapped[list] = mapped_column(
        JSON, nullable=True, comment="职位标签数组，如 [\"五险一金\",\"双休\"]"
    )
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="职位描述（岗位职责）")
    requirements: Mapped[str] = mapped_column(Text, nullable=True, comment="任职要求")
    status: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="状态 1=招聘中 / 0=已关闭"
    )
    hr_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="发布者 user_id（企业HR）；灌库数据可为空"
    )
    hr_name: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="招聘者姓名")
    hr_title: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="招聘者职位")
    hr_active: Mapped[str] = mapped_column(
        String(20), nullable=False, default="今日活跃", comment="招聘者活跃度文案"
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="浏览量")
    applicant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="投递人数")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序（越大越靠前）")
    extra: Mapped[dict] = mapped_column(
        JSON, nullable=True, comment="差异化字段（内推奖金 / 是否远程 / 面试流程等）"
    )
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="发布时间；NULL=未发布"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间（自动维护）",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="逻辑删除时间；NULL=有效"
    )


class JobFavorite(Base):
    """职位收藏表（求职者「我的收藏」）。"""

    __tablename__ = "job_favorite"
    __table_args__ = (
        # 同一人对同一职位只能收藏一次；重复收藏由接口做成幂等
        UniqueConstraint("user_id", "job_id", name="uk_user_job"),
        Index("idx_user_time", "user_id", "created_at"),
        {"comment": "职位收藏表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键"
    )
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="求职者用户ID")
    job_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="职位ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="收藏时间"
    )
