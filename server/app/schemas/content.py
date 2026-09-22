"""内容域出入参与「ORM 行 → 前端字段」映射。

⚠️ 字段名纪律（本文件存在的主要理由）：
    映射出来的键必须与 common/mock/index.js 里的键**完全一致**（camelCase），
    这样各页面从 mock 切成接口时，改的是「数据来源」而不是「字段名」——
    否则每个页面都要改两遍，迁移成本翻倍。
    数据库列是 snake_case，转换只在本层做一次，路由层不再自己拼字段。

⚠️ 那些「一个字段两个名字」的地方（name/title、desc/description）：
    mock 自己就不统一——分类页的 categoryList 用 name/desc，
    首页入口 homeCategories 用 title。两条数据在库里是同一张表（category），
    所以接口同时给出两个键（name+title、desc+description），
    让两个页面都能零改动接上。这是**有意为之的兼容别名**，不是笔误。
"""
from decimal import Decimal, InvalidOperation

from app.models import Category, Course

# ==========================================================
# 通用小工具
# ==========================================================


def num(value) -> int | float:
    """把数据库的 Decimal/Numeric 转成前端友好的 int / float。

    ⚠️ 为什么必须转：Numeric(10,2) 取出的是 Decimal("399.00")，
       JSON 序列化后是 399.0，而 mock 里价格一律是整数 399。
       整数值统一给 int，页面里 `price + '元'` 这类拼接才不会出现 ".0"。
    """
    if value is None:
        return 0
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return 0
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def escape_like(keyword: str) -> str:
    """转义 LIKE 的通配符，避免用户输入的 % / _ 变成通配。

    配合 `like(..., escape="\\\\")` 使用：用户搜 "50%" 时按字面量匹配，
    而不是被当成「50 开头的任意串」。
    """
    return (
        str(keyword)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


# 数据库里真实存在的 course.kind 取值（seed/mock_data.json 的五个来源收敛而来）
VALID_KINDS = ("normal", "quality", "live", "seckill")

# 排序别名：既收英文，也收客户端 categoryFilters.sorts 里的中文原文，
# 这样页面可以把选中的中文排序项直接当参数发过来。
SORT_ALIASES = {
    "default": "default", "综合": "default", "综合排序": "default", "": "default",
    "sales": "sales", "销量": "sales", "销量优先": "sales", "销量最高": "sales",
    "price": "price", "价格": "price", "价格最低": "price", "价格从低到高": "price",
    "new": "new", "最新": "new", "最新上架": "new",
}


def normalize_sort(raw: str | None) -> str | None:
    """把客户端传来的排序值归一成 default/sales/price/new；不认识返回 None。"""
    if raw is None:
        return "default"
    return SORT_ALIASES.get(str(raw).strip())


# ==========================================================
# 分类
# ==========================================================


def category_out(row: Category) -> dict:
    """分类 → 前端结构。

    同时给出 name 与 title、desc 与 description（见模块头的说明）：
        name/desc  → 分类页 categoryList 的用法
        title      → 首页入口 homeCategories 的用法
    """
    return {
        "id": row.id,
        "name": row.name,
        "title": row.name,
        "icon": row.icon,
        "desc": row.description,
        "description": row.description,
        "color": row.color,
        "bg": row.bg,
        "kind": row.kind,
    }


# ==========================================================
# 课程
# ==========================================================


def course_brief(row: Course) -> dict:
    """课程列表项（/content/courses 用）。

    字段是几个 mock 列表的超集，且都用 mock 的叫法：
        coursesByCategory / searchPool → id,title,summary,price,tag
        guessYouLike                   → + teacher,originPrice,enrolled
    多出来的键页面不会读，不影响迁移；少一个键页面就得改代码。
    """
    return {
        "id": row.id,
        "kind": row.kind,
        "categoryId": row.category_id,
        "title": row.title,
        "summary": row.summary,
        "teacher": row.teacher,
        "price": num(row.price),
        "originPrice": num(row.origin_price),
        "enrolled": row.enrolled,
        "tag": row.tag,
        "cover": row.cover,
    }


def course_quality_out(row: Course) -> dict:
    """精品课（首页 qualityCourses 的形状）。

    extra 里存的是 {tags, teachers:[{name}], startTime, lessonCount}，
    这里**提升到顶层**——mock 里这些字段就在顶层，页面直接读 item.tags。
    """
    extra = row.extra or {}
    return {
        "id": row.id,
        "tags": extra.get("tags") or [],
        "title": row.title,
        "startTime": extra.get("startTime") or "",
        "lessonCount": extra.get("lessonCount") or 0,
        "teachers": extra.get("teachers") or [],
        "price": num(row.price),
        "originPrice": num(row.origin_price),
        "enrolled": row.enrolled,
    }


def course_live_out(row: Course) -> dict:
    """直播课（首页 liveCourses 的形状）。

    数据库把讲师名放在 course.teacher，而 mock 的键叫 teacherName；
    extra 里是 {teacherTitle, liveTime, status, viewers}。
    """
    extra = row.extra or {}
    return {
        "id": row.id,
        "title": row.title,
        "teacherName": row.teacher,
        "teacherTitle": extra.get("teacherTitle") or "",
        "liveTime": extra.get("liveTime") or "",
        "status": extra.get("status") or "",
        "price": num(row.price),
        "originPrice": num(row.origin_price),
        "viewers": extra.get("viewers") or 0,
    }


def course_seckill_out(row: Course) -> dict:
    """秒杀商品（home.seckill.list 的形状）。

    ⚠️ 注意这一路用的是 `name` 而不是 `title`：
       mock 的 seckill.list 元素就是 {id,name,price,originPrice,soldPercent}，
       seed 时把原字段 name 落进了 course.title，这里按 mock 的名字还原回去。
    """
    extra = row.extra or {}
    return {
        "id": row.id,
        "name": row.title,
        "price": num(row.price),
        "originPrice": num(row.origin_price),
        "soldPercent": extra.get("soldPercent") or 0,
    }


def course_guess_out(row: Course) -> dict:
    """猜你喜欢（首页 guessYouLike 的形状）。"""
    return {
        "id": row.id,
        "title": row.title,
        "teacher": row.teacher,
        "price": num(row.price),
        "originPrice": num(row.origin_price),
        "enrolled": row.enrolled,
        "tag": row.tag,
    }


def course_full(row: Course) -> dict:
    """课程详情（/content/courses/{id}）。

    在列表项的基础上：
        - 保留原始 extra 整份（便于排查与将来扩展）；
        - 按 kind 把 extra 里的类型化字段提升到顶层，
          使详情页读 course.tags / course.lessonCount / course.liveTime
          的手感与 mock 时期一致。

    ⚠️ 数据库里**没有**的字段（subtitle / rating / highlights / catalog / comments）
       一律不返回，不编造。这些内容目前只存在于 page_config 的单条
       `courseDetail` 里（见 routers/content.py 对 /content/config/{key} 的说明）。
    """
    data = course_brief(row)
    data["extra"] = row.extra or {}
    extra = row.extra or {}
    if row.kind == "quality":
        data["tags"] = extra.get("tags") or []
        data["startTime"] = extra.get("startTime") or ""
        data["lessonCount"] = extra.get("lessonCount") or 0
        data["teachers"] = extra.get("teachers") or []
    elif row.kind == "live":
        data["teacherName"] = row.teacher
        data["teacherTitle"] = extra.get("teacherTitle") or ""
        data["liveTime"] = extra.get("liveTime") or ""
        data["status"] = extra.get("status") or ""
        data["viewers"] = extra.get("viewers") or 0
    elif row.kind == "seckill":
        data["name"] = row.title
        data["soldPercent"] = extra.get("soldPercent") or 0
    data["createdAt"] = row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else None
    return data
