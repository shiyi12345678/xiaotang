"""招聘域 · 面试题库模型：面试题 / 刷题记录。

建表方式（DDL 单源）：在 server/ 目录执行  python -m app.init_db

定位：这是「求职者的备考侧」，对应改造前学习端的题库 / 记忆练习 / 错题本：
    interview_question  面试题库（按职能分类，含参考答案与来源面经）
    question_record     刷题记录（会 / 不会，用于薄弱点复盘与求职报告）

⚠️ 与旧 question / answer_record 表的区别：
    旧表是学习端的学科题，本表是求职场景的面试题，业务含义不同故独立建表，
    旧表原封不动保留，随时可回滚。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InterviewQuestion(Base):
    """面试题库表。"""

    __tablename__ = "interview_question"
    __table_args__ = (
        Index("idx_category_sort", "category_id", "sort_order"),
        Index("idx_hot", "is_hot", "frequency"),
        {"comment": "面试题库表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="题目ID，如 q3001")
    category_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="所属职能分类（关联 job_category.id）"
    )
    position: Mapped[str] = mapped_column(
        String(40), nullable=False, default="", comment="适用岗位关键词，如「后端开发」"
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="题干")
    answer: Mapped[str] = mapped_column(Text, nullable=True, comment="参考答案/答题要点")
    difficulty: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="难度 1=基础 / 2=进阶 / 3=困难"
    )
    tags: Mapped[list] = mapped_column(
        JSON, nullable=True, comment="知识点标签数组，如 [\"MySQL\",\"索引\"]"
    )
    source: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", comment="来源面经，如「某大厂 二面」"
    )
    frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="被考频次（越大越热）"
    )
    is_hot: Mapped[int] = mapped_column(TINYINT, nullable=False, default=0, comment="是否热门 0否/1是")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class QuestionRecord(Base):
    """刷题记录表（面试题版本的「错题本」数据源）。"""

    __tablename__ = "question_record"
    __table_args__ = (
        Index("idx_user_time", "user_id", "created_at"),
        Index("idx_user_question", "user_id", "question_id"),
        {"comment": "面试题刷题记录表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="记录ID"
    )
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="用户ID")
    question_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="题目ID")
    result: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="作答结果 1=会 / 0=不会（进薄弱点）"
    )
    mode: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="practice",
        comment="practice=顺序刷题 / memory=背诵模式 / review=薄弱点复盘",
    )
    duration_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本题耗时（秒）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="作答时间",
    )
