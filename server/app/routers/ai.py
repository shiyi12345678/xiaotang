"""AI 助教路由：前缀 /api/v1/ai。

端点总表（🔒 = 需登录）：
    GET    /sessions                 会话列表          🔒
    GET    /sessions/{sid}/messages  会话全部消息      🔒
    DELETE /sessions/{sid}           删除会话          🔒
    GET    /rag/status               RAG 知识库状态    🔒（只读诊断）
    POST   /rag/warmup               预热向量/精排模型  🔒
    GET    /graph/status             GraphRAG 图谱状态  🔒（只读诊断）
    GET    /graph/search             图谱检索调试      🔒（只读诊断）
    WS     /chat?token=<JWT>         流式对话（WebSocket）

WebSocket 帧契约（2026-09 新增 images 字段，完全向后兼容）：
    客户端 → 服务端
        { "type": "chat", "content": "问题", "session_id": "会话ID(可省)",
          "images": ["上传返回的附件id或url", ...] }   images 可省，省了行为与改造前一致
        { "type": "stop" }                       中途停止本轮生成
    服务端 → 客户端
        { "type": "session", "session_id": "...", "title": "..." }  懒建会话回传
        { "type": "delta",   "content": "增量文本" }                流式增量
        { "type": "done" }                                          正常结束
        { "type": "error",   "code": 41006, "msg": "..." }          出错

    ⚠️ 服务端 → 客户端的四种帧形态与改造前完全一致（未新增任何帧类型）：
       images 只影响「用户消息挂了哪些图」与「发给模型的 content 长什么样」。

AI 域错误码：
    41001 消息内容为空
    41002 会话不存在或无权访问
    41006 模型服务不可用
    41007 生成超时或已取消
    41008 参数不合法
    41009 图片格式不支持（非 jpg/jpeg/png/webp/gif，或文件头不是图片）
    41010 图片过大（超过 AI_UPLOAD_MAX_MB）
    41011 未收到文件 / 文件内容为空
    40100~40102 鉴权失败（复用用户体系，失败时 close 4401）
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    AI_ROUNDS,
    AI_TIMEOUT,
    AI_VISION_MODEL,
    AI_WS_IDLE,
    RAG_ENABLED,
)
from app.core.llm import stream_chat
from app.core.response import BizError, ok
from app.core.security import get_current_user, get_user_by_token
from app.database import SessionLocal, get_db
from app.models import AiMessage, AiMessageImage, AiSession, User
from app.routers.ai_upload import (
    attach_images,
    build_vision_content,
    image_note,
    normalize_images,
    resolve_images,
    stream_vision,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助教"])


def _fmt(dt: datetime | None) -> str | None:
    """时间口径：统一输出 yyyy-MM-dd HH:mm:ss。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


async def _own_session(db: AsyncSession, uid: int, sid_raw: str) -> AiSession:
    """按用户归属取会话；不存在或非本人 → 41002。"""
    sid = int(sid_raw) if str(sid_raw).isdigit() else 0
    result = await db.execute(
        select(AiSession).where(AiSession.id == sid, AiSession.uid == uid)
    )
    s = result.scalar_one_or_none()
    if s is None:
        raise BizError(41002, "会话不存在或无权访问")
    return s


# ==========================================================
# HTTP：会话管理（均需登录）
# ==========================================================


@router.get("/sessions", summary="会话列表")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的会话列表，按最后活跃时间倒序。

    preview 取该会话的首条用户提问（截断 120 字），供列表展示。
    """
    rows = (
        await db.execute(
            select(AiSession)
            .where(AiSession.uid == user.id)
            .order_by(AiSession.updated_at.desc())
            .limit(100)
        )
    ).scalars().all()

    items = []
    for s in rows:
        first = (
            await db.execute(
                select(AiMessage.content)
                .where(AiMessage.session_id == s.id, AiMessage.role == "user")
                .order_by(AiMessage.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        items.append({
            "id": str(s.id),
            "title": s.title,
            "preview": (first or "")[:120],
            "updatedAt": _fmt(s.updated_at),
        })
    return ok({"list": items})


@router.get("/sessions/{sid}/messages", summary="会话消息列表")
async def session_messages(
    sid: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回指定会话的全部消息（按时间升序，最多最近 500 条）。

    ⚠️ 每条消息新增 images 字段（[{url, name}]，没图时为空数组），
       id / role / content / createdAt 四个既有字段的名称与含义均未改动，
       因此老客户端拿到的结构仍然兼容。
    """
    s = await _own_session(db, user.id, sid)
    rows = (
        await db.execute(
            select(AiMessage)
            .where(AiMessage.session_id == s.id)
            .order_by(AiMessage.id.desc())
            .limit(500)
        )
    ).scalars().all()

    ordered = list(reversed(rows))

    # 图片附件：一次查询取回本页所有消息的附件，避免每条消息各查一次（N+1）
    images_by_mid: dict = {}
    if ordered:
        img_rows = (
            await db.execute(
                select(AiMessageImage)
                .where(AiMessageImage.message_id.in_([m.id for m in ordered]))
                .order_by(AiMessageImage.message_id.asc(), AiMessageImage.sort_order.asc())
            )
        ).scalars().all()
        for img in img_rows:
            images_by_mid.setdefault(img.message_id, []).append(
                {"url": img.url, "name": img.name}
            )

    msgs = [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "createdAt": _fmt(m.created_at),
            "images": images_by_mid.get(m.id, []),
        }
        for m in ordered
    ]
    return ok({"list": msgs, "title": s.title})


@router.delete("/sessions/{sid}", summary="删除会话")
async def delete_session(
    sid: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除会话及其全部消息（物理删除，级联）。

    ⚠️ 若此时该会话有在途生成，收尾落库会因会话已不存在而跳过插入，不会报错。
    ⚠️ 图片附件随之删库：显式删 ai_message_image 而不只依赖外键的
       ON DELETE CASCADE，这样即使库里的外键没建成，也不会留下孤儿记录。
    ⚠️ 磁盘上的图片文件【不删】：同一张上传图可能被多条消息引用，
       直接 unlink 会打断其他消息的图片显示。孤儿文件由运维清理
       server/uploads/ai/，属已知取舍（见 README）。
    """
    s = await _own_session(db, user.id, sid)

    mids = (
        await db.execute(select(AiMessage.id).where(AiMessage.session_id == s.id))
    ).scalars().all()
    if mids:
        await db.execute(
            delete(AiMessageImage).where(AiMessageImage.message_id.in_(list(mids)))
        )

    await db.execute(delete(AiMessage).where(AiMessage.session_id == s.id))
    await db.execute(delete(AiSession).where(AiSession.id == s.id))
    await db.commit()
    return ok({})


# ==========================================================
# HTTP：RAG 知识库运维（新增，不改变任何既有接口行为）
# ==========================================================


@router.get("/rag/status", summary="RAG 知识库状态")
async def rag_status(user: User = Depends(get_current_user)):
    """返回知识库连通性、条数与模型配置，用于排查「AI 答不上来」的原因。

    典型用法：
        ok=false             → Milvus 没启动 / 地址端口不对
        count=0              → 连上了但没灌库，需跑 tools/rag_ingest.py
        rerank_enabled=true  → 精排模型已开启（首次检索会触发模型下载，较慢）

    ⚠️ 这是只读诊断接口：不发任何写操作，也不会触发模型下载
       （需要提前加载模型请调用 POST /rag/warmup）。
    """
    from app.config import (
        MILVUS_COLLECTION, RAG_EMBED_MODEL, RAG_ENABLED,
        RAG_RERANK_ENABLED, RAG_RERANK_THRESHOLD, RAG_TOP_K,
    )
    from app.core import milvus_store

    # 走线程池：Milvus 查询是同步阻塞调用，不能卡住事件循环
    info = await asyncio.to_thread(milvus_store.health)
    return ok({
        "enabled": RAG_ENABLED,
        "collection": MILVUS_COLLECTION,
        "embedModel": RAG_EMBED_MODEL,
        "topK": RAG_TOP_K,
        "rerankEnabled": RAG_RERANK_ENABLED,
        "rerankThreshold": RAG_RERANK_THRESHOLD,
        "milvus": info,
    })


@router.post("/rag/warmup", summary="预热 RAG 模型")
async def rag_warmup(user: User = Depends(get_current_user)):
    """主动加载向量化 / 精排模型。

    为什么要这个接口：模型首次使用要从 HuggingFace 下载（数百 MB ~ 1GB+），
    直接提问会卡住几分钟、客户端还以为服务挂了。运维时先打一次这个接口，
    后续对话就是秒级响应。

    ⚠️ 同步阻塞且耗时较长（可能数分钟），务必在部署阶段调用，不要放在对话链路里。
    """
    from app.core import embedding

    info = await asyncio.to_thread(embedding.warmup)
    if not info.get("embed_ok"):
        # 预热失败不改状态码语义，用业务错误码返回，便于前端提示
        raise BizError(41006, info.get("detail") or "模型预热失败")
    return ok(info)


# ==========================================================
# HTTP：GraphRAG 知识图谱运维（新增，不改变任何既有接口行为）
# ==========================================================


@router.get("/graph/status", summary="GraphRAG 知识图谱状态")
async def graph_status(user: User = Depends(get_current_user)):
    """返回图谱连通性、规模与检索参数，用于排查「图谱没生效」的原因。

    典型用法：
        neo4j.ok=false   → Neo4j 没启动 / 地址端口不对 / 密码不对（error 里有原因）
        nodes=0          → 连上了但没灌图，需跑 tools/graph_ingest.py
        entities=0       → 图里没有实体（只灌了知识块）
        relations=0      → 有实体但没有关系，检索只能返回实体属性

    ⚠️ 这是只读诊断接口：不做任何写操作，也不触发大模型调用。
    """
    from app.config import (
        GRAPH_ENABLED, GRAPH_MAX_HOPS, GRAPH_SEED_LIMIT, GRAPH_TOP_K,
        NEO4J_URI, NEO4J_USER,
    )
    from app.core import graph_store

    # 走线程池：Bolt 查询是同步阻塞调用，不能卡住事件循环
    info = await asyncio.to_thread(graph_store.health)
    return ok({
        "enabled": GRAPH_ENABLED,
        "uri": NEO4J_URI,
        "user": NEO4J_USER,
        "topK": GRAPH_TOP_K,
        "seedLimit": GRAPH_SEED_LIMIT,
        "maxHops": GRAPH_MAX_HOPS,
        "neo4j": info,
    })


@router.get("/graph/search", summary="图谱检索调试（只读）")
async def graph_search(
    q: str = Query(..., min_length=1, max_length=200, description="要试的问题"),
    user: User = Depends(get_current_user),
):
    """直接查看图谱检索对一个问题的效果：命中哪些实体、产出哪些事实。

    为什么需要它：图谱检索的效果（实体链接准不准、多跳有没有价值）
    光看日志不直观，这个接口把中间结果摊开，便于联调与答辩演示。

    ⚠️ 只读：只查询，不写入、不改动图谱。
    """
    from app.core import graph_rag

    result = await asyncio.to_thread(graph_rag.retrieve_graph, q)
    return ok({
        "query": q,
        "used": result.get("used"),
        "error": result.get("error"),
        "entities": result.get("entities"),
        "facts": [
            {"text": f.get("text"), "score": f.get("score"),
             "hop": f.get("hop"), "sources": f.get("sources")}
            for f in (result.get("facts") or [])
        ],
        "stats": result.get("stats"),
    })


# ==========================================================
# WebSocket：流式对话
# ==========================================================


async def _guard_send(ws: WebSocket, data: dict) -> None:
    """发送帧；连接已断开时静默忽略（断开状态由 receive 侧感知）。"""
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def _persist_answer(
    session_id: int, answer: str, db: AsyncSession | None = None
) -> None:
    """收尾落库：写入 assistant 回复并显式刷新会话活跃时间。

    参数：
        session_id: 会话ID
        answer:     已生成的正文（可能是不完整的半截内容）
        db:         可复用的会话；传 None 时自开短会话（断连兜底场景）

    ⚠️ 会话可能已被删除：此时直接跳过，不写入孤儿消息。
    ⚠️ 正文为空时不插入空消息行。
    ⚠️ MySQL 的 ON UPDATE 在同一秒内不触发，故这里显式刷新 updated_at。
    """

    async def _do(s: AsyncSession) -> None:
        sess = (
            await s.execute(select(AiSession).where(AiSession.id == session_id))
        ).scalar_one_or_none()
        if sess is None:
            return
        if answer:
            s.add(AiMessage(session_id=session_id, role="assistant", content=answer))
        sess.updated_at = datetime.now()
        await s.commit()

    try:
        if db is not None:
            await _do(db)
        else:
            async with SessionLocal() as s2:
                await _do(s2)
    except Exception:
        logger.exception("[ai.chat] 收尾落库失败 session=%s", session_id)


async def _inject_rag_context(history: list, content: str) -> bool:
    """检索知识库并把资料注入对话历史（RAG 增强）。

    参数：
        history: 待发送给大模型的消息列表（本函数会在开头插入一条 system 消息）
        content: 用户本轮提问
    返回：
        True = 本次注入了知识块；False = 未注入（无命中 / 已降级 / 已关闭）

    设计要点：
        - 【不改帧契约】通过新增 system 消息注入资料，不新增任何 WebSocket 帧，
          客户端无需改动；
        - 【绝不影响主链路】检索、向量化、精排任一环节失败都只记日志并返回 False，
          对话继续以「不带资料」的方式生成 —— RAG 是增强项，不是必需项；
        - 【不阻塞事件循环】检索是同步 CPU 推理，必须走线程池
          （app/core/rag.py 里的 retrieve_async 已用 asyncio.to_thread 包装）。
    """
    if not RAG_ENABLED:
        return False

    try:
        from app.core import rag

        result = await rag.retrieve_async(content)
        if not result.get("used"):
            logger.info("[ai.rag] 未检索到可用知识块：%s", result.get("error") or "无命中")
            return False

        prompt = rag.build_system_prompt(result["contexts"])
        if not prompt:
            return False

        # 插到最前面：先资料、后对话。注意 llm.stream_chat 还会在最前面
        # 再补一条「当前日期」的 system 消息，两条 system 并存是合法的。
        history.insert(0, {"role": "system", "content": prompt})

        logger.info(
            "[ai.rag] 注入 %d 条知识（向量=%s，图谱=%s，最高分=%.4f）",
            len(result["contexts"]), result.get("mode"), result.get("graphMode"),
            float(result["contexts"][0].get("score") or 0.0),
        )
        return True
    except Exception:
        # 兜底：RAG 出任何问题都不允许影响对话
        logger.exception("[ai.rag] 检索注入失败，本轮降级为普通对话")
        return False


async def _image_counts_for(db: AsyncSession, message_ids: list) -> dict:
    """批量查这些消息各挂了几张图，返回 {message_id: 张数}。

    用途：把历史轮次里「当时附带过图片」这件事重新写回提示词，
    否则第二轮之后模型就忘了前文有图，多轮上下文会断裂。
    ⚠️ 用一次 GROUP BY 查询取回全部计数，避免每条历史消息各查一次（N+1）。
    """
    if not message_ids:
        return {}
    rows = (
        await db.execute(
            select(AiMessageImage.message_id, func.count())
            .where(AiMessageImage.message_id.in_(message_ids))
            .group_by(AiMessageImage.message_id)
        )
    ).all()
    return {mid: int(cnt) for mid, cnt in rows}


async def _handle_chat(
    ws: WebSocket, uid: int, frame: dict, cancel: asyncio.Event
) -> None:
    """处理一轮生成。

    终止路径统一收尾（半截内容同样落库）：
        正常流尽 / stop / 抢占 / 断连 / 超时

    ⚠️ images 是可选增强：帧里没有该字段时，本函数的流程与改造前逐行一致。
    """
    text_chunks: list = []
    session_id = 0

    content = str(frame.get("content") or "").strip()
    sid_raw = str(frame.get("session_id") or "").strip()

    if not content:
        await _guard_send(ws, {"type": "error", "code": 41001, "msg": "消息内容不能为空"})
        return

    # 0) 图片附件（可选）：先规范化引用，再解析成真实文件。
    #    格式不对 / 引用了不存在的图 / 超过 AI_IMAGE_MAX_COUNT 的部分都只跳过并记日志，
    #    绝不因此中断整轮对话——图片是增强项，不能让它把主链路弄挂。
    images = resolve_images(normalize_images(frame.get("images")))

    async with SessionLocal() as db:
        # 1) 会话：无 session_id 则懒创建，否则做归属校验
        if sid_raw:
            session = (
                await db.execute(
                    select(AiSession).where(
                        AiSession.id == (int(sid_raw) if sid_raw.isdigit() else 0),
                        AiSession.uid == uid,
                    )
                )
            ).scalar_one_or_none()
            if session is None:
                await _guard_send(
                    ws, {"type": "error", "code": 41002, "msg": "会话不存在或无权访问"}
                )
                return
        else:
            session = AiSession(uid=uid, title=content[:30])
            db.add(session)
            await db.commit()
            await db.refresh(session)

        session_id = session.id

        # 2) 用户消息落库
        msg = AiMessage(session_id=session.id, role="user", content=content)
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        # 2.5) 图片附件落库（挂在上面这条用户消息上，顺序即客户端给的顺序）
        #      ⚠️ 没有图片时这一整段被跳过，行为与改造前一致。
        if images:
            await attach_images(db, msg.id, images)
            await db.commit()
            logger.info(
                "[ai.chat] 用户消息附带 %d 张图片 message=%s session=%s",
                len(images), msg.id, session.id,
            )

        if not sid_raw:
            # 懒建会话：先回 session 帧，客户端据此绑定会话 id 与标题
            await _guard_send(ws, {
                "type": "session",
                "session_id": str(session.id),
                "title": session.title,
            })

        # 3) 上下文滑动窗口：取当前提问之前最近 2*AI_ROUNDS 条
        rows = (
            await db.execute(
                select(AiMessage)
                .where(AiMessage.session_id == session.id, AiMessage.id < msg.id)
                .order_by(AiMessage.id.desc())
                .limit(AI_ROUNDS * 2)
            )
        ).scalars().all()

        # 历史里带过图的消息补回「附带 N 张图片」注记，保持多轮上下文连贯
        ordered = list(reversed(rows))
        note_counts = await _image_counts_for(db, [m.id for m in ordered])
        history = []
        for m in ordered:
            text = m.content
            if m.role == "user" and note_counts.get(m.id):
                text += image_note(note_counts[m.id])
            history.append({"role": m.role, "content": text})

        # 本轮：正文 + 附带图片注记（⚠️ 注记只发给模型，落库的 content 保持用户原文）
        history.append({"role": "user", "content": content + image_note(len(images))})

        # 3.5) RAG 增强：检索课程知识库，把命中的知识块作为 system 消息注入
        #      ⚠️ 检索失败会自动降级（返回 False），对话照常进行，
        #         因此这里不需要 try/except，也不必向客户端抛错误码。
        await _inject_rag_context(history, content)

        # 4) 调用大模型流式生成
        #    ⚠️ 默认（AI_VISION_MODEL 未配置）走 stream_chat，与改造前完全一致：
        #       图片只在上面那句注记里被「提及」，绝不发给模型——
        #       因为 AI_MODEL（deepseek-v4-flash）是纯文本模型，把图塞过去只会被
        #       官方替换成占位文本，反而制造「模型看过了」的假象。
        #       只有显式配置了支持 image_url 的视觉模型，才把最后一条 user 消息
        #       换成内容块数组，真正把图片发出去。
        vision_paths = (
            [Path(it["path"]) for it in images] if (AI_VISION_MODEL and images) else []
        )
        interrupt = None  # None=正常 / 'stop' / 'timeout' / 'upstream'
        upstream_detail = ""
        try:
            async with asyncio.timeout(AI_TIMEOUT):
                if vision_paths:
                    hist = list(history)
                    hist[-1] = {
                        "role": "user",
                        "content": build_vision_content(hist[-1]["content"], vision_paths),
                    }
                    logger.info(
                        "[ai.chat] 使用多模态模型 %s 发送 %d 张图片 session=%s",
                        AI_VISION_MODEL, len(vision_paths), session_id,
                    )
                    stream = stream_vision(hist, AI_VISION_MODEL)
                else:
                    stream = stream_chat(history)

                async for kind, piece in stream:
                    if cancel.is_set():
                        interrupt = "stop"
                        break
                    # 本期不展示思考链，只取正文
                    if kind != "text":
                        continue
                    text_chunks.append(piece)
                    await _guard_send(ws, {"type": "delta", "content": piece})
        except asyncio.TimeoutError:
            logger.warning("[ai.chat] 上游超时 session=%s", session_id)
            interrupt = "timeout"
        except asyncio.CancelledError:
            # 断连取消：尽力落半截，然后继续向上抛
            await _persist_answer(session_id, "".join(text_chunks))
            raise
        except Exception as e:
            logger.error("[ai.chat] 上游异常 session=%s: %r", session_id, e)
            upstream_detail = str(e)
            interrupt = "upstream"

        # 5) 收尾落库（全量或半截）
        await _persist_answer(session_id, "".join(text_chunks), db)

    # 6) 终结帧（在数据库会话之外发送）
    if interrupt == "upstream":
        detail = (upstream_detail or "").strip()[:160]
        text = ("模型服务暂不可用：" + detail) if detail else "模型服务暂不可用，请稍后重试"
        await _guard_send(ws, {"type": "error", "code": 41006, "msg": text})
    elif interrupt == "timeout":
        await _guard_send(ws, {"type": "error", "code": 41007, "msg": "生成超时或已取消"})
    else:
        await _guard_send(ws, {"type": "done"})


@router.websocket("/chat")
async def ai_chat(ws: WebSocket):
    """WebSocket 对话入口。

    生命周期：
        握手校验 ?token= → 失败 close(4401)
        帧循环（chat / stop）→ 空闲 AI_WS_IDLE 秒自动断连
        收到新 chat 时若上一轮仍在生成，先取消旧轮（半截落库）再开新轮
        连接断开 → 取消在途生成
    """
    await ws.accept()
    cur: asyncio.Task | None = None
    cancel = asyncio.Event()

    try:
        # 握手鉴权：token 无效 / 过期 / 已注销 → close 4401
        async with SessionLocal() as db:
            try:
                user = await get_user_by_token(db, ws.query_params.get("token", ""))
            except BizError:
                await ws.close(code=4401, reason="未登录或登录已过期")
                return

        logger.info("[ai.ws] uid=%s 已连接", user.id)

        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=AI_WS_IDLE)
            except asyncio.TimeoutError:
                await ws.close(code=1000)  # 空闲断连
                return

            try:
                frame = json.loads(raw)
            except (TypeError, ValueError):
                await _guard_send(ws, {"type": "error", "code": 41008, "msg": "参数不合法"})
                continue

            ftype = frame.get("type")

            if ftype == "stop":
                cancel.set()
                continue

            if ftype != "chat":
                await _guard_send(ws, {"type": "error", "code": 41008, "msg": "参数不合法"})
                continue

            # 抢占：上一轮仍在生成则先取消，并等它收尾落库后再开新轮
            if cur is not None and not cur.done():
                cancel.set()
                try:
                    await cur
                except Exception:
                    logger.exception("[ai.chat] 旧轮收尾异常")

            cancel.clear()
            cur = asyncio.create_task(_handle_chat(ws, user.id, frame, cancel))

    except WebSocketDisconnect:
        pass  # 客户端断开，交由 finally 取消在途生成
    finally:
        if cur is not None and not cur.done():
            cancel.set()
            cur.cancel()
            try:
                await cur
            except asyncio.CancelledError:
                pass
