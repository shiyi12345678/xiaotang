"""应用入口。

启动方式（工作目录 = server/）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

⚠️ --host 0.0.0.0 是必需的：
    uni-app 真机调试 / 局域网 H5 访问时，客户端填的是电脑的局域网 IP
    （如 192.168.x.x）。若只监听 127.0.0.1，真机会连接超时。
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE, APP_VERSION, BASE_DIR, RAG_ENABLED, RAG_WARMUP
from app.core.response import BizError
from app.routers import ai as ai_router
from app.routers import ai_upload as ai_upload_router
from app.routers import apply as apply_router
from app.routers import chat as chat_router
from app.routers import content as content_router
from app.routers import hr as hr_router
from app.routers import interview as interview_router
from app.routers import job as job_router
from app.routers import mine as mine_router
from app.routers import study as study_router
from app.routers import user as user_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_logger = logging.getLogger(__name__)


async def _maybe_warmup_rag() -> None:
    """启动阶段按需预热 RAG（RAG_WARMUP=true 时才执行）。

    为什么要预热：
        - 云端向量化模式：提前验证 API Key 是否有效、探明向量维度，
          避免第一条用户提问才发现配置错；
        - 本地模型模式：模型加载要数秒（首次还要下载），预热后首问不卡。

    ⚠️ 默认关闭（RAG_WARMUP=false），因此本钩子默认不做任何事，不改变原有启动行为。
    ⚠️ 预热失败只记日志，绝不阻止服务启动：
       服务整体可用性的优先级高于 RAG 这个增强项。
    """
    if not (RAG_ENABLED and RAG_WARMUP):
        return

    try:
        from app.core import embedding

        # 同步阻塞（模型加载 / 网络请求），必须走线程池，否则会卡住启动
        info = await asyncio.to_thread(embedding.warmup)
        if info.get("embed_ok"):
            _logger.info("[startup] RAG 预热完成：provider=%s dim=%s rerank=%s",
                         info.get("provider"), info.get("dim"), info.get("rerank_ok"))
        else:
            _logger.warning("[startup] RAG 预热未通过（不影响服务运行）：%s", info.get("detail"))
    except Exception:
        _logger.exception("[startup] RAG 预热异常（不影响服务运行）")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期钩子：启动时执行可选的 RAG 预热。"""
    await _maybe_warmup_rag()
    yield


app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

# ---------- CORS ----------
# ⚠️ 演示期放开全部来源，便于 H5 / 局域网调试。
#    生产环境必须收紧为具体域名白名单，例如：
#        allow_origins=["https://your-domain.com"]
#    另注意：若将来改为携带 Cookie（allow_credentials=True），
#    浏览器不允许它与 allow_origins=["*"] 共存，必须显式列出域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 注册路由 ----------
app.include_router(user_router.router)
app.include_router(ai_router.router)
app.include_router(ai_upload_router.router)   # POST /api/v1/ai/upload（图片附件）
# 前后端结合（2026-09 新增）：内容域公开只读，我的/学习域一律按 token 的 uid 过滤
app.include_router(content_router.router)     # /api/v1/content/*（公开）
app.include_router(mine_router.router)        # /api/v1/mine/*（🔒）
app.include_router(study_router.router)       # /api/v1/study/*（🔒）
# 招聘改造（2026-09-19 新增）：职位域公开只读 + 收藏需登录
app.include_router(job_router.router)         # /api/v1/job/*（列表/详情公开，收藏 🔒）
app.include_router(apply_router.router)       # /api/v1/apply/*（🔒 投递）
app.include_router(apply_router.resume_router)  # /api/v1/resume/*（🔒 简历与求职报告）
app.include_router(hr_router.router)         # /api/v1/hr/*（🔒 企业招聘方）
app.include_router(chat_router.router)       # /api/v1/chat/*（🔒 求职者 ↔ HR 沟通）
app.include_router(interview_router.router)  # /api/v1/interview/*（题库公开，刷题记录 🔒）

# ---------- 静态文件：AI 助教上传的图片 ----------
# 图片本体落在 server/uploads/ai/，这里把整个 uploads/ 目录挂到 URL 前缀 /uploads，
# 于是 /uploads/ai/<uuid>.jpg 就能直接访问。
# ⚠️ 返回给客户端的 url 形如 /uploads/ai/<uuid>.jpg（站点 origin 之后的路径），
#    客户端要用站点 origin 补全：BASE_URL('http://host:8000/api/v1') 去掉 '/api/v1'。
# ⚠️ StaticFiles 在目录不存在时会直接抛错导致服务起不来，所以先创建目录。
UPLOAD_ROOT = BASE_DIR / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")


@app.get("/", summary="健康检查")
async def read_root():
    """根路径：用于快速确认服务是否已启动。"""
    return {
        "code": 0,
        "msg": "ok",
        "data": {"service": APP_TITLE, "version": APP_VERSION, "docs": "/docs"},
    }


# ==========================================================
# 全局异常处理器（三通道兜底）
# ==========================================================


@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    """业务异常 → HTTP 状态语义化（400/401）+ body {code, msg}。

    说明：业务错误码用于前端精确定位，HTTP 状态码用于网关/监控统计。
    """
    return JSONResponse(
        status_code=exc.http,
        content={"code": exc.code, "msg": exc.msg},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI 原生 422 校验错误归一。

    ⚠️ 入参格式本应由客户端先自校验；若有请求漏到这里，
       统一返回 50000，而不是把框架的 422 结构、字段路径暴露给客户端。
    """
    logging.getLogger("uvicorn.error").warning(
        "[422] %s %s: %s", request.method, request.url.path, exc.errors()[:3]
    )
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "msg": "服务器开小差了"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """兜底异常 → 500 + 50000。

    ⚠️ 异常堆栈只写入服务端日志，绝不返回给客户端（防内部信息泄露）。
    """
    logging.getLogger("uvicorn.error").exception(
        "[500] %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "msg": "服务器开小差了"},
    )
