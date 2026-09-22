"""职位域接口（求职者端）。

路由前缀：/api/v1/job
    公开只读：home / categories / cities / filters / list / detail
    需要登录：favorite/*（收藏属于「我的数据」，一律按 token 的 uid 过滤）

⚠️ 安全约定（与 mine 域一致）：
    收藏相关的每条查询都带 user_id == user.id，且**绝不接受客户端传 uid**，
    因此天然不可能读到或改到别人的收藏。
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import City, Company, Job, JobCategory, JobFavorite, PageConfig, User
from app.schemas.content import escape_like
from app.schemas.job import (
    FavoriteIn,
    category_out,
    city_out,
    job_brief,
    job_detail,
)

router = APIRouter(prefix="/api/v1/job", tags=["职位"])
logger = logging.getLogger(__name__)

# 排序别名：既收英文 key，也收中文原文，页面可以把选中的中文项直接发过来
SORT_ALIASES = {
    "default": "default", "综合": "default", "综合排序": "default", "": "default",
    "salary": "salary", "薪资": "salary", "薪资最高": "salary", "薪资从高到低": "salary",
    "new": "new", "最新": "new", "最新发布": "new",
    "hot": "hot", "热门": "hot", "最热": "hot", "投递最多": "hot",
}

# 职位形态（与 seed 数据的 job.kind 一致）
VALID_KINDS = ("normal", "urgent", "referral", "intern", "campus")


# ==========================================================
# 内部小工具
# ==========================================================


async def _job_or_404(db: AsyncSession, job_id: str) -> Job:
    """取有效职位，不存在则抛业务错误。"""
    row = await db.get(Job, job_id)
    if row is None or row.deleted_at is not None:
        raise BizError(40401, "职位不存在或已下线", http=404)
    return row


async def _config(db: AsyncSession, key: str, default):
    """读取招聘端页面配置（page_config 表的 rc_ 前缀键）。"""
    row = await db.get(PageConfig, key)
    if row is None or row.value is None:
        return default
    return row.value


def _company_join():
    """职位与公司的左连接：公司被删/缺失时职位仍能返回（company 字段为 None）。"""
    return Company.id == Job.company_id


async def _rows_with_company(db: AsyncSession, conditions, order, offset: int, limit: int):
    """按条件查询职位并带出公司，返回 [(Job, Company|None)]。"""
    stmt = (
        select(Job, Company)
        .join(Company, _company_join(), isouter=True)
        .where(*conditions)
        .order_by(*order)
        .offset(offset)
        .limit(limit)
    )
    return (await db.execute(stmt)).all()


async def _count_jobs(db: AsyncSession, conditions) -> int:
    """与 _rows_with_company 完全相同的条件下的总数（分页用）。"""
    stmt = (
        select(func.count())
        .select_from(Job)
        .join(Company, _company_join(), isouter=True)
        .where(*conditions)
    )
    return (await db.execute(stmt)).scalar() or 0


def _base_conditions() -> list:
    """只返回「在招 + 未删除」的职位。"""
    return [Job.status == 1, Job.deleted_at.is_(None)]


# ==========================================================
# 公开只读接口
# ==========================================================


@router.get("/home", summary="职位首页聚合数据")
async def home(db: AsyncSession = Depends(get_db)):
    """一次返回首页所需的全部数据，避免首页发 5~6 个请求。

    组成：轮播、职能入口、公告、搜索热词、列表标签、推荐职位、内推专区。
    """
    banners = await _config(db, "rcHeroBanners", [])
    entries = await _config(db, "rcHomeEntries", [])
    notices = await _config(db, "rcHomeNotices", [])
    keywords = await _config(db, "rcHotKeywords", [])
    tabs = await _config(db, "rcJobListTabs", [])

    # 推荐职位：sort_order 由灌库时的业务优先级决定，越大越靠前
    rows = await _rows_with_company(
        db,
        _base_conditions(),
        (Job.sort_order.desc(), Job.publish_at.desc()),
        0,
        10,
    )
    recommend = [job_brief(job, company) for job, company in rows]

    # 内推专区：kind=referral，单独一组，首页给它独立区块
    referral_rows = await _rows_with_company(
        db,
        _base_conditions() + [Job.kind == "referral"],
        (Job.sort_order.desc(),),
        0,
        4,
    )
    referral = [job_brief(job, company) for job, company in referral_rows]

    # 急招：给首页一条「急招专区」横向列表
    urgent_rows = await _rows_with_company(
        db,
        _base_conditions() + [Job.kind == "urgent"],
        (Job.sort_order.desc(),),
        0,
        6,
    )
    urgent = [job_brief(job, company) for job, company in urgent_rows]

    # 首页职能入口：既可以用 page_config 的静态配置，也可以用分类表 kind='home'
    if not entries:
        cats = (
            await db.execute(
                select(JobCategory)
                .where(JobCategory.level == 1, JobCategory.kind == "home")
                .order_by(JobCategory.sort_order)
            )
        ).scalars().all()
        entries = [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
                "bg": c.bg,
                "link": f"/pages/job/list?category={c.id}",
            }
            for c in cats
        ]

    total_jobs = await _count_jobs(db, _base_conditions())

    return ok({
        "banners": banners,
        "entries": entries,
        "notices": notices,
        "hotKeywords": keywords,
        "listTabs": tabs,
        "recommend": recommend,
        "referral": referral,
        "urgent": urgent,
        "totalJobs": total_jobs,
    })


@router.get("/categories", summary="职能分类（两级）")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """返回一级分类（含子类）、扁平子类列表、首页入口三类视图。"""
    rows = (
        await db.execute(
            select(JobCategory).order_by(JobCategory.level, JobCategory.sort_order)
        )
    ).scalars().all()

    level1 = [category_out(r) for r in rows if r.level == 1]
    level2 = [category_out(r) for r in rows if r.level == 2]

    children: dict = {}
    for item in level2:
        children.setdefault(item["parentId"], []).append(item)
    for item in level1:
        item["children"] = children.get(item["id"], [])

    return ok({
        "list": level1,
        "flat": level2,
        "home": [i for i in level1 if i["kind"] == "home"],
    })


@router.get("/cities", summary="城市列表（热门 + 首字母分组）")
async def list_cities(db: AsyncSession = Depends(get_db)):
    """热门城市用于搜索页顶部，分组数据用于「全部城市」列表。"""
    rows = (await db.execute(select(City).order_by(City.sort_order))).scalars().all()
    items = [city_out(r) for r in rows]

    groups: dict = {}
    for item in items:
        letter = (item["initial"] or "#").upper()
        groups.setdefault(letter, []).append(item)

    return ok({
        "hot": [i for i in items if i["isHot"]],
        "all": items,
        # 分组固定按字母序输出，前端直接渲染索引列表
        "groups": [{"initial": k, "cities": groups[k]} for k in sorted(groups)],
    })


@router.get("/filters", summary="职位筛选条件")
async def list_filters(db: AsyncSession = Depends(get_db)):
    """筛选选项来自 page_config.rcFilterOptions（展示型数据，可后台改而不动代码）。"""
    options = await _config(db, "rcFilterOptions", None)
    if not options:
        # 兜底：配置缺失时给一份可用默认值，保证筛选器不空白
        options = {
            "salary": [
                {"label": "10K以下", "min": 0, "max": 10},
                {"label": "10-20K", "min": 10, "max": 20},
                {"label": "20-30K", "min": 20, "max": 30},
                {"label": "30-50K", "min": 30, "max": 50},
                {"label": "50K以上", "min": 50, "max": 0},
            ],
            "experience": ["经验不限", "应届生", "1年以内", "1-3年", "3-5年", "5-10年", "10年以上"],
            "education": ["学历不限", "大专", "本科", "硕士", "博士"],
            "jobType": [
                {"label": "全职", "value": "fulltime"},
                {"label": "实习", "value": "intern"},
                {"label": "兼职", "value": "parttime"},
            ],
        }
    return ok({"filters": options, "kinds": [
        {"label": "全部", "value": ""},
        {"label": "急招", "value": "urgent"},
        {"label": "名企内推", "value": "referral"},
        {"label": "实习", "value": "intern"},
        {"label": "校招", "value": "campus"},
    ]})


@router.get("/list", summary="职位列表 / 搜索")
async def list_jobs(
    keyword: str | None = Query(None, description="搜索关键词（职位名或公司名）"),
    category: str | None = Query(None, description="职能分类 id；传一级分类会自动展开为全部子类"),
    city: str | None = Query(None, description="城市 id"),
    salary: str | None = Query(None, description="薪资区间，形如 10-20（单位 K）"),
    salary_min: int | None = Query(None, alias="salaryMin"),
    salary_max: int | None = Query(None, alias="salaryMax"),
    experience: str | None = Query(None, description="经验要求（中文枚举）"),
    education: str | None = Query(None, description="学历要求（中文枚举）"),
    kind: str | None = Query(None, description="职位形态 normal/urgent/referral/intern/campus"),
    job_type: str | None = Query(None, alias="jobType"),
    sort: str | None = Query(None, description="排序 default/salary/new/hot，也接受中文"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
):
    """职位列表与搜索共用同一个接口：有 keyword 就是搜索，没有就是列表筛选。"""
    conditions = _base_conditions()

    # ---------- 关键词：职位名 或 公司名 ----------
    if keyword and keyword.strip():
        kw = f"%{escape_like(keyword.strip())}%"
        conditions.append(
            or_(
                Job.title.like(kw, escape="\\"),
                Company.name.like(kw, escape="\\"),
                Company.short_name.like(kw, escape="\\"),
            )
        )

    # ---------- 职能：一级分类展开成全部子类 ----------
    if category:
        cat = await db.get(JobCategory, category)
        if cat is not None and cat.level == 1:
            child_ids = (
                await db.execute(
                    select(JobCategory.id).where(JobCategory.parent_id == category)
                )
            ).scalars().all()
            # 一级分类本身没有职位，必须落到子类；无子类时退回原值以免查出全部
            conditions.append(Job.category_id.in_(list(child_ids) or [category]))
        else:
            conditions.append(Job.category_id == category)

    # ---------- 城市 ----------
    if city:
        conditions.append(Job.city_id == city)

    # ---------- 薪资：区间重叠即算命中 ----------
    low, high = None, None
    if salary and "-" in str(salary):
        parts = str(salary).split("-", 1)
        try:
            low, high = int(parts[0]), int(parts[1])
        except ValueError:
            low = high = None
    if salary_min is not None:
        low = salary_min
    if salary_max is not None:
        high = salary_max
    if low:                      # 0 表示「不限」，不参与过滤
        conditions.append(Job.salary_max >= low)
    if high:
        conditions.append(Job.salary_min <= high)

    # ---------- 其他枚举 ----------
    if experience and experience not in ("经验不限", "不限"):
        conditions.append(Job.experience == experience)
    if education and education not in ("学历不限", "不限"):
        conditions.append(Job.education == education)
    if kind and kind in VALID_KINDS:
        conditions.append(Job.kind == kind)
    if job_type:
        conditions.append(Job.job_type == job_type)

    # ---------- 排序 ----------
    key = SORT_ALIASES.get((sort or "default").strip(), "default")
    if key == "salary":
        order = (Job.salary_max.desc(), Job.sort_order.desc())
    elif key == "new":
        order = (Job.publish_at.desc(), Job.sort_order.desc())
    elif key == "hot":
        order = (Job.applicant_count.desc(), Job.sort_order.desc())
    else:
        order = (Job.sort_order.desc(), Job.publish_at.desc())

    total = await _count_jobs(db, conditions)
    rows = await _rows_with_company(
        db, conditions, order, (page - 1) * page_size, page_size
    )

    return ok({
        "list": [job_brief(job, company) for job, company in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.get("/detail/{job_id}", summary="职位详情")
async def read_job_detail(job_id: str, db: AsyncSession = Depends(get_db)):
    """职位详情 + 公司信息 + 相似职位。"""
    job = await _job_or_404(db, job_id)
    company = await db.get(Company, job.company_id) if job.company_id else None

    # 浏览量 +1。
    # ⚠️ 演示实现：真实系统应做「同 IP/同用户 N 小时内只计一次」并异步落库，
    #    否则一次刷新就涨一个数。这里为了简单直接累加。
    job.view_count = (job.view_count or 0) + 1
    await db.commit()

    similar_rows = await _rows_with_company(
        db,
        _base_conditions() + [Job.category_id == job.category_id, Job.id != job.id],
        (Job.sort_order.desc(),),
        0,
        5,
    )

    return ok({
        "job": job_detail(job, company),
        "similar": [job_brief(j, c) for j, c in similar_rows],
    })


# ==========================================================
# 收藏（需要登录）
# ==========================================================


@router.get("/favorite/ids", summary="我收藏的职位ID集合")
async def favorite_ids(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列表页一次性拿到收藏 id 集合，在本地给卡片打标，避免每张卡都发请求。"""
    ids = (
        await db.execute(select(JobFavorite.job_id).where(JobFavorite.user_id == user.id))
    ).scalars().all()
    return ok({"ids": list(ids)})


@router.get("/favorite/list", summary="我的收藏")
async def favorite_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(JobFavorite).where(JobFavorite.user_id == user.id)
        )
    ).scalar() or 0

    stmt = (
        select(Job, Company, JobFavorite)
        .join(JobFavorite, JobFavorite.job_id == Job.id)
        .join(Company, _company_join(), isouter=True)
        .where(JobFavorite.user_id == user.id)
        .order_by(JobFavorite.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    items = []
    for job, company, fav in rows:
        data = job_brief(job, company, is_favorite=True)
        data["favoriteAt"] = fav.created_at.strftime("%Y-%m-%d %H:%M:%S") if fav.created_at else ""
        items.append(data)

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.post("/favorite", summary="收藏职位")
async def add_favorite(
    payload: FavoriteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """幂等：重复收藏不报错，只是 changed=False。"""
    job = await _job_or_404(db, payload.job_id)

    exists = (
        await db.execute(
            select(JobFavorite).where(
                JobFavorite.user_id == user.id, JobFavorite.job_id == job.id
            )
        )
    ).scalar_one_or_none()

    if exists is None:
        db.add(JobFavorite(user_id=user.id, job_id=job.id))
        await db.commit()
        logger.info("[job.favorite] uid=%s 收藏 %s", user.id, job.id)

    return ok({"jobId": job.id, "favorited": True, "changed": exists is None})


@router.delete("/favorite/{job_id}", summary="取消收藏")
async def remove_favorite(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """幂等：未收藏时删除 0 行也不报错。"""
    result = await db.execute(
        delete(JobFavorite).where(
            JobFavorite.user_id == user.id, JobFavorite.job_id == job_id
        )
    )
    await db.commit()
    if result.rowcount:
        logger.info("[job.favorite] uid=%s 取消收藏 %s", user.id, job_id)
    return ok({"jobId": job_id, "favorited": False, "changed": bool(result.rowcount)})
