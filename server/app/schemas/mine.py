"""「我的」域出入参与 ORM→前端字段映射。

字段名同样对齐 common/mock/index.js：
    orderList  → {id,title,price,status,date,type}
    couponList → {id,amount,threshold,scope,expire,status}
    myCourses  → {id,title,progress,teacher,lastLesson}（外挂 kind 区分 learning/finished/collect）

⚠️ 入参统一用 snake_case（与既有 /user/password 的 old_password/new_password 一致），
   同时通过 populate_by_name 兼容 camelCase 写法（courseId），
   这样客户端无论按哪种风格传都能通，减少一次联调往返。
"""
from pydantic import BaseModel, ConfigDict, Field

from app.models import Coupon, Order, UserCourse
from app.schemas.content import num

# 订单状态词表（与 mock 的 orderList 保持一致）
ORDER_STATUS_UNPAID = "待付款"
ORDER_STATUS_DONE = "已完成"
ORDER_STATUS_CANCELED = "已取消"
ORDER_STATUS_REFUNDED = "已退款"

# user_course.kind 取值
COURSE_KINDS = ("learning", "finished", "collect")


def order_out(row: Order) -> dict:
    """订单 → mock orderList 元素的形状。"""
    return {
        "id": row.id,
        "title": row.title,
        "price": num(row.price),
        "status": row.status,
        "date": row.date,
        "type": row.type,
    }


def coupon_out(row: Coupon) -> dict:
    """优惠券 → mock couponList 元素的形状。"""
    return {
        "id": row.id,
        "amount": row.amount,
        "threshold": row.threshold,
        "scope": row.scope,
        "expire": row.expire,
        "status": row.status,
    }


def user_course_out(row: UserCourse) -> dict:
    """我的课程/收藏记录 → mock myCourses 元素的形状（另附 kind）。"""
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "teacher": row.teacher,
        "progress": row.progress,
        "lastLesson": row.last_lesson,
    }


class CreateOrderIn(BaseModel):
    """下单入参：只需课程ID，标题与价格由服务端从课程行取（不信任客户端报价）。"""

    model_config = ConfigDict(populate_by_name=True)

    course_id: str = Field(alias="courseId")


class AddCourseIn(BaseModel):
    """加入我的课程 / 收藏。"""

    model_config = ConfigDict(populate_by_name=True)

    course_id: str = Field(alias="courseId")
    kind: str = "collect"          # collect=收藏 / learning=在学；非法值由路由层校验


class ProgressIn(BaseModel):
    """学习进度上报。"""

    model_config = ConfigDict(populate_by_name=True)

    progress: int
    last_lesson: str | None = Field(default=None, alias="lastLesson")
