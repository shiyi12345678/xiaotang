"""ORM 模型包。

⚠️ 必须在此显式导入所有模型：
    init_db.py 执行 Base.metadata.create_all 时依赖模型已被导入注册，
    漏导入会导致该表不会被创建。

分区说明（2026-09-19 招聘改造后）：
    学习端（旧，原封不动保留，随时可回滚）：
        content / mine / study / study_user —— 课程、订单、题库、学习记录
    招聘端（新，本次改造新增）：
        recruit_user —— 用户角色（求职者 / 企业HR）
        job          —— 公司、城市、职位分类、职位、职位收藏
        apply        —— 简历、投递、面试邀约、会话、消息
        interview_q  —— 面试题库、刷题记录
    两端共用：
        user（账号体系：注册/登录/验证码/JWT）、ai（对话会话与消息）
"""
from app.models.ai import AiMessage, AiMessageImage, AiSession
from app.models.apply import Application, Conversation, Interview, Message, Resume
from app.models.content import Category, Course, PageConfig
from app.models.interview_q import InterviewQuestion, QuestionRecord
from app.models.job import City, Company, Job, JobCategory, JobFavorite
from app.models.mine import Coupon, Order, UserCourse
from app.models.recruit_user import UserRole
from app.models.study import MemoryCard, Question, QuestionBank
from app.models.study_user import AnswerRecord, MemoryProgress, WrongQuestion
from app.models.user import EmailCode, SmsCode, User

__all__ = [
    # ---------- 两端共用 ----------
    "User",
    "SmsCode",
    "EmailCode",
    "AiSession",
    "AiMessage",
    "AiMessageImage",
    # ---------- 招聘端（新） ----------
    "UserRole",
    "Company",
    "City",
    "JobCategory",
    "Job",
    "JobFavorite",
    "Resume",
    "Application",
    "Interview",
    "Conversation",
    "Message",
    "InterviewQuestion",
    "QuestionRecord",
    # ---------- 学习端（旧，保留回滚） ----------
    "Category",
    "Course",
    "PageConfig",
    "QuestionBank",
    "Question",
    "MemoryCard",
    "Order",
    "Coupon",
    "UserCourse",
    "WrongQuestion",
    "AnswerRecord",
    "MemoryProgress",
]
