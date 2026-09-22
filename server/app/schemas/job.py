"""招聘域出入参与「ORM 行 → 前端字段」映射。

⚠️ 字段名纪律（本文件存在的主要理由，与 schemas/content.py 一致）：
    映射出来的键一律用 camelCase，数据库列是 snake_case，转换只在本层做一次，
    路由层不再自己拼字段，前端页面也不需要做字段名转换。

⚠️ 哪些是「算出来的」而不是直接读列：
    - salaryText   由 salary_min/max/months 拼装。后端拼的唯一好处是口径统一：
                   列表页、详情页、投递快照三处显示必须完全一致；
    - publishText  「3天前发布」这类相对时间，按服务端时间算，避免各端时区/时钟差异；
    - isFavorite   需要结合当前用户的收藏表，由路由层查好后传进来（本层只负责放字段）。
"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.models import City, Company, Job, JobCategory

# ==========================================================
# 小工具
# ==========================================================


def salary_text(job: Job) -> str:
    """薪资文案，如「15-25K·14薪」「20K」「薪资面议」。

    ⚠️ 三种边界都要覆盖：
        - 上下限都为 0 → 面议（有些职位不公开薪资）
        - 上下限相等   → 只显示一个数，不要出现「20-20K」
        - 12 薪        → 不显示「·12薪」，那是默认值，写出来反而啰嗦
    """
    low, high, months = job.salary_min or 0, job.salary_max or 0, job.salary_months or 12
    if low <= 0 and high <= 0:
        return "薪资面议"
    if low == high:
        base = f"{low}K"
    else:
        base = f"{low}-{high}K"
    return f"{base}·{months}薪" if months and months != 12 else base


def relative_time(value: datetime | None) -> str:
    """把时间转成「刚刚 / 3小时前 / 2天前 / 2026-08-01」这类展示文案。"""
    if value is None:
        return ""
    now = datetime.now()
    target = value
    # 数据库里可能取出带时区的值，统一成 naive 再比较，避免 TypeError
    if target.tzinfo is not None:
        target = target.astimezone(timezone.utc).replace(tzinfo=None)
    delta = now - target
    seconds = delta.total_seconds()
    if seconds < 0:
        return "刚刚"
    if seconds < 3600:
        minutes = max(1, int(seconds // 60))
        return f"{minutes}分钟前" if minutes > 1 else "刚刚"
    if seconds < 86400:
        return f"{int(seconds // 3600)}小时前"
    if delta.days < 30:
        return f"{delta.days}天前"
    return target.strftime("%Y-%m-%d")


def text_lines(raw: str | None) -> list:
    """把「1. xxx\\n2. yyy」形式的文本切成数组，供前端逐条渲染。

    ⚠️ 为什么在服务端切：岗位职责/任职要求两个字段在详情页要渲染成有序列表，
       切分规则（换行 + 去掉序号前缀）只应有一份实现。
    """
    if not raw:
        return []
    lines = []
    for line in str(raw).replace("\r\n", "\n").split("\n"):
        item = line.strip()
        if not item:
            continue
        # 去掉「1. 」「1、」「- 」「• 」这类前缀，前端自己用序号渲染
        for prefix in ("- ", "• "):
            if item.startswith(prefix):
                item = item[len(prefix):].strip()
        head = item.split(" ", 1)
        if len(head) == 2 and head[0].rstrip(".、)）").isdigit():
            item = head[1].strip()
        if item:
            lines.append(item)
    return lines


# ==========================================================
# 公司 / 城市 / 职能分类
# ==========================================================


def company_brief(row: Company) -> dict:
    """公司简要信息（列表卡片、职位卡片的公司角标）。"""
    return {
        "id": row.id,
        "name": row.name,
        "shortName": row.short_name or row.name,
        "logoText": row.logo_text or (row.short_name or row.name)[:1],
        "logoColor": row.logo_color,
        "industry": row.industry,
        "scale": row.scale,
        "stage": row.stage,
        "city": row.city,
        "jobCount": row.job_count,
    }


def company_detail(row: Company) -> dict:
    """公司完整信息（公司信息页 / 职位详情页的公司区块）。"""
    data = company_brief(row)
    data.update({
        "address": row.address,
        "intro": row.intro or "",
        # 公司介绍按段落切，前端逐段渲染，避免一坨文本
        "introParagraphs": text_lines(row.intro),
        "benefits": row.benefits or [],
        "website": row.website,
    })
    return data


def city_out(row: City) -> dict:
    """城市（搜索页城市列表 / 筛选器）。"""
    return {
        "id": row.id,
        "name": row.name,
        "province": row.province,
        "initial": row.initial,
        "isHot": bool(row.is_hot),
    }


def category_out(row: JobCategory) -> dict:
    """职能分类（分类页 / 首页入口 / 筛选器）。

    ⚠️ 同时给出 name 与 title 两个键：
       改造前的项目里，分类页用 name、首页入口用 title，
       前端两套页面都能直接接上，不必为同一条数据改字段名。这是有意为之的别名。
    """
    return {
        "id": row.id,
        "name": row.name,
        "title": row.name,
        "parentId": row.parent_id,
        "level": row.level,
        "icon": row.icon,
        "desc": row.description,
        "description": row.description,
        "color": row.color,
        "bg": row.bg,
        "kind": row.kind,
        "isHot": bool(row.is_hot),
        "sort": row.sort_order,
    }


# ==========================================================
# 职位
# ==========================================================


def job_brief(job: Job, company: Company | None = None, is_favorite: bool = False) -> dict:
    """职位卡片（列表页、搜索页、首页推荐、相似职位）。"""
    return {
        "id": job.id,
        "kind": job.kind,
        "title": job.title,
        "salaryText": salary_text(job),
        "salaryMin": job.salary_min,
        "salaryMax": job.salary_max,
        "salaryMonths": job.salary_months,
        "cityId": job.city_id,
        "cityName": job.city_name,
        "district": job.district,
        # 列表卡片上显示的是「北京·海淀区」这种合并文案
        "location": "·".join([x for x in (job.city_name, job.district) if x]),
        "categoryId": job.category_id,
        "experience": job.experience,
        "education": job.education,
        "jobType": job.job_type,
        "tags": job.tags or [],
        "companyId": job.company_id,
        # companyName 给简称（卡片上放不下全称），companyFullName 给全称（详情页用）
        "companyName": (company.short_name or company.name) if company else "",
        "companyFullName": company.name if company else "",
        "logoText": (company.logo_text or company.short_name or company.name[:1]) if company else "",
        "logoColor": company.logo_color if company else "#00A6A7",
        "industry": company.industry if company else "",
        "scale": company.scale if company else "",
        "stage": company.stage if company else "",
        "hrName": job.hr_name,
        "hrTitle": job.hr_title,
        "hrActive": job.hr_active,
        "viewCount": job.view_count,
        "applicantCount": job.applicant_count,
        "publishAt": job.publish_at.strftime("%Y-%m-%d %H:%M:%S") if job.publish_at else "",
        "publishText": relative_time(job.publish_at),
        "isFavorite": bool(is_favorite),
    }


def job_detail(job: Job, company: Company | None = None, is_favorite: bool = False) -> dict:
    """职位详情（详情页）。在 job_brief 基础上补充正文与流程。"""
    data = job_brief(job, company, is_favorite)
    extra = job.extra or {}
    data.update({
        "status": job.status,
        "statusText": "招聘中" if job.status == 1 else "已关闭",
        "jobTypeText": {"fulltime": "全职", "intern": "实习", "parttime": "兼职"}.get(
            job.job_type, "全职"
        ),
        # 详情页把长文本切成数组逐条渲染
        "description": text_lines(job.description),
        "requirements": text_lines(job.requirements),
        # 招聘流程（如 简历筛选 → 一面 → 二面 → HR面 → 发offer）
        "process": extra.get("process") or [],
        # 内推职位额外带奖金
        "referralBonus": extra.get("referralBonus", ""),
        "isRemote": bool(extra.get("isRemote", False)),
        "company": company_detail(company) if company else None,
    })
    return data


# ==========================================================
# 请求体
# ==========================================================


class FavoriteIn(BaseModel):
    """收藏 / 取消收藏入参。

    ⚠️ 只收 jobId，不收 uid：uid 一律取自 token，
       否则任何人都能替别人收藏（与 mine 域的安全约定保持一致）。
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId", min_length=1, max_length=32)
