"""向量化与精排模型（RAG 的「模型层」）。

职责边界（只做模型推理，不碰数据库）：
    1. embed_texts / embed_text —— 把文本编码成稠密向量
    2. rerank                   —— 用交叉编码器对「查询-候选块」逐对打分重排
    3. warmup / unload          —— 预热与释放（便于调试与控制内存）

两种向量化方式（由 .env 的 RAG_EMBED_PROVIDER 决定）：
    local —— 本地 SentenceTransformer 模型（需下载约 1GB，离线可用、无调用费用）
    api   —— 云端 Embedding 接口（零下载、速度快、按量计费；需 API Key）
             用项目已有的 openai SDK 调用，各服务商均为 OpenAI 兼容协议，
             因此不引入任何新依赖。

设计要点：
    - 【懒加载 + 双检锁】：模型/客户端首次真正用时才初始化，且并发下只加载一次。
      直接在 import 阶段加载会拖慢 uvicorn 启动（本地方案首次还要下载模型）。
    - 【同步实现】：sentence-transformers 是同步阻塞的 CPU 推理；
      在 async 路由里必须用 asyncio.to_thread 包一层（见 app/core/rag.py），
      否则会阻塞事件循环，导致 WebSocket 对话整体卡住。
    - 【精排阈值口径修正】：课程示例里 threshold=0.8 直接比对 CrossEncoder 输出，
      但 bge-reranker-base 默认输出的是 logits（约 -10~+10，不是 0~1 概率），
      拿 0.8 当概率阈值会导致过滤结果异常。本实现显式套 Sigmoid 归一化到 0~1，
      阈值语义才正确（推荐 0.3~0.5，见 RAG_RERANK_THRESHOLD）。
"""
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)

# 模型单例与对应锁：锁用于保证「并发首次调用」只加载一次模型
_embed_lock = threading.Lock()
_rerank_lock = threading.Lock()
_api_lock = threading.Lock()
_embed_model = None
_rerank_model = None
_api_client = None
_api_dim = 0          # 云端接口返回的向量维度缓存（首次探测后固定）


# ==========================================================
# 模型引用解析
# ==========================================================


def _resolve_model_ref(name: str) -> str:
    """把配置里的模型引用解析成可直接加载的字符串。

    支持的写法：
        ./models/gte-large-zh      本地目录（相对 server/ 解析）
        D:/models/gte-large-zh     本地目录（绝对路径）
        thenlper/gte-large-zh      HuggingFace 仓库名（联网或走缓存）

    返回：
        本地目录的绝对路径，或原样的仓库名

    异常：
        RuntimeError —— 写成了本地路径形式但目录不存在（提前报错，
                        避免交给 transformers 后抛出一堆难以理解的堆栈）

    ⚠️ 为什么要做这层解析：服务可能以不同工作目录启动（如从项目根跑 uvicorn），
       相对路径 "./models/xxx" 会解析到错误位置，导致「明明下好了却说找不到模型」。
    """
    raw = str(name or "").strip()
    if not raw:
        raise RuntimeError("模型配置为空：请检查 .env 中 RAG_EMBED_MODEL / RAG_RERANK_MODEL")

    from app.config import BASE_DIR

    # 判断是否「看起来就是本地路径」：以 ./ ../ / \ 开头，或形如 C:\ 的盘符路径
    looks_local = (
        raw.startswith(("./", ".\\", "/", "\\"))
        or (len(raw) > 1 and raw[1] == ":")
    )

    p = Path(raw)
    if not p.is_absolute():
        p = (BASE_DIR / raw).resolve()      # 相对路径统一按 server/ 解析

    if p.is_dir():
        return str(p)
    if looks_local:
        raise RuntimeError(
            f"本地模型目录不存在：{p}\n"
            f"请先运行：.venv/Scripts/python.exe -m tools.download_models"
        )
    return raw


# ==========================================================
# 环境准备：国内镜像 / 缓存目录 / 离线模式
# ==========================================================


def _prepare_env() -> None:
    """在加载模型前设置 HuggingFace 相关环境变量。

    ⚠️ 必须在 import transformers（即首次 import sentence_transformers）之前
       写入 os.environ，否则镜像地址不生效。因此本模块把
       `from sentence_transformers import ...` 放在函数内部延迟导入。

    读取的配置项（均在 server/.env 中可改）：
        RAG_HF_MIRROR            —— HF 镜像地址，国内推荐 https://hf-mirror.com
        RAG_MODEL_CACHE          —— 模型缓存目录（默认 server/models_cache）
        RAG_HF_OFFLINE           —— true 时只用本地缓存，不联网（模型已下好可用）
        RAG_HF_DOWNLOAD_TIMEOUT  —— 单文件下载超时（秒），HF 默认 10 秒太小
    """
    # 延迟导入配置：避免 tools/ 下的独立脚本因导入顺序问题读不到 .env
    from app.config import (
        RAG_HF_DOWNLOAD_TIMEOUT, RAG_HF_MIRROR, RAG_HF_OFFLINE, RAG_MODEL_CACHE,
    )

    # 镜像：仅当用户显式配置且系统未设置时才覆盖，不擅自覆盖用户已有环境
    if RAG_HF_MIRROR and not os.getenv("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = RAG_HF_MIRROR
        logger.info("[rag.model] 使用 HuggingFace 镜像：%s", RAG_HF_MIRROR)

    # 缓存目录：把模型文件放在项目内，便于备份与迁移（不污染系统用户目录）
    if RAG_MODEL_CACHE:
        os.environ.setdefault("HF_HOME", RAG_MODEL_CACHE)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", RAG_MODEL_CACHE)

    # ⚠️ 下载超时：HF 默认 10 秒，走国内镜像下载大文件极易超时，
    #    超时后临时文件写坏，下一次读取时会报 "Expecting value: line 1 column 1"
    #    这类看起来莫名其妙的 JSON 解析错误。统一放宽到 60 秒以上。
    if RAG_HF_DOWNLOAD_TIMEOUT > 0:
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", str(RAG_HF_DOWNLOAD_TIMEOUT))

    # 离线模式：模型已下载完成、断网或不想每次都检查更新时开启
    if RAG_HF_OFFLINE:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        logger.info("[rag.model] 已开启 HF 离线模式（只读本地缓存）")


# ==========================================================
# 向量化模型
# ==========================================================


def get_embed_model():
    """获取本地向量化模型单例（懒加载）。

    返回：
        SentenceTransformer 实例

    异常：
        RuntimeError —— 当前是 api 模式（不应直接取本地模型）、依赖未安装或模型加载失败

    ⚠️ RAG_EMBED_PROVIDER=api 时本函数会直接报错：调用方应统一走 embed_texts()，
       由它按 provider 分发，避免在 api 模式下误触发本地模型下载。
    """
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    from app.config import RAG_EMBED_PROVIDER

    if RAG_EMBED_PROVIDER == "api":
        raise RuntimeError(
            "当前为云端向量化模式（RAG_EMBED_PROVIDER=api），不使用本地模型。"
            "请调用 embed_texts() / embed_text()，不要直接取本地模型。"
        )

    with _embed_lock:
        # 双检锁：拿到锁后再判一次，避免并发时重复加载
        if _embed_model is not None:
            return _embed_model

        _prepare_env()
        from app.config import RAG_DEVICE, RAG_EMBED_MODEL

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "未安装 RAG 依赖：请在 server/ 下执行 "
                ".venv/Scripts/pip.exe install -r requirements-rag.txt"
            ) from e

        logger.info("[rag.model] 正在加载向量化模型 %s（首次会下载，请稍候）", RAG_EMBED_MODEL)
        model_ref = _resolve_model_ref(RAG_EMBED_MODEL)
        try:
            _embed_model = SentenceTransformer(model_ref, device=RAG_DEVICE or None)
        except Exception as e:  # 网络 / 磁盘 / 模型名错误统一转为可读错误
            raise RuntimeError(f"向量化模型加载失败（{RAG_EMBED_MODEL}）：{e}") from e

        logger.info("[rag.model] 向量化模型就绪，向量维度=%s", _embed_model.get_sentence_embedding_dimension())
        return _embed_model


# ==========================================================
# 云端 Embedding（RAG_EMBED_PROVIDER=api）
# ==========================================================


def _get_api_client():
    """获取 OpenAI 兼容的 Embedding 客户端（单例）。

    返回：
        openai.OpenAI 实例
    异常：
        RuntimeError —— 依赖未安装或未配置 API Key
    """
    global _api_client
    if _api_client is not None:
        return _api_client

    with _api_lock:
        if _api_client is not None:
            return _api_client

        from app.config import (
            RAG_EMBED_API_BASE, RAG_EMBED_API_KEY, RAG_EMBED_API_MODEL, RAG_EMBED_API_TIMEOUT,
        )

        if not RAG_EMBED_API_KEY:
            raise RuntimeError(
                "RAG_EMBED_API_KEY 未配置：请在 server/.env 中填写云端 Embedding 服务的 API Key"
                "（或把 RAG_EMBED_PROVIDER 改回 local 使用本地模型）"
            )

        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "未安装 openai 库：请执行 .venv/Scripts/pip.exe install -r requirements.txt"
            ) from e

        # ⚠️ 超时交给 SDK 统一控制，避免网络抖动时长时间挂住检索链路
        _api_client = OpenAI(
            api_key=RAG_EMBED_API_KEY,
            base_url=RAG_EMBED_API_BASE,
            timeout=RAG_EMBED_API_TIMEOUT,
            max_retries=0,          # 重试逻辑由本模块自己控制（便于打日志与退避）
        )
        logger.info("[rag.model] 云端 Embedding 客户端就绪：%s / %s",
                    RAG_EMBED_API_BASE, RAG_EMBED_API_MODEL)
        return _api_client


def _is_batch_size_error(err: Exception) -> bool:
    """判断异常是否为「单请求条数超限」。

    为什么要单独识别：各服务商、甚至同一服务商不同账号档位的批大小上限都不同
    （阿里百炼部分账号上限为 10，硅基流动 32，智谱 64）。识别出来后自动缩小批大小重试，
    比让用户去翻文档改配置友好得多。

    参数：
        err: 捕获到的异常
    返回：
        True = 属于批大小超限错误
    """
    text = str(err).lower()
    return "batch size" in text or "batch_size" in text


def _embed_texts_api(texts: Sequence[str]) -> List[List[float]]:
    """调用云端接口批量向量化。

    参数：
        texts: 待编码文本序列（已清洗，非空）
    返回：
        与入参等长、顺序一致的向量列表

    异常：
        RuntimeError —— 未配置 Key、网络失败、返回条数不符（统一转成可读错误）

    ⚠️ 四个坑点已处理：
        1. 单请求条数有上限（不同服务商/档位 10~64 不等）→ 按 RAG_EMBED_API_BATCH 切批，
           且遇到「batch size 超限」错误时**自动对半缩小批大小并重试**，无需人工改配置；
        2. 返回顺序不保证与入参一致 → 按返回项的 index 字段重排；
        3. 网络抖动/限流 → 按 RAG_EMBED_API_RETRIES 退避重试；
        4. 逐批校验返回条数，避免错位导致向量与文本不匹配（错位会让检索结果全乱）。
    """
    from app.config import (
        RAG_EMBED_API_BASE, RAG_EMBED_API_BATCH, RAG_EMBED_API_MODEL, RAG_EMBED_API_RETRIES,
    )

    client = _get_api_client()
    batch_size = max(1, RAG_EMBED_API_BATCH)      # 动态批大小：超限时会自动缩小
    max_retries = max(1, RAG_EMBED_API_RETRIES)
    vectors: List[List[float]] = []
    pos = 0

    while pos < len(texts):
        last_err: Exception | None = None
        attempt = 1

        while attempt <= max_retries:
            # ⚠️ 必须在重试入口重新切片：上一轮可能刚把 batch_size 缩小，
            #    若沿用循环外切好的 part，缩批就只是「改了个数字」而请求内容没变，
            #    表现为「已降到 1 条却依旧报 batch size 超限」。
            part = list(texts[pos:pos + batch_size])

            try:
                resp = client.embeddings.create(model=RAG_EMBED_API_MODEL, input=part)
                items = list(resp.data or [])
                if len(items) != len(part):
                    raise RuntimeError(f"返回条数不符：请求 {len(part)} 条，返回 {len(items)} 条")

                # 按 index 排序，保证向量与入参文本一一对应
                items.sort(key=lambda x: getattr(x, "index", 0))
                vectors.extend([list(it.embedding) for it in items])
                pos += len(part)        # 只有成功才推进游标
                last_err = None
                break
            except Exception as e:
                # 批大小超限：不计入重试次数，直接缩小批大小重跑同一批
                if _is_batch_size_error(e) and batch_size > 1:
                    new_size = max(1, batch_size // 2)
                    logger.warning(
                        "[rag.model] 服务商限制了单请求条数（当前 %d），自动调整为 %d 后重试",
                        batch_size, new_size,
                    )
                    batch_size = new_size
                    last_err = e
                    continue        # 不递增 attempt，避免无谓的等待

                last_err = e
                logger.warning("[rag.model] 云端向量化失败（第 %d/%d 次）：%s",
                               attempt, max_retries, e)
                attempt += 1
                time.sleep(min(2 * attempt, 8))

        if last_err is not None:
            raise RuntimeError(
                f"云端向量化失败（{RAG_EMBED_API_BASE} / {RAG_EMBED_API_MODEL}）：{last_err}"
            ) from last_err

    return vectors

    return vectors


def _api_embedding_dim() -> int:
    """探测（并缓存）云端接口的向量维度。

    为什么要探测而不是照抄文档：部分服务商会按请求参数返回不同维度
    （如智谱 embedding-3 支持 dimensions 降维），照抄文档容易与真实返回不符，
    导致建表维度错误、灌库整批失败。

    返回：
        向量维度（正整数）
    """
    global _api_dim
    from app.config import RAG_EMBED_API_DIM

    if RAG_EMBED_API_DIM > 0:
        return RAG_EMBED_API_DIM
    if _api_dim > 0:
        return _api_dim

    with _api_lock:
        if _api_dim > 0:
            return _api_dim
        probe = _embed_texts_api(["维度探测"])
        if not probe or not probe[0]:
            raise RuntimeError("云端向量化维度探测失败：接口未返回向量")
        _api_dim = len(probe[0])
        logger.info("[rag.model] 云端 Embedding 维度探测结果：%d 维", _api_dim)
        return _api_dim


# ==========================================================
# 统一入口（按 provider 分发）
# ==========================================================


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """批量编码文本 → 稠密向量列表。

    参数：
        texts: 待编码文本序列（空字符串会被过滤，过滤后为空则直接返回空列表）
    返回：
        List[List[float]]，与「过滤后的入参」等长、顺序一致

    说明：
        本地模式 normalize_embeddings=True —— 输出做 L2 归一化，
        配合 Milvus 索引的 COSINE 度量，内积即余弦相似度，检索更稳定。
        ⚠️ 云端模式是否归一化由服务商决定，通常 bge/m3 系列已归一化。
    """
    items = [str(t or "").strip() for t in texts]
    if not items:
        return []

    from app.config import RAG_EMBED_PROVIDER

    if RAG_EMBED_PROVIDER == "api":
        return _embed_texts_api(items)

    model = get_embed_model()
    vectors = model.encode(
        items,
        normalize_embeddings=True,   # 归一化，与 COSINE 度量配套
        batch_size=32,               # 批大小；CPU 上 32 是速度与内存的折中
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> List[float]:
    """单条文本编码（检索时用），返回一条向量。"""
    vectors = embed_texts([text])
    if not vectors:
        raise ValueError("embed_text 收到空文本")
    return vectors[0]


def embedding_dim() -> int:
    """当前向量化方式的输出维度。

    用途：建表时按真实维度定义字段，避免模型/接口与 schema 不一致导致插入失败。
    """
    from app.config import RAG_EMBED_PROVIDER

    if RAG_EMBED_PROVIDER == "api":
        return _api_embedding_dim()

    model = get_embed_model()
    dim = model.get_sentence_embedding_dimension()
    if not isinstance(dim, int) or dim <= 0:
        raise RuntimeError("无法获取向量维度，模型异常")
    return dim


# ==========================================================
# 精排模型（CrossEncoder）
# ==========================================================


def get_rerank_model():
    """获取精排模型单例（懒加载）。

    返回：
        CrossEncoder 实例（已套 Sigmoid，输出 0~1 相关性分数）

    说明：
        精排是可选项：未配置 RAG_RERANK_MODEL 时调用方应先判断（见 is_rerank_configured）。
    ⚠️ 模型默认按目录名加载（如 ./bge-reranker-base），需先把模型文件放到该目录，
       或把 RAG_RERANK_MODEL 改成 HF 上的模型名（如 BAAI/bge-reranker-base，会自动下载）。
    """
    global _rerank_model
    if _rerank_model is not None:
        return _rerank_model

    with _rerank_lock:
        if _rerank_model is not None:
            return _rerank_model

        _prepare_env()
        from app.config import RAG_DEVICE, RAG_RERANK_MODEL

        try:
            import torch
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise RuntimeError(
                "未安装 RAG 依赖：请在 server/ 下执行 "
                ".venv/Scripts/pip.exe install -r requirements-rag.txt"
            ) from e

        logger.info("[rag.model] 正在加载精排模型 %s（首次会下载，请稍候）", RAG_RERANK_MODEL)
        model_ref = _resolve_model_ref(RAG_RERANK_MODEL)
        try:
            # ⚠️ 关键点：activation_fn=Sigmoid 让输出落到 0~1，
            #    这样 RAG_RERANK_THRESHOLD 才是「概率阈值」而不是「logit 阈值」
            _rerank_model = CrossEncoder(
                model_ref,
                max_length=512,                      # 单条候选块最长 512 token，与切块大小匹配
                activation_fn=torch.nn.Sigmoid(),    # 归一化到 0~1
                device=RAG_DEVICE or None,
            )
        except TypeError:
            # 兼容旧版 sentence-transformers（不支持 activation_fn 关键字）：
            # 退化为原始 logits 输出，由 rerank() 里手动做 Sigmoid
            logger.warning("[rag.model] 当前 sentence-transformers 不支持 activation_fn，改为手动归一化")
            _rerank_model = CrossEncoder(model_ref, max_length=512, device=RAG_DEVICE or None)
        except Exception as e:
            raise RuntimeError(f"精排模型加载失败（{RAG_RERANK_MODEL}）：{e}") from e

        logger.info("[rag.model] 精排模型就绪")
        return _rerank_model


def rerank(query: str, passages: Sequence[str], top_n: int = 0) -> List[Tuple[int, float]]:
    """对候选块精排，返回 (原始下标, 相关性分数) 列表，按分数降序。

    参数：
        query:    用户问题
        passages: 候选文本块（顺序与检索结果一致）
        top_n:    只返回前 N 条；<=0 表示全部返回
    返回：
        List[Tuple[int, float]]；分数的下标指向 passages 的位置，
        调用方用 `passages[idx]` 取回原文，避免到处搬运字符串。

    ⚠️ 空候选不调模型，直接返回空列表（模型对空输入会抛异常）。
    ⚠️ 推理异常时上抛，由 app/core/rag.py 统一降级为「不过滤」，
       保证精排挂掉不影响对话主链路。
    """
    items = [str(p or "") for p in passages]
    if not items:
        return []

    model = get_rerank_model()
    pairs = [[query, p] for p in items]
    scores = model.predict(pairs, show_progress_bar=False, convert_to_numpy=True)

    # 兼容未套 Sigmoid 的旧版模型：logits 可能出现负值或 >1，手动归一化
    normalized: List[float] = []
    for s in scores:
        val = float(s)
        if val < 0.0 or val > 1.0:
            val = 1.0 / (1.0 + pow(2.718281828459045, -val))  # Sigmoid 兜底
        normalized.append(val)

    ranked = sorted(zip(range(len(items)), normalized), key=lambda x: x[1], reverse=True)
    return ranked[:top_n] if top_n and top_n > 0 else ranked


# ==========================================================
# 生命周期辅助
# ==========================================================


def warmup() -> dict:
    """预热：主动加载模型，把「首次对话的长时间等待」提前到启动阶段。

    返回：
        {"embed_ok": bool, "rerank_ok": bool, "dim": int|None, "detail": str}
        失败不抛异常，只回报状态——预热失败不应阻止服务启动（检索时会再试）。
    """
    from app.config import RAG_EMBED_PROVIDER, RAG_RERANK_ENABLED

    info = {"embed_ok": False, "rerank_ok": False, "dim": None, "detail": "", "provider": RAG_EMBED_PROVIDER}
    try:
        # 用一条短文本真实跑一次，确保模型/接口可用（不只检查配置）
        vec = embed_text("预热测试")
        info["embed_ok"] = True
        info["dim"] = len(vec)
        logger.info("[rag.warmup] 向量化就绪（%s 模式，%d 维）", RAG_EMBED_PROVIDER, info["dim"])
    except Exception as e:
        info["detail"] = f"向量化预热失败：{e}"
        logger.warning("[rag.warmup] %s", info["detail"])
        return info

    # 精排关闭时完全不加载（省内存），这里只做状态回报，不算失败
    if RAG_RERANK_ENABLED:
        try:
            rerank("预热", ["候选文本"])
            info["rerank_ok"] = True
        except Exception as e:
            info["detail"] = f"精排模型预热失败：{e}"
            logger.warning("[rag.warmup] %s", info["detail"])

    return info


def unload() -> None:
    """释放两个模型占用的内存（调试用；释放后下次调用会重新加载）。

    ⚠️ 不要在请求处理中调用：模型重载需数十秒，会让对端以为服务挂了。
    """
    global _embed_model, _rerank_model
    with _embed_lock, _rerank_lock:
        _embed_model = None
        _rerank_model = None
    logger.info("[rag.model] 模型已释放")
