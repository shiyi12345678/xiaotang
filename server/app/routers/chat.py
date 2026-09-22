"""沟通域接口（求职者 ↔ 企业 HR 的会话与消息）。

路由前缀：/api/v1/chat
    全部需要登录：conversations（会话列表 / 发起沟通）、messages（读消息 / 发消息）、
                  read（清零未读）、unread（两个身份的未读合计，角标用）

⚠️ 安全约定（与 mine / job / apply 域一致）：
    每条查询都带 candidate_id == user.id 或 hr_id == user.id，
    role 参数只决定「按哪一列过滤」，uid 一律取自 token、绝不接受客户端传入；
    因此既读不到别人的会话，也发不出冒充别人的消息。

⚠️ 会话行与消息行是两套数据，必须同步维护：
    发消息时除了插入 message，还要回写会话行的 last_message / last_time / 未读数，
    会话列表才能不扫 message 表直接渲染（这是列表页性能的关键）。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import Company, Conversation, Message, User, UserRole
# 复用「职位不存在 / 已下线」的 404 语义：与 apply 域同一口径，避免两处实现不一致
from app.routers.job import _job_or_404
from app.schemas.chat import (
    LAST_MESSAGE_LEN,
    MAX_CONTENT_LEN,
    ROLE_CANDIDATE,
    ROLE_HR,
    VALID_MSG_TYPES,
    VALID_ROLES,
    ConversationIn,
    MessageIn,
    conversation_out,
    message_out,
    other_role,
)

router = APIRouter(prefix="/api/v1/chat", tags=["沟通"])
logger = logging.getLogger(__name__)


# ==========================================================
# 内部小工具
# ==========================================================


async def _conversation_and_role(
    db: AsyncSession, conversation_id: int, user: User
) -> tuple[Conversation, str]:
    """取会话并判定调用方在该会话里的角色。

    ⚠️ 角色由会话行的双方 id 与 token 里的 uid 比对得出，不看任何入参：
       非参与者一律 403，这是聊天数据唯一的边界，不能只在前端隐藏入口。
    """
    row = await db.get(Conversation, conversation_id)
    if row is None:
        raise BizError(40403, "会话不存在", http=404)
    if row.candidate_id == user.id:
        return row, ROLE_CANDIDATE
    if row.hr_id == user.id:
        return row, ROLE_HR
    raise BizError(40302, "无权查看该会话", http=403)


async def _resolve_hr_id(db: AsyncSession, job) -> int:
    """解析职位的招聘者 user_id。

    ⚠️ 两道兜底的原因：灌库的演示职位大多没有填 job.hr_id，
       若不兜底，求职者从职位详情页点「立即沟通」会直接失败，演示链路断掉；
       因此 hr_id 为空时，退回「该公司下任意一个 HR 角色」。
    """
    if job.hr_id:
        return job.hr_id

    hr_user_id = (
        await db.execute(
            select(UserRole.user_id)
            .where(UserRole.role == ROLE_HR, UserRole.company_id == job.company_id)
            # 同一公司可能配了多位 HR，取最早建的那位，保证结果稳定可复现
            .order_by(UserRole.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if hr_user_id is None:
        raise BizError(40904, "该职位暂未配置招聘者，无法发起沟通", http=409)
    return hr_user_id


async def _nicknames(db: AsyncSession, ids) -> dict:
    """按 id 批量取昵称：{user_id: nickname}。

    ⚠️ 必须一次 IN 查出来：会话列表每页 20 条，
       在循环里逐条查昵称就是典型的 N+1（20 条会话要发 21 次查询）。
    """
    wanted = {int(i) for i in ids if i}
    if not wanted:
        return {}
    rows = (
        await db.execute(select(User.id, User.nickname).where(User.id.in_(wanted)))
    ).all()
    return {uid: nickname for uid, nickname in rows}


# ==========================================================
# 会话
# ==========================================================


@router.get("/conversations", summary="我的会话列表")
async def list_conversations(
    role: str = Query(ROLE_CANDIDATE, description="身份 candidate=求职者 / hr=企业HR"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话列表：同一个接口按 role 服务求职者端与企业端两套页面。"""
    if role not in VALID_ROLES:
        raise BizError(40001, "身份参数不合法")

    # 两个身份用同一张表的两列过滤，条件写法完全对称
    if role == ROLE_CANDIDATE:
        conditions = [
            Conversation.candidate_id == user.id,
            # 该侧「已删除」的会话不再出现在列表里（发新消息时会复位为 0）
            Conversation.candidate_deleted == 0,
        ]
    else:
        conditions = [
            Conversation.hr_id == user.id,
            Conversation.hr_deleted == 0,
        ]

    total = (
        await db.execute(select(func.count()).select_from(Conversation).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Conversation)
            .where(*conditions)
            # ⚠️ 排序显式带上「last_time IS NULL」这一列，不能只靠 DESC：
            #    各数据库对 NULL 的排序默认值不同（MySQL 的 DESC 把 NULL 放最后、
            #    PostgreSQL 放最前），显式升序排「是否为空」才能让
            #    「刚发起、还没聊过」的会话稳定排在最后。
            .order_by(
                Conversation.last_time.is_(None),
                Conversation.last_time.desc(),
                Conversation.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # 对方昵称：role=candidate 时对方是 HR，role=hr 时对方是候选人
    names = await _nicknames(
        db,
        [row.hr_id if role == ROLE_CANDIDATE else row.candidate_id for row in rows],
    )

    items = []
    for row in rows:
        other_id = row.hr_id if role == ROLE_CANDIDATE else row.candidate_id
        items.append(conversation_out(row, role, names.get(other_id, ""), other_id))

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })


@router.post("/conversations", summary="发起沟通")
async def create_conversation(
    payload: ConversationIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职者从职位详情页发起沟通。

    幂等语义：同一「职位 + 求职者 + HR」三元组已存在时直接返回原会话，
    并用 created=false 告知前端，而不是报错或再建一条（表上也有唯一约束兜底）。
    """
    job = await _job_or_404(db, payload.job_id)
    hr_id = await _resolve_hr_id(db, job)

    if hr_id == user.id:
        raise BizError(40905, "不能和自己发起沟通", http=409)

    exists = (
        await db.execute(
            select(Conversation).where(
                Conversation.job_id == job.id,
                Conversation.candidate_id == user.id,
                Conversation.hr_id == hr_id,
            )
        )
    ).scalar_one_or_none()

    names = await _nicknames(db, [hr_id])
    if exists is not None:
        return ok({
            "conversation": conversation_out(exists, ROLE_CANDIDATE, names.get(hr_id, ""), hr_id),
            "created": False,
        })

    company = await db.get(Company, job.company_id) if job.company_id else None
    row = Conversation(
        job_id=job.id,
        candidate_id=user.id,
        hr_id=hr_id,
        company_id=job.company_id,
        # 快照：职位改名/公司改名后，会话列表仍能显示当时聊的是哪个岗位
        job_title=job.title,
        company_name=(company.short_name or company.name) if company else "",
        last_message="",
        last_time=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        "[chat] uid=%s 发起沟通 job=%s hr=%s conversation=%s", user.id, job.id, hr_id, row.id
    )
    return ok({
        "conversation": conversation_out(row, ROLE_CANDIDATE, names.get(hr_id, ""), hr_id),
        "created": True,
    })


# ==========================================================
# 消息
# ==========================================================


@router.get("/conversations/{conversation_id}/messages", summary="会话消息（分页）")
async def list_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=50, alias="pageSize"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话内的消息，按时间正序返回。"""
    row, role = await _conversation_and_role(db, conversation_id, user)

    total = (
        await db.execute(
            select(func.count()).select_from(Message).where(Message.conversation_id == row.id)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == row.id)
            # ⚠️ 「倒序取、正序返」：聊天页是从最新往前翻历史，
            #    分页必须按「最新优先」取（否则第 2 页会取到更早的消息而不是更早的历史，
            #    新消息进来后还会整页错位），取完再反转成正序交给前端渲染。
            .order_by(Message.created_at.desc(), Message.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [message_out(m, role) for m in reversed(list(rows))]

    return ok({
        "list": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
        "role": role,
    })


@router.post("/conversations/{conversation_id}/messages", summary="发送消息")
async def send_message(
    conversation_id: int,
    payload: MessageIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发消息：插一行 message，并同步回写会话行的摘要、时间与对方未读数。"""
    row, role = await _conversation_and_role(db, conversation_id, user)

    content = (payload.content or "").strip()
    if not content:
        raise BizError(40002, "消息内容不能为空")
    if len(content) > MAX_CONTENT_LEN:
        raise BizError(40002, f"消息内容不能超过 {MAX_CONTENT_LEN} 字")

    msg_type = payload.msg_type or "text"
    if msg_type not in VALID_MSG_TYPES:
        raise BizError(40003, "参数不合法")

    msg = Message(
        conversation_id=row.id,
        sender_role=role,
        sender_id=user.id,
        msg_type=msg_type,
        content=content,
        is_read=0,
    )
    db.add(msg)

    # 会话行冗余字段同步（会话列表直出这些字段，不扫 message 表）
    row.last_message = content[:LAST_MESSAGE_LEN]
    row.last_time = datetime.now()
    if role == ROLE_CANDIDATE:
        # 只有「对方」那一侧未读 +1：自己发出去的消息自己当然是已读的
        row.unread_hr = (row.unread_hr or 0) + 1
        row.candidate_deleted = 0
    else:
        row.unread_candidate = (row.unread_candidate or 0) + 1
        row.hr_deleted = 0

    await db.commit()
    await db.refresh(msg)

    logger.info(
        "[chat] uid=%s role=%s 发送消息 conversation=%s msg=%s", user.id, role, row.id, msg.id
    )
    return ok({"message": message_out(msg, role)})


@router.post("/conversations/{conversation_id}/read", summary="标记会话已读")
async def read_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把当前角色那一侧的未读数清零，并把对方发来的消息置为已读。"""
    row, role = await _conversation_and_role(db, conversation_id, user)

    if role == ROLE_CANDIDATE:
        row.unread_candidate = 0
    else:
        row.unread_hr = 0

    # 只改「对方发的 + 还没读的」：带上 is_read == 0 是为了少写无谓的行
    await db.execute(
        update(Message)
        .where(
            Message.conversation_id == row.id,
            Message.sender_role == other_role(role),
            Message.is_read == 0,
        )
        .values(is_read=1)
    )
    await db.commit()

    logger.info("[chat] uid=%s 已读会话 conversation=%s", user.id, row.id)
    return ok({"unread": 0})


@router.get("/unread", summary="未读消息合计（角标）")
async def unread_total(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一次给出两个身份的未读合计，页面切换身份时不必再发请求。

    ⚠️ 口径必须与会话列表一致：两边都只统计未删除的会话，
       否则角标会比列表里实际能看到的多，用户点进去找不到。
    """
    candidate = (
        await db.execute(
            select(func.coalesce(func.sum(Conversation.unread_candidate), 0)).where(
                Conversation.candidate_id == user.id,
                Conversation.candidate_deleted == 0,
            )
        )
    ).scalar() or 0

    hr = (
        await db.execute(
            select(func.coalesce(func.sum(Conversation.unread_hr), 0)).where(
                Conversation.hr_id == user.id,
                Conversation.hr_deleted == 0,
            )
        )
    ).scalar() or 0

    return ok({"candidate": int(candidate), "hr": int(hr)})
