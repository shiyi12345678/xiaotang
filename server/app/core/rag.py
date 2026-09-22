"""RAG 检索入口（RAG 的「编排层」）。

对外只暴露三个东西：
    retrieve()          —— 同步检索，返回结构化结果（含降级信息）
    retrieve_async()    —— 异步包装，供 async 路由直接 await
    build_system_prompt() —— 把检索结果拼成注入大模型的 system 提示词

核心设计原则：【检索永远不能让对话挂掉】
    任何一步失败（Milvus 没起、模型没下、索引异常、Neo4j 没连上……）都只记日志
    并降级为「不带知识块」的普通对话，绝不向上抛异常。原因：
      - 对话主链路是已上线的既有功能，不能因为新增的检索组件而不可用；
      - 学生用户在联调时最怕的是「AI 助教整个不能用」，而不是「回答里没有引用」。

检索流程：
    问题 ┬→ 【向量检索】向量化 → 混合检索（稠密 + BM25，RRF 融合）
         │                → 精排（CrossEncoder，Sigmoid 归一到 0~1）
         │                → 阈值过滤 + 去重 + 截断 → Top N 知识块
         └→ 【图谱检索】实体链接 → 子图多跳扩展 → 事实文本化（见 app/core/graph_rag.py）
    两路结果合并后一起注入提示词：图谱事实在前（精确、结构化），知识块在后（语义补充）。
    ⚠️ 两路互相独立：任一不可用都不影响另一路，两路都不可用才退化为纯对话。
"""
import asyncio
import hashlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _config():
    """集中读取配置（延迟导入：避免子脚本导入顺序导致的配置未加载）。"""
    from app import config

    return config


# ==========================================================
# 同步检索
# ==========================================================


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    filter_extra: Optional[str] = None,
) -> Dict:
    """检索与问题最相关的知识（向量知识块 + 知识图谱事实）。

    参数：
        query:        用户问题原文
        top_k:        向量知识块最终返回条数；None 时取配置 RAG_TOP_K
                      （图谱事实条数由 GRAPH_TOP_K 单独控制，不占用这个额度）
        filter_extra: 额外过滤表达式（如按课程分类过滤），内部调用专用，勿传用户输入
    返回：
        {
          "contexts": [{"text":..., "score":..., "source":..., "title":..., "kind":...}, ...],
          "mode": "hybrid" | "dense" | "none",   # 向量检索实际走通的方式
          "graphMode": "graph" | "none",         # 图谱检索是否命中
          "graph": {...},                        # 图谱检索明细（命中实体、事实、跳数）
          "used": bool,                          # 是否真的检索到了可用知识
          "error": ""                            # 失败原因（已降级，不影响对话）
        }

    检索顺序即注入提示词的先后：
        图谱事实在前（结构化、精确、可多跳），向量知识块在后（非结构化语义召回）。

    ⚠️ 本函数是同步阻塞的（模型推理 + 网络调用），
       在 async 环境务必用 retrieve_async / asyncio.to_thread 调用。
    """
    cfg = _config()

    result = {
        "contexts": [], "mode": "none", "graphMode": "none",
        "graph": {}, "used": False, "error": "",
    }

    question = str(query or "").strip()
    if not question:
        result["error"] = "查询为空"
        return result

    # ---- 第 1 路：向量检索（RAG_ENABLED=false 时整体跳过） ----
    vector_contexts: List[Dict] = []
    if cfg.RAG_ENABLED:
        vector_contexts, result["mode"], vector_error = _vector_retrieve(
            question, top_k or cfg.RAG_TOP_K, cfg, filter_extra
        )
    else:
        vector_error = "RAG 未启用（RAG_ENABLED=false）"

    # ---- 第 2 路：图谱检索（GraphRAG；失败/没命中都只降级） ----
    graph_contexts: List[Dict] = []
    graph_error = ""
    try:
        from app.core import graph_rag

        graph_result = graph_rag.retrieve_graph(question)
        result["graph"] = graph_result
        if graph_result.get("used"):
            result["graphMode"] = graph_result.get("mode") or "graph"
            graph_contexts = graph_rag.to_contexts(graph_result.get("facts") or [])
        else:
            graph_error = graph_result.get("error") or ""
    except Exception as e:                       # noqa: BLE001 - 图谱是增强项，绝不能影响对话
        graph_error = f"图谱检索异常：{e}"
        logger.warning("[rag] %s", graph_error)

    # ---- 合并：图谱事实优先，向量知识块随后 ----
    result["contexts"] = graph_contexts + vector_contexts
    result["used"] = bool(result["contexts"])
    if not result["used"]:
        result["error"] = vector_error or graph_error or "未检索到可用知识"
    return result


def _vector_retrieve(question: str, k: int, cfg, filter_extra: Optional[str]) -> tuple:
    """向量检索主体（从 retrieve 里拆出来的，逻辑与改造前完全一致）。

    参数：
        question:     用户问题
        k:            最终返回条数
        cfg:          配置模块
        filter_extra: 额外过滤表达式
    返回：
        (contexts, mode, error) —— 失败时 contexts 为空、error 说明原因
    """
    if k <= 0:
        return [], "none", "RAG_TOP_K 配置非法"

    # ---- 第 1 步：问题向量化 ----
    try:
        from app.core import embedding

        query_vector = embedding.embed_text(question)
    except Exception as e:
        logger.warning("[rag] 向量化失败：%s", e)
        return [], "none", f"向量化失败：{e}"

    # ---- 第 2 步：混合检索（失败自动降级为纯向量检索）----
    mode = "hybrid"
    try:
        from app.core import milvus_store

        filter_expr = milvus_store.build_filter(extra=filter_extra)
        try:
            hits = milvus_store.hybrid_search(
                query=question,
                query_vector=query_vector,
                limit=cfg.RAG_SEARCH_LIMIT,
                candidate_limit=cfg.RAG_CANDIDATE_LIMIT,
                filter_expr=filter_expr,
            )
        except milvus_store.MilvusNotReady as e:
            # 混合检索不可用（服务端版本低 / 稀疏索引异常）→ 退纯向量检索
            logger.warning("[rag] 混合检索不可用，降级为纯向量检索：%s", e)
            hits = milvus_store.dense_search(
                query_vector=query_vector,
                limit=cfg.RAG_SEARCH_LIMIT,
                filter_expr=filter_expr,
            )
            mode = "dense"
    except Exception as e:
        logger.warning("[rag] 检索失败：%s", e)
        return [], "none", f"检索失败：{e}"

    if not hits:
        return [], mode, "知识库无命中（可能尚未灌库）"

    # ---- 第 3 步：精排（可选；失败则沿用检索排序，不中断）----
    hits = _apply_rerank(question, hits, cfg)

    # ---- 第 4 步：过滤 + 去重 + 截断 ----
    return _finalize(hits, k, cfg), mode, ""


def _apply_rerank(question: str, hits: List[Dict], cfg) -> List[Dict]:
    """对候选块做精排，返回按相关性降序、且带上 score 的新列表。

    ⚠️ 精排是可选项（RAG_RERANK_ENABLED=false 时跳过），
       且任何异常都只降级为「保持原顺序」，因为精排只是锦上添花。
    """
    if not cfg.RAG_RERANK_ENABLED:
        return hits

    try:
        from app.core import embedding

        passages = [h.get("text", "") for h in hits]
        ranked = embedding.rerank(question, passages)

        reranked: List[Dict] = []
        for idx, score in ranked:
            if 0 <= idx < len(hits):
                item = dict(hits[idx])
                item["score"] = float(score)          # 用精排分数覆盖检索分数
                reranked.append(item)
        return reranked or hits
    except Exception as e:
        logger.warning("[rag] 精排失败，沿用检索排序：%s", e)
        return hits


def _finalize(hits: List[Dict], k: int, cfg) -> List[Dict]:
    """阈值过滤 → 去重 → 截断，得到最终给大模型的知识块。

    参数：
        hits: 已排序的候选（精排后分数为 0~1 概率；未精排时为 COSINE/融合分）
        k:    最终条数上限
        cfg:  配置模块

    返回：
        [{"text":..., "score":..., "source":..., "title":..., "type":...}, ...]
    """
    # ---- 1) 阈值过滤（未精排时分数口径不同，故只在精排后生效）----
    threshold = float(cfg.RAG_RERANK_THRESHOLD or 0.0)
    if cfg.RAG_RERANK_ENABLED and threshold > 0:
        passed = [h for h in hits if float(h.get("score", 0.0)) >= threshold]
        if not passed and cfg.RAG_KEEP_WHEN_EMPTY and hits:
            # 全部低于阈值时的策略：
            #   保留分数最高的 1 条（宁可给点参考，也不让 AI 完全没依据），
            #   由 RAG_KEEP_WHEN_EMPTY 控制，默认开启。
            passed = hits[:1]
            logger.info("[rag] 全部候选低于阈值 %.2f，保留 Top1（可关闭 RAG_KEEP_WHEN_EMPTY）", threshold)
        hits = passed

    # ---- 2) 去重（同一段文本被多条记录命中时只保留一份）----
    seen = set()
    deduped: List[Dict] = []
    for h in hits:
        text = str(h.get("text") or "").strip()
        if not text:
            continue
        fingerprint = hashlib.md5(text.encode("utf-8")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        h = dict(h)
        h["text"] = text[:cfg.RAG_CONTEXT_MAX_CHARS]   # 单块截断，防止 prompt 过长
        meta = h.get("metadata") or {}
        h["source"] = meta.get("source", "")
        h["title"] = meta.get("title", "")
        h["type"] = meta.get("type", "")
        deduped.append(h)

    # ---- 3) 截断到 k 条 ----
    return deduped[:k]


async def retrieve_async(query: str, top_k: Optional[int] = None, filter_extra: Optional[str] = None) -> Dict:
    """retrieve 的异步包装。

    ⚠️ 必须走线程池：向量化是 CPU 密集的同步调用，直接在事件循环里跑
       会阻塞所有并发请求（尤其 WebSocket 流式对话会被卡住）。
    """
    return await asyncio.to_thread(retrieve, query, top_k, filter_extra)


# ==========================================================
# 提示词拼装
# ==========================================================


def build_system_prompt(contexts: List[Dict]) -> str:
    """把检索结果拼成注入大模型的 system 提示词。

    参数：
        contexts: retrieve() 返回的 contexts 列表；
                  kind="graph" 的条目来自知识图谱，其余来自向量知识库
    返回：
        提示词字符串；contexts 为空时返回空串（调用方据此跳过注入）

    提示词结构：
        有图谱事实时 —— 先「知识图谱事实」（结构化、精确、优先级最高），
                        再「参考资料」（知识库原文片段，补充细节）；
        没有图谱事实时 —— 与原实现【完全一致】的单段结构，
                          保证未接入 GraphRAG 时的行为一字不变。
    """
    if not contexts:
        return ""

    cfg = _config()
    graph_ctx = [c for c in contexts if c.get("kind") == "graph"]
    doc_ctx = [c for c in contexts if c.get("kind") != "graph"]

    # ---- 无图谱事实：保持原有提示词结构（既有行为不受影响）----
    if not graph_ctx:
        return _truncate_prompt(_reference_lines(doc_ctx, standalone=True), cfg)

    lines = [
        "以下是系统检索到的资料，由两部分组成：",
        "（1）知识图谱事实：从职位库与招聘知识库抽取的结构化事实，精确度高，优先采用；",
        "（2）参考资料：知识库原文片段，用于补充细节与原始表述。",
        "回答要求：",
        "1. 优先依据资料作答，资料能答复时不要凭空发挥；",
        "2. 知识图谱事实与参考资料冲突时，以知识图谱事实为准；",
        "3. 资料不足以回答时，直接说明「现有资料未涵盖」，再基于通用知识补充，并明确标注哪部分是资料外的内容；",
        "4. 不要编造资料中不存在的职位名称、公司、薪资、经验/学历要求或面试题；",
        "5. 引用资料时可用「据《标题》」的形式说明来源，不要输出内部字段名或分数。",
        "",
        "=== 知识图谱事实开始 ===",
    ]
    for i, ctx in enumerate(graph_ctx, start=1):
        lines.append(f"【事实 {i}】{str(ctx.get('text') or '').strip()}")
        cite = "、".join(ctx.get("sources") or [])
        if cite:
            lines.append(f"（出处：{cite}）")
    lines.append("=== 知识图谱事实结束 ===")

    if doc_ctx:
        lines.append("")
        lines.extend(_reference_lines(doc_ctx, standalone=False))

    return _truncate_prompt(lines, cfg)


def _reference_lines(contexts: List[Dict], standalone: bool) -> List[str]:
    """渲染「参考资料」段落。

    参数：
        contexts:   向量知识块列表
        standalone: True = 作为唯一内容（带完整开场白，与改造前一致）；
                    False = 作为「知识图谱事实」之后的补充段落
    返回：
        提示词行列表
    """
    if standalone:
        lines = [
            "以下是与用户问题相关的参考资料（来自招聘知识库检索：职位 JD、公司信息、面试题与参考答案，按相关度排序）。",
            "回答要求：",
            "1. 优先依据参考资料作答，参考资料能答复时不要凭空发挥；",
            "2. 参考资料不足以回答时，直接说明「现有资料未涵盖」，再基于通用知识补充，并明确标注哪部分是资料外的内容；",
            "3. 不要编造参考资料中不存在的职位、公司、薪资或面试题；",
            "4. 引用资料时可用「据《标题》」的形式说明来源，不要输出内部字段名或分数。",
            "",
        ]
    else:
        lines = ["=== 参考资料开始（知识库原文片段）==="]

    for i, ctx in enumerate(contexts, start=1):
        title = ctx.get("title") or "未命名资料"
        source = ctx.get("source") or "未知来源"
        lines.append(f"【资料 {i}】《{title}》（来源：{source}）")
        lines.append(str(ctx.get("text") or "").strip())
        lines.append("")

    lines.append("=== 参考资料结束 ===")
    return lines


def _truncate_prompt(lines: List[str], cfg) -> str:
    """拼装并做长度保护（超过上限即截断，避免撑爆上游模型上下文窗口）。"""
    prompt = "\n".join(lines).strip()
    limit = cfg.RAG_PROMPT_MAX_CHARS
    if limit and len(prompt) > limit:
        logger.warning("[rag] 提示词过长（%d 字），截断至 %d 字", len(prompt), limit)
        prompt = prompt[:limit] + "\n…（参考资料过长已截断）"
    return prompt
