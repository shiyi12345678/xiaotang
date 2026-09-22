"""内容域路由：前缀 /api/v1/content （**公开，无需登录**）。

端点总表：
    GET /home                首页聚合（banners/分类/直播/精品/猜你喜欢…）
    GET /config/{key}        单个 page_config 的原始值
    GET /categories          分类列表（kind=home|main）
    GET /courses             课程列表（分类/类型/关键词过滤 + 排序 + 分页）
    GET /courses/{id}        课程详情
    （无 /courses/{id}/lessons：数据库没有课时表，见文末说明）

本模块错误码：
    42001 内容不存在（课程/分类/配置键）
    42002 参数不合法（kind/sort/page/size）

⚠️ 为什么内容域公开、而 mine/study 必须登录：
    课程、分类、榜单这些是**共享内容**，浏览不需要身份；
    订单、收藏、错题、学习统计是**个人数据**，一律从 token 取 uid。

⚠️ 为什么没有 /courses/{id}/lessons（课表/目录）：
    course 表只有 extra.lessonCount（精品课的「共 68 课时」这种总数），
    没有「第几章第几讲」的明细表；全项目唯一一份章节目录是
    page_config 里那条 `courseDetail`（而且只覆盖 c1001 一门课）。
    与其为 53 门课编造目录，不如不提供这个端点：
    目录内容仍可通过 GET /config/courseDetail 取原始 JSON。
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.database import get_db
from app.models import Category, Course, PageConfig
from app.schemas.content import (
    VALID_KINDS,
    category_out,
    course_brief,
    course_full,
    course_guess_out,
    course_live_out,
    course_quality_out,
    escape_like,
    normalize_sort,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/content", tags=["内容"])

# 首页聚合里那些「原样取自 page_config」的键（顺序即前端消费顺序）
HOME_CONFIG_KEYS = (
    "banners", "homeNotices", "adBanners", "seckill",
    "checkinInfo", "dailyQuote", "rankings",
)

# 配置缺失时的兜底空值：保证 /home 的 11 个键**永远存在**。
# ⚠️ 这不是「编造数据」，而是「如实表示没有数据」——
#    前端拿到 [] / {} 才不会因为 undefined 报错，与 mock 时期的形状也一致。
HOME_CONFIG_FALLBACK = {
    "banners": [],
    "homeNotices": [],
    "adBanners": [],
    "seckill": {},
    "checkinInfo": {},
    "dailyQuote": {},
    "rankings": [],
}

# 猜你喜欢在库里的落法：seed 时归到 category_id='guess'、kind='normal'
GUESS_CATEGORY_ID = "guess"


async def _load_config(db: AsyncSession, keys) -> dict:
    """一次查询取回多个 page_config 键的值，返回 {key: value}。"""
    rows = (
        await db.execute(select(PageConfig).where(PageConfig.key.in_(list(keys))))
    ).scalars().all()
    return {row.key: row.value for row in rows}


@router.get("/home", summary="首页聚合数据")
async def home(db: AsyncSession = Depends(get_db)):
    """首页一次请求拿全部数据，页面不必发六七个请求。

    返回的键与 pages/index/index.vue 现在从 mock 里 import 的名字**一一对应**：
        banners homeNotices homeCategories adBanners seckill
        checkinInfo dailyQuote rankings liveCourses qualityCourses guessYouLike

    ⚠️ 其中只有 homeCategories / liveCourses / qualityCourses / guessYouLike
       是从表里现算的，其余 7 个是 page_config 的原始 JSON。
       （mock 里 homeCategories 与 guessYouLike 不是独立配置项，
         在库里分别是 category(kind='home') 与 course(category_id='guess')。）
    """
    cfg = await _load_config(db, HOME_CONFIG_KEYS)
    data = {key: cfg.get(key, HOME_CONFIG_FALLBACK[key]) for key in HOME_CONFIG_KEYS}

    # 首页入口分类：kind='home'
    cats = (
        await db.execute(
            select(Category)
            .where(Category.kind == "home")
            .order_by(Category.sort_order.asc(), Category.pk.asc())
        )
    ).scalars().all()
    data["homeCategories"] = [category_out(row) for row in cats]

    # 直播课 / 精品课：同一张 course 表按 kind 区分
    live = (
        await db.execute(
            select(Course).where(Course.kind == "live").order_by(Course.sort_order.asc())
        )
    ).scalars().all()
    data["liveCourses"] = [course_live_out(row) for row in live]

    quality = (
        await db.execute(
            select(Course).where(Course.kind == "quality").order_by(Course.sort_order.asc())
        )
    ).scalars().all()
    data["qualityCourses"] = [course_quality_out(row) for row in quality]

    # 猜你喜欢
    guess = (
        await db.execute(
            select(Course)
            .where(Course.category_id == GUESS_CATEGORY_ID)
            .order_by(Course.sort_order.asc())
        )
    ).scalars().all()
    data["guessYouLike"] = [course_guess_out(row) for row in guess]

    return ok(data)


@router.get("/config/{key}", summary="读取页面配置")
async def read_config(key: str, db: AsyncSession = Depends(get_db)):
    """按 key 返回 page_config 的原始 JSON 值。

    ⚠️ 刻意**直接返回原始值**（不包一层 {key,value}）：
       这样 GET /config/banners 拿到的就是 mock 里 `banners` 那个数组，
       页面把 `import { banners }` 换成一次请求即可，字段路径不变。

    可用键（26 个，均为种子数据）：banners / homeNotices / adBanners / seckill /
    checkinInfo / dailyQuote / rankings / categoryFilters / searchData /
    studyOverview / studyTasks / studyReport / freeCourses / learningCourses /
    mineStats / mineGridGroups / settingGroups / loginConfig / aiWelcome /
    aiCapabilities / aiConversations / aiSessionMessages / aiReferences /
    courseDetail / wrongQuestions / studyEntries
    """
    row = (
        await db.execute(select(PageConfig).where(PageConfig.key == key))
    ).scalar_one_or_none()
    if row is None:
        raise BizError(42001, "配置不存在：%s" % key)
    return ok(row.value)


@router.get("/categories", summary="分类列表")
async def list_categories(
    kind: str | None = Query(None, description="home=首页入口 / main=分类页；不传则全给"),
    db: AsyncSession = Depends(get_db),
):
    """分类列表。

    ⚠️ 返回结构同时带 name 与 title（同一个值）：
       mock 的分类页 categoryList 用 name，首页入口 homeCategories 用 title，
       两个页面共用这一个端点，因此两个键都给（见 schemas/content.py 的说明）。
    """
    stmt = select(Category)
    if kind:
        if kind not in ("home", "main"):
            raise BizError(42002, "kind 只能是 home 或 main")
        stmt = stmt.where(Category.kind == kind)
    rows = (
        await db.execute(stmt.order_by(Category.kind.asc(), Category.sort_order.asc()))
    ).scalars().all()
    return ok({"list": [category_out(row) for row in rows]})


@router.get("/courses", summary="课程列表")
async def list_courses(
    category_id: str | None = Query(None, description="按分类过滤，如 ai / recommend / guess"),
    kind: str | None = Query(None, description="normal / quality / live / seckill"),
    keyword: str | None = Query(None, description="关键词，匹配标题/简介/角标/讲师"),
    sort: str | None = Query(None, description="综合排序|销量优先|价格最低|最新上架 或 default|sales|price|new"),
    page: int = Query(1, description="页码，从 1 起"),
    size: int = Query(20, description="每页条数，1~100"),
    db: AsyncSession = Depends(get_db),
):
    """课程列表：过滤 + 排序 + 分页。

    返回：{list, total, page, size, hasMore}
        list 元素是几个 mock 课程数组的**超集**（字段名全部沿用 mock 叫法）：
        id/title/summary/teacher/price/originPrice/enrolled/tag/cover/categoryId/kind

    ⚠️ 关键词搜索覆盖 title + summary + tag + teacher 四列（LIKE '%kw%'）。
       没有建全文索引：create_all 不会给**已存在**的表补索引，
       而本期约定不改既有表结构（不 ALTER）。课程量级只有 53 行，
       LIKE 扫描完全够用；真要上全文检索需要单独 ALTER 加 FULLTEXT/ngram 索引。

    ⚠️ kind=free（免费好课）会返回 42002 而不是空列表：
       免费好课在库里不是 course.kind，而是 page_config.freeCourses，
       直接报错并给出正确读法，比静默返回空数组更好排查。
    """
    # ---- 参数校验（放在路由层，才能给业务错误码而不是被框架吞成 50000）----
    if page < 1:
        raise BizError(42002, "page 必须 ≥ 1")
    if size < 1 or size > 100:
        raise BizError(42002, "size 必须在 1~100 之间")

    order_key = normalize_sort(sort)
    if order_key is None:
        raise BizError(
            42002,
            "sort 只能是 综合排序/销量优先/价格最低/最新上架（或 default/sales/price/new）",
        )

    conditions = []
    if category_id:
        conditions.append(Course.category_id == category_id)
    if kind:
        if kind not in VALID_KINDS:
            raise BizError(
                42002,
                "kind 只能是 %s；免费好课请读 /api/v1/content/config/freeCourses"
                % "/".join(VALID_KINDS),
            )
        conditions.append(Course.kind == kind)
    keyword = (keyword or "").strip()
    if keyword:
        like = "%%%s%%" % escape_like(keyword)
        conditions.append(
            or_(
                Course.title.like(like, escape="\\"),
                Course.summary.like(like, escape="\\"),
                Course.tag.like(like, escape="\\"),
                Course.teacher.like(like, escape="\\"),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(Course).where(*conditions))
    ).scalar() or 0

    # ---- 排序口径 ----
    if order_key == "sales":
        order_by = (Course.enrolled.desc(), Course.sort_order.asc(), Course.id.asc())
    elif order_key == "price":
        order_by = (Course.price.asc(), Course.sort_order.asc(), Course.id.asc())
    elif order_key == "new":
        # 种子数据是同一批写入的，created_at 基本同秒，故再用 id 兜一层保证稳定
        order_by = (Course.created_at.desc(), Course.id.desc())
    else:
        order_by = (Course.sort_order.asc(), Course.id.asc())

    rows = (
        await db.execute(
            select(Course)
            .where(*conditions)
            .order_by(*order_by)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()

    return ok({
        "list": [course_brief(row) for row in rows],
        "total": int(total),
        "page": page,
        "size": size,
        "hasMore": page * size < int(total),
    })


@router.get("/courses/{course_id}", summary="课程详情")
async def course_detail(course_id: str, db: AsyncSession = Depends(get_db)):
    """课程详情：列表字段 + 类型化字段（tags/startTime/lessonCount/teachers…）+ 原始 extra。

    ⚠️ 数据库里没有的字段一律不返回，也不编造：
        subtitle / rating / highlights / catalog / comments 这几项 page_config 里
        **只有 c1001 一门课**的一份 JSON（键名 courseDetail），
       所以它们不会出现在本接口里；课程详情页的「亮点/目录/评价」目前仍应
       读 /config/courseDetail，或等这些数据真正建表后再补。
    """
    row = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if row is None:
        raise BizError(42001, "课程不存在：%s" % course_id)
    return ok(course_full(row))
