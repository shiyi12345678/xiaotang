"""种子数据灌入脚本。

用途：把客户端 Mock 数据（server/seed/mock_data.json）导入数据库。

运行（工作目录 = server/）：
    python -m app.seed

⚠️ 幂等性：采用「先清空后写入」策略，可反复执行。
⚠️ 仅限开发 / 演示环境使用，请勿在生产库执行。
"""
import asyncio
import json
from pathlib import Path

from sqlalchemy import delete

from app.config import DB_NAME
from app.database import SessionLocal, engine
from app.models import (
    Category,
    Coupon,
    Course,
    MemoryCard,
    Order,
    PageConfig,
    Question,
    QuestionBank,
    UserCourse,
)

# 种子数据文件（由 tools/export_mock_data.mjs 生成）
SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "mock_data.json"

# 需要清空的表（顺序不影响，因为表间无外键约束）
CLEAR_MODELS = (
    Category, Course, PageConfig, QuestionBank, Question,
    MemoryCard, Order, Coupon, UserCourse,
)

# 直接以「原样 JSON」存入 page_config 的配置项
PAGE_CONFIG_KEYS = (
    "banners", "homeNotices", "adBanners", "seckill", "checkinInfo",
    "dailyQuote", "rankings", "categoryFilters", "searchData",
    "studyOverview", "studyEntries", "studyTasks", "studyReport",
    "mineStats", "mineGridGroups", "settingGroups", "learningCourses",
    "wrongQuestions", "freeCourses", "loginConfig",
    "aiWelcome", "aiCapabilities", "aiReferences",
    "aiConversations", "aiSessionMessages", "courseDetail",
)


def load_data() -> dict:
    """读取并返回 mock_data.json 的内容。"""
    if not SEED_FILE.exists():
        raise FileNotFoundError(
            "未找到种子数据：%s\n"
            "请先在项目根目录执行：node server/tools/export_mock_data.mjs" % SEED_FILE
        )
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def build_categories(data: dict) -> list:
    """构造分类记录。

    来源有两个，合并后统一用 name 字段：
      - categoryList     → kind='main'（分类页左侧）
      - homeCategories   → kind='home'（首页入口，字段是 title）
    """
    rows = []
    for i, item in enumerate(data.get("categoryList", [])):
        rows.append(Category(
            id=item["id"], name=item["name"], icon=item.get("icon", ""),
            description=item.get("desc", ""), kind="main", sort_order=i,
        ))
    for i, item in enumerate(data.get("homeCategories", [])):
        rows.append(Category(
            id=item["id"], name=item.get("title", ""), icon=item.get("icon", ""),
            description="", color=item.get("color", ""), bg=item.get("bg", ""),
            kind="home", sort_order=i,
        ))
    return rows


def build_courses(data: dict) -> list:
    """构造课程记录（统一收敛到 course 表，用 kind 区分来源）。"""
    rows = []

    # 1) 分类课程：coursesByCategory 的每个分类展开，kind=normal
    #    ⚠️ searchPool 正是这些课程的全量聚合，因此不再重复导入
    by_cat = data.get("coursesByCategory", {})
    for cat_id, items in by_cat.items():
        for i, item in enumerate(items):
            rows.append(Course(
                id=item["id"], kind="normal", category_id=cat_id,
                title=item.get("title", ""), summary=item.get("summary", ""),
                price=item.get("price", 0), origin_price=item.get("originPrice", 0),
                tag=item.get("tag", ""), sort_order=i,
            ))

    # 2) 猜你喜欢：字段与分类课程接近，但带 teacher/enrolled，无 summary
    for i, item in enumerate(data.get("guessYouLike", [])):
        rows.append(Course(
            id=item["id"], kind="normal", category_id="guess",
            title=item.get("title", ""), teacher=item.get("teacher", ""),
            price=item.get("price", 0), origin_price=item.get("originPrice", 0),
            enrolled=item.get("enrolled", 0), tag=item.get("tag", ""), sort_order=100 + i,
        ))

    # 3) 精品课：tags / startTime / lessonCount / teachers 放 extra
    for i, item in enumerate(data.get("qualityCourses", [])):
        rows.append(Course(
            id=item["id"], kind="quality", category_id="quality",
            title=item.get("title", ""), price=item.get("price", 0),
            origin_price=item.get("originPrice", 0), enrolled=item.get("enrolled", 0),
            sort_order=i, extra={
                "tags": item.get("tags", []),
                "startTime": item.get("startTime", ""),
                "lessonCount": item.get("lessonCount", 0),
                "teachers": item.get("teachers", []),
            },
        ))

    # 4) 直播课
    for i, item in enumerate(data.get("liveCourses", [])):
        rows.append(Course(
            id=item["id"], kind="live", category_id="live",
            title=item.get("title", ""), teacher=item.get("teacherName", ""),
            price=item.get("price", 0), origin_price=item.get("originPrice", 0),
            sort_order=i, extra={
                "teacherTitle": item.get("teacherTitle", ""),
                "liveTime": item.get("liveTime", ""),
                "status": item.get("status", ""),
                "viewers": item.get("viewers", 0),
            },
        ))

    # 5) 秒杀商品：原字段为 name，统一映射到 title
    for i, item in enumerate(data.get("seckill", {}).get("list", [])):
        rows.append(Course(
            id=item["id"], kind="seckill", category_id="seckill",
            title=item.get("name", ""), price=item.get("price", 0),
            origin_price=item.get("originPrice", 0), sort_order=i,
            extra={"soldPercent": item.get("soldPercent", 0)},
        ))

    return rows


def build_questions(data: dict) -> tuple:
    """构造题库与题目记录。"""
    banks = []
    for i, item in enumerate(data.get("questionBanks", [])):
        banks.append(QuestionBank(
            id=item["id"], name=item.get("name", ""), count=item.get("count", 0),
            done=item.get("done", 0), correct_rate=item.get("correctRate", 0),
            icon=item.get("icon", ""), sort_order=i,
        ))

    questions = []
    for i, item in enumerate(data.get("mockQuestions", [])):
        questions.append(Question(
            id=item["id"], bank_id=item.get("bankId", "qb1") or "qb1",
            type=item.get("type", "single"), stem=item.get("stem", ""),
            options=item.get("options", []), answer=item.get("answer", []),
            analysis=item.get("analysis", ""), knowledge=item.get("knowledge", ""),
            sort_order=i,
        ))
    return banks, questions


def build_memory_cards(data: dict) -> list:
    """构造记忆卡记录。"""
    rows = []
    for i, item in enumerate(data.get("memoryCards", [])):
        rows.append(MemoryCard(
            id=item["id"], front=item.get("front", ""), back=item.get("back", ""),
            tag=item.get("tag", ""), stage=item.get("stage", 0),
            next_review=item.get("nextReview", ""), sort_order=i,
        ))
    return rows


def build_mine(data: dict, uid) -> tuple:
    """构造订单 / 优惠券 / 我的课程（统一挂在演示账号 uid 下）。"""
    orders = []
    for i, item in enumerate(data.get("orderList", [])):
        orders.append(Order(
            id=item["id"], uid=uid, title=item.get("title", ""),
            price=item.get("price", 0), status=item.get("status", ""),
            date=item.get("date", ""), type=item.get("type", "course"), sort_order=i,
        ))

    coupons = []
    for i, item in enumerate(data.get("couponList", [])):
        coupons.append(Coupon(
            id=item["id"], uid=uid, amount=item.get("amount", 0),
            threshold=item.get("threshold", ""), scope=item.get("scope", ""),
            expire=item.get("expire", ""), status=item.get("status", "unused"), sort_order=i,
        ))

    user_courses = []
    my = data.get("myCourses", {})
    for kind in ("learning", "finished", "collect"):
        for i, item in enumerate(my.get(kind, [])):
            user_courses.append(UserCourse(
                id=item["id"], uid=uid, kind=kind, title=item.get("title", ""),
                teacher=item.get("teacher", ""), progress=item.get("progress", 0),
                last_lesson=item.get("lastLesson", ""), sort_order=i,
            ))

    return orders, coupons, user_courses


async def seed() -> None:
    """执行灌库（先清空后写入，可重复运行）。"""
    from sqlalchemy import func, select

    from app.models import User

    data = load_data()

    async with SessionLocal() as db:
        # 1) 清空旧数据，保证幂等
        for model in CLEAR_MODELS:
            await db.execute(delete(model))

        # 2) 取演示账号 uid（"我的"域数据挂到该账号下）
        #    ⚠️ 若库中还没有任何用户，则 uid 为 None（数据仍会导入，只是不归属用户）
        first_user = (
            await db.execute(select(User).order_by(User.id.asc()).limit(1))
        ).scalar_one_or_none()
        uid = first_user.id if first_user else None

        # 3) 内容域
        db.add_all(build_categories(data))
        db.add_all(build_courses(data))

        # 4) 页面配置（原样 JSON 存储）
        for key in PAGE_CONFIG_KEYS:
            if key in data:
                db.add(PageConfig(key=key, value=data[key]))

        # 5) 学习域
        banks, questions = build_questions(data)
        db.add_all(banks)
        db.add_all(questions)
        db.add_all(build_memory_cards(data))

        # 6) 我的域
        orders, coupons, user_courses = build_mine(data, uid)
        db.add_all(orders)
        db.add_all(coupons)
        db.add_all(user_courses)

        await db.commit()

    # 统计输出
    async with SessionLocal() as db:
        print("灌库完成（库 %s）：" % DB_NAME)
        for model in (Category, Course, PageConfig, QuestionBank, Question,
                      MemoryCard, Order, Coupon, UserCourse):
            n = (await db.execute(select(func.count()).select_from(model))).scalar()
            print("  %-16s %d 行" % (model.__tablename__, n))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
