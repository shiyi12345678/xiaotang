"""AI 助教图片附件：上传端点 + 附件工具 + 可选的多模态通路。

为什么单独一个模块（而不是塞进 routers/ai.py）：
    本模块只处理「图片」这一条支线，routers/ai.py 只处理会话与帧协议。
    两者共用 /api/v1/ai 前缀（FastAPI 允许多个 router 共用前缀），
    这样既不动既有的帧契约，也不用把 500 行路由文件撑得更大。

对外提供三样东西：
    1. POST /api/v1/ai/upload   —— multipart 上传一张图片（需登录）
    2. 一组供 routers/ai.py 复用的纯函数：
       normalize_images / resolve_images / attach_images / image_note
    3. AI_VISION_MODEL 配置存在时的多模态流式生成：
       build_vision_content / stream_vision

⚠️ 与既有 WebSocket 帧契约的关系（重要）：
    本模块【不新增、不修改任何帧的类型与字段】。
    它只改变两件事：(a) 用户消息附带了哪些图片（写 ai_message_image 表）；
    (b) 发给大模型的那条 user 消息长什么样（纯文本→加一句注记，
    或配置了视觉模型时改成 OpenAI 兼容的内容块数组）。
    因此 session / delta / done / error 四种帧的形态与改造前完全一致。

⚠️ 诚实原则（本模块的设计前提）：
    默认的 AI_MODEL（deepseek-v4-flash）是纯文本模型，看不到图片。
    所以默认路径【不把图片发给模型】，只在提示词里注明「用户上传了 N 张图片」，
    并明确告知模型它无法查看图片内容——不伪造「模型看懂了图」的假象。
    只有显式配置 AI_VISION_MODEL 后，才会走真正的多模态请求。

⚠️ 为什么这里不直接复用 app/core/llm.py 的 stream_chat：
    stream_chat 的 model 固定取 AI_MODEL、content 固定是字符串，
    多模态需要在同一份请求里换模型并改用 image_url 内容块。
    为了不改动既有模块的对外行为，这里复用它已经写好的三个内部件
    （get_client / _today_line / _delta_text）自行组装请求，
    避免把那句「当前日期」提示词和增量解析逻辑复制一份后各自跑偏。
"""
import base64
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    AI_IMAGE_MAX_COUNT,
    AI_UPLOAD_MAX_MB,
    AI_VISION_MODEL,
    BASE_DIR,
)
from app.core import llm
from app.core.response import BizError, ok
from app.core.security import get_current_user
from app.models import AiMessageImage, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助教"])

# ==========================================================
# 常量
# ==========================================================

# 上传根目录：server/uploads/
# ⚠️ main.py 会把 UPLOAD_ROOT 用 StaticFiles 挂到 URL 前缀 /uploads，
#    因此磁盘位置与访问路径必须一起改，二者是绑定的。
UPLOAD_ROOT = BASE_DIR / "uploads"
UPLOAD_DIR = UPLOAD_ROOT / "ai"
URL_PREFIX = "/uploads/ai"

# 单张图片体积上限（字节）。AI_UPLOAD_MAX_MB 非法时兜底 1MB，避免配成 0 后什么都传不上来
MAX_BYTES = max(1, AI_UPLOAD_MAX_MB) * 1024 * 1024

# 扩展名 → MIME 白名单。
# ⚠️ 只认这 5 个扩展名；MIME 由服务端按扩展名/文件头判定，
#    绝不用客户端 multipart 里声明的 content_type 作为最终依据（可被伪造）。
ALLOWED_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

# 落盘文件名的白名单正则：32 位十六进制 + 允许的扩展名，正是我们自己生成的样子。
# ⚠️ 用它解析客户端回传的 id/url，天然挡掉 "../"、"..\\"、绝对路径等穿越写法。
_FILENAME_RE = re.compile(r"^([0-9a-f]{32})\.(jpg|jpeg|png|webp|gif)$")

# 读盘分块大小：边读边累计体积，避免把超大文件一次性读进内存
_CHUNK = 64 * 1024


# ==========================================================
# 校验 / 清洗工具
# ==========================================================


def _sniff_ext(head: bytes) -> str | None:
    """按文件头判断真实图片格式，返回规范扩展名；不认识则返回 None。

    为什么不能只信扩展名与 content_type：
        两者都由客户端提供，把 a.php 改名成 a.jpg、或谎报 image/jpeg 都能绕过。
        读前 16 字节做魔数校验，能确保落盘的东西确实是图片。

    参数：
        head: 文件开头的若干字节（至少 16 字节才能识别 WEBP）
    返回：
        "jpg" / "png" / "gif" / "webp"；无法识别返回 None
    """
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _safe_name(raw: str | None, ext: str) -> str:
    """把客户端文件名收敛成「仅供展示」的安全短名。

    ⚠️ 返回值只写进数据库的 name 字段用于界面展示，
       绝不参与磁盘路径（磁盘名一律是自己生成的 uuid），因此不存在覆盖与穿越风险。
       这里仍然去掉控制字符与目录部分，避免脏数据污染日志与前端渲染。

    参数：
        raw: 客户端原始文件名（可为 None / 含任意路径）
        ext: 最终确定的扩展名（用于兜底命名）
    返回：
        长度 ≤120 的安全文件名
    """
    name = Path(str(raw or "")).name                      # 去掉任何目录部分
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()   # 去掉控制字符
    name = name.strip(". ")                               # 去掉首尾的点与空格
    if not name or name in (".", ".."):
        return "image." + ext
    return name[:120]


def _token_of(item) -> tuple[str, str | None] | None:
    """把 images 数组里的单个元素收敛成 (token, 展示名或 None)。

    兼容三种写法（客户端实现自由度大，这里都吃下来）：
        "9f3c...e1.jpg"                                  上传响应里的 id
        "/uploads/ai/9f3c...e1.jpg"                      上传响应里的 url
        {"id": "...", "name": "作业.jpg"}                需要保留原文件名的客户端
    返回：
        (token, name)；无法识别返回 None
    """
    if isinstance(item, dict):
        token = ""
        for key in ("id", "url", "file", "filename", "path"):
            value = item.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                if str(value).strip():
                    token = str(value).strip()
                    break
        if not token:
            return None
        raw_name = item.get("name") or item.get("originalName")
        name = None
        if isinstance(raw_name, str) and raw_name.strip():
            name = raw_name.strip()[:120]
        return token, name
    if isinstance(item, (str, int)) and not isinstance(item, bool):
        token = str(item).strip()
        return (token, None) if token else None
    return None


def normalize_images(raw) -> list:
    """把帧里的 images 字段收敛成 [{token, name}]，最多 AI_IMAGE_MAX_COUNT 项。

    ⚠️ 宽容策略（刻意为之）：images 是可选的增强项，
       格式不对、元素没意义、张数超限都只记日志并忽略，
       绝不抛错——一条脏数据不该让用户整轮对话失败。
       真正「引用了不存在的图片」的判定在 resolve_images 里做，同样只跳过。

    参数：
        raw: 客户端帧里的 images 值（期望是数组，也容忍单个字符串/对象）
    返回：
        [{"token": str, "name": str | None}, ...]，顺序与客户端一致
    """
    if raw is None:
        return []

    if isinstance(raw, (list, tuple)):
        seq = list(raw)
    elif isinstance(raw, (str, int, dict)) and not isinstance(raw, bool):
        seq = [raw]           # 客户端只传了一张、且没包成数组，也认
    else:
        logger.warning("[ai.image] images 字段类型不支持，已忽略：%s", type(raw).__name__)
        return []

    out = []
    for item in seq:
        parsed = _token_of(item)
        if parsed is None:
            continue
        out.append({"token": parsed[0], "name": parsed[1]})
        if len(out) >= AI_IMAGE_MAX_COUNT:
            break

    if len(seq) > AI_IMAGE_MAX_COUNT > 0:
        logger.warning(
            "[ai.image] 单条消息最多 %d 张图，已忽略多出的 %d 项",
            AI_IMAGE_MAX_COUNT, len(seq) - AI_IMAGE_MAX_COUNT,
        )
    return out


def resolve_image(token: str) -> tuple[str, Path] | None:
    """把一个图片引用解析成本地真实文件。

    参数：
        token: "9f3c...e1.jpg" / "/uploads/ai/9f3c...e1.jpg" /
               "http://host:8000/uploads/ai/9f3c...e1.jpg"（带查询串也认）
    返回：
        (文件名, 绝对路径)；无法识别或文件不存在/不是文件时返回 None

    ⚠️ 安全：只取路径最后一段并用白名单正则校验，
       再断言结果确实位于 UPLOAD_DIR 之内。两重保险，
       因此 "../../.env"、"..\\..\\app\\config.py" 之类都不可能命中。
    """
    text = str(token or "").strip()
    if not text:
        return None

    text = text.split("?")[0].split("#")[0]          # 去掉查询串与锚点
    basename = Path(text.replace("\\", "/")).name    # 只保留最后一段
    if not _FILENAME_RE.match(basename.lower()):
        return None

    path = UPLOAD_DIR / basename.lower()
    try:
        if not path.is_file() or not path.is_relative_to(UPLOAD_DIR):
            return None
    except OSError:
        return None
    return basename.lower(), path


def _item_from_path(filename: str, path: Path, display_name: str | None) -> dict:
    """由磁盘文件构造一条「可落库的附件信息」（供 resolve_images 与上传端点共用）。"""
    ext = path.suffix.lower().lstrip(".")
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "url": f"{URL_PREFIX}/{filename}",
        "name": display_name or filename,
        "size": size,
        "mime": ALLOWED_MIME.get(ext, ""),
        "path": str(path),
    }


def resolve_images(items: list) -> list:
    """把 normalize_images 的产物解析成可落库的附件信息，无效项跳过。

    参数：
        items: normalize_images 的返回值
    返回：
        [{"url", "name", "size", "mime", "path"}, ...]，顺序即客户端给的顺序
    """
    out = []
    for item in items or []:
        resolved = resolve_image(item.get("token", ""))
        if resolved is None:
            logger.warning("[ai.image] 忽略无法解析的图片引用：%.120s", item.get("token", ""))
            continue
        filename, path = resolved
        out.append(_item_from_path(filename, path, item.get("name")))
    return out


async def attach_images(db: AsyncSession, message_id: int, images: list) -> int:
    """把图片附件挂到某条 ai_message 上（按顺序写 sort_order）。

    ⚠️ 本函数只 add 不 commit，由调用方与「用户消息落库」放在同一个事务里提交，
       避免出现「消息写进去了、图片没写进去」的半写状态。

    参数：
        db:         数据库会话
        message_id: 目标消息 ID（ai_message.id）
        images:     resolve_images 的返回值
    返回：
        写入的条数
    """
    for index, item in enumerate(images or []):
        db.add(AiMessageImage(
            message_id=message_id,
            url=item["url"],
            name=item["name"],
            size=item["size"],
            mime=item["mime"],
            sort_order=index,
        ))
    return len(images or [])


# ==========================================================
# 提示词注记 / 多模态
# ==========================================================


def image_note(count: int) -> str:
    """构造追加到 user 消息末尾的「附带图片」注记。

    为什么要这段文字：
        模型本身并不知道这条消息在界面上还挂了图。不告诉它，它就会对
        「这张图里是什么」类追问毫无头绪，多轮上下文会断裂。

    ⚠️ 诚实优先：默认（未配置 AI_VISION_MODEL）模型确实看不到图片，
       注记里必须写明这一点，否则模型极可能凭空描述图片内容（幻觉）。
       这里宁可让回答说「我看不到图片」，也不要编一个看起来像样的描述。

    参数：
        count: 本条消息附带的图片张数
    返回：
        以 "\\n\\n" 开头的注记；count<=0 时返回空串（此时调用方行为与改造前一致）
    """
    if count <= 0:
        return ""
    if AI_VISION_MODEL:
        return f"\n\n[用户上传了 {count} 张图片，已随本条消息以图片形式提供]"
    return (
        f"\n\n[用户上传了 {count} 张图片；"
        f"当前模型为纯文本模型，无法查看图片内容，"
        f"请如实说明看不到图片，需要时让用户用文字描述图片里的关键信息]"
    )


def _data_url(path: Path) -> str:
    """把本地图片编码成 data URL（OpenAI image_url 协议接受这种内联形式）。"""
    ext = path.suffix.lower().lstrip(".")
    mime = ALLOWED_MIME.get(ext, "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_vision_content(text: str, image_paths: list):
    """构造多模态 user 消息的 content（OpenAI 兼容的内容块数组）。

    参数：
        text:        用户提问正文（已含 image_note 注记）
        image_paths: 本地图片路径列表
    返回：
        内容块数组 [{"type":"text",...}, {"type":"image_url",...}, ...]；
        ⚠️ 一张都读不出来时返回原始字符串 text（OpenAI 同样接受字符串 content），
           这样上层无需为「降级」写分支。

    ⚠️ 体积提示：图片以 base64 内联，体积约为原文件的 1.33 倍。
       AI_UPLOAD_MAX_MB（默认 10MB）× AI_IMAGE_MAX_COUNT（默认 4）
       理论上最坏可达 50MB+ 的单次请求，超出多数服务商上限——
       真要开多模态时建议同时调小这两项（见 README）。
    """
    parts = [{"type": "text", "text": text}]
    skipped = 0
    for path in image_paths:
        try:
            parts.append({"type": "image_url", "image_url": {"url": _data_url(path)}})
        except OSError:
            # 文件在上传后被外部删掉了：跳过这张，不影响其余图片与整轮对话
            skipped += 1
            logger.warning("[ai.image] 图片已不可读，跳过：%s", path.name)
    if skipped:
        logger.warning("[ai.image] 共跳过 %d 张不可读图片", skipped)
    return parts if len(parts) > 1 else text


async def stream_vision(messages: list, model: str):
    """多模态流式生成，逐段产出 (kind, text)，kind ∈ {'text','thinking'}。

    与 app/core/llm.py:stream_chat 的唯一区别：
        - 模型名用传入的视觉模型（而不是 AI_MODEL）；
        - messages 里最后一条 user 消息的 content 是内容块数组而非字符串。
    产出格式与 stream_chat 完全一致，因此 routers/ai.py 的收尾逻辑无需任何改动。

    参数：
        messages: 已拼好的上游消息列表（最后一条 content 可为 list）
        model:    视觉模型名（来自 AI_VISION_MODEL）
    """
    msgs = [{"role": "system", "content": llm._today_line()}, *messages]
    client = llm.get_client()
    resp = await client.chat.completions.create(model=model, messages=msgs, stream=True)
    async for chunk in resp:
        if not chunk.choices:
            continue
        content, thinking = llm._delta_text(chunk.choices[0].delta)
        if thinking:
            yield "thinking", thinking
        elif content:
            yield "text", content


# ==========================================================
# HTTP 端点
# ==========================================================


@router.post("/upload", summary="上传图片附件")
async def upload_image(
    file: UploadFile | None = File(None, description="图片文件，表单字段名必须是 file"),
    user: User = Depends(get_current_user),
):
    """上传一张图片，返回可访问 URL 与附件 id。

    请求：multipart/form-data，单个字段 file（需 Authorization: Bearer <token>）
    响应：{code:0, msg:'ok', data:{id, url, name, size, mime}}

    校验顺序（任一不通过都不落盘）：
        41011 没收到文件/内容为空
        41009 扩展名不在白名单，或 MIME 不是图片，或文件头不是图片
        41010 超过 AI_UPLOAD_MAX_MB

    ⚠️ 这里刻意把 file 声明为「可选」而不是 File(...)：
       若写成必填，字段缺失会被 FastAPI 的校验拦下 → 全局处理器归一成
       HTTP 500 / code 50000「服务器开小差了」，客户端拿不到可定位的原因。
       声明成可选后由我们自己抛 41011，错误语义清晰得多。

    ⚠️ 落盘文件名一律用 uuid4().hex，客户端文件名只作为展示名存库，
       绝不参与磁盘路径（防路径穿越、防覆盖他人文件）。
    ⚠️ 此时【不写数据库】：还没有 ai_message 行可挂。附件记录在聊天落库时
       由 attach_images 写入（见 routers/ai.py）。因此「上传了但没发出去」的图片
       会成为磁盘上的孤儿文件，属预期行为，可由运维清理 server/uploads/ai/。
    ⚠️ 返回的 url 是「站点 origin + 路径」的形式（/uploads/ai/xxx.jpg），
       客户端需要用站点 origin 补全（BASE_URL 去掉 /api/v1 那一段）。
    """
    if file is None:
        raise BizError(41011, "未收到文件，请以 multipart 字段 file 上传图片")

    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower().lstrip(".")

    # ---- 1) 扩展名白名单（先挡住明显不对的，省得读盘） ----
    if not ext:
        raise BizError(41011, "未收到文件，请以 multipart 字段 file 上传图片")
    if ext not in ALLOWED_MIME:
        raise BizError(41009, "仅支持 jpg / jpeg / png / webp / gif 格式的图片")

    # ---- 2) 客户端声明的 MIME（只作为辅助信号，不作为最终依据） ----
    declared = str(file.content_type or "").lower()
    if declared and not declared.startswith("image/"):
        raise BizError(41009, "上传的文件不是图片（Content-Type 非 image/*）")

    # ---- 3) 读首块 → 魔数校验：确认真的是图片，并且体积没超限 ----
    try:
        first = await file.read(_CHUNK)
        if not first:
            raise BizError(41011, "上传的文件内容为空")

        sniffed = _sniff_ext(first[:16])
        if sniffed is None:
            raise BizError(41009, "文件内容不是有效的图片（文件头校验未通过）")

        # 文件名与真实内容不符时以内容为准（例如把 png 存成了 .jpg）
        if not (sniffed == ext or (sniffed == "jpg" and ext == "jpeg")):
            logger.info("[ai.upload] 扩展名 %s 与文件头 %s 不符，按文件头处理", ext, sniffed)
            ext = sniffed

        size = len(first)
        if size > MAX_BYTES:
            raise BizError(41010, f"图片不能超过 {AI_UPLOAD_MAX_MB} MB")

        # ---- 4) 落盘：先写首块，再边读边写边计体积 ----
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{ext}"
        target = UPLOAD_DIR / filename
        try:
            with target.open("wb") as fp:
                fp.write(first)
                while True:
                    chunk = await file.read(_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise BizError(41010, f"图片不能超过 {AI_UPLOAD_MAX_MB} MB")
                    fp.write(chunk)
        except BaseException:
            # 任何异常（含超限中断）都不留下半截文件
            target.unlink(missing_ok=True)
            raise
    finally:
        await file.close()

    name = _safe_name(raw_name, ext)
    mime = ALLOWED_MIME[ext]                    # 服务端按文件头判定，不用客户端声明值
    url = f"{URL_PREFIX}/{filename}"

    # 只记事件与体积，不记文件名（可能含用户隐私信息）
    logger.info("[ai.upload] uid=%s 已保存 %s（%d 字节，%s）", user.id, filename, size, mime)
    return ok({"id": filename, "url": url, "name": name, "size": size, "mime": mime})
