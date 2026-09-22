"""Milvus 封装（RAG 的「存储层」）。

职责边界（只管向量库，不碰大模型）：
    - 连接管理（单例，避免每次检索都重建 gRPC 连接）
    - collection 与索引的定义、创建、加载
    - 知识块写入（insert）与删除
    - 混合检索：稠密向量（语义）+ 稀疏 BM25（关键词）→ RRF 融合

字段设计（与课程示例一致，仅按本项目的实际数据放宽长度限制）：
    id            INT64            主键，auto_id 自增
    embedding     FLOAT_VECTOR     稠密向量（gte-large-zh，1024 维），COSINE 度量
    chunks        VARCHAR          知识块原文，开启分词（BM25 的输入字段）
    metadata      JSON             元数据：来源、标题、类型、权限等，可做过滤
    text_sparse   SPARSE_FLOAT_VEC 稀疏向量，由内置 BM25 Function 从 chunks 自动生成

⚠️ 关键坑点（都已在代码里处理，改代码时不要删）：
    1. VARCHAR 的 max_length 单位争议（字节 / 字符）——统一按「字节能装下」取值，
       并在入库前主动截断超长文本，避免插入时整批失败。
    2. BM25 Function 要求输入字段 enable_analyzer=True，且 2.5 以下服务端不支持，
       故服务端必须 ≥ 2.5（推荐 2.6.22，见 docker/milvus-compose.yml）。
    3. 过滤表达式是拼字符串，用户输入必须消毒（见 _safe_like），否则可被注入。
"""
import logging
import threading
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# 连接单例
# ----------------------------------------------------------
_client_lock = threading.Lock()
_client = None

# 各类文本字段长度上限（按字节保守估计：中文 1 字 ≈ 3 字节）
_VARCHAR_MAX_LEN = 8192       # schema 里 VARCHAR 的 max_length
_CHUNK_TEXT_MAX = 1500        # 单块原文实际入库上限（字符数）：1500*3=4500 < 8192，安全


class MilvusNotReady(RuntimeError):
    """Milvus 不可用（服务没起、端口不通、collection 不存在等）。

    单独定义异常类型，便于上层（app/core/rag.py）精确降级：
    检索失败时退化为「纯大模型对话」，而不是把异常抛给客户端。
    """


def get_client():
    """获取 MilvusClient 单例。

    返回：
        MilvusClient 实例

    异常：
        MilvusNotReady —— 依赖未安装，或连接失败（含服务未启动、地址错误）。
    """
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        from app.config import MILVUS_TOKEN, MILVUS_URI, RAG_MILVUS_TIMEOUT

        try:
            from pymilvus import MilvusClient
        except ImportError as e:
            raise MilvusNotReady(
                "未安装 pymilvus：请在 server/ 下执行 "
                ".venv/Scripts/pip.exe install -r requirements-rag.txt"
            ) from e

        try:
            # token 为空时不传该参数，避免部分版本把空串当作非法凭据
            kwargs = {"uri": MILVUS_URI, "timeout": RAG_MILVUS_TIMEOUT}
            if MILVUS_TOKEN:
                kwargs["token"] = MILVUS_TOKEN
            _client = MilvusClient(**kwargs)
        except TypeError:
            # 兼容不接受 timeout 关键字的旧版客户端
            logger.warning("[rag.milvus] 当前 pymilvus 不支持 timeout 参数，使用默认连接参数")
            _client = MilvusClient(uri=MILVUS_URI)
        except Exception as e:
            raise MilvusNotReady(
                f"连接 Milvus 失败（{MILVUS_URI}）：{e}。"
                f"请确认已执行 docker compose -f docker/milvus-compose.yml up -d"
            ) from e

        logger.info("[rag.milvus] 已连接 %s", MILVUS_URI)
        return _client


# ==========================================================
# Schema 与索引
# ==========================================================


def _build_schema(dim: int, analyzer_type: str = "chinese"):
    """构造 collection schema。

    参数：
        dim:           稠密向量维度（由向量化模型决定，不写死 1024）
        analyzer_type: BM25 用的分词器类型；空字符串表示用服务端默认分词器
    返回：
        CollectionSchema 对象

    ⚠️ create_schema 用 MilvusClient 的静态方法调用（官方推荐写法）；
       两个开关含义：
         auto_id=True            —— 主键由服务端自增，入库时不用自己造 id
         enable_dynamic_field=True —— 允许插入未在 schema 中声明的字段（兼容性更好）

    ⚠️ 分词器是 BM25 检索质量的关键：
       服务端默认分词器按空白/标点切分，中文长句会被切成一整串或碎片，
       导致 BM25 只靠「AI」这类短词命中，**短文本块会靠长度优势霸榜**
       （实测：「首页课程分类「AI·数字技能」（标识 ai）。」这种 20 字小块的
       BM25 排名会超过真正相关的长块，把正确答案挤出候选）。
       指定 analyzer_params={"type": "chinese"} 后服务端用 jieba 分词，
       中文关键词命中才符合预期。
    """
    from pymilvus import DataType, Function, FunctionType, MilvusClient

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dim)

    # 按配置决定是否指定中文分词器（留空则用服务端默认）
    chunk_field = {
        "field_name": "chunks",
        "datatype": DataType.VARCHAR,
        "max_length": _VARCHAR_MAX_LEN,
        "enable_analyzer": True,        # ⚠️ BM25 的前提：该字段需开启分词
        "description": "知识块原文",
    }
    if analyzer_type:
        chunk_field["analyzer_params"] = {"type": analyzer_type}
    schema.add_field(**chunk_field)

    schema.add_field(field_name="metadata", datatype=DataType.JSON, description="来源/标题/类型/权限等")
    schema.add_field(
        field_name="text_sparse",
        datatype=DataType.SPARSE_FLOAT_VECTOR,
        description="BM25 稀疏向量，由内置 Function 从 chunks 自动生成",
    )

    # 内置 BM25：写入时自动把 chunks 转成稀疏向量，无需手工计算
    bm25 = Function(
        name="text_bm25_emb",
        input_field_names=["chunks"],
        output_field_names=["text_sparse"],
        function_type=FunctionType.BM25,
    )
    schema.add_function(bm25)
    return schema


def _build_index_params(client, dim: int):
    """构造索引参数（含稠密 / 稀疏两路索引）。"""
    index_params = client.prepare_index_params()

    index_params.add_index(field_name="id", index_type="AUTOINDEX")
    index_params.add_index(
        field_name="embedding",
        index_name="text_dense_index",
        index_type="AUTOINDEX",
        metric_type="COSINE",     # 与归一化向量配套，值越大越相似
    )
    index_params.add_index(
        field_name="text_sparse",
        index_name="text_sparse_index",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
        # DAAT_MAXSCORE：动态剪枝，长文本下比 TAAT_NAIVE 快，官方推荐默认
        params={"inverted_index_algo": "DAAT_MAXSCORE"},
    )
    return index_params


def collection_exists() -> bool:
    """判断目标 collection 是否已存在。"""
    from app.config import MILVUS_COLLECTION

    try:
        return get_client().has_collection(collection_name=MILVUS_COLLECTION)
    except Exception as e:
        raise MilvusNotReady(f"查询 collection 失败：{e}") from e


def ensure_collection(dim: int, recreate: bool = False) -> Dict:
    """确保 collection 存在并可用；不存在则按当前模型维度创建。

    参数：
        dim:      稠密向量维度（建议传 embedding.embedding_dim() 的真实值）
        recreate: True = 先删后建（⚠️ 会清空全部已入库知识，需重新灌库）
    返回：
        {"existed": bool, "created": bool, "loaded": bool, "collection": 名称, "analyzer": 实际分词器}
    """
    from app.config import MILVUS_COLLECTION, RAG_ANALYZER_TYPE

    client = get_client()
    existed = client.has_collection(collection_name=MILVUS_COLLECTION)

    if existed and recreate:
        # ⚠️ 破坏性操作：仅在 --rebuild 显式触发时执行
        logger.warning("[rag.milvus] 重建 collection，将清空已有知识：%s", MILVUS_COLLECTION)
        client.drop_collection(collection_name=MILVUS_COLLECTION)
        existed = False

    created = False
    used_analyzer = RAG_ANALYZER_TYPE
    if not existed:
        index_params = _build_index_params(client, dim)
        try:
            client.create_collection(
                collection_name=MILVUS_COLLECTION,
                schema=_build_schema(dim, RAG_ANALYZER_TYPE),
                index_params=index_params,
            )
        except Exception as e:
            # ⚠️ 兼容降级：更早版本的服务端不支持指定分词器，
            #    此时退回服务端默认分词器（BM25 中文效果会变差，但功能可用），
            #    而不是直接让灌库失败。
            if not RAG_ANALYZER_TYPE:
                raise
            logger.warning(
                "[rag.milvus] 指定分词器 %s 不被服务端支持（%s），降级为默认分词器",
                RAG_ANALYZER_TYPE, str(e)[:120],
            )
            used_analyzer = ""
            client.create_collection(
                collection_name=MILVUS_COLLECTION,
                schema=_build_schema(dim, ""),
                index_params=index_params,
            )
        created = True
        logger.info("[rag.milvus] 已创建 collection %s（dim=%s，分词器=%s）",
                    MILVUS_COLLECTION, dim, used_analyzer or "服务端默认")

    loaded = _ensure_loaded(client)
    return {
        "existed": existed,
        "created": created,
        "loaded": loaded,
        "collection": MILVUS_COLLECTION,
        "analyzer": used_analyzer or "default",
    }


def _ensure_loaded(client) -> bool:
    """确保 collection 处于 loaded 状态（未 load 时检索会直接报错）。

    ⚠️ 服务重启后 collection 可能处于未加载状态，这里主动 load 一次；
       已加载时重复调用是幂等的，不会重复加载。
    """
    from app.config import MILVUS_COLLECTION

    try:
        client.load_collection(collection_name=MILVUS_COLLECTION)
        return True
    except Exception as e:
        logger.warning("[rag.milvus] collection 加载失败：%s", e)
        return False


# ==========================================================
# 写入
# ==========================================================


def _clip_text(text: str) -> str:
    """入库前截断超长文本，避免单条记录撑爆 VARCHAR 上限导致整批插入失败。"""
    s = str(text or "").strip()
    if len(s) > _CHUNK_TEXT_MAX:
        logger.warning("[rag.milvus] 知识块超长（%d 字），已截断至 %d 字", len(s), _CHUNK_TEXT_MAX)
        return s[:_CHUNK_TEXT_MAX]
    return s


def insert_chunks(chunks: Sequence[Dict], batch_size: int = 64) -> int:
    """批量写入知识块。

    参数：
        chunks: 形如 [{"text": "原文", "embedding": [float...], "metadata": {...}}]
                ⚠️ embedding 必填且维度必须与建表时一致，否则整批失败
        batch_size: 每批写入条数（默认 64：单批过大易超时，过小则往返次数多）
    返回：
        实际写入条数

    异常：
        MilvusNotReady —— 连接/写入失败（含维度不匹配，会有明确提示）
    """
    if not chunks:
        return 0

    from app.config import MILVUS_COLLECTION

    client = get_client()
    written = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        rows = []
        for item in batch:
            text = _clip_text(item.get("text"))
            if not text:
                continue  # 空块直接跳过，不占用向量库空间
            rows.append({
                "embedding": item["embedding"],
                "chunks": text,
                "metadata": item.get("metadata") or {},
            })

        if not rows:
            continue

        try:
            client.insert(collection_name=MILVUS_COLLECTION, data=rows)
            written += len(rows)
        except Exception as e:
            # 维度不一致是最常见的失败原因，单独给出可操作的提示
            msg = str(e)
            hint = ""
            if "dimension" in msg.lower() or "dim" in msg.lower():
                hint = "。⚠️ 向量维度与建表时不符，通常是更换了向量化模型 —— 需先重建 collection"
            raise MilvusNotReady(f"写入第 {start + 1}~{start + len(rows)} 条失败：{e}{hint}") from e

    logger.info("[rag.milvus] 写入完成，共 %d 条", written)
    return written


def delete_by_source(source: str) -> int:
    """按 metadata 中的 source 字段删除旧知识块（重新灌库前清理用）。

    返回：
        报告删除的条数（Milvus 的 delete 为异步生效，返回值为删除请求数）

    ⚠️ 过滤值做了消毒处理，避免来源名里的引号破坏表达式。
    """
    from app.config import MILVUS_COLLECTION

    safe = _escape_expr_value(source)
    if not safe:
        return 0
    expr = f'metadata["source"] == "{safe}"'
    try:
        res = get_client().delete(collection_name=MILVUS_COLLECTION, filter=expr)
    except Exception as e:
        raise MilvusNotReady(f"按来源删除失败：{e}") from e

    # 不同版本返回结构不同：列表 / 字典 / 计数，统一兜底
    try:
        if isinstance(res, dict):
            return int(res.get("delete_count", 0) or 0)
        if isinstance(res, list):
            return len(res)
    except Exception:
        pass
    return 0


def count() -> int:
    """统计当前 collection 内的知识块总数（用 query 计数，避免统计延迟问题）。"""
    from app.config import MILVUS_COLLECTION

    try:
        res = get_client().query(
            collection_name=MILVUS_COLLECTION,
            filter="id >= 0",                     # 全量条件：主键恒成立
            output_fields=["count(*)"],
        )
    except Exception as e:
        raise MilvusNotReady(f"统计条数失败：{e}") from e

    # 返回形如 [{'count(*)': 123}]
    if res and isinstance(res[0], dict):
        for v in res[0].values():
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return 0


# ==========================================================
# 检索
# ==========================================================


def _escape_expr_value(value: str) -> str:
    """转义过滤表达式里的字符串值。

    ⚠️ 安全点：Milvus 过滤表达式是拼接出来的，值里的双引号/反斜杠会让表达式
       结构被破坏甚至被注入，因此统一做白名单过滤 + 截断。
    """
    cleaned = str(value or "").replace("\\", "").replace('"', "").replace("%", "")
    return cleaned.strip()[:64]


def _safe_like(keyword: str) -> str:
    """把用户关键词转成 Milvus LIKE 片段（形如 chunks like "%病假%"）。

    ⚠️ 安全点：只保留中英文、数字与空格，其余字符一律剔除，
       防止 `"` 提前闭合字符串造成表达式注入。
    """
    import re

    kept = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", str(keyword or ""))[:32]
    if not kept:
        return ""
    return f'chunks like "%{kept}%"'


def build_filter(keyword: str = "", extra: Optional[str] = None) -> str:
    """拼装过滤表达式（各条件 AND 相连，为空则返回空串表示不过滤）。

    参数：
        keyword: 用户问题里提炼的关键词（可选，命中原文才算候选）
        extra:   额外表达式，如 'metadata["type"] == "course"'（内部调用，勿传用户输入）
    说明：
        课程示例里用 chunks like "%病假%" 做硬过滤，实际会「关键词不在原文里就
        一条都搜不到」，召回反而变差。本项目默认【不过滤】，
        把关键词约束留给 BM25 那一路去表达（更符合混合检索的本意）。
    """
    parts = []
    if keyword:
        like = _safe_like(keyword)
        if like:
            parts.append(like)
    if extra:
        parts.append(f"({extra})")
    return " and ".join(parts)


def hybrid_search(
    query: str,
    query_vector: Sequence[float],
    limit: int = 20,
    candidate_limit: int = 30,
    filter_expr: str = "",
) -> List[Dict]:
    """混合检索：稠密语义 + 稀疏 BM25，用 RRF 融合两路排名。

    参数：
        query:          用户原始问题（BM25 那一路直接用原文）
        query_vector:   问题向量（稠密那一路用）
        limit:          最终返回条数
        candidate_limit:每一路各自先召回多少条（再融合，故需大于 limit）
        filter_expr:    过滤表达式（由 build_filter 生成，不直接吃用户输入）
    返回：
        [{"id":..., "score":..., "text":..., "metadata": {...}}, ...] 按融合分降序

    异常：
        MilvusNotReady —— 连接失败 / 服务端不支持混合检索
    """
    from app.config import MILVUS_COLLECTION
    from pymilvus import AnnSearchRequest, Function, FunctionType

    client = get_client()

    # ---------- 第 1 路：稠密向量语义检索 ----------
    dense = {
        "data": [list(query_vector)],
        "anns_field": "embedding",
        "param": {"nprobe": 10},        # 探测的倒排桶数，越大越准越慢
        "limit": candidate_limit,
        "expr": filter_expr or None,    # None 表示不过滤
    }
    # ---------- 第 2 路：BM25 全文检索（稀疏） ----------
    sparse = {
        "data": [query],                # ⚠️ 稀疏那一路传原始文本，由服务端分词
        "anns_field": "text_sparse",
        "param": {},                    # 稀疏检索参数留空，用默认倒排配置
        "limit": candidate_limit,
        "expr": filter_expr or None,
    }

    try:
        reqs = [AnnSearchRequest(**dense), AnnSearchRequest(**sparse)]

        # RRF（Reciprocal Rank Fusion）：按排名倒数求和融合，无需调权重
        ranker = Function(
            name="rrf",
            input_field_names=[],       # ⚠️ RRF 必须为空列表，官方约定
            function_type=FunctionType.RERANK,
            params={"reranker": "rrf", "k": 60},
        )

        raw = client.hybrid_search(
            collection_name=MILVUS_COLLECTION,
            reqs=reqs,
            ranker=ranker,
            limit=limit,
            output_fields=["id", "chunks", "metadata"],
        )
    except Exception as e:
        raise MilvusNotReady(f"混合检索失败：{e}") from e

    return _normalize_hits(raw)


def dense_search(
    query_vector: Sequence[float],
    limit: int = 20,
    filter_expr: str = "",
) -> List[Dict]:
    """纯稠密向量检索（混合检索不可用时的降级路径）。

    用途：服务端版本过低（不支持 BM25 Function）或稀疏索引异常时兜底，
          保证「还能检索」，而不是直接退化成纯大模型对话。
    """
    from app.config import MILVUS_COLLECTION

    client = get_client()
    try:
        raw = client.search(
            collection_name=MILVUS_COLLECTION,
            data=[list(query_vector)],
            anns_field="embedding",
            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
            limit=limit,
            filter=filter_expr or "",
            output_fields=["id", "chunks", "metadata"],
        )
    except Exception as e:
        raise MilvusNotReady(f"向量检索失败：{e}") from e

    return _normalize_hits(raw)


def _normalize_hits(raw) -> List[Dict]:
    """把 pymilvus 的原始返回统一成稳定结构。

    ⚠️ 不同版本/不同检索方式返回的命中项，有的是 dict、有的是带 .entity 属性的
       对象；这里两种都兼容，避免上层到处写 hasattr 判断。
    """
    out: List[Dict] = []
    if not raw:
        return out

    # search / hybrid_search 均返回「按查询分组的二维结构」，我们只发一个查询
    hits = raw[0] if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], (list, tuple)) else raw

    for hit in hits or []:
        if isinstance(hit, dict):
            entity = hit.get("entity") or {}
            score = hit.get("distance", hit.get("score", 0.0))
            hid = hit.get("id")
        else:
            entity = getattr(hit, "entity", None) or {}
            score = getattr(hit, "distance", getattr(hit, "score", 0.0))
            hid = getattr(hit, "id", None)
            # 兼容 ORM 风格对象：entity 需要 get()
            if not isinstance(entity, dict) and hasattr(entity, "get"):
                entity = {k: entity.get(k) for k in ("chunks", "metadata")}

        text = (entity or {}).get("chunks", "") if isinstance(entity, dict) else ""
        meta = (entity or {}).get("metadata", {}) if isinstance(entity, dict) else {}
        out.append({
            "id": hid,
            "score": float(score or 0.0),
            "text": text or "",
            "metadata": meta or {},
        })
    return out


def health() -> Dict:
    """健康检查：返回 Milvus 连通性、collection 状态与条数。

    返回（全部为可 JSON 序列化的基础类型，供 /rag/status 接口直接输出）：
        {"ok": bool, "uri":..., "collection":..., "exists":..., "loaded":..., "count":..., "error": ""}
    """
    from app.config import MILVUS_COLLECTION, MILVUS_URI

    info = {
        "ok": False,
        "uri": MILVUS_URI,
        "collection": MILVUS_COLLECTION,
        "exists": False,
        "count": 0,
        "error": "",
    }
    try:
        client = get_client()
        info["exists"] = bool(client.has_collection(collection_name=MILVUS_COLLECTION))
        if info["exists"]:
            info["count"] = count()
            state = client.get_load_state(collection_name=MILVUS_COLLECTION)
            # 不同版本返回 dict 或枚举，统一转成字符串便于排查
            info["load_state"] = str(state)
        info["ok"] = True
    except Exception as e:
        info["error"] = str(e)
    return info
