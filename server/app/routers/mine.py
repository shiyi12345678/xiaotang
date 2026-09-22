"""「我的」域路由：前缀 /api/v1/mine （**全部需要登录**）。

端点总表（🔒 全部需 `Authorization: Bearer <token>`）：
    GET    /orders                订单列表（?status= 过滤）
    POST   /orders                下单（报名课程）
    POST   /orders/{id}/pay       支付：待付款 → 已完成
    POST   /orders/{id}/cancel    取消：待付款 → 已取消
    DELETE /orders/{id}           删除订单（物理删除）
    GET    /coupons               优惠券列表（?status= 过滤）
    GET    /courses               我的课程（?kind=learning|finished|collect）
    POST   /courses               加入我的课程 / 收藏（幂等 upsert）
    DELETE /courses/{id}          移出我的课程 / 取消收藏
    PUT    /courses/{id}/progress 上报学习进度
    GET    /stats                 四宫格计数（真实数据）

本模块错误码：
    43001 订单不存在或无权访问
    43002 订单状态不允许此操作
    43003 课程不存在
    43004 学习记录不存在或无权访问
    43005 参数不合法

⚠️ uid 一律取自 token（get_current_user），**绝不接受客户端传 uid**：
   「我的」域的每条查询都带 `uid == user.id`，因此天然不可能读到或改到别人的数据。
   对不属于自己的 id 一律返回「不存在或无权访问」，不区分「不存在」与「不是你的」，
   避免通过错误文案探测他人数据是否存在。

⚠️ user_course 表没有 course_id 列（本期不加字段、不 ALTER 既有表），
   所以「我的课程」的一条记录用它**自己的 id** 作为标识，
   与课程行的关联靠 (uid, kind, title) 去重。这条约束在下面两个写接口里都体现：
   POST /courses 传的是 course_id（用来从课程行复制标题/讲师），
   DELETE /courses/{id} 与 PUT /courses/{id}/progress 传的是**记录 id**。
"""
import logging
import random
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import Coupon, Course, Order, User, UserCourse
from app.schemas.mine import (
    COURSE_KINDS,
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_DONE,
    ORDER_STATUS_UNPAID,
    AddCourseIn,
    CreateOrderIn,
    ProgressIn,
    coupon_out,
    order_out,
    user_course_out,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mine", tags=["我的"])

# 四宫格的键/文案/跳转，与 mock 的 mineStats 完全一致（value 换成真实计数）
MINE_STAT_ITEMS = (
    ("course", "我的课程", "/pages/mine/my-course"),
    ("collect", "我的收藏", "/pages/mine/my-course?tab=collect"),
    ("coupon", "优惠券", "/pages/mine/mine"),
    ("points", "积分", "/pages/mine/mine"),
)


def _new_order_id() -> str:
    """生成订单号：od + 年月日时分秒 + 3 位随机数（22 位以内，不超 String(32)）。

    ⚠️ 不依赖自增主键：order_info.id 是字符串主键，演示环境用「时间 + 随机」
       已经不会撞；真接支付时需要换成支付网关的商户单号。
    """
    return "od%s%03d" % (datetime.now().strftime("%y%m%d%H%M%S"), random.randint(0, 999))


def _new_user_course_id() -> str:
    """生成我的课程记录 id。"""
    return "uc%s%03d" % (datetime.now().strftime("%y%m%d%H%M%S"), random.randint(0, 999))


async def _own_order(db: AsyncSession, uid: int, order_id: str) -> Order:
    """取本人订单；不存在或不属于本人 → 43001。"""
    row = (
        await db.execute(
            select(Order).where(Order.id == order_id, Order.uid == uid)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(43001, "订单不存在或无权访问")
    return row


async def _own_user_course(db: AsyncSession, uid: int, record_id: str) -> UserCourse:
    """取本人的「我的课程/收藏」记录；不存在或不属于本人 → 43004。"""
    row = (
        await db.execute(
            select(UserCourse).where(UserCourse.id == record_id, UserCourse.uid == uid)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(43004, "学习记录不存在或无权访问")
    return row


async def _course_or_404(db: AsyncSession, course_id: str) -> Course:
    """按 id 取课程；不存在 → 43003。"""
    row = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if row is None:
        raise BizError(43003, "课程不存在：%s" % course_id)
    return row


# ==========================================================
# 订单
# ==========================================================


@router.get("/orders", summary="订单列表")
async def list_orders(
    status: str | None = Query(None, description="按状态过滤，如 待付款/已完成/已取消/已退款"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本人订单列表，按 sort_order 升序（与 mock orderList 的顺序口径一致）。"""
    stmt = select(Order).where(Order.uid == user.id)
    if status:
        stmt = stmt.where(Order.status == status)
    rows = (
        await db.execute(stmt.order_by(Order.sort_order.asc(), Order.id.asc()))
    ).scalars().all()
    return ok({"list": [order_out(row) for row in rows]})


@router.post("/orders", summary="下单（报名课程）")
async def create_order(
    body: CreateOrderIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为某门课创建订单。

    请求：{"course_id": "c1001"}（也接受 {"courseId": "c1001"}）
    响应：{order: {...新增的订单...}, duplicated: bool}

    ⚠️ 标题与价格一律从 course 行读取，**不采信客户端传来的金额**（防篡改报价）。
    ⚠️ 幂等：同一门课若已有「待付款」或「已完成」的订单，直接返回那张单
       （duplicated=true），不会重复下单。
    ⚠️ 只支持课程报名；mock 里的 VIP 订单（type=vip）没有对应的商品表，
       因此 POST /orders 不提供 type 参数（不下单不编造）。
    """
    course = await _course_or_404(db, body.course_id)

    existing = (
        await db.execute(
            select(Order)
            .where(
                Order.uid == user.id,
                Order.title == course.title,
                Order.status.in_((ORDER_STATUS_UNPAID, ORDER_STATUS_DONE)),
            )
            .order_by(Order.sort_order.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return ok({"order": order_out(existing), "duplicated": True})

    max_sort = (
        await db.execute(
            select(func.max(Order.sort_order)).where(Order.uid == user.id)
        )
    ).scalar()
    order = Order(
        id=_new_order_id(),
        uid=user.id,
        title=course.title,
        price=course.price,
        status=ORDER_STATUS_UNPAID,
        date=datetime.now().strftime("%Y-%m-%d"),
        type="course",
        sort_order=(int(max_sort) + 1) if max_sort is not None else 0,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    logger.info("[mine.order] uid=%s 下单成功 order=%s course=%s", user.id, order.id, course.id)
    return ok({"order": order_out(order), "duplicated": False})


@router.post("/orders/{order_id}/pay", summary="支付订单")
async def pay_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """待付款 → 已完成（真实落库，不再是本地 toast）。

    ⚠️ 已完成的订单重复支付：直接返回当前状态（幂等，不报错）。
       其它状态（已取消/已退款）→ 43002。
    """
    order = await _own_order(db, user.id, order_id)
    if order.status == ORDER_STATUS_DONE:
        return ok({"order": order_out(order), "changed": False})
    if order.status != ORDER_STATUS_UNPAID:
        raise BizError(43002, "当前状态（%s）不支持支付" % order.status)

    order.status = ORDER_STATUS_DONE
    await db.commit()
    await db.refresh(order)
    logger.info("[mine.order] uid=%s 支付成功 order=%s", user.id, order.id)
    return ok({"order": order_out(order), "changed": True})


@router.post("/orders/{order_id}/cancel", summary="取消订单")
async def cancel_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """待付款 → 已取消。

    ⚠️ 已取消的订单重复取消：直接返回当前状态（幂等）。
       已完成/已退款 → 43002（已完成的订单请走退款流程，本期没做）。
    ⚠️ 「已取消」是本期新增的状态值：mock 的订单词表里只有
       待付款/已完成/已退款，没有「取消」。客户端订单页的筛选 tab
       需要相应加一个「已取消」，否则取消后的订单在筛选视图里看不见。
    """
    order = await _own_order(db, user.id, order_id)
    if order.status == ORDER_STATUS_CANCELED:
        return ok({"order": order_out(order), "changed": False})
    if order.status != ORDER_STATUS_UNPAID:
        raise BizError(43002, "当前状态（%s）不支持取消" % order.status)

    order.status = ORDER_STATUS_CANCELED
    await db.commit()
    await db.refresh(order)
    logger.info("[mine.order] uid=%s 已取消 order=%s", user.id, order.id)
    return ok({"order": order_out(order), "changed": True})


@router.delete("/orders/{order_id}", summary="删除订单")
async def delete_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """物理删除本人订单。

    ⚠️ 订单不做逻辑删除：与「账号可追溯」不同，订单只是用户自己的消费记录副本，
       删了就删了（与 ai_session 的策略一致）。真要留痕应另建归档表。
    """
    order = await _own_order(db, user.id, order_id)
    await db.execute(delete(Order).where(Order.id == order.id, Order.uid == user.id))
    await db.commit()
    logger.info("[mine.order] uid=%s 已删除 order=%s", user.id, order_id)
    return ok({"id": order_id, "deleted": True})


# ==========================================================
# 优惠券
# ==========================================================


@router.get("/coupons", summary="优惠券列表")
async def list_coupons(
    status: str | None = Query(None, description="unused=可用 / expired=已过期；不传则全给"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本人优惠券。

    ⚠️ 只读：领券、核销需要营销域（发券规则/门槛校验/订单抵扣），本期没做，
       因此没有 POST/DELETE 券的接口——不做半套写入。
    """
    stmt = select(Coupon).where(Coupon.uid == user.id)
    if status:
        stmt = stmt.where(Coupon.status == status)
    rows = (
        await db.execute(stmt.order_by(Coupon.sort_order.asc(), Coupon.id.asc()))
    ).scalars().all()
    return ok({"list": [coupon_out(row) for row in rows]})


# ==========================================================
# 我的课程 / 收藏
# ==========================================================


@router.get("/courses", summary="我的课程 / 收藏")
async def list_my_courses(
    kind: str | None = Query(None, description="learning=在学 / finished=已学完 / collect=收藏"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """本人课程记录（字段与 mock myCourses 元素一致：id/title/teacher/progress/lastLesson）。"""
    if kind and kind not in COURSE_KINDS:
        raise BizError(43005, "kind 只能是 %s" % "/".join(COURSE_KINDS))
    stmt = select(UserCourse).where(UserCourse.uid == user.id)
    if kind:
        stmt = stmt.where(UserCourse.kind == kind)
    rows = (
        await db.execute(stmt.order_by(UserCourse.sort_order.asc(), UserCourse.id.asc()))
    ).scalars().all()
    return ok({"list": [user_course_out(row) for row in rows]})


@router.post("/courses", summary="加入我的课程 / 收藏")
async def add_my_course(
    body: AddCourseIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把课程加入「我的课程（learning）」或「我的收藏（collect）」。

    请求：{"course_id": "c1001", "kind": "collect"}（kind 省略时默认 collect）
    响应：{record: {...}, created: bool}

    ⚠️ 幂等：同一用户、同一 kind、同一标题的记录只会有一条，
       重复调用返回已有记录（created=false），不会产生重复行。
    ⚠️ 去重键是 (uid, kind, title) 而不是 course_id —— 因为 user_course
       表没有 course_id 列（本期不 ALTER 既有表）。副作用：库里两门**同名**课程
       会被视为同一门。种子数据里标题唯一，暂无影响；要根治需要给表加 course_id。
    """
    if body.kind not in ("collect", "learning"):
        raise BizError(43005, "kind 只能是 collect 或 learning")
    course = await _course_or_404(db, body.course_id)

    existing = (
        await db.execute(
            select(UserCourse)
            .where(
                UserCourse.uid == user.id,
                UserCourse.kind == body.kind,
                UserCourse.title == course.title,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return ok({"record": user_course_out(existing), "created": False})

    max_sort = (
        await db.execute(
            select(func.max(UserCourse.sort_order)).where(UserCourse.uid == user.id)
        )
    ).scalar()
    record = UserCourse(
        id=_new_user_course_id(),
        uid=user.id,
        kind=body.kind,
        title=course.title,
        teacher=course.teacher,
        progress=0,
        last_lesson="",
        sort_order=(int(max_sort) + 1) if max_sort is not None else 0,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(
        "[mine.course] uid=%s 新增 %s 记录 id=%s course=%s",
        user.id, body.kind, record.id, course.id,
    )
    return ok({"record": user_course_out(record), "created": True})


@router.delete("/courses/{record_id}", summary="移出我的课程 / 取消收藏")
async def remove_my_course(
    record_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除本人的一条课程记录（{record_id} 是 GET /courses 返回的 id）。"""
    record = await _own_user_course(db, user.id, record_id)
    await db.execute(
        delete(UserCourse).where(UserCourse.id == record.id, UserCourse.uid == user.id)
    )
    await db.commit()
    logger.info("[mine.course] uid=%s 已删除记录 id=%s", user.id, record_id)
    return ok({"id": record_id, "deleted": True})


@router.put("/courses/{record_id}/progress", summary="上报学习进度")
async def update_progress(
    record_id: str,
    body: ProgressIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新学习进度与「最近学到哪一讲」。

    请求：{"progress": 62, "lastLesson": "第 42 讲 · 用 Agent 自动化周报"}
         （lastLesson 可省，省略则不改）

    ⚠️ 进度到 100 时自动把 kind 从 learning 变成 finished（对应「已学完」tab）；
       从 100 降回 <100 时自动变回 learning。收藏（collect）记录不参与这个自动流转，
       否则一次进度上报会把用户的收藏从收藏夹里挪走。
    """
    if body.progress < 0 or body.progress > 100:
        raise BizError(43005, "progress 必须在 0~100 之间")

    record = await _own_user_course(db, user.id, record_id)
    record.progress = int(body.progress)
    if body.last_lesson is not None:
        record.last_lesson = body.last_lesson.strip()

    if record.kind in ("learning", "finished"):
        record.kind = "finished" if record.progress >= 100 else "learning"

    await db.commit()
    await db.refresh(record)
    return ok({"record": user_course_out(record)})


# ==========================================================
# 四宫格计数
# ==========================================================


@router.get("/stats", summary="我的统计（四宫格）")
async def my_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """四宫格计数。

    返回结构与 mock 的 mineStats **完全同构**（[{key,label,value,path}]），
    只是 value 换成真实计数：
        course  在学 + 已学完的记录数
        collect 收藏记录数
        coupon  可用（status=unused）优惠券数
        points  用户积分（user.points，真实列）
    """
    course_count = (
        await db.execute(
            select(func.count()).select_from(UserCourse).where(
                UserCourse.uid == user.id, UserCourse.kind.in_(("learning", "finished"))
            )
        )
    ).scalar() or 0
    collect_count = (
        await db.execute(
            select(func.count()).select_from(UserCourse).where(
                UserCourse.uid == user.id, UserCourse.kind == "collect"
            )
        )
    ).scalar() or 0
    coupon_count = (
        await db.execute(
            select(func.count()).select_from(Coupon).where(
                Coupon.uid == user.id, Coupon.status == "unused"
            )
        )
    ).scalar() or 0

    values = {
        "course": int(course_count),
        "collect": int(collect_count),
        "coupon": int(coupon_count),
        "points": int(user.points or 0),
    }
    return ok({
        "list": [
            {"key": key, "label": label, "value": values[key], "path": path}
            for key, label, path in MINE_STAT_ITEMS
        ]
    })
