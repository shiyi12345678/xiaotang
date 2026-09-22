"""Neo4j 封装（GraphRAG 的「图存储层」）。

职责边界（只管图数据库，不碰大模型、不碰向量库）：
    - 连接管理（Driver 单例，避免每次检索都重建连接）
    - 约束与索引（Entity/Chunk 主键唯一、实体名全文索引）
    - 图谱写入（节点 / 关系 / 溯源边，全部 MERGE，可反复执行不产生重复）
    - 实体链接（把用户问题映射到图里的实体，就是 GraphRAG 里的 entity linking）
    - 邻域扩展（按跳数取子图，支撑多跳问答）
    - 健康检查与统计

图模型（实体节点统一带 :Entity 标签，具体类型作为第二标签，
        这样「统一遍历」和「按类型查询」都不用改查询语句）：
    (:Entity:Job      {id, name, type, aliases, ...业务属性})
    (:Entity:Company  {id, name, type, ...})
    (:Chunk           {id, title, source, type, text})  知识块（与 Milvus 同源同步）

⚠️ 本项目已从「学习类 App」改造为招聘 App「直聘通」，本文件里所有课程域的
   类型/关系都已换成招聘域（职位 / 公司 / 城市 / 职能 / 技能 / 面试题 / 行业 /
   平台规则 / 面试题库）。之所以必须改这一层：图谱与 Milvus 是同一份知识的两个
   副本，向量侧已换成 recruit_jobs.json / recruit_content.json，
   图侧若还留着课程实体，AI 求职助手会在问「AI 数字技能是什么」这类问题时
   把「某课程属于某分类」当成事实注入提示词 —— 对招聘 App 是直接的内容事故。

关系（语义关系）：
    (Job)-[:BELONGS_TO]->(Category)         职位属于哪个职能（二级职能→一级方向同理）
    (Job)-[:AT_COMPANY]->(Company)          职位由哪家公司招聘
    (Job)-[:IN_CITY]->(City)                职位的工作城市
    (Job)-[:REQUIRES]->(Skill)              职位要求什么技能
    (Question)-[:TESTS]->(Skill)            面试题考查哪个技能
    (Question)-[:BELONGS_TO]->(Category)    面试题属于哪个职能方向
    (Question)-[:IN_BANK]->(QuestionBank)   面试题收录在面试题库
    (Company)-[:IN_INDUSTRY]->(Industry)    公司属于哪个行业
    (Company)-[:IN_CITY]->(City)            公司的所在城市
    (Guide)-[:APPLIES_TO]->(Job)            平台规则适用于哪些职位（如内推规则→内推职位）
    (Chunk)-[:MENTIONS]->(Entity)           某知识块提到了某实体（事实溯源）
    LLM 抽取的关系：RELATES_TO / PART_OF / INCLUDES / SUPPORTS / PROVIDES / USES

⚠️ 安全要点（改代码时不要删）：
    1. Cypher 一律参数化：用户问题、实体名、属性值全部走参数，绝不拼进语句；
    2. 标签与关系类型在 Cypher 里【无法】参数化（语法限制），
       因此先用白名单常量校验，再拼接，杜绝注入；
    3. 只有显式调用 reset_graph()（对应 CLI 的 --rebuild）才会清空全图，
       正常写入路径不做任何破坏性操作。
"""
import hashlib
import logging
import re
import threading
import time
from typing import Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# 白名单常量：实体类型 ↔ 图标签、允许的关系类型
# ----------------------------------------------------------
# 实体类型（业务侧叫法）→ Neo4j 标签
TYPE_TO_LABEL = {
    "job": "Job",              # 职位（招聘 App 的第一等实体）
    "company": "Company",      # 招聘公司
    "city": "City",            # 工作城市
    "category": "Category",    # 职能方向（一级方向 + 二级职能）
    "skill": "Skill",          # 技能（面试题标签 + 职位要求里出现的技术栈）
    "question": "Question",    # 面试题（含参考答案）
    "industry": "Industry",    # 行业
    "guide": "Guide",          # 平台规则与求职/招聘建议
    "bank": "QuestionBank",    # 面试题库（聚合节点，回答「面试常考什么」这类问法）
}
# 兜底标签：类型没登记时用它，保证节点仍能被统一遍历
_FALLBACK_LABEL = "Concept"
_ALLOWED_LABELS = frozenset(list(TYPE_TO_LABEL.values()) + [_FALLBACK_LABEL])

# 允许写入的关系类型（拼进 Cypher 前必须过这张表）
REL_TYPES = frozenset({
    "BELONGS_TO",   # 职位 → 职能；面试题 → 职能；二级职能 → 一级方向
    "AT_COMPANY",   # 职位 → 公司
    "IN_CITY",      # 职位 / 公司 → 城市
    "REQUIRES",     # 职位 → 技能
    "TESTS",        # 面试题 → 技能
    "IN_INDUSTRY",  # 公司 → 行业
    "IN_BANK",      # 面试题 → 面试题库
    "APPLIES_TO",   # 平台规则 → 适用职位（如内推规则 → 内推职位）
    "MENTIONS",     # 知识块 → 实体（溯源，不参与事实渲染）
    "RELATES_TO", "PART_OF", "PROVIDES", "USES", "INCLUDES", "SUPPORTS",
})
# 溯源边：只表示「出处」，不代表语义关系，取子图时要排除
PROVENANCE_REL = "MENTIONS"

# 属性值保护：过长的字符串不进图（避免把整篇文档塞成属性）
_MAX_VALUE_CHARS = 400
_MAX_LIST_ITEMS = 20


class GraphNotReady(RuntimeError):
    """图谱库不可用（驱动没装、服务没起、账号密码不对、查询失败等）。

    单独定义异常类型，便于上层（app/core/graph_rag.py）精确降级：
    图谱不可用时退化为「只用向量检索」，而不是把异常抛给客户端。
    """


# ----------------------------------------------------------
# 连接单例
# ----------------------------------------------------------
_driver_lock = threading.Lock()
_driver = None


def get_driver():
    """获取 Neo4j Driver 单例。

    返回：
        neo4j.Driver 实例

    异常：
        GraphNotReady —— 驱动未安装 / 密码未配置 / 连接或鉴权失败。
    """
    global _driver
    if _driver is not None:
        return _driver

    with _driver_lock:
        if _driver is not None:
            return _driver

        from app.config import (
            GRAPH_NEO4J_POOL_SIZE, GRAPH_NEO4J_TIMEOUT,
            NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER,
        )

        try:
            from neo4j import GraphDatabase
        except ImportError as e:
            raise GraphNotReady(
                "未安装 neo4j 驱动：请在 server/ 下执行 "
                ".venv/Scripts/pip.exe install -r requirements-rag.txt"
            ) from e

        if not NEO4J_PASSWORD:
            raise GraphNotReady(
                "NEO4J_PASSWORD 未配置：请在 server/.env 中填写 Neo4j 密码"
            )

        try:
            _driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                connection_timeout=GRAPH_NEO4J_TIMEOUT,
                max_connection_pool_size=GRAPH_NEO4J_POOL_SIZE,
            )
            # verify_connectivity 会真正建一次连接，把「地址错 / 服务没起 / 密码错」
            # 这类问题在这里就暴露出来，而不是等到用户提问时才发现
            _driver.verify_connectivity()
        except Exception as e:
            _driver = None
            raise GraphNotReady(
                f"连接 Neo4j 失败（{NEO4J_URI}，用户 {NEO4J_USER}）：{e}。"
                f"请确认：1) Neo4j 服务已启动（sc query neo4j）；"
                f"2) .env 里 NEO4J_URI / NEO4J_PASSWORD 与实际情况一致"
            ) from e

        logger.info("[graph.neo4j] 已连接 %s", NEO4J_URI)
        return _driver


def close_driver() -> None:
    """关闭连接（灌图脚本收尾、单元测试用）。"""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.close()
            except Exception as e:              # pragma: no cover - 关闭失败不影响主流程
                logger.warning("[graph.neo4j] 关闭连接异常：%s", e)
            _driver = None


def _database() -> str:
    from app.config import NEO4J_DATABASE

    return NEO4J_DATABASE


def _run(cypher: str, **params) -> List:
    """执行一条 Cypher 并取回全部记录（同步阻塞）。

    参数：
        cypher: 语句（只允许参数占位 $xxx，不要拼用户输入）
        params: 参数
    返回：
        记录列表
    异常：
        GraphNotReady —— 连接或查询失败（上层据此降级）
    """
    from app.config import GRAPH_NEO4J_TIMEOUT

    driver = get_driver()
    try:
        with driver.session(database=_database()) as session:
            result = session.run(cypher, params, timeout=GRAPH_NEO4J_TIMEOUT)
            return list(result)
    except GraphNotReady:
        raise
    except Exception as e:
        raise GraphNotReady(f"Neo4j 查询失败：{e}") from e


# ==========================================================
# Schema：约束与索引
# ==========================================================
_schema_ready = False
_schema_lock = threading.Lock()

# 唯一约束：让 MERGE 走索引（否则每次写入都全表扫），同时防止重复节点
_CONSTRAINTS = (
    ("entity_id_unique", "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
                         "FOR (e:Entity) REQUIRE e.id IS UNIQUE"),
    ("chunk_id_unique", "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS "
                        "FOR (c:Chunk) REQUIRE c.id IS UNIQUE"),
)
_INDEXES = (
    ("entity_name", "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)"),
    ("entity_type", "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)"),
    ("chunk_source", "CREATE INDEX chunk_source IF NOT EXISTS FOR (c:Chunk) ON (c.source)"),
)
# 全文索引：实体链接「字典匹配」失败时的兜底（中文靠 cjk 分词器）
_FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX entity_name_fts IF NOT EXISTS "
    "FOR (e:Entity) ON EACH [e.name, e.aliases_text] "
    "OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk'}}"
)
_FULLTEXT_INDEX_NO_ANALYZER = (
    "CREATE FULLTEXT INDEX entity_name_fts IF NOT EXISTS "
    "FOR (e:Entity) ON EACH [e.name, e.aliases_text]"
)
FULLTEXT_INDEX_NAME = "entity_name_fts"


def ensure_schema(force: bool = False) -> Dict:
    """创建约束与索引（幂等）。

    说明：约束和索引只需建一次，进程内用 _schema_ready 打标，避免每次写入都执行。
         Neo4j 的 `IF NOT EXISTS` 本身也是幂等的，重复执行不会有副作用。

    返回：
        {"constraints": [...], "indexes": [...], "fulltext": bool}
    """
    global _schema_ready
    if _schema_ready and not force:
        return {"cached": True}

    with _schema_lock:
        if _schema_ready and not force:
            return {"cached": True}

        done = {"constraints": [], "indexes": [], "fulltext": False}
        for name, stmt in _CONSTRAINTS:
            _run(stmt)
            done["constraints"].append(name)
        for name, stmt in _INDEXES:
            _run(stmt)
            done["indexes"].append(name)

        # 全文索引：个别服务端不支持 cjk 分词器，降级为默认分词器，
        # 再失败也不影响主流程（实体链接的主路径是内存字典匹配）
        try:
            _run(_FULLTEXT_INDEX)
            done["fulltext"] = True
        except GraphNotReady as e:
            logger.warning("[graph.neo4j] cjk 全文索引创建失败，改用默认分词器：%s", e)
            try:
                _run(_FULLTEXT_INDEX_NO_ANALYZER)
                done["fulltext"] = True
            except GraphNotReady as e2:
                logger.warning("[graph.neo4j] 全文索引不可用（实体链接将只用字典匹配）：%s", e2)

        _schema_ready = True
        logger.info("[graph.neo4j] schema 就绪：%s", done)
        return done


# ==========================================================
# 主键生成规则（灌图与检索必须用同一套，否则实体对不上）
# ==========================================================


def make_entity_id(etype: str, name: str) -> str:
    """实体主键：`类型:归一化名称`，如 `job:后端开发工程师`。

    ⚠️ 为什么不用自增 id：名称是业务上的唯一标识，
       用「类型 + 归一化名称」做 id 才能让不同来源（结构化数据、
       大模型抽取、知识块溯源）自动合并到同一个节点上，MERGE 天然幂等。
    """
    return f"{str(etype or '').strip().lower()}:{_norm(name)}"


def make_chunk_id(text: str) -> str:
    """知识块主键：正文的 MD5。

    ⚠️ 与 app/core/rag.py 里去重用的指纹算法保持一致，
       这样「图里的 Chunk 节点」与「Milvus 里的知识块」能一一对应上。
    """
    return hashlib.md5(str(text or "").encode("utf-8")).hexdigest()


# ==========================================================
# 写入
# ==========================================================


def _batched(items: Sequence, size: int) -> Iterable[Sequence]:
    """把列表切成若干批（Neo4j 单条 UNWIND 参数不宜过大）。"""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _clean_props(props: Optional[Dict]) -> Dict:
    """清洗属性：只保留 Neo4j 能存的类型，去掉空值与嵌套结构。

    ⚠️ 为什么要清洗：Neo4j 属性只接受「基本类型或其列表」，
       直接把原始 JSON（含嵌套 dict/list[dict]）塞进去会整批写入失败。
    """
    out: Dict = {}
    for k, v in (props or {}).items():
        if k in ("id", "name", "type") or v is None or v == "":
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v.strip()[:_MAX_VALUE_CHARS]
        elif isinstance(v, (list, tuple)):
            items = [
                (x.strip()[:60] if isinstance(x, str) else x)
                for x in v if isinstance(x, (str, int, float, bool)) and x != ""
            ]
            if items:
                out[k] = items[:_MAX_LIST_ITEMS]
    return out


def _aliases_text(name: str, aliases: Sequence[str]) -> str:
    """把「主名 + 别名」拼成全文索引用的单串。"""
    parts = [str(name or "")] + [str(a) for a in (aliases or []) if a]
    return " | ".join(p for p in parts if p)[:_MAX_VALUE_CHARS]


def upsert(nodes: Sequence[Dict], edges: Sequence[Dict],
           chunks: Sequence[Dict] = (), batch_size: int = 500) -> Dict:
    """写入图谱（节点 / 关系 / 知识块 + 溯源边）。

    参数：
        nodes: [{"id","name","type","aliases":[...],"props":{...}}]
        edges: [{"start","end","type","props":{}}]
        chunks:[{"id","title","source","type","text"}] —— 知识块节点（事实出处）
    返回：
        {"nodes": n, "edges": n, "chunks": n, "skipped": {...}}

    ⚠️ 全部使用 MERGE：同一个知识块反复灌库不会产生重复数据，
       这也是「可反复执行」的保证（不需要先删再写）。
    """
    ensure_schema()

    counts = {"nodes": 0, "edges": 0, "chunks": 0}
    skipped = {"bad_label": 0, "bad_relation": 0, "missing_end": 0}

    # ---------- 1) 实体节点 ----------
    node_rows = []
    by_label: Dict[str, List[str]] = {}
    for n in nodes:
        nid, name = str(n.get("id") or "").strip(), str(n.get("name") or "").strip()
        if not nid or not name:
            continue
        ntype = str(n.get("type") or "").strip().lower()
        label = TYPE_TO_LABEL.get(ntype, _FALLBACK_LABEL)
        if label not in _ALLOWED_LABELS:          # 双保险，理论上到不了这里
            skipped["bad_label"] += 1
            continue
        aliases = [str(a).strip() for a in (n.get("aliases") or []) if str(a).strip()]
        node_rows.append({
            "id": nid,
            "name": name[:120],
            "type": ntype or _FALLBACK_LABEL.lower(),
            "aliases": aliases,
            "aliases_text": _aliases_text(name, aliases),
            "props": _clean_props(n.get("props")),
        })
        by_label.setdefault(label, []).append(nid)

    for part in _batched(node_rows, batch_size):
        _run(
            """
            UNWIND $rows AS row
            MERGE (n:Entity {id: row.id})
            SET n.name = row.name,
                n.type = row.type,
                n.aliases = row.aliases,
                n.aliases_text = row.aliases_text,
                n += row.props,
                n.updated_at = datetime()
            """,
            rows=part,
        )
        counts["nodes"] += len(part)

    # ---------- 2) 第二标签（按类型批量打标） ----------
    for label, ids in by_label.items():
        for part in _batched(ids, batch_size):
            # 标签来自白名单常量，不存在注入风险（Cypher 语法不允许参数化标签）
            _run(f"UNWIND $ids AS id MATCH (n:Entity {{id: id}}) SET n:`{label}`", ids=part)

    # ---------- 3) 知识块节点 ----------
    chunk_rows = []
    for c in chunks:
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        chunk_rows.append({
            "id": cid,
            "title": str(c.get("title") or "")[:200],
            "source": str(c.get("source") or "")[:200],
            "type": str(c.get("type") or "")[:40],
            "text": str(c.get("text") or "")[:_MAX_VALUE_CHARS],
        })
    for part in _batched(chunk_rows, batch_size):
        _run(
            """
            UNWIND $rows AS row
            MERGE (c:Chunk {id: row.id})
            SET c.title = row.title, c.source = row.source,
                c.type = row.type, c.text = row.text, c.updated_at = datetime()
            """,
            rows=part,
        )
        counts["chunks"] += len(part)

    # ---------- 4) 关系（按类型分组，类型必须过白名单） ----------
    by_rel: Dict[str, List[Dict]] = {}
    for e in edges:
        rel = str(e.get("type") or "").strip().upper()
        start, end = str(e.get("start") or "").strip(), str(e.get("end") or "").strip()
        if not start or not end:
            skipped["missing_end"] += 1
            continue
        if rel not in REL_TYPES:
            logger.warning("[graph.neo4j] 忽略未登记的关系类型：%s", rel)
            skipped["bad_relation"] += 1
            continue
        by_rel.setdefault(rel, []).append({
            "start": start, "end": end, "props": _clean_props(e.get("props")),
        })

    for rel, rows in by_rel.items():
        for part in _batched(rows, batch_size):
            if rel == PROVENANCE_REL:
                # 溯源边：知识块 → 实体（起点是 Chunk，不是 Entity）
                _run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (c:Chunk {{id: row.start}})
                    MATCH (e:Entity {{id: row.end}})
                    MERGE (c)-[:`{rel}`]->(e)
                    """,
                    rows=part,
                )
            else:
                # 语义关系：两端都是实体；row.props 为空 map 时 SET += 不会报错
                _run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a:Entity {{id: row.start}})
                    MATCH (b:Entity {{id: row.end}})
                    MERGE (a)-[r:`{rel}`]->(b)
                    SET r += row.props
                    """,
                    rows=part,
                )
        counts["edges"] += len(rows)

    logger.info("[graph.neo4j] 写入完成：节点 %d、关系 %d、知识块 %d",
                counts["nodes"], counts["edges"], counts["chunks"])
    return {"nodes": counts["nodes"], "edges": counts["edges"],
            "chunks": counts["chunks"], "skipped": skipped}


def reset_graph() -> int:
    """清空 GraphRAG 自己的图数据（⚠️ 破坏性操作，只应由 CLI 的 --rebuild 触发）。

    ⚠️ 只删除本项目写入的 :Entity 与 :Chunk 节点，
       【不会】动同一个 Neo4j 里其他实验用的数据
       （比如手工建的「武将/诸侯」小图）—— 一个库多人多用途是常态，
       全库 DETACH DELETE 是绝对不能做的操作。

    返回：
        删除的节点数
    """
    rows = _run("MATCH (n) WHERE n:Entity OR n:Chunk RETURN count(n) AS c")
    total = int(rows[0]["c"]) if rows else 0
    _run("MATCH (n) WHERE n:Entity OR n:Chunk DETACH DELETE n")
    logger.warning("[graph.neo4j] 已清空图谱，删除节点 %d 个", total)
    return total


# ==========================================================
# 实体链接（问题 → 图里的实体）
# ==========================================================
# 归一化：只保留「中文 + 字母 + 数字」，其余（空格、·、-、（）、/ 等）全部去掉。
# 目的：「UI 设计师」与「UI设计师」、「后端开发工程师」与「后端 开发 工程师」
#       能被认成同一个实体 —— 用户提问时不会精确复现图里的标点。
_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

# 同长度命中时的类型优先级：越靠前越具体、越可能是用户真正在问的东西。
# ⚠️ 口径：请求里同时出现「职位名」和「公司名」时（如「星野智能的后端开发工程师」），
#    职位才是最贴题的起点；职能/城市/行业都是宽泛概念，排在后面，
#    避免它们的邻居把具体职位的事实挤出事实名额（GRAPH_TOP_K 很小）。
_TYPE_PRIORITY = {
    "job": 1, "company": 2, "question": 3, "skill": 4, "category": 5,
    "bank": 6, "city": 7, "industry": 8, "guide": 9,
}

_entity_cache: Dict = {"at": 0.0, "items": []}
_entity_cache_lock = threading.Lock()


def normalize_name(text: str) -> str:
    """归一化文本：只保留「中文 + 字母 + 数字」，其余字符全部去掉。

    实体主键生成、实体链接、抽取校验全都基于它，
    因此这里作为全项目唯一的「归一化规则」出口，改动会影响整条链路。
    """
    return _NORM_RE.sub("", str(text or "").lower())


# 模块内简写（本文件用得比较多）
_norm = normalize_name


def entity_index(force: bool = False) -> List[Dict]:
    """读取全图实体名清单（带 TTL 缓存）。

    返回：
        [{"id","name","type","aliases":[...],"norm_names":[...]}, ...]
    """
    from app.config import GRAPH_ENTITY_CACHE_TTL

    now = time.time()
    with _entity_cache_lock:
        if not force and _entity_cache["items"] and now - _entity_cache["at"] < GRAPH_ENTITY_CACHE_TTL:
            return _entity_cache["items"]

    rows = _run(
        """
        MATCH (e:Entity)
        RETURN e.id AS id, e.name AS name, e.type AS type,
               coalesce(e.aliases, []) AS aliases
        """
    )
    items = []
    for r in rows:
        name = str(r["name"] or "")
        aliases = [str(a) for a in (r["aliases"] or [])]
        norms = [n for n in (_norm(name), *(_norm(a) for a in aliases)) if len(n) >= 2]
        if not norms:
            continue
        items.append({
            "id": str(r["id"]), "name": name, "type": str(r["type"] or ""),
            "aliases": aliases, "norm_names": sorted(set(norms), key=len, reverse=True),
        })

    with _entity_cache_lock:
        _entity_cache["at"] = now
        _entity_cache["items"] = items
    logger.info("[graph.neo4j] 实体索引已加载：%d 个实体", len(items))
    return items


def clear_entity_cache() -> None:
    """清空实体名缓存（灌完图后调用，让新实体立刻可被检索到）。"""
    with _entity_cache_lock:
        _entity_cache["at"] = 0.0
        _entity_cache["items"] = []


def _safe_lucene(query: str) -> str:
    """消毒 Lucene 查询串（全文索引兜底路径用）。

    ⚠️ Lucene 查询语法里的 + - && || ! ( ) { } [ ] ^ " ~ * ? : \\ /
       都是元字符，用户问题里随手一个「？」「（）」就可能让查询报错，
       这里统一剔除，只留下词元与空格。
    """
    cleaned = re.sub(r'[+\-!(){}\[\]^"~*?:\\/|&]', " ", str(query or ""))
    return " ".join(cleaned.split())[:200]


def link_entities(question: str, limit: int = 5) -> List[Dict]:
    """实体链接：把用户问题映射到图中的实体。

    策略（先精确、后模糊，两段都做了规模与噪声控制）：
        1. 主路径 —— 内存字典最长匹配：问题归一化后是否【包含】实体名（或别名）。
           命中多个时按「匹配到的名字长度」降序（越长的名字越具体越准），
           同长度按实体类型优先级排序；
        2. 兜底 —— 全文索引：字典匹配不到时（例如用户只说了「后端开发」，
           而图里叫「后端开发工程师」），用 cjk 分词后的全文检索补召回。

    参数：
        question: 用户问题原文
        limit:    最多返回几个实体
    返回：
        [{"id","name","type","matched","score"}, ...]，按可信度降序
    """
    q = _norm(question)
    if not q:
        return []

    try:
        index = entity_index()
    except GraphNotReady:
        raise

    hits: List[Dict] = []
    for ent in index:
        matched = next((n for n in ent["norm_names"] if n in q), None)
        if not matched:
            continue
        hits.append({
            "id": ent["id"], "name": ent["name"], "type": ent["type"],
            "matched": matched,
            # 命中的实体名越长，说明匹配越具体（「后端开发工程师」优于「后端开发」）
            "score": min(1.0, 0.4 + 0.15 * len(matched)),
        })

    hits.sort(key=lambda h: (-len(h["matched"]), _TYPE_PRIORITY.get(h["type"], 99), h["name"]))

    # 去掉「被更长命中覆盖」的重复实体：一个实体只留最好的一次命中
    seen, unique = set(), []
    for h in hits:
        if h["id"] in seen:
            continue
        seen.add(h["id"])
        unique.append(h)

    if unique:
        return unique[:limit]

    # ---------- 兜底：全文索引 ----------
    return _link_by_fulltext(question, limit)


def _longest_common_run(a: str, b: str, cap: int = 24) -> tuple:
    """求两个字符串的最长公共子串，返回 (长度, 子串)。

    用途：全文索引兜底召回的「相似度闸门」。
    ⚠️ 为什么不能只看 Lucene 分数：中文分词后「后端开发工程师」与
       「前端开发工程师」共享「开发」「工程师」等词，分数都能很高，
       于是「前端开发工程师」会被当成相关实体召回，最终变成一条
       与问题无关的事实塞进提示词。用「最长公共子串」这个直观指标后，
       只有真正共享长片段的候选才能通过。

    cap：找到这么长的公共子串就提前返回（只用于判断「够不够长」，不需要精确最大值）
    """
    if not a or not b:
        return 0, ""
    if len(a) > len(b):
        a, b = b, a

    best_len, best_end = 0, 0
    prev = [0] * (len(a) + 1)
    for j in range(1, len(b) + 1):
        cur = [0] * (len(a) + 1)
        ch = b[j - 1]
        for i in range(1, len(a) + 1):
            if a[i - 1] == ch:
                cur[i] = prev[i - 1] + 1
                if cur[i] > best_len:
                    best_len, best_end = cur[i], i
        prev = cur
        if best_len >= cap:
            break
    return best_len, a[best_end - best_len:best_end]


# 兜底召回的相对闸门：公共子串还要占到实体名长度的这个比例以上
_MIN_OVERLAP_RATIO = 0.35


def _link_by_fulltext(question: str, limit: int) -> List[Dict]:
    """全文索引兜底召回（字典匹配完全没命中时才走这里）。

    两道闸门，都是为了「宁可召回少几条，也不要把无关事实塞进提示词」：
        1. 候选与问题的最长公共子串要 ≥ GRAPH_LINK_MIN_OVERLAP，
           且占实体名长度的 _MIN_OVERLAP_RATIO 以上；
        2. 通过后再按公共子串长度排序取前 limit 个。

    任何异常都吞掉并返回空列表：这条路只是「锦上添花」，
    失败了仍会退化为纯向量检索，不该影响对话。
    """
    from app.config import GRAPH_LINK_MIN_OVERLAP

    q_norm = normalize_name(question)
    q = _safe_lucene(question)
    if not q or not q_norm:
        return []

    try:
        rows = _run(
            f"""
            CALL db.index.fulltext.queryNodes('{FULLTEXT_INDEX_NAME}', $q, {{limit: $limit}})
            YIELD node, score
            RETURN node.id AS id, node.name AS name, node.type AS type, score
            """,
            q=q, limit=max(20, limit * 4),
        )
    except GraphNotReady as e:
        logger.info("[graph.neo4j] 全文兜底不可用：%s", e)
        return []

    hits: List[Dict] = []
    for r in rows:
        name = str(r["name"] or "")
        name_norm = normalize_name(name)
        if not name_norm:
            continue
        run, fragment = _longest_common_run(q_norm, name_norm)
        if run < GRAPH_LINK_MIN_OVERLAP or run < _MIN_OVERLAP_RATIO * len(name_norm):
            continue
        hits.append({
            "id": str(r["id"]), "name": name, "type": str(r["type"] or ""),
            # matched 记的是真正重叠的那段文字，便于排查「为什么命中了它」
            "matched": fragment or name_norm,
            # 与字典路径用同一套打分口径，两路结果才可比
            "score": min(1.0, 0.4 + 0.15 * run),
        })

    hits.sort(key=lambda h: (-len(h["matched"]), _TYPE_PRIORITY.get(h["type"], 99), h["name"]))
    return hits[:limit]


# ==========================================================
# 子图扩展（多跳）
# ==========================================================


def expand(seed_ids: Sequence[str], hops: int = 1, limit: int = 40) -> Dict:
    """从起点实体向外扩展，取回子图（节点 + 语义关系边）。

    参数：
        seed_ids: 起点实体 id 列表
        hops:     扩展跳数（1 = 直接邻居；2 = 邻居的邻居）
        limit:    最多取回多少条边（防止热门实体把候选撑爆）
    返回：
        {
          "nodes": {id: {"id","name","type","props"...}},   # 含起点
          "edges": [{"start","rel","end","start_props","end_props"}],
          "truncated": bool,                                # 是否因为 limit 截断
        }

    ⚠️ 实现方式：按跳数逐层做 1 跳查询（每次都是参数化查询），
       而不是写 `-[r*1..$hops]-` —— Cypher 不支持把跳数写成参数，
       拼字符串又容易埋下注入隐患，逐层查询还顺带能做到「每层限量」。
    """
    max_hops = 1 if hops <= 1 else 2      # 只支持 1~2 跳，更多跳噪声大于收益
    nodes: Dict[str, Dict] = {}
    edges: List[Dict] = []
    edge_keys = set()
    visited = set(str(i) for i in seed_ids if i)
    frontier = sorted(visited)
    truncated = False

    for _ in range(max_hops):
        if not frontier or len(edges) >= limit:
            truncated = truncated or bool(frontier)
            break

        remaining = limit - len(edges)
        # ⚠️ 关键点：用 startNode(r)/endNode(r) 取【真实方向】。
        #    这里必须用无向匹配（因为子图要从任一端的命中实体出发），
        #    但事实渲染对方向极其敏感 —— 「职位属于职能」和「职能属于职位」
        #    是完全不同的两句话，方向搞反等于往提示词里灌错误事实。
        rows = _run(
            """
            MATCH (a:Entity)-[r]-(b:Entity)
            WHERE a.id IN $ids AND type(r) <> $skip_rel
            RETURN properties(startNode(r)) AS s_props,
                   type(r)                   AS rel,
                   properties(endNode(r))    AS e_props
            ORDER BY a.id, type(r), b.id
            LIMIT $limit
            """,
            ids=frontier, skip_rel=PROVENANCE_REL, limit=remaining,
        )

        new_frontier = set()
        for row in rows:
            s, e = dict(row["s_props"]), dict(row["e_props"])
            sid, eid = str(s.get("id")), str(e.get("id"))
            rel = str(row["rel"])
            key = (sid, rel, eid)
            if key in edge_keys:
                continue
            edge_keys.add(key)
            edges.append({"start": sid, "rel": rel, "end": eid,
                          "start_props": s, "end_props": e})
            # 两个端点都登记进节点表；不在已访问集合里的就是下一层前沿
            for props in (s, e):
                nid = str(props.get("id"))
                if nid and nid not in nodes:
                    nodes[nid] = props
                if nid and nid not in visited:
                    new_frontier.add(nid)
            if len(edges) >= limit:
                truncated = True
                break

        visited |= new_frontier
        frontier = sorted(new_frontier)

    # 起点自身的属性也要带上（问题常常只是问某个实体的属性，如「这个岗位薪资多少」）
    missing = [i for i in seed_ids if i and str(i) not in nodes]
    if missing:
        rows = _run(
            "MATCH (e:Entity) WHERE e.id IN $ids RETURN properties(e) AS props",
            ids=[str(i) for i in missing],
        )
        for row in rows:
            props = dict(row["props"])
            nodes[str(props.get("id"))] = props

    return {"nodes": nodes, "edges": edges, "truncated": truncated}


def provenance(entity_ids: Sequence[str], per_entity: int = 2) -> Dict[str, List[str]]:
    """取实体的出处（哪些知识块提到了它），用于给图谱事实标注来源。

    返回：
        {entity_id: ["知识块标题", ...]}
    """
    ids = [str(i) for i in entity_ids if i]
    if not ids:
        return {}
    rows = _run(
        """
        MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
        WHERE e.id IN $ids
        RETURN e.id AS id, collect(DISTINCT c.title)[0..$n] AS titles
        """,
        ids=ids, n=per_entity,
    )
    return {str(r["id"]): [t for t in (r["titles"] or []) if t] for r in rows}


# ==========================================================
# 运维：统计与健康检查
# ==========================================================


def stats() -> Dict:
    """图谱统计（实体数、知识块数、关系数、类型分布）。

    ⚠️ 统计口径只覆盖本项目写入的数据（:Entity / :Chunk 及其关系）：
       同一个 Neo4j 里可能还有别人手工实验建的图，
       那些数据既不该混进这里的数字，也不该被本项目改动。

    异常：
        GraphNotReady —— 连不上（CLI 直接暴露给使用者，便于排查）
    """
    out: Dict = {"nodes": 0, "entities": 0, "chunks": 0, "relations": 0,
                 "semantic_relations": 0, "provenance_relations": 0,
                 "entityTypes": {}, "relations_by_type": {}}

    rows = _run("MATCH (e:Entity) RETURN count(e) AS c")
    out["entities"] = int(rows[0]["c"]) if rows else 0

    rows = _run("MATCH (c:Chunk) RETURN count(c) AS c")
    out["chunks"] = int(rows[0]["c"]) if rows else 0

    # 语义关系（实体↔实体）与溯源关系（知识块→实体）分开统计，便于判断图的质量：
    # 「有实体没关系」和「有关系没出处」是两种完全不同的待修状态
    rows = _run("MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS c")
    out["semantic_relations"] = int(rows[0]["c"]) if rows else 0

    rows = _run(f"MATCH (:Chunk)-[r:`{PROVENANCE_REL}`]->(:Entity) RETURN count(r) AS c")
    out["provenance_relations"] = int(rows[0]["c"]) if rows else 0

    out["nodes"] = out["entities"] + out["chunks"]
    out["relations"] = out["semantic_relations"] + out["provenance_relations"]

    rows = _run("MATCH (e:Entity) RETURN e.type AS t, count(*) AS c ORDER BY c DESC")
    out["entityTypes"] = {str(r["t"] or "unknown"): int(r["c"]) for r in rows}

    rows = _run(
        """
        MATCH (:Entity)-[r]->(:Entity)
        RETURN type(r) AS t, count(*) AS c
        UNION ALL
        MATCH (:Chunk)-[r]->(:Entity)
        RETURN type(r) AS t, count(*) AS c
        """
    )
    by_type: Dict[str, int] = {}
    for r in rows:
        by_type[str(r["t"])] = by_type.get(str(r["t"]), 0) + int(r["c"])
    out["relations_by_type"] = dict(sorted(by_type.items(), key=lambda x: -x[1]))
    return out


def health() -> Dict:
    """健康检查：连通性 + 规模概览（供 /ai/graph/status 使用，绝不抛异常）。

    返回：
        {"enabled","uri","database","user","ok","error","nodes","entities",
         "chunks","relations","entityTypes"}
    """
    from app.config import (
        GRAPH_ENABLED, NEO4J_DATABASE, NEO4J_URI, NEO4J_USER,
    )

    info = {
        "enabled": GRAPH_ENABLED,
        "uri": NEO4J_URI,
        "database": NEO4J_DATABASE,
        "user": NEO4J_USER,
        "ok": False,
        "error": "",
        "nodes": 0,
        "entities": 0,
        "chunks": 0,
        "relations": 0,
        "entityTypes": {},
    }
    try:
        info.update(stats())
        info["ok"] = True
    except Exception as e:                       # noqa: BLE001 - 诊断接口要「有错也返回」
        info["error"] = str(e)
    return info
