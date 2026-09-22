"""面试题库域接口（求职者的备考侧）。

路由前缀：/api/v1/interview
    公开只读：banks（题库分类聚合）、questions（题目列表 / 详情）
    需要登录：questions/{id}/record（记录作答）、wrong（薄弱点）、progress（刷题进度）

⚠️ 安全约定（与 job / apply / mine 域一致）：
    刷题记录、薄弱点、进度统计一律按 **token 里的 uid** 过滤，绝不接受客户端传 uid；
    题库与题目本身是公开数据，因此这几个只读接口不需要登录。

⚠️ 「最近一次作答」的判定统一用 MAX(question_record.id)，不用 MAX(created_at)：
    created_at 是 DATETIME（秒精度），同一秒内连续作答两次会并列、排序不确定；
    id 是自增主键、严格单调，与插入顺序一致，正好等价于「最近一条记录」。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import InterviewQuestion, JobCategory, QuestionRecord, User
from app.schemas.content import escape_like
from app.schemas.interview import (
    VALID_MODES,
    VALID_RESULTS,
    RecordIn,
    bank_out,
    category_progress_out,
    question_brief,
    question_detail,
    wrong_item,
)

router = APIRouter(prefix="/api/v1/interview", tags=["面试题库"])
logger = logging.getLogger(__name__)

# 允许的难度取值（与 interview_question.difficulty 的注释一致）
VALID_DIFFICULTIES = (1, 2, 3)


# ==========================================================
# 内部小工具
# ==========================================================


async def _get_question(db: AsyncSession, question_id: str) -> InterviewQuestion:
    """取题目，不存在则抛业务错误。"""
    row = await db.get(InterviewQuestion, question_id)
    if row is None:
        raise BizError(40404, "题目不存在", http=404)
    return row


async def _record_stats(db: AsyncSession, uid: int) -> dict:
    """按题聚合本人的刷题记录，返回 {question_id: {lastTime, lastResult, wrongCount, answerCount}}。

    实现方式（两条查询，没有 N+1）：
        1) 一条 GROUP BY question_id 的聚合，一次算出每题的
           作答次数 / 答错次数 / 最近一次作答时间 / 最近一条记录的 id；
        2) 用上一步收集到的「最近记录 id」集合，一次性把这批记录的 result 查回来，
           于是「每题最近一次作答结果」不需要逐题回查。

    ⚠️ 为什么把「最近一条」交给 MAX(id)：见文件头说明（created_at 秒精度会并列）。
    ⚠️ 这是 /wrong 与 /progress 两个接口唯一的统计来源：
       两处的「已掌握 / 仍薄弱」口径因此天然一致，不会一个算最近一次、一个算历史累计。
    """
    rows = (
        await db.execute(
            select(
                QuestionRecord.question_id,
                func.max(QuestionRecord.id),
                func.max(QuestionRecord.created_at),
                func.count(),
                func.sum(case((QuestionRecord.result == 0, 1), else_=0)),
            )
            .where(QuestionRecord.user_id == uid)
            .group_by(QuestionRecord.question_id)
        )
    ).all()

    last_ids = [last_id for _, last_id, _, _, _ in rows]
    last_results: dict = {}
    if last_ids:
        last_results = {
            rec_id: int(result)
            for rec_id, result in (
                await db.execute(
                    select(QuestionRecord.id, QuestionRecord.result).where(
                        QuestionRecord.id.in_(last_ids)
                    )
                )
            ).all()
        }

    stats: dict = {}
    for question_id, last_id, last_time, answer_count, wrong_count in rows:
        stats[question_id] = {
            "lastTime": last_time,
            "lastResult": last_results.get(last_id, 0),
            "wrongCount": int(wrong_count or 0),
            "answerCount": int(answer_count or 0),
        }
    return stats


# ==========================================================
# 公开只读接口
# ==========================================================


@router.get("/banks", summary="题库分类聚合")
async def list_banks(db: AsyncSession = Depends(get_db)):
    """按职能分类聚合题库：只返回「有题目」的二级分类。

    ⚠️ 题量与首题岗位都用 SQL 的相关子查询一次算完，
       避免「先查分类列表、再对每个分类查一次题目」的 N+1（分类数 = 查询数）。
    """
    count_sub = (
        select(func.count())
        .select_from(InterviewQuestion)
        .where(InterviewQuestion.category_id == JobCategory.id)
        .scalar_subquery()
    )
    # position：该分类下第一道题（sort_order 最小，与列表排序一致）的适用岗位
    position_sub = (
        select(InterviewQuestion.position)
        .where(InterviewQuestion.category_id == JobCategory.id)
        .order_by(InterviewQuestion.sort_order, InterviewQuestion.id)
        .limit(1)
        .scalar_subquery()
    )

    rows = (
        await db.execute(
            select(JobCategory, count_sub, position_sub)
            .where(JobCategory.level == 2)
            .order_by(JobCategory.sort_order, JobCategory.id)
        )
    ).all()

    # 只保留有题目的分类：空分类点进去是空白页，不该出现在题库首页
    banks = [bank_out(cat, count, position) for cat, count, position in rows if count]

    # 题目总数与热门题数：一条查询里同时算出来（count + 条件求和）
    total, hot = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(case((InterviewQuestion.is_hot == 1, 1), else_=0)), 0
                ),
            ).select_from(InterviewQuestion)
        )
    ).one()

    return ok({"banks": banks, "total": int(total or 0), "hot": int(hot or 0)})


@router.get("/questions", summary="面试题列表")
async def list_questions(
    category: str | None = Query(None, description="职能分类 id（精确匹配 category_id）"),
    difficulty: int | None = Query(None, description="难度 1=基础 / 2=进阶 / 3=困难"),
    keyword: str | None = Query(None, description="题干关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
):
    """题目列表（公开）。列表不返回 answer，答案走详情接口。"""
    conditions = []

    if category:
        conditions.append(InterviewQuestion.category_id == category)

    # 非 1/2/3 的难度值直接忽略而不是报错：前端筛选器里「全部」可能传 0 或空串
    if difficulty in VALID_DIFFICULTIES:
        conditions.append(InterviewQuestion.difficulty == difficulty)

    if keyword and keyword.strip():
        # ⚠️ 必须转义：否则用户输入的 % / _ 会变成通配符，把整库题目都捞出来
        kw = f"%{escape_like(keyword.strip())}%"
        conditions.append(InterviewQuestion.question.like(kw, escape="\\"))

    total = (
        await db.execute(
            select(func.count()).select_from(InterviewQuestion).where(*conditions)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(InterviewQuestion)
            .where(*conditions)
            # sort_order 是灌库时按「高频/常考」人工排的序，比按热度算更贴近备考顺序
            .order_by(InterviewQuestion.sort_order, InterviewQuestion.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return ok({
        "list": [question_brief(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.get("/questions/{question_id}", summary="题目详情（含参考答案）")
async def read_question(question_id: str, db: AsyncSession = Depends(get_db)):
    """单题完整内容；answer 只在这里返回。"""
    row = await _get_question(db, question_id)
    return ok({"question": question_detail(row)})


# ==========================================================
# 需要登录：作答与统计
# ==========================================================


@router.post("/questions/{question_id}/record", summary="记录作答结果")
async def record_answer(
    question_id: str,
    payload: RecordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """刷题记录：会 / 不会各记一条，供薄弱点与进度统计使用。"""
    if payload.result not in VALID_RESULTS or payload.mode not in VALID_MODES:
        raise BizError(40003, "参数不合法")

    # ⚠️ 先校验题目存在：否则客户端可以随便传 id 写脏记录，
    #    把「已作答题数」灌到超过题库总数，进度页的百分比就没意义了
    await _get_question(db, question_id)

    row = QuestionRecord(
        user_id=user.id,
        question_id=question_id,
        result=payload.result,
        mode=payload.mode,
        # 耗时只用于展示统计，负数按 0 处理（不因为一个展示字段把整个请求打回）
        duration_sec=max(0, int(payload.duration_sec or 0)),
    )
    db.add(row)
    await db.commit()

    logger.info(
        "[interview] uid=%s 作答 %s result=%s mode=%s",
        user.id, question_id, payload.result, payload.mode,
    )
    return ok({"recorded": True, "result": payload.result})


@router.get("/wrong", summary="薄弱点（错题）列表")
async def list_wrong(
    category: str | None = Query(None, description="按职能分类过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """薄弱点 = 本人「答错过」的题目（wrongCount > 0），同一题只出现一次。

    ⚠️ 同题去重 / 取最近时间 / 计数的做法（固定 3 条查询：2 条聚合 + 1 条取题目，无 N+1）：
        1) _record_stats 用一条 GROUP BY question_id 的聚合同时算出每题的
           作答次数、答错次数、最近一次作答时间与最近一条记录 id；
        2) 取其中 wrongCount > 0 的题（即出现过 result == 0 的题）作为薄弱点，
           按最近一次作答时间倒序排序后**在内存里分页**——聚合结果的行数
           等于「答过的不同题目数」，本来就有限，total 也就不必再发 count 查询；
        3) 只用本页的 question_id 一次性把题目查回来，再按 page_ids 的顺序还原排序
           （IN 查询不保证顺序），绝不逐题回查。
    ⚠️ 列表包含「已攻克」的题：lastResult == 1 表示最近一次已经答对，
       前端据此打「已掌握」标签（与旧学习端错题本的 mastered 标记同义）。
    """
    stats = await _record_stats(db, user.id)
    wrong_ids = [qid for qid, s in stats.items() if s["wrongCount"] > 0]

    if category and wrong_ids:
        # 分类过滤先落到 question_id 上再分页：否则 total / hasMore 会把其他分类也算进去
        in_category = set(
            (
                await db.execute(
                    select(InterviewQuestion.id).where(
                        InterviewQuestion.id.in_(wrong_ids),
                        InterviewQuestion.category_id == category,
                    )
                )
            ).scalars().all()
        )
        wrong_ids = [qid for qid in wrong_ids if qid in in_category]

    # 最近错的排最前；时间缺失（理论上不会有）排最后
    wrong_ids.sort(key=lambda qid: stats[qid]["lastTime"] or datetime.min, reverse=True)
    total = len(wrong_ids)

    page_ids = wrong_ids[(page - 1) * page_size: page * page_size]
    questions: dict = {}
    if page_ids:
        rows = (
            await db.execute(
                select(InterviewQuestion).where(InterviewQuestion.id.in_(page_ids))
            )
        ).scalars().all()
        questions = {r.id: r for r in rows}

    items = []
    for qid in page_ids:
        row = questions.get(qid)
        if row is None:
            # 题目已从题库移除（题库是只读种子数据，正常不会发生）：跳过而不是报错
            continue
        s = stats[qid]
        items.append(wrong_item(row, s["lastResult"], s["lastTime"], s["wrongCount"]))

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.get("/progress", summary="刷题进度统计")
async def read_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """刷题进度：已作答 / 已掌握 / 仍薄弱，外加按职能的分类进度。

    ⚠️ mastered 与 wrong 都按「每题**最近一次**作答结果」判定，不是把历史记录简单计数：
       同一题先答错、后答对，它应该从「仍薄弱」移到「已掌握」，只计一次。
       判定依据由 _record_stats 聚合出来（MAX(id) 取最近一条记录）。
    """
    stats = await _record_stats(db, user.id)
    answered = len(stats)
    mastered = sum(1 for s in stats.values() if s["lastResult"] == 1)
    wrong = sum(1 for s in stats.values() if s["lastResult"] == 0)

    total = (
        await db.execute(select(func.count()).select_from(InterviewQuestion))
    ).scalar() or 0

    # ---------- 按职能分类的进度 ----------
    # 每个分类的题目总数：一条 GROUP BY 搞定
    total_by_cat = {
        cid: int(count)
        for cid, count in (
            await db.execute(
                select(InterviewQuestion.category_id, func.count()).group_by(
                    InterviewQuestion.category_id
                )
            )
        ).all()
    }

    # 已作答的题落在哪个分类：一次 IN 查询取回全部映射，再在内存里归类
    answered_by_cat: dict = {}
    if stats:
        cat_of = {
            qid: cid
            for qid, cid in (
                await db.execute(
                    select(InterviewQuestion.id, InterviewQuestion.category_id).where(
                        InterviewQuestion.id.in_(list(stats.keys()))
                    )
                )
            ).all()
        }
        for qid in stats:
            cid = cat_of.get(qid)
            if cid is None:
                # 题目已不在题库：answered 里仍计入，但不归类（避免凭空多出一个分类项）
                continue
            answered_by_cat[cid] = answered_by_cat.get(cid, 0) + 1

    # 分类名与排序：一次批量取，避免按分类逐个查库
    cat_meta = {
        cid: (name, sort_order)
        for cid, name, sort_order in (
            await db.execute(
                select(JobCategory.id, JobCategory.name, JobCategory.sort_order).where(
                    JobCategory.id.in_(list(total_by_cat.keys()))
                )
            )
        ).all()
    } if total_by_cat else {}

    by_category = [
        category_progress_out(
            cid,
            # 库里有题、分类表里却查不到（脏数据）时给空名兜底，保证分类进度能对上总数
            cat_meta.get(cid, ("", 0))[0],
            answered_by_cat.get(cid, 0),
            total_by_cat[cid],
        )
        for cid in sorted(total_by_cat, key=lambda c: (cat_meta.get(c, ("", 0))[1], c))
    ]

    return ok({
        "total": int(total),
        "answered": answered,
        "mastered": mastered,
        "wrong": wrong,
        # 掌握率 = 已掌握 / 已作答（不是 / 题库总数）：分母用总数会在刚开始刷题时恒为 0%
        "accuracy": round(mastered / answered * 100) if answered else 0,
        "byCategory": by_category,
    })
