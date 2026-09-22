"""企业 HR 端接口。

路由前缀：/api/v1/hr
    身份：me / bind / companies（绑定公司才具备招聘方权限）
    工作台：dashboard
    职位：jobs（增删改查 + 上下架）
    简历：applications（收到的简历、候选人详情、状态流转、发面试邀约）
    面试：interviews
    公司：company（企业主页维护）

⚠️ 数据隔离的唯一依据是 company_id：
    调用者绑定了哪家公司，就只能看到、也只能操作这家公司的职位与简历，
    每条查询都带 company_id 条件，绝不接受客户端传入 companyId。
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import (
    Application,
    City,
    Company,
    Interview,
    Job,
    JobCategory,
    Resume,
    User,
    UserRole,
)
from app.schemas.apply import application_out, interview_out, resume_brief, resume_detail
from app.schemas.hr import (
    DIRECT_STATUSES,
    ApplicationStatusIn,
    BindCompanyIn,
    CompanyUpdateIn,
    InterviewInviteIn,
    JobPostIn,
    JobStatusIn,
    can_transition,
    transition_error,
)
from app.schemas.job import company_detail, job_brief, job_detail

router = APIRouter(prefix="/api/v1/hr", tags=["企业招聘"])
logger = logging.getLogger(__name__)


# ==========================================================
# 身份
# ==========================================================


async def _hr_context(db: AsyncSession, user: User) -> tuple[UserRole, Company]:
    """取当前用户的 HR 身份与所属公司；未绑定则拒绝访问。

    ⚠️ 这是整个企业端的权限闸门：所有 HR 接口都必须先过这里，
       因此「未绑定公司的账号看不到任何招聘数据」是结构性保证，而不是靠各处自觉。
    """
    role = (
        await db.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role == "hr")
        )
    ).scalar_one_or_none()
    if role is None or not role.company_id:
        raise BizError(40301, "当前账号还不是企业招聘方，请先选择公司并绑定", http=403)

    company = await db.get(Company, role.company_id)
    if company is None or company.deleted_at is not None:
        raise BizError(40303, "绑定的公司不存在，请重新绑定", http=403)
    return role, company


async def _own_job(db: AsyncSession, company_id: str, job_id: str) -> Job:
    """取本公司名下的职位，越权访问按「不存在」处理（不泄露别家职位是否存在）。"""
    row = await db.get(Job, job_id)
    if row is None or row.deleted_at is not None or row.company_id != company_id:
        raise BizError(40401, "职位不存在或不属于你所在的公司", http=404)
    return row


async def _own_application(db: AsyncSession, company_id: str, application_id: int) -> Application:
    """取本公司收到的投递，越权访问同样按「不存在」处理。"""
    row = (
        await db.execute(
            select(Application).where(
                Application.id == application_id, Application.company_id == company_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(40402, "投递记录不存在或不属于你所在的公司", http=404)
    return row


@router.get("/me", summary="我的招聘方身份")
async def read_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """前端启动企业端时先调这个：未绑定则引导去绑定公司。"""
    role = (
        await db.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role == "hr")
        )
    ).scalar_one_or_none()
    if role is None or not role.company_id:
        return ok({"bound": False, "role": None, "company": None})

    company = await db.get(Company, role.company_id)
    return ok({
        "bound": True,
        "role": {
            "role": role.role,
            "companyId": role.company_id,
            "hrTitle": role.hr_title,
            "isDefault": bool(role.is_default),
        },
        "company": company_detail(company) if company else None,
    })


@router.get("/companies", summary="可选公司列表（绑定用）")
async def list_companies(
    keyword: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """演示环境简化：直接从公司表里选一家绑定，不做企业资质审核。"""
    stmt = select(Company).where(Company.deleted_at.is_(None))
    if keyword and keyword.strip():
        from app.schemas.content import escape_like

        stmt = stmt.where(Company.name.like(f"%{escape_like(keyword.strip())}%", escape="\\"))
    stmt = stmt.order_by(Company.sort_order, Company.id).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return ok({"list": [{
        "id": c.id,
        "name": c.name,
        "shortName": c.short_name,
        "logoText": c.logo_text,
        "logoColor": c.logo_color,
        "industry": c.industry,
        "scale": c.scale,
        "city": c.city,
        "jobCount": c.job_count,
    } for c in rows]})


@router.post("/bind", summary="绑定公司，成为招聘方")
async def bind_company(
    payload: BindCompanyIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """绑定成功后会把这批「没有归属招聘者」的职位挂到当前账号名下。

    ⚠️ 为什么要回填 job.hr_id：
       种子职位是平台预置数据，hr_id 为空；而求职者「立即沟通」需要知道跟谁聊。
       绑定后把该公司 hr_id 为空的职位指向当前账号，沟通链路才通。
    """
    company = await db.get(Company, payload.company_id)
    if company is None or company.deleted_at is not None:
        raise BizError(40403, "公司不存在", http=404)

    role = (
        await db.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role == "hr")
        )
    ).scalar_one_or_none()

    if role is None:
        # 第一个身份设为默认身份
        has_role = (
            await db.execute(select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id))
        ).scalar() or 0
        role = UserRole(
            user_id=user.id,
            role="hr",
            company_id=company.id,
            hr_title=payload.hr_title,
            is_default=1 if has_role == 0 else 0,
        )
        db.add(role)
    else:
        role.company_id = company.id
        role.hr_title = payload.hr_title

    await db.flush()

    # 回填无人认领的职位
    unowned = (
        await db.execute(
            select(Job).where(
                Job.company_id == company.id, Job.hr_id.is_(None), Job.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    for job in unowned:
        job.hr_id = user.id
        job.hr_title = payload.hr_title
        job.hr_name = job.hr_name or (user.nickname or "")

    await db.commit()
    logger.info(
        "[hr] uid=%s 绑定公司 %s，接管 %d 个职位", user.id, company.id, len(unowned)
    )
    return ok({
        "bound": True,
        "company": company_detail(company),
        "adoptedJobs": len(unowned),
    })


# ==========================================================
# 工作台
# ==========================================================


@router.get("/dashboard", summary="HR 工作台概览")
async def dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """工作台首页：职位与简历的汇总数字 + 待办列表。"""
    role, company = await _hr_context(db, user)

    async def count_jobs(*conds) -> int:
        return (
            await db.execute(
                select(func.count()).select_from(Job).where(
                    Job.company_id == company.id, Job.deleted_at.is_(None), *conds
                )
            )
        ).scalar() or 0

    async def count_apps(*conds) -> int:
        return (
            await db.execute(
                select(func.count()).select_from(Application).where(
                    Application.company_id == company.id, *conds
                )
            )
        ).scalar() or 0

    open_jobs = await count_jobs(Job.status == 1)
    total_jobs = await count_jobs()
    total_apps = await count_apps()
    pending = await count_apps(Application.status == "submitted")
    interviewing = await count_apps(Application.status == "interview")
    hired = await count_apps(Application.status == "hired")
    # 今日新增投递（从今天 00:00 起算）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_apps = await count_apps(Application.created_at >= today_start)

    # 待处理简历（最新的 5 条）
    recent_rows = (
        await db.execute(
            select(Application, Resume)
            .join(Resume, Resume.id == Application.resume_id, isouter=True)
            .where(Application.company_id == company.id)
            .order_by(Application.created_at.desc())
            .limit(5)
        )
    ).all()

    # 即将到来的面试
    upcoming = (
        await db.execute(
            select(Interview)
            .where(
                Interview.company_id == company.id,
                Interview.status.in_(("pending", "confirmed")),
                Interview.interview_time.is_not(None),
                Interview.interview_time >= datetime.now() - timedelta(hours=2),
            )
            .order_by(Interview.interview_time)
            .limit(5)
        )
    ).scalars().all()

    return ok({
        "company": {
            "id": company.id,
            "name": company.name,
            "shortName": company.short_name or company.name,
            "logoText": company.logo_text,
            "logoColor": company.logo_color,
        },
        "hrTitle": role.hr_title,
        "stats": {
            "openJobs": open_jobs,
            "totalJobs": total_jobs,
            "totalApplications": total_apps,
            "pending": pending,
            "interviewing": interviewing,
            "hired": hired,
            "todayApplications": today_apps,
        },
        "recentApplications": [
            application_out(a, "hr", resume=r) for a, r in recent_rows
        ],
        "upcomingInterviews": [interview_out(i) for i in upcoming],
    })


# ==========================================================
# 职位管理
# ==========================================================


def _new_job_id(existing_max: int) -> str:
    """生成新职位 ID：沿用种子的 j + 四位数字风格，从当前最大值往后排。"""
    return "j%d" % (max(existing_max, 2000) + 1)


async def _next_job_id(db: AsyncSession) -> str:
    """取当前最大的 jxxxx 编号并加一。

    ⚠️ 只在「数字后缀」上比较，非数字命名的历史数据会被忽略而不是报错。
    """
    ids = (await db.execute(select(Job.id))).scalars().all()
    nums = []
    for value in ids:
        if isinstance(value, str) and value.startswith("j") and value[1:].isdigit():
            nums.append(int(value[1:]))
    return _new_job_id(max(nums) if nums else 2000)


async def _validate_job_input(db: AsyncSession, payload: JobPostIn) -> tuple[JobCategory, City]:
    """校验职位入参：职能必须是二级分类，城市必须存在，薪资区间必须合法。"""
    if payload.salary_min >= payload.salary_max:
        raise BizError(40010, "薪资下限必须小于上限")

    category = await db.get(JobCategory, payload.category_id)
    if category is None or category.level != 2:
        raise BizError(40011, "请选择有效的职能子分类")

    city = await db.get(City, payload.city_id)
    if city is None:
        raise BizError(40012, "请选择有效的城市")

    return category, city


@router.get("/jobs", summary="我发布的职位")
async def list_my_jobs(
    status: int | None = Query(None, description="1=在招 / 0=已关闭；不传返回全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """职位管理列表：除了职位字段，还带上「收到简历数」这个 HR 最关心的数字。"""
    _role, company = await _hr_context(db, user)

    conditions = [Job.company_id == company.id, Job.deleted_at.is_(None)]
    if status is not None:
        conditions.append(Job.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Job).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Job)
            .where(*conditions)
            .order_by(Job.status.desc(), Job.sort_order.desc(), Job.publish_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # 一次性把这批职位的投递数查出来，避免每行一次查询
    job_ids = [j.id for j in rows]
    counts: dict = {}
    if job_ids:
        count_rows = (
            await db.execute(
                select(Application.job_id, func.count())
                .where(Application.job_id.in_(job_ids))
                .group_by(Application.job_id)
            )
        ).all()
        counts = {jid: n for jid, n in count_rows}

    items = []
    for job in rows:
        data = job_brief(job, company)
        data["jobId"] = job.id
        data["status"] = job.status
        data["statusText"] = "招聘中" if job.status == 1 else "已关闭"
        data["applicationCount"] = counts.get(job.id, 0)
        data["descriptionText"] = (job.description or "")[:80]
        items.append(data)

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.post("/jobs", summary="发布职位")
async def create_job(
    payload: JobPostIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role, company = await _hr_context(db, user)
    category, city = await _validate_job_input(db, payload)

    job_id = await _next_job_id(db)

    extra = {}
    if payload.process:
        extra["process"] = payload.process

    job = Job(
        id=job_id,
        kind=payload.kind,
        title=payload.title,
        # ⚠️ 归属只来自调用者绑定的公司，绝不接受客户端传入
        company_id=company.id,
        category_id=category.id,
        city_id=city.id,
        city_name=city.name,
        district=payload.district,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        salary_months=payload.salary_months,
        experience=payload.experience,
        education=payload.education,
        job_type=payload.job_type,
        tags=payload.tags,
        description=payload.description,
        requirements=payload.requirements,
        status=payload.status,
        hr_id=user.id,
        hr_name=user.nickname or "",
        hr_title=role.hr_title,
        hr_active="今日活跃",
        view_count=0,
        applicant_count=0,
        # 新职位排在最前：sort_order 取一个足够大的值（现有种子最大 44）
        sort_order=100 + int(datetime.now().timestamp()) % 1000,
        extra=extra or None,
        publish_at=datetime.now() if payload.status == 1 else None,
    )
    db.add(job)

    company.job_count = (company.job_count or 0) + (1 if payload.status == 1 else 0)
    await db.commit()
    await db.refresh(job)

    logger.info("[hr] uid=%s 发布职位 %s（%s）", user.id, job.id, job.title)
    return ok({"job": job_detail(job, company)})


@router.put("/jobs/{job_id}", summary="编辑职位")
async def update_job(
    job_id: str,
    payload: JobPostIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _role, company = await _hr_context(db, user)
    job = await _own_job(db, company.id, job_id)
    category, city = await _validate_job_input(db, payload)

    was_open = job.status == 1

    job.title = payload.title
    job.kind = payload.kind
    job.category_id = category.id
    job.city_id = city.id
    job.city_name = city.name
    job.district = payload.district
    job.salary_min = payload.salary_min
    job.salary_max = payload.salary_max
    job.salary_months = payload.salary_months
    job.experience = payload.experience
    job.education = payload.education
    job.job_type = payload.job_type
    job.tags = payload.tags
    job.description = payload.description
    job.requirements = payload.requirements
    job.status = payload.status
    if payload.process:
        extra = dict(job.extra or {})
        extra["process"] = payload.process
        job.extra = extra
    if payload.status == 1 and not was_open:
        job.publish_at = datetime.now()

    if was_open != (payload.status == 1):
        company.job_count = max(0, (company.job_count or 0) + (1 if payload.status == 1 else -1))

    await db.commit()
    await db.refresh(job)
    logger.info("[hr] uid=%s 编辑职位 %s", user.id, job.id)
    return ok({"job": job_detail(job, company)})


@router.post("/jobs/{job_id}/status", summary="职位上下架")
async def set_job_status(
    job_id: str,
    payload: JobStatusIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _role, company = await _hr_context(db, user)
    job = await _own_job(db, company.id, job_id)

    if job.status == payload.status:
        return ok({"jobId": job.id, "status": job.status, "changed": False})

    job.status = payload.status
    if payload.status == 1:
        job.publish_at = datetime.now()
    company.job_count = max(
        0, (company.job_count or 0) + (1 if payload.status == 1 else -1)
    )
    await db.commit()
    logger.info("[hr] uid=%s 职位 %s 状态改为 %s", user.id, job.id, payload.status)
    return ok({"jobId": job.id, "status": job.status, "changed": True})


@router.delete("/jobs/{job_id}", summary="删除职位")
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """逻辑删除：投递记录里保留了职位快照，因此删职位不会让候选人的投递记录失联。"""
    _role, company = await _hr_context(db, user)
    job = await _own_job(db, company.id, job_id)

    job.deleted_at = datetime.now()
    if job.status == 1:
        job.status = 0
        company.job_count = max(0, (company.job_count or 0) - 1)
    await db.commit()
    logger.info("[hr] uid=%s 删除职位 %s", user.id, job.id)
    return ok({"jobId": job.id, "deleted": True})


# ==========================================================
# 收到的简历（投递）
# ==========================================================


@router.get("/applications", summary="收到的简历")
async def list_applications(
    job_id: str | None = Query(None, alias="jobId"),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _role, company = await _hr_context(db, user)

    conditions = [Application.company_id == company.id]
    if job_id:
        conditions.append(Application.job_id == job_id)
    if status:
        conditions.append(Application.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Application).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Application, Resume)
            .join(Resume, Resume.id == Application.resume_id, isouter=True)
            .where(*conditions)
            .order_by(Application.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return ok({
        "list": [application_out(a, "hr", resume=r) for a, r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
        # 各状态数量：HR 列表页的筛选标签要显示角标
        "counts": await _status_counts(db, company.id, job_id),
    })


async def _status_counts(db: AsyncSession, company_id: str, job_id: str | None) -> dict:
    """按状态汇总该公司的投递数（列表页筛选标签角标用）。"""
    stmt = select(Application.status, func.count()).where(
        Application.company_id == company_id
    )
    if job_id:
        stmt = stmt.where(Application.job_id == job_id)
    rows = (await db.execute(stmt.group_by(Application.status))).all()
    return {status: n for status, n in rows}


@router.get("/applications/{application_id}", summary="候选人详情")
async def read_application(
    application_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看候选人：这里是「简历已查看」的触发点。

    ⚠️ 副作用放在读接口里是有意的：HR 打开简历就算已查看，
       若交给前端再发一个「标记已查看」的请求，网络失败时状态就丢了。
    """
    _role, company = await _hr_context(db, user)
    row = await _own_application(db, company.id, application_id)

    resume = await db.get(Resume, row.resume_id) if row.resume_id else None
    job = await db.get(Job, row.job_id)

    # 首次查看：记录时间并推进状态（只从 submitted 推进，不覆盖 HR 已经手动改过的状态）
    if row.viewed_at is None:
        row.viewed_at = datetime.now()
        if can_transition(row.status, "viewed"):
            row.status = "viewed"
        await db.commit()
        await db.refresh(row)

    interviews = (
        await db.execute(
            select(Interview)
            .where(Interview.application_id == row.id)
            .order_by(Interview.round_no)
        )
    ).scalars().all()

    data = application_out(row, "hr", resume=resume, interviews=list(interviews))
    data["candidateDetail"] = resume_detail(resume) if resume else None
    data["job"] = {
        "id": job.id,
        "title": job.title,
        "salaryText": job_brief(job, company)["salaryText"] if job else "",
        "status": job.status if job else 0,
    } if job else None
    return ok({"application": data})


@router.post("/applications/{application_id}/status", summary="变更候选人状态")
async def update_application_status(
    application_id: int,
    payload: ApplicationStatusIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """状态流转。合法性由 schemas/hr.py 的 ALLOWED_TRANSITIONS 单点决定。"""
    _role, company = await _hr_context(db, user)
    row = await _own_application(db, company.id, application_id)

    target = payload.status
    if target not in DIRECT_STATUSES:
        # interview 只能通过「发面试邀约」设置，保证状态与邀约记录一致
        raise BizError(40013, "不支持的状态值；「待面试」请使用发面试邀约接口")
    if not can_transition(row.status, target):
        raise BizError(40910, transition_error(row.status, target), http=409)

    row.status = target
    if payload.remark:
        row.hr_remark = payload.remark
    if payload.rating:
        row.hr_rating = payload.rating
    if row.viewed_at is None:
        row.viewed_at = datetime.now()

    await db.commit()
    await db.refresh(row)
    logger.info("[hr] uid=%s 投递 %s 状态 %s", user.id, row.id, target)
    return ok({"application": application_out(row, "hr")})


@router.post("/applications/{application_id}/interview", summary="发出面试邀约")
async def invite_interview(
    application_id: int,
    payload: InterviewInviteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建面试邀约，并把投递状态推进到「待面试」。"""
    role, company = await _hr_context(db, user)
    row = await _own_application(db, company.id, application_id)

    if row.status in ("hired", "rejected", "withdrawn"):
        raise BizError(40911, transition_error(row.status, "interview"), http=409)

    try:
        interview_time = datetime.strptime(payload.interview_time.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        raise BizError(40014, "面试时间格式应为 YYYY-MM-DD HH:MM")

    if payload.mode not in ("onsite", "video", "phone"):
        raise BizError(40015, "面试方式不合法")

    invite = Interview(
        application_id=row.id,
        job_id=row.job_id,
        user_id=row.user_id,
        company_id=company.id,
        hr_id=user.id,
        round_no=payload.round_no,
        round_name=payload.round_name,
        interview_time=interview_time,
        duration_min=payload.duration_min,
        mode=payload.mode,
        address=payload.address,
        online_link=payload.online_link,
        interviewer=payload.interviewer,
        contact=payload.contact,
        status="pending",
        remark=payload.remark,
    )
    db.add(invite)

    # 状态推进到「待面试」（只有状态机允许时才改，避免覆盖更靠后的状态）
    if can_transition(row.status, "interview"):
        row.status = "interview"
    if row.viewed_at is None:
        row.viewed_at = datetime.now()

    await db.commit()
    await db.refresh(invite)

    logger.info(
        "[hr] uid=%s 向投递 %s 发出 %s（%s）",
        user.id, row.id, payload.round_name, payload.interview_time,
    )
    return ok({"interview": interview_out(invite), "applicationStatus": row.status})


# ==========================================================
# 面试安排 / 公司信息
# ==========================================================


@router.get("/interviews", summary="面试安排")
async def list_interviews(
    status: str | None = Query(None, description="pending / confirmed / finished / canceled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按时间正序返回（HR 关心的是「接下来要面谁」）。"""
    _role, company = await _hr_context(db, user)

    conditions = [Interview.company_id == company.id]
    if status:
        conditions.append(Interview.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Interview).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Interview, Application, Resume)
            .join(Application, Application.id == Interview.application_id, isouter=True)
            .join(Resume, Resume.id == Application.resume_id, isouter=True)
            .where(*conditions)
            .order_by(Interview.interview_time.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = []
    for interview, application, resume in rows:
        data = interview_out(interview)
        data["jobTitle"] = application.job_title if application else ""
        if resume is not None:
            data["candidate"] = resume_brief(resume)
        items.append(data)

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.get("/company", summary="公司信息")
async def read_company(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _role, company = await _hr_context(db, user)
    return ok({"company": company_detail(company)})


@router.put("/company", summary="更新公司信息")
async def update_company(
    payload: CompanyUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """企业主页维护。空字符串表示「不改这一项」，避免误清空已有内容。"""
    _role, company = await _hr_context(db, user)

    simple_fields = (
        "short_name", "logo_text", "logo_color", "industry", "scale",
        "stage", "city", "address", "intro", "website",
    )
    for field in simple_fields:
        value = getattr(payload, field)
        if value:
            setattr(company, field, value)
    if payload.benefits:
        company.benefits = payload.benefits

    await db.commit()
    await db.refresh(company)
    logger.info("[hr] uid=%s 更新公司信息 %s", user.id, company.id)
    return ok({"company": company_detail(company)})
