"""学习域「用户数据」ORM 模型：错题本 / 答题记录 / 记忆卡复习进度。

⚠️ 为什么另起一个文件、而不是塞进 models/study.py：
    study.py 放的是「可复用内容」（题库、题目、记忆卡），与具体用户无关；
    本文件放的是「某个用户的学习行为」，三张表全部带 uid。
    把这条边界摆在目录结构上，读代码时一眼能看出哪些数据属于用户。

⚠️ 建表：python -m app.init_db
    create_all 只创建「尚不存在」的表，不会 ALTER 已有表——
    因此这三张是**新增**表，可以直接加在已有库上，不会动到任何既有表结构。

⚠️ 为什么不给已有的 question_bank / memory_card 加字段：
    同上的原因（create_all 加不了列）。题库的「已做/正确率」、
    记忆卡的「复习阶段」这类**每用户一份**的数据，本来也不该存在内容表里：
    内容表是全局共享的，存进去就变成「所有人共用一个进度」。
    所以进度类数据一律独立成 uid 维度的表（记忆卡表里的 stage/next_review
    保留为「初始调度」的种子值，见 routers/study.py 的说明）。
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


class WrongQuestion(Base):
    """错题本（每用户一份）。

    ⚠️ 为什么把题干/选项/答案/解析整份「快照」下来，而不是只存 question_id：
        题目属于内容层，将来可能被改写或下架。错题本的价值在于「我当时错的是这道题」，
        只留外键的话，题目一改，历史错题就变成另一道题了。
        因此这里冗余存储快照 + 保留 question_id 便于回溯。
    """

    __tablename__ = "wrong_question"
    __table_args__ = (
        Index("idx_uid_mastered", "uid", "mastered"),
        Index("idx_uid_question", "uid", "question_id"),
        {"comment": "错题本（用户数据）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="错题记录ID"
    )
    uid: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属用户（user.id）"
    )
    question_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="来源题目（question.id）"
    )
    bank_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="所属题库（question_bank.id）"
    )
    bank_name: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        comment="题库名快照：客户端按题库名筛选/展示，题库改名前也要能显示原来的名字",
    )
    q_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="single", comment="题型快照 single/multiple"
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False, comment="题干快照")
    options: Mapped[list] = mapped_column(
        JSON, nullable=False, comment='选项快照 [{"key":"A","text":"..."}]'
    )
    my_answer: Mapped[list] = mapped_column(
        JSON, nullable=False, comment='我的作答快照，如 ["B"]；未作答为空数组'
    )
    answer: Mapped[list] = mapped_column(
        JSON, nullable=False, comment='正确答案快照，如 ["B"]'
    )
    analysis: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="解析快照"
    )
    knowledge: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="知识点快照"
    )
    reason: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", comment="错因标签（客户端可选填）"
    )
    wrong_times: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="累计答错次数"
    )
    mastered: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, comment="是否已掌握 0否/1是"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="首次加入错题本的时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="最近一次答错/操作时间（路由层显式刷新，ON UPDATE 同秒不触发）",
    )


class AnswerRecord(Base):
    """答题记录（一次「刷完一组题」落一行）。

    ⚠️ 粒度是「一组」而不是「一题」：
        客户端刷题是连续做 N 道后交卷，逐题落库既无必要也放大了写入量。
        这一粒度足够算出：已做题数（SUM total）、正确率（SUM correct / SUM total）、
        本周刷题数（按 created_at 过滤）。

    ⚠️ 这里没有「用时/分钟数」字段：客户端目前不上报单题耗时，
        所以 /study/report 里那些 minutes 类字段是被**省略**而不是编造的。
    """

    __tablename__ = "answer_record"
    __table_args__ = (
        Index("idx_uid_created", "uid", "created_at"),
        Index("idx_uid_bank", "uid", "bank_id"),
        {"comment": "答题记录（用户数据）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="记录ID"
    )
    uid: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属用户（user.id）"
    )
    bank_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="题库ID（question_bank.id）"
    )
    bank_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="", comment="题库名快照"
    )
    total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本组题数"
    )
    correct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本组答对题数"
    )
    minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="本组用时（分钟）：由客户端上报；未上报为 0（服务端不估算）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="交卷时间（周报按它分天统计）",
    )


class MemoryProgress(Base):
    """记忆卡复习进度（每用户每卡一份）。

    ⚠️ (uid, card_id) 唯一：调度状态必须唯一，否则「下次复习时间」会出现多份冲突值。
        POST /study/memory/progress 依赖这个唯一约束做 upsert。
    ⚠️ next_review 用字符串（与 memory_card.next_review 一致）：
       客户端按自己的复习策略写「1 天后」「明天」这类展示提示；
       服务端不解释它的语义，只负责保存与回显。
    """

    __tablename__ = "memory_progress"
    __table_args__ = (
        UniqueConstraint("uid", "card_id", name="uk_uid_card"),
        {"comment": "记忆卡复习进度（用户数据）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="进度ID"
    )
    uid: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), nullable=False, comment="所属用户（user.id）"
    )
    card_id: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="记忆卡ID（memory_card.id）"
    )
    stage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="记忆阶段（0 起，越大越熟）"
    )
    times: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="累计复习次数"
    )
    next_review: Mapped[str] = mapped_column(
        String(30), nullable=False, default="", comment="下次复习提示（展示用）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="首次复习时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="最近一次复习时间（活跃天数按它统计）",
    )
