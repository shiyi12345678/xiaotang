"""招聘域 · 流程模型：简历 / 投递 / 面试邀约 / 会话 / 消息。

建表方式（DDL 单源）：在 server/ 目录执行  python -m app.init_db

⚠️ 投递状态机（前后端必须一致，改这里就要同步改前端 services 与页面文案）：
    submitted  已投递（HR 未查看）
    viewed     简历已查看
    chatting   沟通中
    interview  待面试（已发出面试邀约）
    passed     面试通过
    hired      已入职 / 已发 offer
    rejected   不合适
    withdrawn  求职者主动撤回
    状态流转规则见 routers/apply.py，本文件只定义存储结构。

设计要点：
    - 简历的「教育经历 / 工作经历 / 项目经历」用 JSON 数组存在一行里：
      它们是简历的组成部分、永远整体读写，拆成三张子表只会增加联表成本；
    - 会话与消息分表：会话行冗余「最后一条消息 + 未读数」，
      会话列表因此不需要扫 message 表，这是列表页性能的关键。
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


class Resume(Base):
    """简历表：一个用户一份（当前版本），支持线上编辑。"""

    __tablename__ = "resume"
    __table_args__ = (
        # 本期一个账号只维护一份简历；将来要支持多版本再放开唯一约束
        UniqueConstraint("user_id", name="uk_user"),
        {"comment": "简历表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="简历ID"
    )
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="所属用户")
    name: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="姓名")
    gender: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="性别 0=未填 / 1=男 / 2=女"
    )
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="出生年份")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="联系电话")
    email: Mapped[str] = mapped_column(String(120), nullable=False, default="", comment="联系邮箱")
    city: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="现居城市")
    education_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", comment="最高学历（中文文案）"
    )
    school: Mapped[str] = mapped_column(String(60), nullable=False, default="", comment="毕业院校")
    major: Mapped[str] = mapped_column(String(60), nullable=False, default="", comment="专业")
    graduation_year: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="毕业年份")
    work_years: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="工作年限（0=应届）"
    )
    current_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="离职-随时到岗", comment="求职状态"
    )
    expected_city: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="期望城市")
    expected_position: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", comment="期望职位"
    )
    expected_salary_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="期望薪资下限（单位 K）"
    )
    expected_salary_max: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="期望薪资上限（单位 K）"
    )
    skills: Mapped[list] = mapped_column(JSON, nullable=True, comment="技能标签数组")
    advantage: Mapped[str] = mapped_column(Text, nullable=True, comment="个人优势（自我评价）")
    educations: Mapped[list] = mapped_column(
        JSON, nullable=True, comment="教育经历数组 [{school,major,degree,start,end}]"
    )
    experiences: Mapped[list] = mapped_column(
        JSON, nullable=True,
        comment="工作经历数组 [{company,title,start,end,desc,highlights:[...]}]",
    )
    projects: Mapped[list] = mapped_column(
        JSON, nullable=True, comment="项目经历数组 [{name,role,start,end,desc}]"
    )
    completeness: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="简历完整度 0~100（后端计算）"
    )
    is_open: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="是否公开给企业 1公开/0隐藏"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间（自动维护）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class Application(Base):
    """投递记录表（求职者投递职位，企业侧即「收到的简历」）。"""

    __tablename__ = "application"
    __table_args__ = (
        # 同一人对同一职位只能投一次；重复投递由接口做成幂等提示
        UniqueConstraint("job_id", "user_id", name="uk_job_user"),
        Index("idx_user_time", "user_id", "created_at"),
        Index("idx_hr_status", "hr_id", "status"),
        Index("idx_job_status", "job_id", "status"),
        {"comment": "投递记录表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="投递ID"
    )
    job_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="职位ID")
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="求职者用户ID")
    company_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="公司ID（冗余，列表免联表）")
    hr_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="对应 HR 的 user_id"
    )
    resume_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="投递时使用的简历ID"
    )
    # 投递时的职位快照：职位下架/改名后，求职者仍能看到自己当时投的是什么
    job_title: Mapped[str] = mapped_column(String(80), nullable=False, default="", comment="职位名称快照")
    company_name: Mapped[str] = mapped_column(String(80), nullable=False, default="", comment="公司名称快照")
    salary_text: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="薪资文案快照")
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="submitted", comment="见文件头状态机"
    )
    greeting: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="打招呼语（投递附言）"
    )
    hr_remark: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="HR 备注（仅企业侧可见）"
    )
    hr_rating: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="HR 评价 0=未评 / 1~5 星"
    )
    viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="HR 首次查看时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="投递时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="状态更新时间（自动维护）",
    )


class Interview(Base):
    """面试邀约表（一轮一条，同一投递可有多轮）。"""

    __tablename__ = "interview"
    __table_args__ = (
        Index("idx_application", "application_id"),
        Index("idx_user_time", "user_id", "interview_time"),
        {"comment": "面试邀约表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="面试ID"
    )
    application_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="关联投递ID"
    )
    job_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="职位ID")
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="求职者用户ID")
    company_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="公司ID")
    hr_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="发起邀约的 HR user_id"
    )
    round_no: Mapped[int] = mapped_column(TINYINT, nullable=False, default=1, comment="第几轮")
    round_name: Mapped[str] = mapped_column(
        String(20), nullable=False, default="一面", comment="轮次名称，如「技术面」「HR面」"
    )
    interview_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="面试时间"
    )
    duration_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="预计时长（分钟）"
    )
    mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="onsite", comment="onsite=现场 / video=视频 / phone=电话"
    )
    address: Mapped[str] = mapped_column(String(160), nullable=False, default="", comment="面试地址")
    online_link: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="线上会议链接")
    interviewer: Mapped[str] = mapped_column(String(40), nullable=False, default="", comment="面试官")
    contact: Mapped[str] = mapped_column(String(60), nullable=False, default="", comment="联系方式")
    status: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="pending",
        comment="pending=待确认 / confirmed=已确认 / finished=已结束 / canceled=已取消",
    )
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="备注/面试须知")
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


class Conversation(Base):
    """会话表（求职者 ↔ 企业 HR，按「职位」维度分开）。

    ⚠️ 同一对用户聊不同职位应各自独立成会话：
       HR 需要按职位区分候选人，求职者也想看清「这段沟通是关于哪个岗位的」。
    """

    __tablename__ = "conversation"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", "hr_id", name="uk_job_candidate_hr"),
        Index("idx_candidate_time", "candidate_id", "last_time"),
        Index("idx_hr_time", "hr_id", "last_time"),
        {"comment": "沟通会话表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="会话ID"
    )
    job_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="关联职位ID")
    candidate_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="求职者 user_id")
    hr_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="HR user_id")
    company_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="公司ID")
    job_title: Mapped[str] = mapped_column(String(80), nullable=False, default="", comment="职位名称快照")
    company_name: Mapped[str] = mapped_column(String(80), nullable=False, default="", comment="公司名称快照")
    last_message: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="最后一条消息摘要（列表直出）"
    )
    last_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后一条消息时间（会话列表排序依据）"
    )
    unread_candidate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="求职者侧未读数"
    )
    unread_hr: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="企业侧未读数")
    candidate_deleted: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="求职者侧是否删除 0否/1是"
    )
    hr_deleted: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="企业侧是否删除 0否/1是"
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


class Message(Base):
    """消息表（会话内的每条消息）。

    ⚠️ sender_role 而不是只存 sender_id：
        前端渲染左右气泡只需要判断「这条是不是我发的」，
        存角色可避免为每条消息回查会话双方，也便于将来接入系统消息。
    """

    __tablename__ = "message"
    __table_args__ = (
        Index("idx_conversation_time", "conversation_id", "created_at"),
        {"comment": "沟通消息表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="消息ID"
    )
    conversation_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属会话ID"
    )
    sender_role: Mapped[str] = mapped_column(
        String(12), nullable=False, comment="candidate=求职者 / hr=企业HR / system=系统"
    )
    sender_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True, comment="发送者 user_id；system 消息为 NULL"
    )
    msg_type: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="text",
        comment="text=文本 / invite=面试邀请 / resume=简历卡片 / system=系统提示",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    extra: Mapped[dict] = mapped_column(
        JSON, nullable=True, comment="结构化附加信息（如面试邀约卡片字段）"
    )
    is_read: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0, comment="是否已读 0否/1是")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="发送时间"
    )
