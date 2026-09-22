"""GraphRAG 检索入口（图谱的「编排层」）。

对外只暴露三样东西：
    retrieve_graph()        —— 同步检索，把问题变成「图谱事实」（含降级信息）
    build_facts_text()      —— 把事实渲染成可注入提示词的文本块
    to_contexts()           —— 把事实转成与向量检索一致的知识块结构（供 app/core/rag.py 融合）

核心设计原则与 app/core/rag.py 完全一致：【图谱检索永远不能让对话挂掉】
    Neo4j 没启动、密码没填、图里没数据、实体没命中……一律只记日志 +
    标记 used=False，由上层决定只用向量检索，绝不向上抛异常。

检索流程（GraphRAG 的经典三步，都在这里）：
    问题 → ① 实体链接（entity linking）：把问题里的词映射到图里的实体
         → ② 子图扩展（多跳）：从命中实体向外取 1~2 跳的邻域
         → ③ 事实文本化：把「实体属性 + 关系三元组」渲染成人能读懂、
            大模型也能直接用的中文事实句

与向量检索的分工：
    向量检索回答「哪段资料在讲这件事」（非结构化、模糊语义）；
    图谱检索回答「这些实体之间到底是什么关系」（结构化、精确、可多跳）。
    两者在 app/core/rag.py 里合并注入提示词，互为补充。

⚠️ 与 app/core/rag.py 的接口契约（本次改造刻意【不动】rag.py）：
    to_contexts() 产出的每条知识块都必须带 kind="graph"，
    rag.build_system_prompt 靠这个标记把它拆到「知识图谱事实」段落
    （其余走「参考资料」段落）。标记一旦改名，图谱事实会被当成普通资料，
    优先级与提示词结构都会退化，因此这里只改渲染内容、不改标记。

⚠️ 本文件里的类型/关系字典已整体换成招聘域（职位/公司/城市/职能/技能/面试题/
   行业/平台规则/面试题库）。渲染文案是【模型看到的事实原文】，改错一个字
   就等于给求职者灌错误事实，所以类型中文名、关系句式、包裹符号三者必须与
   灌图侧（app/core/graph_extract.py）的实体/关系定义严格对应。
"""
import logging
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _config():
    """集中读取配置（延迟导入，避免子脚本导入顺序导致的配置未加载）。"""
    from app import config

    return config


# ==========================================================
# 渲染字典：类型中文名 / 关系中文说法 / 属性展示顺序
# ==========================================================
TYPE_ZH = {
    "job": "职位",
    "company": "公司",
    "city": "城市",
    "category": "职能",
    "skill": "技能",
    "question": "面试题",
    "industry": "行业",
    "guide": "平台规则",
    # ⚠️ 刻意不写「题库」两个字：课程域也有「题库」实体，统计输出里出现光秃秃的
    #    「题库」很容易被当成改造残留。写成「面试题库」才是这次真正建的类型。
    "bank": "面试题库",
}

# 关系类型 → 中文说法（兜底用；正常情况下走下面的模板）
REL_ZH = {
    "BELONGS_TO": "属于职能",
    "AT_COMPANY": "由……招聘",
    "IN_CITY": "的工作地点是",
    "REQUIRES": "要求掌握",
    "TESTS": "考查的知识点是",
    "IN_INDUSTRY": "属于行业",
    "IN_BANK": "收录于题库",
    "APPLIES_TO": "适用于",
    "RELATES_TO": "与……相关",
    "PART_OF": "是……的组成部分",
    "PROVIDES": "提供",
    "USES": "使用",
    "INCLUDES": "包含",
    "SUPPORTS": "支持",
}

# 关系渲染模板：{a} / {b} 替换成两端实体的展示名。
# ⚠️ 为什么用「自然句」而不是箭头符号（A -> B）：
#    这段文本会被直接拼进提示词喂给大模型，越接近人话，
#    模型越不容易搞错关系的方向与语义（尤其是反向关系）。
# ⚠️ 刻意【不】在中文之间加空格：读起来更像人话，也更省提示词字数。
#    例：《后端开发工程师》（职位：25-45K·15薪、3-5年、本科）属于职能「后端开发」（职能）
REL_TEMPLATE = {
    "BELONGS_TO": "{a}属于职能{b}",
    "AT_COMPANY": "{a}由{b}招聘",
    "IN_CITY": "{a}的工作地点是{b}",
    "REQUIRES": "{a}要求掌握{b}",
    "TESTS": "{a}考查的知识点是{b}",
    "IN_INDUSTRY": "{a}属于行业{b}",
    "IN_BANK": "{a}收录在{b}",
    "APPLIES_TO": "{a}适用于{b}",
    "RELATES_TO": "{a}与{b}相关",
    "PART_OF": "{a}是{b}的组成部分",
    "PROVIDES": "{a}提供{b}",
    "USES": "{a}使用{b}",
    "INCLUDES": "{a}包含{b}",
    "SUPPORTS": "{a}支持{b}",
}

# 名称包裹符号：职位与面试题用书名号（都像「作品名/题名」），
# 公司/城市/职能/技能/行业/规则用直角引号，与项目其它中文文案保持一致的观感。
_WRAP = {
    "job": ("《", "》"),
    "question": ("《", "》"),
    "company": ("「", "」"),
    "city": ("「", "」"),
    "category": ("「", "」"),
    "skill": ("「", "」"),
    "industry": ("「", "」"),
    "guide": ("「", "」"),
    "bank": ("「", "」"),
}

# 每种实体渲染时展示哪些属性、按什么顺序、带什么单位
# （只列「用户真正会问」的字段，避免把内部字段名泄进提示词）
_PROP_ORDER = {
    "job": [
        # ⚠️ 前三项刻意【不带字段名】：JD 头部本来就是「薪资 · 经验 · 学历」这个
        #    固定顺序，渲染成「25-45K·15薪、3-5年、本科」比「薪资 25-45K·15薪」
        #    更像人话，也更省提示词字数；其余字段名有歧义，必须带标签。
        ("salary", "", ""), ("experience", "", ""), ("education", "", ""),
        ("kind", "类型", ""), ("location", "地点", ""),
        ("tags", "福利", ""), ("hr", "招聘负责人", ""),
        ("heat", "热度", ""), ("process", "招聘流程", ""),
    ],
    "company": [
        ("scale", "规模", ""), ("stage", "融资阶段", ""),
        ("jobCount", "在招职位", "个"), ("city", "城市", ""),
        ("benefits", "福利", ""), ("address", "地址", ""),
        ("fullName", "公司全称", ""), ("website", "官网", ""),
    ],
    "city": [("province", "省份", ""), ("jobCount", "在招职位", "个")],
    "category": [("levelZh", "层级", ""), ("desc", "说明", ""),
                 ("jobCount", "在招职位", "个"), ("parentName", "上级方向", "")],
    "skill": [("questionCount", "关联面试题", "道"), ("jobCount", "要求该技能的职位", "个")],
    "question": [("position", "面试岗位", ""), ("difficulty", "难度", ""),
                 ("frequency", "热度", ""), ("answer", "参考答案", ""),
                 ("source", "来源面经", "")],
    "bank": [("count", "题目数", ""), ("desc", "说明", ""), ("tip", "备考建议", "")],
    "industry": [("companyCount", "公司数", "家"), ("companies", "代表公司", "")],
    "guide": [("items", "要点", ""), ("source", "出处", "")],
}

# 个别属性渲染时的字符上限：列表类属性一条就能占满整条事实，
# 而事实本身还有 GRAPH_FACT_MAX_CHARS（默认 300 字）的硬上限，
# 这里先做一层更细的控制，保证「参考答案」「规则要点」不会被从中间截断。
_PROP_MAX_CHARS = {"answer": 180, "items": 260, "companies": 80, "benefits": 60, "tags": 60}


# ==========================================================
# 渲染
# ==========================================================


def type_zh(ntype: str) -> str:
    """实体类型的中文名（灌图脚本打印概览时也会用到）。"""
    return TYPE_ZH.get(str(ntype or "").lower(), "实体")


# 模块内简写
_type_zh = type_zh


def _display_name(props: Dict) -> str:
    """实体的展示名（带类型特有的包裹符号）。"""
    name = str(props.get("name") or "").strip() or "未命名"
    left, right = _WRAP.get(str(props.get("type") or "").lower(), ("", ""))
    return f"{left}{name}{right}"


def _fmt_prop_value(key: str, value, unit: str) -> str:
    """把一个属性值渲染成短文本（列表拼成一句，并做单项长度保护）。"""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if str(v or "").strip()]
        # ⚠️ 分隔符按内容长短切换：福利标签这类短词用顿号（「五险一金、双休」），
        #    平台规则/FAQ 这类整句用分号 —— 整句之间用顿号会和句内的顿号混在一起，
        #    模型读不出条目边界（实测「内推规则」5 条要点会连成一片）。
        sep = "；" if any(len(x) > 16 for x in items) else "、"
        text = sep.join(items)
    else:
        text = str(value)
    cap = _PROP_MAX_CHARS.get(key)
    if cap and len(text) > cap:
        text = text[:cap] + "…"
    return f"{text}{unit}" if text else ""


def describe_node(props: Dict, with_attrs: bool = True, max_attrs: int = 4) -> str:
    """把一个实体渲染成一句人话，如：
    《后端开发工程师》（职位：25-45K·15薪、3-5年、本科、社招全职）
    「星野智能」（公司：规模 500-999人、融资阶段 B轮、在招职位 7个）

    参数：
        props:      实体属性（Neo4j 的 properties(n)）
        with_attrs: 是否附带业务属性（关系句里的节点通常不需要，太啰嗦）
        max_attrs:  最多展示几个属性
    """
    ntype = str(props.get("type") or "").lower()
    base = f"{_display_name(props)}（{_type_zh(ntype)}"
    if with_attrs:
        attrs = []
        for key, zh, unit in _PROP_ORDER.get(ntype, []):
            value = props.get(key)
            if value in (None, "", [], {}):
                continue
            text = _fmt_prop_value(key, value, unit)
            if not text:
                continue
            # zh 为空的字段（如职位的薪资/经验/学历）直接写值，见 _PROP_ORDER 的说明
            attrs.append(f"{zh} {text}" if zh else text)
            if len(attrs) >= max_attrs:
                break
        if attrs:
            base += "：" + "、".join(attrs)
    return base + "）"


# 边渲染时给「主语」带上属性的实体类型。
# ⚠️ 为什么只给职位/公司开这个口子：求职者最关心的就是「这岗位给多少钱、什么要求、
#    哪家在招」，一条关系里顺手带出来，比再单开一条事实更省事实名额（GRAPH_TOP_K=6）；
#    面试题/技能则不行 —— 题干上千字、答案几百字，带进来会把整条事实撑爆。
_EDGE_SUBJECT_ATTR_TYPES = frozenset({"job", "company"})


def describe_edge(edge: Dict, with_attrs: bool = False) -> str:
    """把一条关系渲染成一句事实，如：
    《后端开发工程师》（职位：25-45K·15薪、3-5年、本科）属于职能「后端开发」（职能）
    《后端开发工程师》（职位）由「星野智能」（公司）招聘，工作地点「北京」（城市）
    《MySQL 的索引为什么用 B+ 树…》（面试题）考查的知识点是「B+树」（技能）
    """
    start = edge.get("start_props") or {}
    end = edge.get("end_props") or {}
    show = with_attrs or str(start.get("type") or "").lower() in _EDGE_SUBJECT_ATTR_TYPES
    left = describe_node(start, with_attrs=show, max_attrs=3)
    right = describe_node(end, with_attrs=False, max_attrs=2)
    rel = str(edge.get("rel") or "").upper()
    template = REL_TEMPLATE.get(rel)
    if template:
        return template.format(a=left, b=right)
    # 未登记的模板（理论上不会出现，关系类型有白名单）→ 退化成通用句式
    phrase = REL_ZH.get(rel, rel.lower().replace("_", " ") or "关联")
    return f"{left}{phrase}{right}"


# 事实排序时的关系优先级：数字越小越先出现。
# ⚠️ 为什么需要它：一个职能方向下可能有十几个职位、几十道面试题，
#    如果按字母序排（APPLIES_TO < AT_COMPANY < BELONGS_TO…），
#    「哪家公司招的、薪资多少、什么职能」这些最常被问的信息反而进不了事实列表。
_REL_ORDER = {
    "AT_COMPANY": 1,    # 谁在招 + 在哪上班（会与 IN_CITY 合并成一条）
    "BELONGS_TO": 2,    # 属于哪个职能
    "IN_CITY": 3,       # 工作地点（没有 AT_COMPANY 时单独出现）
    "REQUIRES": 4,      # 岗位要求什么技能
    "TESTS": 5,         # 面试题考查什么技能
    "IN_INDUSTRY": 6,   # 公司在什么行业
    "IN_BANK": 7,       # 面试题属于面试题库
    "APPLIES_TO": 8,    # 平台规则适用于哪些岗位
    "PART_OF": 9,
    "RELATES_TO": 10,
    "INCLUDES": 11,
    "PROVIDES": 12,
    "USES": 13,
    "SUPPORTS": 14,
}

# 同类关系在一份事实里的条数上限：避免「一个职能下的 12 个职位」或
# 「一份岗位的 5 个技能」垄断事实列表，保证事实的多样性。
_REL_FACT_CAP = {
    "BELONGS_TO": 3,    # 职能/题库下的职位、面试题最多给 3 条
    "AT_COMPANY": 3,    # 一家公司在招的职位最多给 3 条
    "IN_CITY": 2,
    "REQUIRES": 2,      # 技能最多 2 条
    "TESTS": 2,
    "IN_BANK": 4,       # 「面试常考什么」需要看到几条真题才有用
    "APPLIES_TO": 3,
}


def _distance_of(edge: Dict, seed_ids: Sequence[str]) -> int:
    """判断这条关系离起点有几跳（1 = 直接邻居；其余按 2 处理）。

    用途：图谱事实的可信度按跳数递减 —— 直接关系比「邻居的邻居」更贴题。
    """
    ends = {str(edge.get("start")), str(edge.get("end"))}
    return 1 if ends & set(seed_ids) else 2


# ==========================================================
# 检索
# ==========================================================


def _expand_subgraph(seed_ids: Sequence[str], hops: int, budget: int) -> Dict:
    """按「最佳命中实体优先」分两阶段扩展子图。

    为什么要分阶段：子图扩展有额度上限（GRAPH_EXPAND_LIMIT），
    而一个宽泛实体（如「后端开发」职能）的邻居可能几十个，
    如果和具体实体（如某个职位）一起扩展，额度很容易被宽泛实体吃光，
    导致「这个职位哪家在招、要什么技能」这些最贴题的关系反而取不回来。
    因此：阶段一先给最佳实体 60% 额度，阶段二再扩展其余实体（用剩余额度）。

    返回：
        与 graph_store.expand 相同的结构（nodes / edges / truncated）
    """
    from app.core import graph_store

    nodes: Dict[str, Dict] = {}
    edges: List[Dict] = []
    seen = set()
    truncated = False
    remaining = max(1, int(budget))
    first_budget = max(1, int(budget * 0.6))

    for phase, (ids, cap) in enumerate((
        (list(seed_ids[:1]), first_budget),
        (list(seed_ids[1:]), remaining),
    )):
        if not ids or remaining <= 0:
            continue
        sub = graph_store.expand(ids, hops=hops, limit=min(cap, remaining))
        for nid, props in (sub.get("nodes") or {}).items():
            nodes.setdefault(nid, props)
        added = 0
        for e in sub.get("edges") or []:
            key = (e.get("start"), e.get("rel"), e.get("end"))
            if key in seen:
                continue
            seen.add(key)
            edges.append(e)
            added += 1
        remaining -= added
        truncated = truncated or bool(sub.get("truncated"))
        # 阶段一的额度没用完时，阶段二可以直接用完整剩余额度
        if phase == 0:
            first_budget = remaining

    return {"nodes": nodes, "edges": edges, "truncated": truncated}


def _merge_job_facts(edges: Sequence[Dict], nodes: Dict[str, Dict]) -> tuple:
    """把同一职位上的「公司」与「城市」两条关系合成一句人话。

    渲染成：《后端开发工程师》（职位）由「星野智能」（公司）招聘，工作地点「北京」（城市）

    ⚠️ 为什么值得单独合并：
        1) GRAPH_TOP_K 只有 6 条事实名额，「谁在招」和「在哪上班」对求职者是
           同一个问题的两面，拆成两条既占名额，单看也不像人话；
        2) 职位同时命中这两个关系是最常见的情形（45 个职位全都有公司 + 城市），
           合并后 6 条事实里能多放 1~2 个真正不同的信息（技能、面试题、职能）。

    返回：
        (merged, suppressed)
        merged:     {AT_COMPANY 边的 key: (事实文本, 相关实体 id 列表)}
        suppressed: {IN_CITY 边的 key}（已经并进合并事实，不再单独渲染）
    """
    # 只收 AT_COMPANY / IN_CITY 两种关系：它们是唯一「同一主语、同一个问题」的组合
    by_start: Dict[str, Dict[str, Dict]] = {}
    for e in edges:
        rel = str(e.get("rel") or "")
        if rel in ("AT_COMPANY", "IN_CITY"):
            by_start.setdefault(str(e.get("start")), {})[rel] = e

    merged: Dict[tuple, tuple] = {}
    suppressed: set = set()
    for sid, rels in by_start.items():
        at, city = rels.get("AT_COMPANY"), rels.get("IN_CITY")
        if not at or not city:
            continue
        props = nodes.get(sid) or (at.get("start_props") or {})
        # 只对「职位」做合并：公司自己也有 IN_CITY，但它没有 AT_COMPANY，
        # 天然不会进到这里；这里显式判一次类型，防止以后加了别的同构关系后走岔。
        if str(props.get("type") or "").lower() != "job":
            continue
        # ⚠️ 两端都【不带】属性：这句话的价值在于「谁在招 + 在哪上班」，
        #    公司规模、城市职位数这些属于另一条事实的内容，堆进来只会挤占
        #    GRAPH_FACT_MAX_CHARS（默认 300 字）的额度。
        text = (f"{describe_node(props, with_attrs=False)}由"
                f"{describe_node(at.get('end_props') or {}, with_attrs=False)}招聘，"
                f"工作地点{describe_node(city.get('end_props') or {}, with_attrs=False)}")
        at_key = (str(at.get("start")), str(at.get("rel")), str(at.get("end")))
        city_key = (str(city.get("start")), str(city.get("rel")), str(city.get("end")))
        merged[at_key] = (text, [str(at.get("start")), str(at.get("end")), str(city.get("end"))])
        suppressed.add(city_key)
    return merged, suppressed


def retrieve_graph(query: str, top_k: Optional[int] = None) -> Dict:
    """图谱检索主入口。

    参数：
        query: 用户问题原文
        top_k: 最多返回几条事实；None 时取配置 GRAPH_TOP_K
    返回：
        {
          "facts":  [{"text","score","hop","entities":[...],"sources":[...]}],
          "entities": [{"id","name","type","matched","score"}],   # 命中的起点实体
          "mode": "graph" | "none",
          "used": bool,
          "error": "",
          "stats": {"seeds","edges","truncated"},
        }

    ⚠️ 同步阻塞（Bolt 网络调用），async 环境请用 asyncio.to_thread 调用
       （app/core/rag.py 里已经这么做了）。
    """
    cfg = _config()
    result = {
        "facts": [], "entities": [], "mode": "none", "used": False, "error": "",
        "stats": {"seeds": 0, "edges": 0, "truncated": False},
    }

    # ---- 开关：GRAPH_ENABLED=false 时直接返回空，等价于「没有图谱这回事」 ----
    if not cfg.GRAPH_ENABLED:
        result["error"] = "图谱检索未启用（GRAPH_ENABLED=false）"
        return result

    question = str(query or "").strip()
    if not question:
        result["error"] = "查询为空"
        return result

    k = top_k or cfg.GRAPH_TOP_K
    if k <= 0:
        result["error"] = "GRAPH_TOP_K 配置非法"
        return result

    from app.core import graph_store

    # ---- 第 1 步：实体链接 ----
    try:
        seeds = graph_store.link_entities(question, limit=cfg.GRAPH_SEED_LIMIT)
    except Exception as e:                       # noqa: BLE001 - 降级优先，不区分异常类型
        result["error"] = f"图谱不可用：{e}"
        logger.warning("[graph] %s", result["error"])
        return result

    if not seeds:
        result["error"] = "问题里没有识别到图谱实体（可能是闲聊或问法太泛）"
        return result

    result["entities"] = seeds
    result["stats"]["seeds"] = len(seeds)
    seed_ids = [s["id"] for s in seeds]

    # ---- 第 2 步：子图扩展（多跳；最佳命中实体优先，见 _expand_subgraph） ----
    try:
        sub = _expand_subgraph(seed_ids, hops=cfg.GRAPH_MAX_HOPS, budget=cfg.GRAPH_EXPAND_LIMIT)
    except Exception as e:                       # noqa: BLE001
        result["error"] = f"图谱扩展失败：{e}"
        logger.warning("[graph] %s", result["error"])
        return result

    nodes = sub.get("nodes") or {}
    edges = sub.get("edges") or []
    result["stats"]["edges"] = len(edges)
    result["stats"]["truncated"] = bool(sub.get("truncated"))

    # ---- 第 3 步：渲染事实（起点自身属性优先，然后按跳数由近到远） ----
    # 溯源信息：这些实体在哪些知识块里被提到过（用于事实末尾标注来源）
    try:
        sources = graph_store.provenance(list(nodes.keys())[:20])
    except Exception as e:                       # noqa: BLE001 - 溯源失败不影响事实本身
        logger.info("[graph] 溯源查询失败（忽略）：%s", e)
        sources = {}

    facts: List[Dict] = []
    seen_text = set()

    def _push(text: str, score: float, hop: int, ents: Sequence[str]) -> None:
        text = " ".join(str(text or "").split())
        if not text:
            return
        if len(text) > cfg.GRAPH_FACT_MAX_CHARS:
            text = text[:cfg.GRAPH_FACT_MAX_CHARS] + "…"
        if text in seen_text:
            return
        seen_text.add(text)
        cited: List[str] = []
        for eid in ents:
            for title in sources.get(eid, []):
                if title and title not in cited:
                    cited.append(title)
        facts.append({"text": text, "score": score, "hop": hop,
                      "entities": list(ents), "sources": cited[:2]})

    # 3.1 起点实体自身（问题往往就是在问它的属性，如「这个岗位薪资多少」）
    for s in seeds[:3]:
        props = nodes.get(s["id"])
        if props:
            _push(describe_node(props), 1.0, 0, [s["id"]])

    # 3.2 关系事实：先 1 跳（直接关系），再 2 跳（多跳推理）
    # ⚠️ 排序里额外加一层「是否接在最佳命中实体上」：
    #    问题往往同时命中一个具体实体（如某个职位）和一个宽泛实体（如它的职能），
    #    宽泛实体的邻居数量远多于具体实体 —— 不区分的话，
    #    职能下的其他职位会把「这个职位哪家在招」挤出事实列表，反而不贴题。
    primary = seed_ids[0] if seed_ids else ""

    def _edge_rank(edge: Dict):
        ends = {str(edge.get("start")), str(edge.get("end"))}
        rel = str(edge.get("rel"))
        return (0 if primary in ends else 1,
                _distance_of(edge, seed_ids),
                _REL_ORDER.get(rel, 10),
                rel)

    ordered = sorted(edges, key=_edge_rank)

    # 3.2.1 合并事实：同一职位上的「公司」与「城市」合成一句人话
    merged, suppressed = _merge_job_facts(ordered, nodes)

    rel_count: Dict[str, int] = {}
    for e in ordered:
        key = (str(e.get("start")), str(e.get("rel")), str(e.get("end")))
        if key in suppressed:
            # 已经被合并进 AT_COMPANY 那条事实里，不重复渲染
            continue
        hop = _distance_of(e, seed_ids)
        rel = str(e.get("rel"))
        cap = _REL_FACT_CAP.get(rel)
        if cap is not None and rel_count.get(rel, 0) >= cap:
            # 同类关系已到上限（如技能已给了 2 条），跳过，把名额让给其他关系
            continue

        if key in merged:
            text, ents = merged[key]
            # 合并事实同时代表 AT_COMPANY 与 IN_CITY 两条关系，
            # 因此两条关系的名额都要记一笔（否则后面还会再挤进来一条同义的）
            rel_count["AT_COMPANY"] = rel_count.get("AT_COMPANY", 0) + 1
            rel_count["IN_CITY"] = rel_count.get("IN_CITY", 0) + 1
            _push(text, 0.85 if hop == 1 else 0.7, hop, ents)
            continue

        rel_count[rel] = rel_count.get(rel, 0) + 1
        _push(describe_edge(e), 0.85 if hop == 1 else 0.7, hop,
              [str(e.get("start")), str(e.get("end"))])

    result["facts"] = facts[:k]
    result["mode"] = "graph"
    result["used"] = bool(result["facts"])
    if not result["used"]:
        result["error"] = "图谱命中实体但没有可展示的关系/属性"

    logger.info(
        "[graph] 命中实体 %d 个（%s），扩展边 %d 条，产出事实 %d 条%s",
        len(seeds), "、".join(s["name"] for s in seeds[:3]),
        len(edges), len(result["facts"]),
        "（已按上限截断）" if sub.get("truncated") else "",
    )
    return result


def build_facts_text(facts: Sequence[Dict]) -> str:
    """把事实列表拼成一段纯文本（调试、日志、接口返回用）。

    返回：
        多行文本；facts 为空时返回空串
    """
    lines = []
    for i, f in enumerate(facts, start=1):
        cite = f"（来源：{'、'.join(f.get('sources') or [])}）" if f.get("sources") else ""
        lines.append(f"{i}. {f.get('text')}{cite}")
    return "\n".join(lines)


def to_contexts(facts: Sequence[Dict]) -> List[Dict]:
    """把图谱事实转成与向量检索一致的知识块结构，供 app/core/rag.py 融合。

    返回：
        [{"text","score","kind":"graph","title","source","type","sources","entities"}, ...]
        ⚠️ kind="graph" 是给 build_system_prompt 用的分流标记：
           图谱事实会被渲染到「知识图谱事实」段落，而不是「参考资料」段落；
           sources 是这条事实的出处（知识块标题），渲染成「（出处：…）」。
    """
    out: List[Dict] = []
    for f in facts:
        text = str(f.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "text": text,
            "score": float(f.get("score") or 0.0),
            "kind": "graph",
            "hop": int(f.get("hop") or 0),
            "title": "知识图谱事实",
            "source": "Neo4j 知识图谱",
            "type": "graph",
            # 出处单独放在 sources 里（提示词渲染时要拼成「（出处：...）」）
            "sources": list(f.get("sources") or []),
            "entities": list(f.get("entities") or []),
        })
    return out
