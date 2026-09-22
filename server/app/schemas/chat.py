"""招聘域 · 沟通（会话 / 消息）的出入参与字段映射。

⚠️ 字段命名纪律（与 schemas/job.py、schemas/apply.py 一致）：
    数据库列是 snake_case，转换只在本层做一次，映射出来的键一律 camelCase；
    路由层不再自己拼字段，前端页面也不需要做字段名转换。

⚠️ 两个「按身份算出来」的字段放在本层，而不是让两端各自判断：
    - conversation.unread：会话行同时存了 unread_candidate / unread_hr 两个计数，
      到底给哪一个，取决于调用方这次是以求职者还是 HR 的身份在看列表；
    - message.mine：前端渲染左右气泡只需判断「这条是不是我发的」，
      比较 sender_role 与调用方角色这件事只应有一份实现。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Conversation, Message
from app.schemas.job import relative_time

# 会话参与者角色（与 message.sender_role 的取值、conversation 的双方字段一一对应）
ROLE_CANDIDATE = "candidate"
ROLE_HR = "hr"
VALID_ROLES = (ROLE_CANDIDATE, ROLE_HR)

# 允许发送的消息类型（与 message.msg_type 的注释一致）
VALID_MSG_TYPES = ("text", "invite", "resume", "system")

# 单条消息长度上限（业务校验放路由层，见 MessageIn 的说明）
MAX_CONTENT_LEN = 500

# 会话行 last_message 是 String(200)，但列表里只显示一行，
# 截前 50 字足够展示，也避免把长消息整段冗余进会话行
LAST_MESSAGE_LEN = 50


def other_role(role: str) -> str:
    """会话里的另一方角色。

    未读数 +1、「把对方的消息置为已读」都是按「对方那一侧」处理的，
    这个映射只写一次，避免各处自己写 if role == "candidate"。
    """
    return ROLE_HR if role == ROLE_CANDIDATE else ROLE_CANDIDATE


def _time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def conversation_out(
    row: Conversation,
    role: str,
    contact_name: str = "",
    contact_id: int | None = None,
) -> dict:
    """会话 → 会话列表项。

    ⚠️ contactName / contactId 需要查 user 表（会话行里只有双方 id、没有昵称），
       由路由层**一次批量**查好后传进来，本层只负责放字段、绝不查库。
    """
    unread = row.unread_candidate if role == ROLE_CANDIDATE else row.unread_hr
    return {
        "id": row.id,
        "jobId": row.job_id,
        "jobTitle": row.job_title,
        "companyId": row.company_id,
        "companyName": row.company_name,
        # 会话行冗余的最后一条消息摘要：会话列表因此不必扫 message 表
        "lastMessage": row.last_message or "",
        "lastTime": _time_text(row.last_time),
        # 相对时间（刚刚 / 3小时前 / 2026-08-01），与职位列表同口径
        "lastText": relative_time(row.last_time),
        "unread": int(unread or 0),
        "role": role,
        # 对方（role=candidate 时是 HR，role=hr 时是候选人）
        "contactId": int(contact_id or 0),
        "contactName": contact_name or "",
    }


def message_out(row: Message, role: str) -> dict:
    """消息 → 聊天页消息项。

    ⚠️ mine 由 sender_role 与调用方角色比较得出：
       system 消息（sender_role="system"）对两边都是 False，
       前端据此渲染成居中的系统提示，而不是某一侧的气泡。
    """
    return {
        "id": row.id,
        "conversationId": row.conversation_id,
        "senderRole": row.sender_role,
        "senderId": int(row.sender_id or 0),
        "content": row.content or "",
        "msgType": row.msg_type,
        "extra": row.extra or {},
        "isRead": bool(row.is_read),
        "createdAt": _time_text(row.created_at),
        "timeText": relative_time(row.created_at),
        "mine": row.sender_role == role,
    }


# ==========================================================
# 请求体
# ==========================================================


class ConversationIn(BaseModel):
    """发起沟通入参。

    ⚠️ 只收 jobId：求职者只能是 token 里的当前用户，HR 由服务端按职位解析，
       客户端无权指定「跟谁聊」，否则可以凭空造出与任意 HR 的会话行。
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId", min_length=1, max_length=32)


class MessageIn(BaseModel):
    """发送消息入参。

    ⚠️ content 的「非空 + 500 字上限」刻意不写进 Field：
       框架校验失败会被 main.py 归一成 50000「服务器开小差了」，
       前端拿不到「消息内容不能为空」这种可展示的提示；
       业务校验统一放路由层，返回 40002 / 40003。
    """

    model_config = ConfigDict(populate_by_name=True)

    content: str = Field(default="")
    msg_type: str = Field(default="text", alias="msgType")
