"""学习域路由：前缀 /api/v1/study （**全部需要登录**）。

端点总表（🔒 全部需 `Authorization: Bearer <token>`）：
    GET    /banks                    题库列表（含本人已做/正确率）
    GET    /banks/{id}/questions     题库下的题目
    GET    /memory/cards             记忆卡（内容 + 本人调度状态）
    GET    /memory/progress          记忆卡进度列表
    POST   /memory/progress          复习一张卡（推进调度，upsert）
    GET    /wrong                    错题本
    POST   /wrong                    收录错题（幂等，重复收录则次数+1）
    POST   /wrong/{id}/master        标记已掌握
    DELETE /wrong/{id}               删除一条错题
    DELETE /wrong                    清空错题本
    POST   /answers                  记录一组已结算的答题
    GET    /stats                    题库维度统计 + 汇总（已做/正确率/本周刷题数）
    GET    /overview                 学习页概览（真实活动聚合）
    GET    /report                   学习周报（真实活动聚合）

本模块错误码：
    44001 题库不存在
    44002 题目不存在
    44003 错题记录不存在或无权访问
    44004 参数不合法
    44005 记忆卡不存在

⚠️ 数据一致性口径（本模块所有数字只有**一个来源**：answer_record）：
    「学习天数 / 本周刷题数 / 正确率 / 柱状图」全部由 answer_record 聚合而来，
    因此 /overview 与 /report 的数字互相自洽，不会像原来的 mock 那样
    「总计 268 分钟、但七天相加只有 236 分钟」。
    ⚠️ 已知边界：只有「交卷」这一种行为会落到 answer_record。
       单纯复习记忆卡、看错题不会产生学习天数（服务端没有活动上报端点）。
       记忆卡的复习量单独在 memory 字段里体现，不掺进学习天数。

⚠️ 那些分钟数字从哪来：POST /answers 的 minutes 字段（客户端交卷时上报）。
    客户端不上报时一律为 0 —— 服务端**不估算**学习时长，宁可显示 0 也不编。
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import (
    AnswerRecord,
    MemoryCard,
    MemoryProgress,
    Question,
    QuestionBank,
    User,
    UserCourse,
    WrongQuestion,
)
from app.schemas.study import (
    DATE_FMT,
    DEFAULT_BANK_NAME,
    MEMORY_LEVELS,
    MEMORY_MAX_STAGE,
    AnswerIn,
    MemoryProgressIn,
    WrongIn,
    activity_bucket,
    apply_memory_level,
    bank_out,
    continue_days,
    date_key,
    memory_card_out,
    memory_progress_out,
    question_out,
    today_key,
    week_keys,
    week_range_label,
    weekday_label,
    wrong_out,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/study", tags=["学习"])

# 学习报告的四项能力值（名称与 mock 的 studyReport.ability 一致，值是真实算出来的）
ABILITY_NAMES = ("知识记忆", "刷题正确率", "学习坚持度", "课程完成度")


# ==========================================================
# 聚合查询（本模块所有统计的唯一来源）
# ==========================================================


async def _answer_days(db: AsyncSession, uid: int) -> dict:
    """按天聚合本人的答题：{日期key: {questions, correct, minutes}}。"""
    rows = (
        await db.execute(
            select(
                func.date(AnswerRecord.created_at),
                func.sum(AnswerRecord.total),
                func.sum(AnswerRecord.correct),
                func.sum(AnswerRecord.minutes),
            )
            .where(AnswerRecord.uid == uid)
            .group_by(func.date(AnswerRecord.created_at))
        )
    ).all()
    out = {}
    for day, questions, correct, minutes in rows:
        if day is None:
            continue
        key = day.strftime(DATE_FMT) if hasattr(day, "strftime") else str(day)
        out[key] = {
            "questions": int(questions or 0),
            "correct": int(correct or 0),
            "minutes": int(minutes or 0),
        }
    return out


async def _bank_aggregates(db: AsyncSession, uid: int) -> dict:
    """按题库聚合：{bank_id: {done, correct, groups}}。"""
    rows = (
        await db.execute(
            select(
                AnswerRecord.bank_id,
                func.sum(AnswerRecord.total),
                func.sum(AnswerRecord.correct),
                func.count(),
            )
            .where(AnswerRecord.uid == uid)
            .group_by(AnswerRecord.bank_id)
        )
    ).all()
    return {
        bank_id: {"done": int(done or 0), "correct": int(correct or 0), "groups": int(groups or 0)}
        for bank_id, done, correct, groups in rows
    }


def _totals_from(days: dict) -> dict:
    """由按天聚合算出汇总（字段名对齐前端 answerTotals()）。"""
    done = sum(d["questions"] for d in days.values())
    correct = sum(d["correct"] for d in days.values())
    keys = week_keys()
    week_done = sum(days.get(k, {}).get("questions", 0) for k in keys)
    week_correct = sum(days.get(k, {}).get("correct", 0) for k in keys)
    today = days.get(today_key(), {"questions": 0, "correct": 0})
    return {
        "done": done,
        "correct": correct,
        "rate": round(correct / done * 100) if done else None,
        "weekDone": week_done,
        "weekCorrect": week_correct,
        "weekRate": round(week_correct / week_done * 100) if week_done else None,
        "todayDone": int(today.get("questions", 0)),
        "todayCorrect": int(today.get("correct", 0)),
    }


async def _wrong_counts(db: AsyncSession, uid: int) -> dict:
    """错题本计数：{total, mastered, todo}。"""
    rows = (
        await db.execute(
            select(WrongQuestion.mastered, func.count())
            .where(WrongQuestion.uid == uid)
            .group_by(WrongQuestion.mastered)
        )
    ).all()
    counts = {int(m): int(c) for m, c in rows}
    mastered = counts.get(1, 0)
    total = mastered + counts.get(0, 0)
    return {"total": total, "mastered": mastered, "todo": total - mastered}


async def _memory_counts(db: AsyncSession, uid: int) -> dict:
    """记忆卡复习计数：{reviewedCards, totalTimes, mastered}。"""
    row = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(MemoryProgress.times), 0))
            .where(MemoryProgress.uid == uid)
        )
    ).one()
    mastered = (
        await db.execute(
            select(func.count())
            .select_from(MemoryProgress)
            .where(MemoryProgress.uid == uid, MemoryProgress.stage >= MEMORY_MAX_STAGE)
        )
    ).scalar() or 0
    return {
        "reviewedCards": int(row[0] or 0),
        "totalTimes": int(row[1] or 0),
        "mastered": int(mastered),
    }


async def _bank_name(db: AsyncSession, bank_id: str) -> str:
    """按题库 id 取名字；取不到返回空串（由调用方决定兜底文案）。"""
    if not bank_id:
        return ""
    name = (
        await db.execute(select(QuestionBank.name).where(QuestionBank.id == bank_id))
    ).scalar_one_or_none()
    return name or ""


async def _week_buckets(db: AsyncSession, uid: int) -> tuple:
    """本周 7 天的活动桶 + 按天聚合；桶结构对齐前端 readWeekActivity()。"""
    days = await _answer_days(db, uid)
    buckets = [
        activity_bucket(key, days.get(key, {}).get("minutes", 0), days.get(key, {}).get("questions", 0))
        for key in week_keys()
    ]
    return buckets, days


# ==========================================================
# 题库 / 题目
# ==========================================================


@router.get("/banks", summary="题库列表")
async def list_banks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """题库列表。

    ⚠️ done / correctRate 是**本人真实作答**的聚合，不是 question_bank 表里那两个
       种子列（那两列只能表示「全局一行」，无法表达每人一份的进度）。
       count（题库总题数）仍取内容表的真实值。
    """
    banks = (
        await db.execute(select(QuestionBank).order_by(QuestionBank.sort_order.asc()))
    ).scalars().all()
    agg = await _bank_aggregates(db, user.id)
    return ok({
        "list": [
            bank_out(
                row,
                done=agg.get(row.id, {}).get("done", 0),
                correct=agg.get(row.id, {}).get("correct", 0),
                groups=agg.get(row.id, {}).get("groups", 0),
            )
            for row in banks
        ]
    })


@router.get("/banks/{bank_id}/questions", summary="题库下的题目")
async def list_questions(
    bank_id: str = Path(..., description="题库ID，如 qb1"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回题库下的全部题目（含答案与解析，供客户端本地判卷）。

    ⚠️ answer/analysis 一起下发是**有意的**：客户端目前是即时本地判卷，
       没有答案就无法给对错反馈。若将来改为服务端判卷，
       应新增一个「答题用」的字段集（不含答案），本期不做。
    """
    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
    ).scalar_one_or_none()
    if bank is None:
        raise BizError(44001, "题库不存在：%s" % bank_id)

    rows = (
        await db.execute(
            select(Question)
            .where(Question.bank_id == bank_id)
            .order_by(Question.sort_order.asc(), Question.id.asc())
        )
    ).scalars().all()
    agg = await _bank_aggregates(db, user.id)
    return ok({
        "bank": bank_out(
            bank,
            done=agg.get(bank.id, {}).get("done", 0),
            correct=agg.get(bank.id, {}).get("correct", 0),
            groups=agg.get(bank.id, {}).get("groups", 0),
        ),
        "list": [question_out(row) for row in rows],
    })


# ==========================================================
# 记忆卡
# ==========================================================


@router.get("/memory/cards", summary="记忆卡列表")
async def list_memory_cards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记忆卡内容 + 本人的调度状态。

    ⚠️ 该用户还没复习过的卡，stage/nextReview 回退到 memory_card 的**初始种子值**；
       复习过就以 memory_progress 为准（否则所有人共用一份进度）。
    """
    cards = (
        await db.execute(select(MemoryCard).order_by(MemoryCard.sort_order.asc()))
    ).scalars().all()
    progress = {
        row.card_id: row
        for row in (
            await db.execute(select(MemoryProgress).where(MemoryProgress.uid == user.id))
        ).scalars().all()
    }
    return ok({"list": [memory_card_out(row, progress.get(row.id)) for row in cards]})


@router.get("/memory/progress", summary="记忆卡进度列表")
async def list_memory_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本人已复习过的卡片调度状态（字段对齐前端 cardState()）。"""
    rows = (
        await db.execute(
            select(MemoryProgress)
            .where(MemoryProgress.uid == user.id)
            .order_by(MemoryProgress.updated_at.desc())
        )
    ).scalars().all()
    return ok({"list": [memory_progress_out(row) for row in rows]})


@router.post("/memory/progress", summary="复习记忆卡（推进调度）")
async def upsert_memory_progress(
    body: MemoryProgressIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """upsert 一张卡的复习状态，返回最新状态。

    两种用法：
        {"card_id": "mc1", "level": "know"}                    服务端按同源规则推进
        {"card_id": "mc1", "stage": 3, "next_review": "2026-09-20"}  客户端算好直接存

    ⚠️ level 的推进规则与前端 rateMemoryCard() 完全一致（know/vague/forget），
       阶段上限 6，间隔表 [1,1,2,4,7,10,15]，见 schemas/study.py。
    ⚠️ 每调用一次 times 都会 +1（每次调用代表「复习了一次」）。
    """
    card = (
        await db.execute(select(MemoryCard).where(MemoryCard.id == body.card_id))
    ).scalar_one_or_none()
    if card is None:
        raise BizError(44005, "记忆卡不存在：%s" % body.card_id)

    row = (
        await db.execute(
            select(MemoryProgress).where(
                MemoryProgress.uid == user.id, MemoryProgress.card_id == body.card_id
            )
        )
    ).scalar_one_or_none()

    base_stage = row.stage if row else card.stage

    if body.level is not None:
        if body.level not in MEMORY_LEVELS:
            raise BizError(44004, "level 只能是 %s" % "/".join(MEMORY_LEVELS))
        stage, next_review = apply_memory_level(base_stage, body.level)
    else:
        if body.stage is None:
            raise BizError(44004, "必须提供 level，或提供 stage（可另附 next_review）")
        if body.stage < 0 or body.stage > MEMORY_MAX_STAGE:
            raise BizError(44004, "stage 必须在 0~%d 之间" % MEMORY_MAX_STAGE)
        stage = int(body.stage)
        next_review = (body.next_review or "").strip()
        if next_review:
            try:
                datetime.strptime(next_review, DATE_FMT)
            except ValueError:
                raise BizError(44004, "next_review 必须是 YYYY-MM-DD 格式的日期，或留空")

    if row is None:
        row = MemoryProgress(
            uid=user.id,
            card_id=body.card_id,
            stage=stage,
            times=1,
            next_review=next_review,
        )
        db.add(row)
    else:
        row.stage = stage
        row.next_review = next_review
        row.times = int(row.times or 0) + 1
        row.updated_at = datetime.now()   # MySQL ON UPDATE 同秒不触发，显式刷新

    await db.commit()
    await db.refresh(row)
    return ok({"record": memory_progress_out(row)})


# ==========================================================
# 错题本
# ==========================================================


@router.get("/wrong", summary="错题本")
async def list_wrong(
    mastered: bool | None = Query(None, description="true=已掌握 / false=待复习；不传则全给"),
    bank_id: str | None = Query(None, description="按题库ID过滤"),
    bank: str | None = Query(None, description="按题库名过滤（客户端筛选用的是名字）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本人错题本。

    排序与前端 readWrongBook 一致：**未掌握优先，其次按最近操作时间倒序**。
    元素结构与前端 normalizeWrong() 的产物同构。
    """
    stmt = select(WrongQuestion).where(WrongQuestion.uid == user.id)
    if mastered is not None:
        stmt = stmt.where(WrongQuestion.mastered == (1 if mastered else 0))
    if bank_id:
        stmt = stmt.where(WrongQuestion.bank_id == bank_id)
    if bank:
        stmt = stmt.where(WrongQuestion.bank_name == bank)

    rows = (
        await db.execute(
            stmt.order_by(
                WrongQuestion.mastered.asc(),
                WrongQuestion.updated_at.desc(),
                WrongQuestion.id.desc(),
            )
        )
    ).scalars().all()
    return ok({
        "list": [wrong_out(row) for row in rows],
        "stats": await _wrong_counts(db, user.id),
    })


@router.post("/wrong", summary="收录错题")
async def add_wrong(
    body: WrongIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把一道错题写进错题本（幂等：同一题重复收录 → 次数 +1、重置为未掌握）。

    请求（对齐前端 addWrong 的入参，字段名兼容 camelCase）：
        {"srcId": "q-1", "bankId": "qb1", "bank": "AI 基础能力测验",
         "type": "single", "stem": "...", "options": [{"key":"A","text":"..."}],
         "analysis": "...", "knowledge": "...", "myAnswer": ["C"], "answer": ["B"],
         "reason": "答错收录"}

    ⚠️ 题干/选项/答案/解析一律**快照存档**（题目将来被改写也不影响历史错题）。
       若 src_id 能在 question 表里找到，则以库里的题目为权威来源覆盖快照字段；
       找不到（例如免费好课的题目不在题库里）就用客户端内联的快照。
    ⚠️ 去重键：有 src_id 按 (uid, src_id)，否则按 (uid, 题干)。
    """
    qid = (body.src_id or body.question_id or body.id or "").strip()

    question = None
    if qid:
        question = (
            await db.execute(select(Question).where(Question.id == qid))
        ).scalar_one_or_none()

    stem = question.stem if question is not None else (body.stem or "")
    if not stem.strip():
        raise BizError(44004, "缺少题干：该题既不在题库中，也没有传内联的 stem 快照")

    bank_id = (question.bank_id if question is not None else (body.bank_id or "")) or ""
    bank_name = await _bank_name(db, bank_id)
    if not bank_name:
        # 库里有名字优先用库里的；否则用客户端传来的名字；都没有则用统一兜底名
        bank_name = (body.bank or "").strip() or DEFAULT_BANK_NAME

    options = (question.options if question is not None else body.options) or []
    answer = (question.answer if question is not None else body.answer) or []
    analysis = (question.analysis if question is not None else body.analysis) or ""
    knowledge = (question.knowledge if question is not None else body.knowledge) or ""
    q_type = (question.type if question is not None else body.q_type) or "single"
    my_answer = body.my_answer or []

    if qid:
        existing = (
            await db.execute(
                select(WrongQuestion).where(
                    WrongQuestion.uid == user.id, WrongQuestion.question_id == qid
                )
            )
        ).scalar_one_or_none()
    else:
        existing = (
            await db.execute(
                select(WrongQuestion).where(
                    WrongQuestion.uid == user.id, WrongQuestion.stem == stem
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        existing.wrong_times = int(existing.wrong_times or 0) + 1
        existing.my_answer = my_answer
        existing.mastered = 0                      # 又错一次 → 重新回到待复习
        if body.reason:
            existing.reason = body.reason.strip()
        existing.updated_at = datetime.now()
        await db.commit()
        await db.refresh(existing)
        logger.info("[study.wrong] uid=%s 重复收录，次数=%s", user.id, existing.wrong_times)
        return ok({"record": wrong_out(existing), "created": False})

    record = WrongQuestion(
        uid=user.id,
        question_id=qid,
        bank_id=bank_id,
        bank_name=bank_name,
        q_type=q_type,
        stem=stem,
        options=options,
        my_answer=my_answer,
        answer=answer,
        analysis=analysis,
        knowledge=knowledge,
        reason=(body.reason or "答错收录").strip(),
        wrong_times=1,
        mastered=1 if body.mastered else 0,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info("[study.wrong] uid=%s 新增错题 id=%s", user.id, record.id)
    return ok({"record": wrong_out(record), "created": True})


@router.post("/wrong/{wrong_id}/master", summary="标记错题已掌握")
async def master_wrong(
    wrong_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记为已掌握（幂等：已掌握时重复调用不报错）。"""
    row = (
        await db.execute(
            select(WrongQuestion).where(
                WrongQuestion.id == (int(wrong_id) if wrong_id.isdigit() else 0),
                WrongQuestion.uid == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(44003, "错题记录不存在或无权访问")

    changed = not bool(row.mastered)
    row.mastered = 1
    row.updated_at = datetime.now()
    await db.commit()
    await db.refresh(row)
    return ok({"record": wrong_out(row), "changed": changed})


@router.delete("/wrong/{wrong_id}", summary="删除一条错题")
async def delete_wrong(
    wrong_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除本人的一条错题。"""
    row = (
        await db.execute(
            select(WrongQuestion).where(
                WrongQuestion.id == (int(wrong_id) if wrong_id.isdigit() else 0),
                WrongQuestion.uid == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(44003, "错题记录不存在或无权访问")

    await db.execute(
        delete(WrongQuestion).where(WrongQuestion.id == row.id, WrongQuestion.uid == user.id)
    )
    await db.commit()
    return ok({"id": str(row.id), "deleted": True})


@router.delete("/wrong", summary="清空错题本")
async def clear_wrong(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空本人的错题本（只影响自己，返回删除条数）。"""
    result = await db.execute(
        delete(WrongQuestion).where(WrongQuestion.uid == user.id)
    )
    await db.commit()
    return ok({"deleted": int(result.rowcount or 0)})


# ==========================================================
# 答题记录与统计
# ==========================================================


@router.post("/answers", summary="记录一组答题")
async def add_answers(
    body: AnswerIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """交卷时上报一组答题（对齐前端 recordGroup 的入参）。

    请求：{"bankId": "qb1", "bankName": "AI 基础能力测验", "total": 10, "correct": 7, "minutes": 6}
    响应：{record, bank（该题库最新统计）, totals（最新汇总）}
        —— 一次往返就把「记录 + 刷新后的统计」都给了，客户端不用再补一次 GET。

    ⚠️ minutes 由客户端上报，服务端不估算；不传就是 0。
    ⚠️ correct 会被夹到 [0, total]，避免脏数据把正确率算成负数或超过 100%。
    """
    if body.total < 1:
        raise BizError(44004, "total 必须 ≥ 1")
    if body.correct < 0 or body.correct > body.total:
        raise BizError(44004, "correct 必须在 0~total 之间")
    if body.minutes < 0:
        raise BizError(44004, "minutes 不能为负数")

    bank_name = (body.bank_name or "").strip() or await _bank_name(db, body.bank_id)
    if not bank_name:
        raise BizError(44001, "题库不存在：%s" % body.bank_id)

    record = AnswerRecord(
        uid=user.id,
        bank_id=body.bank_id,
        bank_name=bank_name,
        total=int(body.total),
        correct=int(body.correct),
        minutes=int(body.minutes),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    agg = await _bank_aggregates(db, user.id)
    days = await _answer_days(db, user.id)
    stat = agg.get(body.bank_id, {"done": 0, "correct": 0, "groups": 0})
    logger.info(
        "[study.answers] uid=%s bank=%s total=%s correct=%s",
        user.id, body.bank_id, body.total, body.correct,
    )
    return ok({
        "record": {
            "id": str(record.id),
            "bankId": record.bank_id,
            "bankName": record.bank_name,
            "total": record.total,
            "correct": record.correct,
            "minutes": record.minutes,
            "at": int(record.created_at.timestamp() * 1000) if record.created_at else 0,
        },
        "bank": {
            "bankId": body.bank_id,
            "name": bank_name,
            "done": stat["done"],
            "correct": stat["correct"],
            "groups": stat["groups"],
            "rate": round(stat["correct"] / stat["done"] * 100) if stat["done"] else None,
        },
        "totals": _totals_from(days),
    })


@router.get("/stats", summary="学习统计")
async def study_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """题库维度统计 + 汇总。

    返回：
        list   —— 每个题库的 count/done/correct/correctRate（字段名对齐前端 bankStat）
        totals —— 累计与本周汇总（字段名对齐前端 answerTotals：done/correct/rate/
                  weekDone/weekCorrect/weekRate/todayDone/todayCorrect）
                  其中 **weekDone 就是「本周刷题数」**
        wrong  —— 错题本计数
        memory —— 记忆卡复习计数
        weekKeys / weekDays —— 本周 7 天的日期 key 与逐日刷题数（给柱状图用）
    """
    banks = (
        await db.execute(select(QuestionBank).order_by(QuestionBank.sort_order.asc()))
    ).scalars().all()
    agg = await _bank_aggregates(db, user.id)
    days = await _answer_days(db, user.id)
    keys = week_keys()

    return ok({
        "list": [
            bank_out(
                row,
                done=agg.get(row.id, {}).get("done", 0),
                correct=agg.get(row.id, {}).get("correct", 0),
                groups=agg.get(row.id, {}).get("groups", 0),
            )
            for row in banks
        ],
        "totals": _totals_from(days),
        "wrong": await _wrong_counts(db, user.id),
        "memory": await _memory_counts(db, user.id),
        "weekKeys": keys,
        "weekDays": [
            {
                "key": key,
                "label": weekday_label(key),
                "questions": days.get(key, {}).get("questions", 0),
                "correct": days.get(key, {}).get("correct", 0),
                "minutes": days.get(key, {}).get("minutes", 0),
            }
            for key in keys
        ],
    })


# ==========================================================
# 学习页概览 / 周报
# ==========================================================


@router.get("/overview", summary="学习页概览")
async def study_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习页概览：真实活动聚合。

    对齐 mock studyOverview 的字段（值全部真实计算）：
        nickname / continueDays / todayMinutes / weekMinutes（长度 7 的数组）/ totalHours
    ⚠️ 故意**不返回**的 mock 字段（数据库没有对应数据，宁缺毋造）：
        rankPercent（需要全体用户排名样本）、medals（没有成就系统）、
        finishedLessons（没有课时级进度；只有「已学完课程数」finishedCourses）。
    额外提供的真实数据：weekActivities（与前端 readWeekActivity 同构的 7 个桶，
    可直接画柱状图）、todayQuestions/weekQuestions、wrong、memory、totals、
    以及 learningCourses（在学课程，供「继续学习」区块）。
    """
    buckets, days = await _week_buckets(db, user.id)

    # 在学课程（「继续学习」区块）；mock 里的 lastTime/remainMinutes 没有数据来源，故不返回
    my_courses = (
        await db.execute(
            select(UserCourse)
            .where(UserCourse.uid == user.id, UserCourse.kind == "learning")
            .order_by(UserCourse.sort_order.asc())
        )
    ).scalars().all()

    finished_courses = (
        await db.execute(
            select(func.count())
            .select_from(UserCourse)
            .where(UserCourse.uid == user.id, UserCourse.kind == "finished")
        )
    ).scalar() or 0

    total_minutes = sum(d["minutes"] for d in days.values())
    week_minutes = sum(b["minutes"] for b in buckets)
    active_keys = {
        k for k, v in days.items() if v["questions"] > 0 or v["minutes"] > 0
    }

    return ok({
        "nickname": user.nickname,
        "continueDays": continue_days(active_keys),
        "todayMinutes": days.get(today_key(), {}).get("minutes", 0),
        "weekMinutes": [b["minutes"] for b in buckets],
        "weekQuestions": sum(b["questions"] for b in buckets),
        "todayQuestions": days.get(today_key(), {}).get("questions", 0),
        "totalMinutes": total_minutes,
        "totalHours": round(total_minutes / 60),
        "finishedCourses": int(finished_courses),
        "weekActiveDays": sum(1 for b in buckets if b["hasRecord"]),
        "weekActivities": buckets,
        "learningCourses": [
            {
                "id": row.id,
                "title": row.title,
                "teacher": row.teacher,
                "progress": row.progress,
                "lastLesson": row.last_lesson,
            }
            for row in my_courses
        ],
        "wrong": await _wrong_counts(db, user.id),
        "memory": await _memory_counts(db, user.id),
        "totals": _totals_from(days),
        "note": (
            "minutes 类字段来自客户端在 POST /study/answers 时上报的学习时长，未上报为 0；"
            "学习天数与刷题数均由 answer_record 聚合，本响应内各数字互相自洽。"
        ),
    })


@router.get("/report", summary="学习周报")
async def study_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习周报（本周，周一 → 周日）。

    对齐 mock studyReport 的字段：week / totalMinutes / dayAvgMinutes / bestDay /
    chart / ability / suggestion。
    ⚠️ 与 mock 的两处**必要差异**（都是为了让数字真实且自洽）：
        1. chart 元素由 {day, minutes} 变成 {day, date, minutes, count, correct}：
           保留 minutes 的同时给出「答题数」，因为学习时长依赖客户端上报，
           只画分钟会出现「有答题但全 0」的空图。
        2. 不再返回 rankText（「超过 92% 的同学」需要全体用户排名样本，
           库里没有可比样本，编一个百分比没有意义）。
    ⚠️ bestDay 保持 mock 的**字符串**形状（如 "周六 · 答题 61 道"），
       本周无数据时为 null。
    """
    buckets, days = await _week_buckets(db, user.id)
    keys = week_keys()

    week_minutes = sum(b["minutes"] for b in buckets)
    total_questions = sum(b["questions"] for b in buckets)
    total_correct = sum(days.get(k, {}).get("correct", 0) for k in keys)
    active = [b for b in buckets if b["hasRecord"]]
    elapsed = [b for b in buckets if not b["isFuture"]] or buckets[:1]

    # 最佳一天：优先看学习时长，没有时长就看答题数
    best_text = None
    if week_minutes > 0:
        best = max(buckets, key=lambda b: b["minutes"])
        if best["minutes"] > 0:
            best_text = "%s · 学习 %d 分钟" % (best["label"], best["minutes"])
    elif total_questions > 0:
        best = max(buckets, key=lambda b: b["questions"])
        if best["questions"] > 0:
            best_text = "%s · 答题 %d 道" % (best["label"], best["questions"])

    # ---- 四项能力值（公式都是真实、可复现的，不含任何写死的数字）----
    wrong = await _wrong_counts(db, user.id)
    memory = await _memory_counts(db, user.id)
    course_rows = (
        await db.execute(
            select(UserCourse.progress).where(
                UserCourse.uid == user.id, UserCourse.kind.in_(("learning", "finished"))
            )
        )
    ).scalars().all()

    knowledge = round(wrong["mastered"] / wrong["total"] * 100) if wrong["total"] else 0
    accuracy = round(total_correct / total_questions * 100) if total_questions else 0
    persistence = round(len(active) / max(1, len(elapsed)) * 100)
    course_done = round(sum(course_rows) / len(course_rows)) if course_rows else 0

    chart = [
        {
            "day": bucket["label"],
            "date": bucket["key"],
            "minutes": bucket["minutes"],
            "count": bucket["questions"],
            "correct": days.get(bucket["key"], {}).get("correct", 0),
        }
        for bucket in buckets
    ]

    return ok({
        "week": week_range_label(),
        "weekStart": keys[0],
        "weekEnd": keys[6],
        "totalMinutes": week_minutes,
        "dayAvgMinutes": round(week_minutes / len(elapsed)),
        "totalQuestions": total_questions,
        "correctQuestions": total_correct,
        "accuracy": accuracy if total_questions else None,
        "dayAvgQuestions": round(total_questions / len(elapsed)),
        "bestDay": best_text,
        "chart": chart,
        "ability": [
            {"name": ABILITY_NAMES[0], "value": knowledge, "detail": "错题已掌握 %d/%d" % (wrong["mastered"], wrong["total"])},
            {"name": ABILITY_NAMES[1], "value": accuracy, "detail": "本周答对 %d/%d" % (total_correct, total_questions)},
            {"name": ABILITY_NAMES[2], "value": persistence, "detail": "本周有 %d 天有记录" % len(active)},
            {"name": ABILITY_NAMES[3], "value": course_done, "detail": "课程平均进度 %d%%" % course_done},
        ],
        "suggestion": _suggestion(accuracy, total_questions, len(active), wrong),
        "wrong": wrong,
        "memory": memory,
        "totals": _totals_from(days),
        "note": (
            "minutes 来自客户端上报（POST /study/answers 的 minutes），未上报为 0；"
            "chart 同时给出 minutes 与 count，客户端可按有数据的一项作图。"
        ),
    })


def _suggestion(accuracy: int, total_questions: int, active_days: int, wrong: dict) -> str:
    """按真实数据给一条本周建议（规则固定、可复现，不是随机文案）。"""
    if total_questions == 0:
        return "本周还没有刷题记录，先从「必刷题库」做 10 道题开始吧。"
    if accuracy < 70:
        return (
            "本周正确率 %d%%，建议先复盘错题本里待复习的 %d 道题，再刷新题。"
            % (accuracy, wrong["todo"])
        )
    if active_days < 3:
        return (
            "本周只有 %d 天有记录，坚持度比正确率更重要，试试每天固定 15 分钟。"
            % active_days
        )
    if wrong["todo"] > 0:
        return "节奏不错（正确率 %d%%），顺手把 %d 道待复习错题清掉就更稳了。" % (
            accuracy, wrong["todo"],
        )
    return "本周表现稳定（正确率 %d%%），可以挑战更难一级的题库。" % accuracy
