"""投递与简历域接口（求职者端）。

两个路由前缀：
    /api/v1/apply   投递（投递、我的投递、投递详情、撤回、求职中心统计）
    /api/v1/resume  简历（读取、保存、求职报告）

⚠️ 安全约定（与 mine / job 域一致）：
    所有查询都带 user_id == user.id，uid 一律取自 token，绝不接受客户端传入。

⚠️ 状态流转规则（本文件是唯一实现处，前端只负责展示）：
    submitted → viewed → chatting → interview → passed → hired
    - 求职者只能在「未进入面试」之前撤回（interview/passed/hired/rejected 之后不允许）
    - HR 的状态推进在 routers/hr.py，两边都只能走状态机允许的边
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import (
    Application,
    Company,
    Interview,
    Job,
    JobFavorite,
    QuestionRecord,
    Resume,
    User,
)
# 复用餐位：职位不存在时的 404 语义在 job 域已实现一次，避免两处口径不一
from app.routers.job import _job_or_404
from app.schemas.apply import (
    FUNNEL_STAGES,
    ApplyIn,
    ResumeIn,
    application_out,
    compute_completeness,
    empty_resume,
    interview_out,
    resume_detail,
)

router = APIRouter(prefix="/api/v1/apply", tags=["投递"])
resume_router = APIRouter(prefix="/api/v1/resume", tags=["简历"])
logger = logging.getLogger(__name__)

# 允许撤回的状态（进入面试之后就不能撤了）
WITHDRAWABLE = ("submitted", "viewed", "chatting")

# 视为「已进入面试及以后」的状态
INTERVIEW_STAGE = ("interview", "passed", "hired")


async def _my_resume(db: AsyncSession, uid: int) -> Resume | None:
    return (
        await db.execute(select(Resume).where(Resume.user_id == uid))
    ).scalar_one_or_none()


async def _interviews_of(db: AsyncSession, application_id: int) -> list:
    rows = (
        await db.execute(
            select(Interview)
            .where(Interview.application_id == application_id)
            .order_by(Interview.round_no)
        )
    ).scalars().all()
    return list(rows)


# ==========================================================
# 投递
# ==========================================================


@router.post("", summary="投递职位")
async def create_application(
    payload: ApplyIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """投递职位。同一职位重复投递会被拒绝（幂等语义：返回已投递而不是新建一条）。"""
    job = await _job_or_404(db, payload.job_id)
    if job.status != 1:
        raise BizError(40902, "该职位已停止招聘", http=409)

    exists = (
        await db.execute(
            select(Application).where(
                Application.job_id == job.id, Application.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BizError(40901, "你已经投递过这个职位了", http=409)

    company = await db.get(Company, job.company_id) if job.company_id else None

    # 简历：没有就按账号信息建一份最小简历。
    # ⚠️ 这样做的原因：HR 端「收到简历」必须能看到候选人，
    #    否则新用户投递后企业侧是一片空白，演示链路不完整。
    resume = await _my_resume(db, user.id)
    if resume is None:
        resume = Resume(
            user_id=user.id,
            name=user.nickname or "",
            email=user.email or "",
            is_open=1,
        )
        db.add(resume)
        await db.flush()
        logger.info("[apply] uid=%s 首次投递，自动创建最小简历 id=%s", user.id, resume.id)

    row = Application(
        job_id=job.id,
        user_id=user.id,
        company_id=job.company_id,
        hr_id=job.hr_id,
        resume_id=resume.id,
        # 快照：职位改名/下架后，求职者仍能看到自己当时投的是什么
        job_title=job.title,
        company_name=(company.short_name or company.name) if company else "",
        salary_text=_salary_text(job),
        status="submitted",
        greeting=payload.greeting or "",
    )
    db.add(row)

    job.applicant_count = (job.applicant_count or 0) + 1
    await db.commit()
    await db.refresh(row)

    logger.info("[apply] uid=%s 投递成功 job=%s application=%s", user.id, job.id, row.id)
    return ok({"application": application_out(row, "candidate")})


def _salary_text(job: Job) -> str:
    """投递快照用的薪资文案（与 schemas/job.salary_text 同口径）。"""
    from app.schemas.job import salary_text

    return salary_text(job)


@router.get("/list", summary="我的投递")
async def list_applications(
    status: str | None = Query(None, description="按状态过滤；不传返回全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conditions = [Application.user_id == user.id]
    if status:
        conditions.append(Application.status == status)

    total = (
        await db.execute(
            select(func.count()).select_from(Application).where(*conditions)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Application)
            .where(*conditions)
            .order_by(Application.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return ok({
        "list": [application_out(r, "candidate") for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.get("/stats", summary="求职中心统计")
async def application_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职中心首页用：各状态数量 + 漏斗 + 待办（即将到来的面试）。"""
    rows = (
        await db.execute(
            select(Application.status, func.count())
            .where(Application.user_id == user.id)
            .group_by(Application.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}
    delivered = sum(by_status.values())

    favorited = (
        await db.execute(
            select(func.count()).select_from(JobFavorite).where(JobFavorite.user_id == user.id)
        )
    ).scalar() or 0

    # 待面试：未来的面试邀约（含今天）
    upcoming = (
        await db.execute(
            select(Interview)
            .where(
                Interview.user_id == user.id,
                Interview.status.in_(("pending", "confirmed")),
                Interview.interview_time.is_not(None),
                Interview.interview_time >= datetime.now(),
            )
            .order_by(Interview.interview_time)
            .limit(5)
        )
    ).scalars().all()

    interviewed = by_status.get("interview", 0) + by_status.get("passed", 0) + by_status.get("hired", 0)

    return ok({
        "delivered": delivered,
        "favorited": favorited,
        "byStatus": by_status,
        "funnel": [
            {"stage": key, "label": label, "count": _funnel_count(key, by_status, delivered)}
            for key, label in FUNNEL_STAGES
        ],
        "upcomingInterviews": [interview_out(i) for i in upcoming],
        # 面试转化率（前端进度环直接显示）
        "interviewRate": round(interviewed / delivered * 100) if delivered else 0,
    })


def _funnel_count(stage: str, by_status: dict, delivered: int) -> int:
    """漏斗各阶段数量。

    ⚠️ 漏斗是「累计」概念（进入面试的人必然先被查看），
       而 by_status 是「当前状态」的快照，两者不是一回事，必须显式换算。
    """
    if stage == "submitted":
        return delivered
    if stage == "viewed":
        # 走到 viewed 及之后的都算被查看过
        return sum(
            by_status.get(s, 0)
            for s in ("viewed", "chatting", "interview", "passed", "hired", "rejected")
        )
    if stage == "interview":
        return sum(by_status.get(s, 0) for s in INTERVIEW_STAGE)
    if stage == "passed":
        return sum(by_status.get(s, 0) for s in ("passed", "hired"))
    if stage == "hired":
        return by_status.get("hired", 0)
    return 0


@router.get("/detail/{application_id}", summary="投递详情（含面试邀约）")
async def read_application(
    application_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(40402, "投递记录不存在", http=404)

    interviews = await _interviews_of(db, row.id)
    job = await db.get(Job, row.job_id)

    data = application_out(row, "candidate", interviews=interviews)
    data["job"] = {
        "id": job.id,
        "title": job.title,
        "salaryText": job.salary_min and _salary_text(job) or "",
        "cityName": job.city_name,
        "district": job.district,
        "experience": job.experience,
        "education": job.education,
        "status": job.status,
    } if job else None
    return ok({"application": data})


@router.post("/{application_id}/withdraw", summary="撤回投递")
async def withdraw_application(
    application_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤回投递。已进入面试流程后不允许撤回。"""
    row = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(40402, "投递记录不存在", http=404)
    if row.status not in WITHDRAWABLE:
        raise BizError(40903, "已进入面试流程，无法撤回", http=409)

    row.status = "withdrawn"
    await db.commit()
    await db.refresh(row)
    logger.info("[apply] uid=%s 撤回投递 application=%s", user.id, row.id)
    return ok({"application": application_out(row, "candidate")})


# ==========================================================
# 简历
# ==========================================================


@resume_router.get("", summary="我的简历")
async def read_resume(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """未创建时返回结构完整的空模板，前端表单无需判空。"""
    row = await _my_resume(db, user.id)
    if row is None:
        data = empty_resume()
        # 用账号信息预填，减少用户输入
        data["name"] = user.nickname or ""
        data["email"] = user.email or ""
        data["phone"] = user.phone or ""
        return ok({"resume": data, "exists": False})
    return ok({"resume": resume_detail(row), "exists": True})


@resume_router.put("", summary="保存简历")
async def save_resume(
    payload: ResumeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """全量覆盖式保存，保存后回写完整度。"""
    row = await _my_resume(db, user.id)
    if row is None:
        row = Resume(user_id=user.id)
        db.add(row)

    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.is_open = 1 if payload.is_open else 0

    # ⚠️ 必须先 flush 再算完整度：完整度依赖刚写入的字段值
    await db.flush()
    row.completeness = compute_completeness(row)

    await db.commit()
    await db.refresh(row)
    logger.info("[resume] uid=%s 保存简历 完整度=%s", user.id, row.completeness)
    return ok({"resume": resume_detail(row)})


@resume_router.get("/report", summary="求职报告")
async def resume_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职报告：漏斗 + 求职力雷达 + 规则化建议。

    ⚠️ 雷达与建议都是「按规则算出来的」，不是 AI 生成：
       它们要能解释、要能复现，且不消耗用户的 AI 额度。
       AI 的那份分析在 /api/v1/ai/*（求职助手）里单独提供。
    """
    from app.routers.apply import _funnel_count  # 同文件函数，避免重复实现

    rows = (
        await db.execute(
            select(Application.status, func.count())
            .where(Application.user_id == user.id)
            .group_by(Application.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}
    delivered = sum(by_status.values())

    resume = await _my_resume(db, user.id)
    completeness = resume.completeness if resume else 0

    # 备考充分度：刷题记录条数
    answered = (
        await db.execute(
            select(func.count()).select_from(QuestionRecord).where(QuestionRecord.user_id == user.id)
        )
    ).scalar() or 0

    favorited = (
        await db.execute(
            select(func.count()).select_from(JobFavorite).where(JobFavorite.user_id == user.id)
        )
    ).scalar() or 0

    interviewed = sum(by_status.get(s, 0) for s in INTERVIEW_STAGE)
    passed = by_status.get("passed", 0) + by_status.get("hired", 0)

    def clamp(value: float) -> int:
        return max(0, min(100, int(round(value))))

    radar = [
        {"name": "简历完整度", "value": clamp(completeness), "desc": "信息越完整，被查看率越高"},
        {"name": "投递活跃度", "value": clamp(delivered * 8), "desc": "建议保持每周 5 次以上投递"},
        {"name": "面试转化率", "value": clamp(interviewed / delivered * 100) if delivered else 0,
         "desc": "进入面试的比例，反映简历与岗位的匹配度"},
        {"name": "备考充分度", "value": clamp(answered * 4), "desc": "面试题练习量，直接影响面试表现"},
        {"name": "目标清晰度", "value": clamp(_target_clarity(resume)), "desc": "期望岗位与城市越明确，推荐越准"},
    ]

    tips = []
    if completeness < 80:
        tips.append("简历完整度只有 %d%%，补齐工作经历与项目经历后，被查看率通常能明显提升。" % completeness)
    if delivered == 0:
        tips.append("还没有投递记录：先从「推荐职位」里挑 3 个匹配度高的岗位投出去。")
    elif delivered < 5:
        tips.append("投递量偏少（%d 次）：建议本周内再投 3~5 个岗位，扩大面试机会。" % delivered)
    if delivered and interviewed == 0:
        tips.append("还没有进入面试：可以按目标岗位的职能分类刷一遍高频面试题，同时检查简历与 JD 的关键词匹配度。")
    if answered < 10:
        tips.append("面试题练习量偏少：先做目标岗位的高频题，比盲目刷题更有效。")
    if favorited > 0 and passed == 0:
        tips.append("收藏了 %d 个职位：收藏不等于投递，别让心仪岗位错过窗口期。" % favorited)
    if not tips:
        tips.append("求职状态良好：保持投递节奏，同时针对已进入面试的岗位做专项准备。")

    return ok({
        "funnel": [
            {"stage": key, "label": label, "count": _funnel_count(key, by_status, delivered)}
            for key, label in FUNNEL_STAGES
        ],
        "radar": radar,
        "tips": tips,
        "summary": {
            "delivered": delivered,
            "interviewed": interviewed,
            "passed": passed,
            "favorited": favorited,
            "answered": answered,
            "completeness": completeness,
            "interviewRate": round(interviewed / delivered * 100) if delivered else 0,
        },
    })


def _target_clarity(resume: Resume | None) -> float:
    """目标清晰度：期望岗位、期望城市、期望薪资三项填了几项。"""
    if resume is None:
        return 0
    score = 0
    if resume.expected_position:
        score += 50
    if resume.expected_city:
        score += 30
    if resume.expected_salary_min or resume.expected_salary_max:
        score += 20
    return score
