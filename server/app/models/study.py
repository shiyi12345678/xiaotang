"""学习域 ORM 模型：题库 / 题目 / 记忆卡。

建表：python -m app.init_db
说明：题库、题目、记忆卡属于「可复用内容」，与具体用户无关；
      用户的答题记录、错题、复习进度属于用户数据，后续单独扩展。
"""
from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QuestionBank(Base):
    """题库表（刷题首页列表展示）。"""

    __tablename__ = "question_bank"
    __table_args__ = ({"comment": "题库表"},)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="题库ID")
    name: Mapped[str] = mapped_column(String(80), nullable=False, comment="题库名称")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="题目总数")
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已做题数")
    correct_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="正确率(%)")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="图标名")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class Question(Base):
    """题目表（刷题模块）。"""

    __tablename__ = "question"
    __table_args__ = (
        Index("idx_bank", "bank_id"),
        {"comment": "题目表"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="题目ID")
    bank_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="所属题库")
    type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="single", comment="single=单选 / multiple=多选"
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False, comment="题干")
    options: Mapped[list] = mapped_column(JSON, nullable=False, comment='选项 [{"key":"A","text":"..."}]')
    answer: Mapped[list] = mapped_column(JSON, nullable=False, comment='正确答案 ["B"]')
    analysis: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="解析")
    knowledge: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="知识点")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class MemoryCard(Base):
    """记忆卡表（间隔重复复习）。"""

    __tablename__ = "memory_card"
    __table_args__ = ({"comment": "记忆卡表"},)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="卡片ID")
    front: Mapped[str] = mapped_column(Text, nullable=False, comment="正面（问题）")
    back: Mapped[str] = mapped_column(Text, nullable=False, comment="背面（答案）")
    tag: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="标签")
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="记忆阶段")
    next_review: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="下次复习提示")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
