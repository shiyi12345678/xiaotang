"""实体关系抽取（GraphRAG 的「数据准备层」）。

两条抽取路线，对应两类数据，最后合并成同一张图：

    A. 规则抽取（extract_structural）—— 面向【结构化数据】
       职位、公司、城市、职能方向、技能标签、面试题、行业、平台规则……这些字段
       本身就已经是「实体 + 属性 + 关系」，用代码直接翻译成图即可：
       零成本、100% 准确、可重复、可增量，不调用任何大模型。

    B. 大模型抽取（extract_llm）—— 面向【非结构化文本】
       平台规则与求职建议这类整段散文里的实体关系只能靠语义理解抽取。
       用 DeepSeek 按固定 JSON 结构输出，并做严格的「反幻觉」校验：
         · 实体名必须逐字出现在原文里（改写/翻译/自造的一律丢弃）
         · 关系两端必须是同一片段里抽出的实体
         · 实体类型、关系类型必须在白名单内
       任一校验不通过就丢该条，而不是把脏数据写进图。

⚠️ 设计取向：图宁可比真实数据「瘦」一点，也不要混入幻觉。
   图谱一旦写入脏实体，检索时会把错误事实喂给大模型，比没有图谱更糟。

⚠️ 为什么这一层必须整体换成招聘域（而不是打补丁）：
   改造前整张图是课程域（课程 / 讲师 / 题库 / 记忆卡……），而 Milvus 向量库
   已经换成 136 条招聘知识块。两套知识口径不一致时，AI 求职助手在问
   「AI 数字技能是什么」时会把「某课程属于某分类」当成事实讲给求职者 ——
   这不是准确性问题，而是对招聘 App 的内容事故。因此实体类型与关系类型
   一起换血，并由 tools/graph_ingest.py --rebuild 重建整张图。
"""
import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.graph_store import (
    PROVENANCE_REL, REL_TYPES, TYPE_TO_LABEL, make_chunk_id, make_entity_id,
    normalize_name,
)

logger = logging.getLogger(__name__)

# 大模型允许输出的关系类型：只留「语义开放」的几种。
# ⚠️ 刻意排除 BELONGS_TO / AT_COMPANY / IN_CITY / REQUIRES / TESTS /
#    IN_INDUSTRY / IN_BANK：这些关系的两端在结构化数据里是明确字段，
#    规则抽取已经 100% 覆盖；让模型再抽一遍只会引入
#    「把 A 职位的职能挂到 B 职位」这类错关系，而错关系比没关系的危害大得多。
LLM_REL_TYPES = ("RELATES_TO", "PART_OF", "INCLUDES", "SUPPORTS", "PROVIDES", "USES")

# 大模型允许输出的实体类型：只留 skill。
# ⚠️ 这是实测结论，不是拍脑袋：让模型抽全部类型跑一遍（14 条平台规则知识块），
#    它抽出了「全职 / 实习 / 兼职」当职位、「城市」当城市、「职能方向」当职能、
#    「我的投递 / 热门搜索词」当平台规则 —— 全是把正文里的词硬套成实体。
#    这些伪实体会直接污染实体链接（同名实体按类型优先级抢起点），
#    对求职者是错误事实，比没有这条图数据更糟。
#    真正规则抽不出来、又确实有价值的只有「技能之间的关系」：
#    职位的技能由 JD 正文匹配、面试题的技能由标签给出，但技能之间怎么关联
#    只能靠语义理解，因此把模型的能力收窄到这一件事上。
LLM_ENTITY_TYPES = ("skill",)

# 抽取失败时的重试与并发（灌图时对上游接口要客气一点）
_LLM_CONCURRENCY = 3

# 招聘语义枚举 → 中文。
# ⚠️ 与 tools/rag_ingest.py 的 KIND_LABELS / JOB_TYPE_LABELS 保持一致口径，
#    但 app 层不反向依赖 tools 脚本（app 是运行时、tools 是运维脚本），
#    因此这里本地保留一份；改动时两处要同步（漏改只会让图谱文案与知识块不一致）。
KIND_LABELS = {
    "normal": "社招全职",
    "urgent": "急招",
    "referral": "名企内推",
    "intern": "实习",
    "campus": "校园招聘",
}
JOB_TYPE_LABELS = {"fulltime": "全职", "intern": "实习", "parttime": "兼职"}
DIFFICULTY_LABELS = {1: "简单", 2: "中等", 3: "困难"}

# 面试题库节点的别名：用户不会说「面试题库」，而是说「面试常考什么」，
# 实体链接是子串匹配，靠别名才能把这些口语问法对齐到同一个节点。
BANK_NAME = "面试题库"
BANK_ALIASES = ("面试题", "高频面试题", "面试真题", "面试常考", "常考面试题", "面试考察点")

# JD 正文匹配时要排除的「泛化技能词」。
# ⚠️ 这些词本身是面试题标签（保留为 Skill 实体没问题），但拿去做 JD 文本匹配会
#    大面积误命中：实测「沟通」命中 17 个职位、「优化」15 个、「协作」11 个、
#    「复盘」10 个 —— 渲染出来就是「《算法工程师》要求掌握「沟通」」这种废话，
#    还会把真实技术栈（MySQL/Redis）挤出 REQUIRES 的名额。
GENERIC_SKILL_STOPWORDS = (
    "沟通", "协作", "复盘", "优化", "自动化", "统计", "算法", "谈判", "招聘",
    "选题", "留存", "爆款", "供给", "优先级", "归因", "需求分析", "员工关系",
    "候选人体验", "服务质量",
)

# JD 正文里出现、但面试题标签里没有的技术栈补充词（关键词, 规范技能名）。
# ⚠️ 表刻意做小：只在 JD 正文里真的出现时才建实体，绝不凭空造技能；
#    ASCII 关键词用词边界匹配，避免 Java 命中 JavaScript、Go 命中 Google。
EXTRA_JD_SKILLS = (
    ("Python", "Python"), ("Go", "Go"), ("Django", "Django"), ("FastAPI", "FastAPI"),
    ("Spring", "Spring"), ("SQL", "SQL"), ("Docker", "Docker"), ("Nginx", "Nginx"),
    ("K8s", "Kubernetes"), ("Kubernetes", "Kubernetes"), ("React", "React"),
    ("TypeScript", "TypeScript"), ("Vue", "Vue3"), ("Spark", "Spark"),
    ("Hive", "Hive"), ("Flink", "Flink"), ("Excel", "Excel"), ("Figma", "Figma"),
    ("Axure", "Axure"), ("Photoshop", "Photoshop"), ("CRM", "CRM"), ("ERP", "ERP"),
)

# 每个职位最多挂几条 REQUIRES：保持事实多样性，避免「技术栈一串」占满事实名额
_MAX_SKILLS_PER_JOB = 5
# 职位名唯一时直接用它做主名（用户就是这么问的）；重名时才追加公司简称消歧
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 自检：大模型白名单必须是存储层白名单的子集。
# 两处白名单一旦改漏（例如这里加了新实体类型、graph_store 忘了登记），
# 抽取结果会被存储层静默跳过，排查起来非常费劲，因此在导入时就断掉。
assert set(LLM_ENTITY_TYPES) <= set(TYPE_TO_LABEL), "LLM 实体白名单超出存储层白名单"
assert set(LLM_REL_TYPES) <= set(REL_TYPES), "LLM 关系白名单超出存储层白名单"


# ==========================================================
# A. 规则抽取：结构化数据 → 图
# ==========================================================


def _to_int(value) -> int:
    """把种子里的「数字或数字字符串」安全转成 int（转不了就当 0）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _fmt_salary(job: Dict) -> str:
    """把 salary_min / salary_max / salary_months 拼成招聘端文案「25-45K·15薪」。

    ⚠️ 口径与 tools/rag_ingest.py 的 _fmt_salary 一致：12 薪是默认值，
       写出来只是噪声，因此只在 13 薪及以上时才带月份数。
    """
    lo, hi = _to_int(job.get("salary_min")), _to_int(job.get("salary_max"))
    months = _to_int(job.get("salary_months"))
    if not lo and not hi:
        return "薪资面议"
    text = f"{lo}-{hi}K" if lo and hi and lo != hi else f"{lo or hi}K"
    if months and months != 12:
        text += f"·{months}薪"
    return text


def _job_props(job: Dict) -> Dict:
    """职位节点的属性：只放「求职者真正会问」的短事实。

    ⚠️ 岗位职责 / 任职要求这类长文本【刻意不进图】：图谱事实会被直接拼进提示词，
       而长文本已经在向量知识块里了（同源同口径）。图里只留可渲染的短字段，
       避免一个职位节点就把提示词预算吃掉。
    """
    kind = str(job.get("kind") or "").strip()
    job_type = str(job.get("job_type") or "").strip()
    kind_zh = KIND_LABELS.get(kind, kind)
    type_zh = JOB_TYPE_LABELS.get(job_type, job_type)
    # kind 与 job_type 有重叠（normal+fulltime = 社招全职+全职、intern+intern = 实习+实习），
    # 只在前者「装不下」后者时才并列写出来
    kind_text = kind_zh if (not type_zh or type_zh in kind_zh) else f"{kind_zh}/{type_zh}"

    city = str(job.get("city_name") or "").strip()
    district = str(job.get("district") or "").strip()
    hr = "·".join(x for x in (str(job.get("hr_name") or "").strip(),
                              str(job.get("hr_title") or "").strip(),
                              str(job.get("hr_active") or "").strip()) if x)
    process = " → ".join(str(p) for p in ((job.get("extra") or {}).get("process") or []))

    props = {
        "salary": _fmt_salary(job),
        "experience": str(job.get("experience") or "经验不限").strip(),
        "education": str(job.get("education") or "学历不限").strip(),
        "kind": kind_text,
        "location": f"{city}·{district}" if city and district else (city or district),
        "hr": hr,
        "tags": [str(t).strip() for t in (job.get("tags") or []) if str(t or "").strip()],
        "process": process,
    }
    views, applicants = _to_int(job.get("view_count")), _to_int(job.get("applicant_count"))
    if views or applicants:
        # 招聘热度是「这个岗位竞争激烈吗」的唯一依据，保留
        props["heat"] = f"被浏览 {views} 次，{applicants} 人投递"
    return props


def _build_skill_patterns(skill_tags: Sequence[str]) -> List[Tuple[str, str, str, bool]]:
    """把技能词表编译成匹配模式：[(匹配键, 规范技能名, 关键词, 是否 ASCII)]。

    匹配策略按「名字里有没有中文」分两路：
        · 含中文（如「性能优化」「AB实验」）：在【归一化文本】上做子串匹配，
          标点差异（B+树 与 B树）不影响；
        · 纯 ASCII（如 MySQL / CI/CD）：在原文上做词边界匹配，
          否则 Java 会命中 JavaScript、Go 会命中 Google、CI 会命中 CICD。
    """
    patterns: List[Tuple[str, str, str, bool]] = []
    seen = set()
    entries: List[Tuple[str, str]] = [(t, t) for t in skill_tags] + list(EXTRA_JD_SKILLS)
    for keyword, canonical in entries:
        keyword, canonical = str(keyword or "").strip(), str(canonical or "").strip()
        if len(normalize_name(canonical)) < 2:
            continue
        is_ascii = not _CJK_RE.search(keyword)
        key = ("a" if is_ascii else "c") + keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        patterns.append((key, canonical, keyword, is_ascii))
    return patterns


def _match_skills(text: str, patterns: Sequence[Tuple[str, str, str, bool]],
                  limit: int = _MAX_SKILLS_PER_JOB) -> List[str]:
    """在职位正文里匹配技能词，返回规范技能名（长的名字更具体，优先保留）。"""
    raw = str(text or "").lower()
    norm_text = normalize_name(text)
    stop = {normalize_name(w) for w in GENERIC_SKILL_STOPWORDS}
    hits: List[str] = []
    for _key, canonical, keyword, is_ascii in patterns:
        if normalize_name(canonical) in stop:
            continue
        if is_ascii:
            pattern = r"(?<![0-9a-z])" + re.escape(keyword.lower()) + r"(?![0-9a-z])"
            if re.search(pattern, raw):
                hits.append(canonical)
        elif normalize_name(keyword) in norm_text:
            hits.append(canonical)
    # 「性能优化」比「优化」具体：先保留长名字，再截断到上限
    hits.sort(key=lambda n: (-len(normalize_name(n)), n))
    return hits[:max(1, limit)]


def _common_run_len(a: str, b: str) -> int:
    """两个字符串的最长公共子串长度（用于面试题 position 与职能名的兜底匹配）。"""
    if not a or not b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    best, prev = 0, [0] * (len(a) + 1)
    for ch in b:
        cur = [0] * (len(a) + 1)
        for i in range(1, len(a) + 1):
            if a[i - 1] == ch:
                cur[i] = prev[i - 1] + 1
                if cur[i] > best:
                    best = cur[i]
        prev = cur
    return best


def _clip(text: str, limit: int) -> str:
    """按字符数截断并补省略号（用于必须塞进图谱属性里的长句）。"""
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:max(1, limit - 1)] + "…"


def extract_structural(data: Dict, content: Optional[Dict] = None) -> Dict[str, List[Dict]]:
    """从招聘种子数据里构建图谱（规则抽取，零 token 成本）。

    参数：
        data:    seed/recruit_jobs.json 的内容
                 （companies 10 / cities 16 / jobCategories 45 / jobs 45）
        content: seed/recruit_content.json 的内容
                 （interviewQuestions 55 / pageConfig），可省略
    返回：
        {"nodes": [...], "edges": [...]}，结构与 graph_store.upsert 的入参一致

    ⚠️ 实体/关系的取舍（都是按招聘语义重新定的，不是照搬课程域）：
        1) 职位标签（job.tags，如「五险一金」「双休」）是【福利】不是技能，
           因此只作为职位属性保留，不建 Welfare 实体：45 个职位 × 4 个标签
           ≈ 180 条低信息量的边，会把「哪家公司招的、薪资多少、什么职能」
           这些真正贴题的事实挤出 GRAPH_TOP_K=6 的事实名额
           （旧图里 HAS_TAG 51 条就是这个毛病）。
        2) 技能（skill）有两个来源：面试题的 tags（权威，153 个）+
           职位 JD 正文里出现的少量技术栈补充词（Python/Docker/K8s 等）。
           补充词表刻意很小，且只在正文里真的出现时才建实体，不凭空造技能。
        3) 行业与面试题库只从结构化字段确定性生成，不交给大模型抽。
        4) 平台规则（guide）只取 pageConfig 里的【规则/建议】类内容
           （内推规则与答疑、求职建议、HR 招聘建议、平台安全提示）；
           功能入口、筛选选项、公告列表属于前端展示配置，不进图。
    """
    nodes: List[Dict] = []
    edges: List[Dict] = []
    node_ids = set()
    edge_keys = set()
    by_id: Dict[str, Dict] = {}

    def add_node(etype: str, name: str, props: Optional[Dict] = None,
                 aliases: Optional[Sequence[str]] = None) -> Optional[str]:
        name = str(name or "").strip()
        if not name:
            return None
        nid = make_entity_id(etype, name)
        if nid in node_ids:
            # 同一实体被多个来源提到（如技能既来自面试题标签、又来自 JD 正文）：
            # 属性以先到的为准，别名取并集
            node = by_id[nid]
            for a in aliases or []:
                if a and a not in node["aliases"]:
                    node["aliases"].append(a)
            return nid
        node_ids.add(nid)
        node = {
            "id": nid, "name": name, "type": etype,
            "props": props or {}, "aliases": [a for a in (aliases or []) if a],
        }
        nodes.append(node)
        by_id[nid] = node
        return nid

    def add_edge(start: Optional[str], rel: str, end: Optional[str],
                 props: Optional[Dict] = None) -> None:
        if not start or not end or start == end:
            return
        key = (start, rel, end)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({"start": start, "end": end, "type": rel, "props": props or {}})

    def set_props(nid: Optional[str], **extra) -> None:
        """回填统计类属性（如「在招职位 7 个」），空值不写入。"""
        if not nid or nid not in by_id:
            return
        for k, v in extra.items():
            if v not in (None, "", [], {}):
                by_id[nid]["props"][k] = v

    jobs = data.get("jobs") or []
    companies = data.get("companies") or []
    cities = data.get("cities") or []
    cats = data.get("jobCategories") or []
    questions = (content or {}).get("interviewQuestions") or []
    page_config = (content or {}).get("pageConfig") or {}

    # ---------- 1) 城市（cities 是权威表；职位里出现但表里没有的城市兜底建档） ----------
    city_by_name: Dict[str, str] = {}
    city_jobs: Dict[str, int] = {}
    for job in jobs:
        name = str(job.get("city_name") or "").strip()
        if name:
            city_jobs[name] = city_jobs.get(name, 0) + 1

    for c in cities:
        cname = str(c.get("name") or "").strip()
        nid = add_node("city", cname, props={"province": c.get("province")})
        if nid and cname:
            city_by_name[normalize_name(cname)] = nid
    for job in jobs:
        cname = str(job.get("city_name") or "").strip()
        if cname and normalize_name(cname) not in city_by_name:
            nid = add_node("city", cname)
            if nid:
                city_by_name[normalize_name(cname)] = nid
    for cname, cnt in city_jobs.items():
        set_props(city_by_name.get(normalize_name(cname)), jobCount=cnt)

    # ---------- 2) 行业（从公司 industry 字段确定性生成，不让模型造） ----------
    industry_ids: Dict[str, str] = {}
    for comp in companies:
        iname = str(comp.get("industry") or "").strip()
        if not iname:
            continue
        industry_ids.setdefault(normalize_name(iname), add_node("industry", iname) or "")

    # ---------- 3) 职能方向（一级 10 + 二级 35，二级 → 一级 建 BELONGS_TO） ----------
    cat_ids: Dict[str, str] = {}
    cat_by_id: Dict[str, Dict] = {str(c.get("id")): c for c in cats}
    cat_jobs: Dict[str, int] = {}
    for job in jobs:
        cid = str(job.get("category_id") or "")
        if cid:
            cat_jobs[cid] = cat_jobs.get(cid, 0) + 1

    used_cat_names: Dict[str, str] = {}
    # 先建一级方向（level=1），再建二级职能：同名判定要能查到一级
    for c in sorted(cats, key=lambda x: _to_int(x.get("level")) or 99):
        cid = str(c.get("id") or "")
        cname = str(c.get("name") or "").strip()
        if not cname:
            continue
        level = _to_int(c.get("level")) or 1
        display = cname
        if normalize_name(cname) in used_cat_names:
            # ⚠️ 实测数据里「产品经理」既是一级方向、又是二级职能（cat-product /
            #    cat-product-pm）。同名会被 MERGE 成同一个节点，层级关系随之丢失
            #    （二级→一级 的边会变成自环被丢弃），因此给后来者加后缀，
            #    同时把原名登记成别名，保证「产品经理」这个问法仍然命中两个节点。
            display = f"{cname}（二级职能）"
        parent = cat_by_id.get(str(c.get("parent_id") or "")) or {}
        nid = add_node("category", display, props={
            "levelZh": "一级方向" if level == 1 else "二级职能",
            "desc": c.get("description"),
            "parentName": parent.get("name"),
        }, aliases=[cname] if display != cname else None)
        if nid and cid:
            cat_ids[cid] = nid
            used_cat_names[normalize_name(cname)] = nid
            set_props(nid, jobCount=cat_jobs.get(cid))
    # 二级职能 → 一级方向
    for c in cats:
        pid = str(c.get("parent_id") or "")
        if pid:
            add_edge(cat_ids.get(str(c.get("id"))), "BELONGS_TO", cat_ids.get(pid))

    # ---------- 4) 公司（主名用简称：用户问的从来是「星野智能」而不是全称） ----------
    company_ids: Dict[str, str] = {}
    company_jobs: Dict[str, int] = {}
    for job in jobs:
        key = str(job.get("company_id") or "")
        if key:
            company_jobs[key] = company_jobs.get(key, 0) + 1

    for comp in companies:
        cid = str(comp.get("id") or "")
        short = str(comp.get("short_name") or comp.get("name") or "").strip()
        full = str(comp.get("name") or "").strip()
        props = {
            "fullName": full if full and full != short else None,
            "scale": comp.get("scale"),
            "stage": comp.get("stage"),
            "city": comp.get("city"),
            "address": comp.get("address"),
            "benefits": [str(b).strip() for b in (comp.get("benefits") or []) if str(b or "").strip()],
            "website": comp.get("website"),
        }
        nid = add_node("company", short, props={k: v for k, v in props.items() if v},
                       aliases=[full] if full and full != short else None)
        if not nid:
            continue
        company_ids[cid] = nid
        set_props(nid, jobCount=company_jobs.get(cid))
        # 行业只走 IN_INDUSTRY 关系，不再重复存一份属性（同一事实在提示词里出现两次只是浪费）
        add_edge(nid, "IN_INDUSTRY", industry_ids.get(normalize_name(comp.get("industry"))))
        add_edge(nid, "IN_CITY", city_by_name.get(normalize_name(comp.get("city"))))

    # ---------- 5) 公司 → 行业 的统计属性（回答「人工智能行业有哪些公司」） ----------
    industry_companies: Dict[str, List[str]] = {}
    for comp in companies:
        iname = str(comp.get("industry") or "").strip()
        short = str(comp.get("short_name") or comp.get("name") or "").strip()
        if iname and short:
            industry_companies.setdefault(normalize_name(iname), []).append(short)
    for key, names in industry_companies.items():
        set_props(industry_ids.get(key), companyCount=len(names), companies=names)

    # ---------- 6) 技能（面试题标签是权威词表；JD 正文只用来补技术栈） ----------
    skill_tags = [str(t).strip() for q in questions
                  for t in (q.get("tags") or []) if str(t or "").strip()]
    skill_patterns = _build_skill_patterns(skill_tags)
    skill_ids: Dict[str, str] = {}
    skill_job_hits: Dict[str, int] = {}
    skill_question_hits: Dict[str, int] = {}

    def add_skill(name: str) -> Optional[str]:
        norm = normalize_name(name)
        if len(norm) < 2:
            # 「AI」这种两字符以内的名字一律不成实体：它会在任何句子里命中，
            # 属于典型的「宽泛实体霸榜」源头
            return None
        if norm in skill_ids:
            return skill_ids[norm]
        nid = add_node("skill", name)
        if nid:
            skill_ids[norm] = nid
        return nid

    for tag in skill_tags:
        add_skill(tag)

    # ---------- 7) 职位（招聘 App 的第一等实体，一次连齐职能/公司/城市/技能） ----------
    company_by_id = {str(c.get("id")): c for c in companies}
    title_counts: Dict[str, int] = {}
    for job in jobs:
        key = normalize_name(job.get("title"))
        title_counts[key] = title_counts.get(key, 0) + 1

    referral_job_ids: List[str] = []
    for job in jobs:
        title = str(job.get("title") or "").strip()
        if not title:
            continue
        comp = company_by_id.get(str(job.get("company_id") or "")) or {}
        short = str(comp.get("short_name") or comp.get("name") or "").strip()

        job_name, aliases = title, []
        if title_counts.get(normalize_name(title), 0) > 1:
            # ⚠️ 实测有 2 条「物流运营专员」（分属不同公司）：同名会被 MERGE 成
            #    同一个节点 —— 职位少一个，公司/薪资还会串在一起。给重名职位
            #    追加公司简称消歧，同时把原职位名登记成别名，
            #    保证「物流运营专员」这个问法仍然能同时命中两条。
            job_name = f"{title}（{short}）" if short else title
            aliases = [title]
        nid = add_node("job", job_name, props=_job_props(job), aliases=aliases)
        if not nid:
            continue

        add_edge(nid, "BELONGS_TO", cat_ids.get(str(job.get("category_id") or "")))
        add_edge(nid, "AT_COMPANY", company_ids.get(str(job.get("company_id") or "")))
        add_edge(nid, "IN_CITY", city_by_name.get(normalize_name(job.get("city_name"))))

        # REQUIRES：在「职位名 + 任职要求 + 岗位职责」里匹配技能词表。
        # 只用正文匹配（不做语义推断），因此宁可少几条也不错挂一条。
        jd_text = " ".join([title, str(job.get("requirements") or ""),
                            str(job.get("description") or "")])
        for skill_name in _match_skills(jd_text, skill_patterns):
            sid = skill_ids.get(normalize_name(skill_name)) or add_skill(skill_name)
            if not sid:
                continue
            add_edge(nid, "REQUIRES", sid)
            key = normalize_name(skill_name)
            skill_job_hits[key] = skill_job_hits.get(key, 0) + 1

        if str(job.get("kind") or "") == "referral":
            referral_job_ids.append(nid)

    for key, sid in skill_ids.items():
        set_props(sid, jobCount=skill_job_hits.get(key))

    # ---------- 8) 面试题（题干 + 参考答案 + 难度 + 热度，串起技能与职能） ----------
    # ⚠️ 实测坑：recruit_content.json 里有 22 道题的 category_id 还是旧命名
    #    （cat-pm-plan / cat-sc-plan / cat-mkt-growth…），在 jobCategories 里查不到。
    #    种子文件不在本次改造范围内，因此这里做三级兜底（都由题目自带的 position 推导）：
    #      ① 同名（「产品经理」→ 职能「产品经理」）；
    #      ② 互为子串且候选唯一（「财务会计」→「会计」）；
    #      ③ 最长公共片段 ≥2 字且候选唯一（「客服专员」→「在线客服」）。
    #    有歧义就放弃（「数据分析师」既像「数据运营」又像「数据开发」）——
    #    宁可少一条边，也不能给求职者挂错职能：错关系会被当成事实注入提示词。
    #    注意：同名职能（一级「产品经理」与二级「产品经理（二级职能）」）取后者，
    #    与职位数据里 cat-product-pm 的归属保持一致。
    cat_norm_names: Dict[str, str] = {}
    for c in cats:
        cname = str(c.get("name") or "").strip()
        nid = cat_ids.get(str(c.get("id") or ""))
        if cname and nid:
            cat_norm_names[normalize_name(cname)] = nid

    def resolve_question_cat(q: Dict) -> Optional[str]:
        nid = cat_ids.get(str(q.get("category_id") or ""))
        if nid:
            return nid
        pos = normalize_name(q.get("position"))
        if len(pos) < 2:
            return None
        if pos in cat_norm_names:
            return cat_norm_names[pos]
        sub = [cid for name, cid in cat_norm_names.items()
               if name and (name in pos or pos in name)]
        if len(sub) == 1:
            return sub[0]
        near = [cid for name, cid in cat_norm_names.items()
                if name and _common_run_len(pos, name) >= 2]
        return near[0] if len(near) == 1 else None

    question_cats = set()
    for q in questions:
        stem = str(q.get("question") or "").strip()
        if not stem:
            continue
        position = str(q.get("position") or "通用").strip()
        difficulty = DIFFICULTY_LABELS.get(_to_int(q.get("difficulty")), "")
        frequency = _to_int(q.get("frequency"))
        # ⚠️ 题干可能有上百字：直接当名字会让实体名长到没法匹配，
        #    截断成前 60 字作为显示名；完整题干本来就在向量知识块里，不会丢信息。
        qid = add_node("question", stem[:60], props={
            "answer": str(q.get("answer") or "").strip(),
            "difficulty": difficulty,
            "position": position,
            "frequency": f"被 {frequency} 条面经提到" if frequency else None,
            "source": q.get("source"),
        })
        if not qid:
            continue
        cat_nid = resolve_question_cat(q)
        if cat_nid:
            question_cats.add(cat_nid)
        add_edge(qid, "BELONGS_TO", cat_nid)
        for tag in (q.get("tags") or []):
            sid = skill_ids.get(normalize_name(tag)) or add_skill(tag)
            if not sid:
                continue
            add_edge(qid, "TESTS", sid)
            key = normalize_name(tag)
            skill_question_hits[key] = skill_question_hits.get(key, 0) + 1

    # ---------- 9) 面试题库（聚合节点） ----------
    # ⚠️ 为什么需要这个节点：「面试常考什么」「面试题库里有什么」这类问法里
    #    没有任何具体职位/公司/技能名，实体链接（子串匹配）必然落空，
    #    图谱就永远帮不上忙。给它一个带口语别名的聚合节点，
    #    这一整类「聚合型提问」才有 1 跳的入口（参见 BANK_ALIASES 的说明）。
    seeker_tips = [str(t).strip() for t in
                   ((page_config.get("rcSeekerReport") or {}).get("tips") or [])
                   if str(t or "").strip()]
    if questions:
        bank_nid = add_node("bank", BANK_NAME, props={
            "count": f"{len(questions)} 道",
            "desc": f"覆盖 {len(question_cats)} 个职能方向，含参考答案与难度标注",
            "tip": next((t for t in seeker_tips if "面试" in t), ""),
        }, aliases=list(BANK_ALIASES))
        for q in questions:
            stem = str(q.get("question") or "").strip()
            if stem:
                add_edge(make_entity_id("question", stem[:60]), "IN_BANK", bank_nid)

    # ---------- 10) 平台规则与求职建议（只取 pageConfig 里的规则/建议类） ----------
    # ⚠️ 取舍：pageConfig 里还有横幅、入口、筛选选项、公告、AI 能力介绍等，
    #    那些属于「前端展示配置」而不是平台规则，进图只会制造噪声事实
    #    （旧的 feature/doc 实体就是这么来的），因此这里只挑 rules / tips。
    referral = page_config.get("rcReferralZone") or {}
    rules = [str(r).strip() for r in (referral.get("rules") or []) if str(r or "").strip()]
    # ⚠️ 问答拼成一条后必须自己截断：graph_store 对列表项的硬上限是 60 字，
    #    超出会被从中间切掉（会切出「反馈速度更快；但面」这种断句）。
    #    这里主动按 58 字裁并补省略号，读起来是「有意省略」而不是「数据坏了」。
    faq_items = [_clip(f"{f.get('q')} → {f.get('a')}", 58)
                 for f in (referral.get("faq") or [])
                 if isinstance(f, dict) and str(f.get("q") or "").strip()]

    guide_rules = None
    if rules:
        # 别名里带上「内推」这两个字：用户问的是「内推有什么规则」「内推要满足什么条件」，
        # 问题里并不会连着出现「内推规则」四个字，而实体链接是子串匹配
        # （实测没有这个别名时「内推有什么规则」完全命中不到图谱）。
        guide_rules = add_node("guide", "内推规则", props={
            "items": rules, "source": "名企内推专区",
        }, aliases=["内推", "内推专区", "名企内推", "内推条件"])
    if guide_rules and referral_job_ids:
        # 内推规则 ↔ 名企内推职位：问「内推岗位有哪些」时两条线都能走通
        for jid in referral_job_ids:
            add_edge(guide_rules, "APPLIES_TO", jid)
    if faq_items:
        guide_faq = add_node("guide", "内推常见问题", props={
            "items": faq_items, "source": "名企内推专区 · 常见问题",
        }, aliases=["内推答疑", "内推问答", "内推faq", "内推收费"])
        add_edge(guide_faq, "RELATES_TO", guide_rules)

    if seeker_tips:
        add_node("guide", "求职建议", props={
            "items": seeker_tips, "source": "求职报告给出的建议",
        }, aliases=["投递建议", "提高投递转化率", "求职报告建议"])

    hr_tips = [str(t).strip() for t in
               ((page_config.get("rcHrDashboard") or {}).get("tips") or [])
               if str(t or "").strip()]
    if hr_tips:
        add_node("guide", "HR 招聘建议", props={
            "items": hr_tips, "source": "HR 工作台给出的建议",
        }, aliases=["招聘建议", "hr建议", "企业端建议"])

    login_tips = [str(t).strip() for t in
                  ((page_config.get("rcLoginConfig") or {}).get("tips") or [])
                  if str(t or "").strip()]
    # 公告里只有「安全提醒」这一类属于平台规则（不会被时间冲淡），其余公告不进图
    safe_notices = [str(n).strip() for n in (page_config.get("rcHomeNotices") or [])
                    if "安全" in str(n) or "收费" in str(n)]
    if login_tips or safe_notices:
        add_node("guide", "平台使用与安全提示", props={
            "items": login_tips + safe_notices, "source": "登录与平台公告",
        }, aliases=["平台安全提示", "防骗提示", "安全提示", "求职防骗"])

    for key, sid in skill_ids.items():
        set_props(sid, questionCount=skill_question_hits.get(key))

    return {"nodes": nodes, "edges": edges}


# ==========================================================
# B. 大模型抽取：非结构化文本 → 图
# ==========================================================
_SYSTEM_PROMPT = """你是知识图谱抽取助手。请从给定的「招聘平台规则 / 求职与招聘建议」片段里，
抽取【技能类实体】以及技能之间的关系。

实体类型只能是 skill（技能 / 能力 / 知识点），type 字段固定填 "skill"：
职位、公司、城市、职能方向、面试题、行业、平台规则这些类型都由平台的结构化数据
自动生成，你【不要】抽，抽了也会被程序丢弃。

关系类型只能是以下之一（rel 字段填英文代码）：
RELATES_TO(相关) / PART_OF(组成部分) / INCLUDES(包含) /
SUPPORTS(支持) / PROVIDES(提供) / USES(使用)

严格要求（违反的条目会被程序丢弃）：
1. 实体名必须【逐字出现在原文里】，直接照抄，不要改写、不要翻译、不要缩写、不要自己补充；
2. 只抽「一门具体的技能 / 能力 / 知识点」（如 系统设计、数据库、结构化面试、简历优化）；
   页面名称、按钮名称、功能入口、公告标题、职位类型枚举（全职/实习）等一律不算技能；
3. 关系两端的实体必须都是你在同一个片段里抽出的实体，没有明确关系就不要猜，宁缺勿滥；
4. 只输出 JSON，不要输出任何解释、前言或 Markdown 代码块标记。

输出格式（index 是资料片段的序号，必须与输入一致）：
{"items":[{"index":0,"entities":[{"name":"技能名","type":"skill"}],
"relations":[{"start":"技能名","rel":"RELATES_TO","end":"技能名"}]}]}"""


def _strip_json_fence(text: str) -> str:
    """去掉模型可能自带的 ```json 代码块标记。"""
    t = str(text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    return t.strip()


def _parse_items(raw: str) -> List[Dict]:
    """解析模型输出，容错到「能救回多少算多少」。

    ⚠️ 大模型偶尔会把 JSON 包在解释文字里，或用 ``` 包裹，
       这里先直接解析，失败再截取第一个 { 到最后一个 } 之间的部分。
    """
    text = _strip_json_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])

    if isinstance(data, dict):
        items = data.get("items")
        if items is None:
            # 兼容模型直接返回单个片段结果的情况
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [i for i in items if isinstance(i, dict)]


def _validate_items(items: Sequence[Dict], chunks: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """校验并转换模型输出（反幻觉的核心：名字必须出现在原文里）。

    参数：
        items:  模型输出的片段结果（含 index / entities / relations）
        chunks: 对应的知识块（顺序与发给模型时一致）
    返回：
        {"nodes": [...], "edges": [...], "dropped": {...}}，dropped 记录丢弃原因计数
    """
    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str, str], Dict] = {}
    dropped = {"bad_index": 0, "bad_type": 0, "not_in_text": 0,
               "bad_rel": 0, "unknown_endpoint": 0}

    for item in items:
        try:
            idx = int(item.get("index"))
            chunk = chunks[idx]
        except (TypeError, ValueError, IndexError):
            dropped["bad_index"] += 1
            continue

        # 原文归一化后用于「实体名是否真的出现在原文里」的校验
        chunk_norm = normalize_name(chunk.get("text"))
        local: Dict[str, str] = {}       # 实体名 → 节点 id（仅本片段内，用于校验关系端点）

        for ent in item.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            etype = str(ent.get("type") or "").strip().lower()
            if not name:
                continue
            if etype not in LLM_ENTITY_TYPES:
                dropped["bad_type"] += 1
                continue
            # 反幻觉：实体名必须逐字出现在原文中（归一化后比较，容忍标点差异）
            if normalize_name(name) not in chunk_norm:
                dropped["not_in_text"] += 1
                continue

            nid = make_entity_id(etype, name)
            local[name] = nid
            if nid not in nodes:
                nodes[nid] = {"id": nid, "name": name, "type": etype,
                              "props": {"extracted": True}, "aliases": []}

        for rel in item.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            rtype = str(rel.get("rel") or "").strip().upper()
            start_name = str(rel.get("start") or "").strip()
            end_name = str(rel.get("end") or "").strip()
            if rtype not in LLM_REL_TYPES:
                dropped["bad_rel"] += 1
                continue
            sid, eid = local.get(start_name), local.get(end_name)
            if not sid or not eid or sid == eid:
                # 关系端点不是本片段抽出的实体 → 丢弃（防止模型串联不同片段、编造关系）
                dropped["unknown_endpoint"] += 1
                continue
            edges.setdefault((sid, rtype, eid), {
                "start": sid, "end": eid, "type": rtype, "props": {"extracted": True},
            })

    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "dropped": dropped}


async def _one_batch(client, model: str, chunks: Sequence[Dict], cfg) -> Dict[str, List[Dict]]:
    """抽取一批知识块（一次请求）。"""
    lines = []
    for i, c in enumerate(chunks):
        text = str(c.get("text") or "")[:cfg.GRAPH_EXTRACT_MAX_CHARS]
        lines.append(f"【片段 {i}】标题：{c.get('title') or ''}\n{text}")
    user_msg = "请抽取下面每个资料片段中的实体与关系：\n\n" + "\n\n".join(lines)

    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": user_msg}],
            # temperature=0：抽取任务要的是稳定可复现，不是创造力
            temperature=0,
            response_format={"type": "json_object"},
        ),
        timeout=cfg.GRAPH_EXTRACT_TIMEOUT,
    )
    raw = resp.choices[0].message.content or ""
    items = _parse_items(raw)
    return _validate_items(items, chunks)


async def extract_llm_async(chunks: Sequence[Dict], on_progress=None) -> Dict:
    """用大模型从知识块里抽取实体关系（异步）。

    参数：
        chunks:      [{"text","title","type","source"}]
        on_progress: 可选回调 (done, total, nodes, edges)
    返回：
        {"nodes": [...], "edges": [...], "failed": n, "dropped": {...}}

    ⚠️ 单批失败只记日志并计数，不中断整体流程：
       灌图是「能灌多少灌多少」，一批超时不该让整张图白跑。
    """
    cfg = _config()
    provider = cfg.GRAPH_EXTRACT_PROVIDER
    if provider not in ("llm", "both"):
        return {"nodes": [], "edges": [], "failed": 0, "dropped": {}, "skipped": "未启用 LLM 抽取"}

    from app.core import llm

    try:
        client = llm.get_client()
    except Exception as e:                       # noqa: BLE001 - 没配 Key 就整体跳过
        logger.warning("[graph.extract] 大模型不可用，跳过 LLM 抽取：%s", e)
        return {"nodes": [], "edges": [], "failed": 0, "dropped": {}, "skipped": str(e)}

    batch_size = max(1, cfg.GRAPH_EXTRACT_BATCH)
    batches = [list(chunks[i:i + batch_size]) for i in range(0, len(chunks), batch_size)]

    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str, str], Dict] = {}
    dropped: Dict[str, int] = {}
    failed = 0
    done = 0
    sem = asyncio.Semaphore(_LLM_CONCURRENCY)

    async def run(batch):
        async with sem:
            try:
                return await _one_batch(client, cfg.GRAPH_EXTRACT_MODEL, batch, cfg)
            except Exception as e:               # noqa: BLE001
                logger.warning("[graph.extract] 抽取失败（跳过该批）：%s", e)
                return None

    tasks = [asyncio.create_task(run(b)) for b in batches]
    for coro in asyncio.as_completed(tasks):
        partial = await coro
        done += 1
        if partial is None:
            failed += 1
        else:
            for n in partial["nodes"]:
                nodes.setdefault(n["id"], n)
            for e in partial["edges"]:
                edges.setdefault((e["start"], e["type"], e["end"]), e)
            for k, v in (partial.get("dropped") or {}).items():
                dropped[k] = dropped.get(k, 0) + v
        if on_progress:
            on_progress(done, len(batches), len(nodes), len(edges))

    return {"nodes": list(nodes.values()), "edges": list(edges.values()),
            "failed": failed, "dropped": dropped}


def extract_llm(chunks: Sequence[Dict], on_progress=None) -> Dict:
    """extract_llm_async 的同步包装（供 CLI 直接调用）。"""
    return asyncio.run(extract_llm_async(chunks, on_progress=on_progress))


def _config():
    """集中读取配置（延迟导入，避免子脚本导入顺序导致的配置未加载）。"""
    from app import config

    return config


# ==========================================================
# 合并
# ==========================================================


def merge_extractions(*results: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """把多次抽取结果合并成一份（同名实体自动合并，重复关系去重）。

    参数：
        results: 若干 {"nodes": [...], "edges": [...]}，**调用方必须把规则抽取放最前**
    返回：
        {"nodes": [...], "edges": [...]}
    说明：
        规则抽取得到的属性更可信（来自数据库字段），
        模型抽取只补「图上还没有的实体与关系」，不覆盖规则抽取的属性。
    """
    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str, str], Dict] = {}
    # 归一化名 → 已占用的节点 id：用于拦截「同名不同型」的模型幻觉实体
    name_owner: Dict[str, str] = {}
    dropped_ids = set()

    for idx, res in enumerate(results):
        # ⚠️ 约定：规则抽取的结果必须放在第一个（graph_ingest 就是这么调的）。
        #    只有【模型】抽出来的实体才做「同名不同型」检查 ——
        #    结构化数据内部本来就有合法的同名（职位「测试工程师」与职能「测试工程师」、
        #    技能「用户运营」与职能「用户运营」，它们是两个不同的东西），
        #    对规则抽取也套这层检查会误删真实数据。
        is_llm_result = idx > 0
        for n in (res or {}).get("nodes") or []:
            nid = n.get("id")
            if not nid:
                continue
            # 节点 id 形如 `type:归一化名`，取冒号后那段就是「名字指纹」
            name_key = str(nid).split(":", 1)[-1]
            owner = name_owner.get(name_key)
            if is_llm_result and owner and owner != nid:
                # ⚠️ 同名不同型：结构化数据里已经有这个实体（如职能「前端开发」），
                #    模型又把它抽成了「技能」——这是把类型搞错了。这类错型实体必须丢：
                #    实体链接在同长度命中时按类型优先级抢起点，一个假的「前端开发（技能）」
                #    会让「前端开发需要什么经验」命中一个没有内容的技能节点，
                #    真正有用的职能事实反而取不回来。
                dropped_ids.add(nid)
                continue
            name_owner.setdefault(name_key, nid)

            if nid in nodes:
                # 合并属性：已有属性优先（规则抽取写在前），别名取并集
                merged = dict(n.get("props") or {})
                merged.update(nodes[nid].get("props") or {})
                nodes[nid]["props"] = merged
                aliases = list(dict.fromkeys((nodes[nid].get("aliases") or [])
                                             + (n.get("aliases") or [])))
                nodes[nid]["aliases"] = aliases
            else:
                nodes[nid] = dict(n)
        for e in (res or {}).get("edges") or []:
            key = (e.get("start"), e.get("type"), e.get("end"))
            if all(key) and key not in edges:
                edges[key] = dict(e)

    if dropped_ids:
        # 掉的是模型幻觉实体，打日志而不是静默丢弃，便于判断抽取质量
        logger.warning("[graph.extract] 丢弃同名不同型的模型实体 %d 个（类型搞错）", len(dropped_ids))
        edges = {k: v for k, v in edges.items()
                 if v.get("start") not in dropped_ids and v.get("end") not in dropped_ids}
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def link_chunks_to_entities(chunks: Sequence[Dict], nodes: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """为每个知识块找出它提到的实体，生成溯源边（Chunk → MENTIONS → Entity）。

    做法：把实体名（含别名）归一化后，在知识块正文里做子串匹配。
    这一步不调用大模型，纯字符串匹配，因此任何知识块的出处都能被追踪，
    也为「图谱事实来源可查」提供了依据。

    返回：
        {"chunks": [Chunk 节点...], "edges": [MENTIONS 边...]}
    """
    index: List[Tuple[str, str]] = []            # (归一化名, 实体 id)
    for n in nodes:
        for raw in [n.get("name")] + list(n.get("aliases") or []):
            norm = normalize_name(raw)
            if len(norm) >= 2:
                index.append((norm, n["id"]))
    # 长名字优先，避免短名（如「AI」）先把长名（如「AI 大模型应用实战营」）的机会占掉
    index.sort(key=lambda x: len(x[0]), reverse=True)

    chunk_nodes: List[Dict] = []
    edges: List[Dict] = []
    for c in chunks:
        text_norm = normalize_name(c.get("text"))
        if not text_norm:
            continue
        cid = make_chunk_id(c.get("text"))
        chunk_nodes.append({
            "id": cid, "title": c.get("title") or "",
            "source": c.get("source") or "", "type": c.get("type") or "",
            "text": c.get("text") or "",
        })
        for norm, nid in index:
            if norm in text_norm:
                edges.append({"start": cid, "end": nid, "type": PROVENANCE_REL, "props": {}})
    return {"chunks": chunk_nodes, "edges": edges}
