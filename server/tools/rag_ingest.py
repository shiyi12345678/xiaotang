"""知识块生成与灌库脚本（RAG 的「数据准备层」）—— 招聘业务知识库。

作用：把招聘端已有的结构化种子数据与页面配置，切成人能看懂、模型能用的知识块，
      向量化后写入 Milvus，供「直聘通 AI 求职助手」检索。

用法（在 server/ 目录下执行）：
    # 1) 先看会生成哪些知识块（不连数据库，安全，建议第一次先跑这个）
    .venv/Scripts/python.exe -m tools.rag_ingest --dry-run

    # 2) 正式灌库（按来源先删后写，可反复执行）
    .venv/Scripts/python.exe -m tools.rag_ingest

    # 3) ⚠️ 重建集合（清空整个知识库后重灌；换向量化模型或换业务时必须用）
    .venv/Scripts/python.exe -m tools.rag_ingest --rebuild

    # 4) 只灌某一个来源 / 追加自定义 JSON 知识块
    .venv/Scripts/python.exe -m tools.rag_ingest --source jobs
    .venv/Scripts/python.exe -m tools.rag_ingest --source content
    .venv/Scripts/python.exe -m tools.rag_ingest --extra ./seed/my_chunks.json

知识来源（原「课程 mock_data + 网易云客户端需求文档」两路已随业务改造下线：
学习端数据已经不再是这个 App 的业务事实，留在库里只会让 AI 答非所问）：
    A. seed/recruit_jobs.json     职位（每条职位一个块）、公司（每家公司一个块）、
                                  职能分类（总览 + 一级方向）、覆盖城市
    B. seed/recruit_content.json  面试题（每题一个块，含参考答案）、
                                  平台规则与求职/招聘建议（pageConfig 里的 rc* 配置）
    C. --extra 指定的 JSON 文件   支持两种格式：
         [{"text": "...", "title": "...", "type": "..."}]     本项目格式
         [{"doc": "...", "metadata": {...}}]                  旧课程示例格式（兼容）

⚠️ 安全与边界说明：
    - 本脚本只做「写入」与「按来源删除」，不做全库删除；
      唯一会清空数据的路径是 --rebuild（显式传参才触发，且会打印醒目提示）。
    - 所有文件路径都做存在性判断与目录越界校验，不接受项目目录之外的路径。
    - 只灌「业务事实」，不灌个人数据：求职报告的漏斗/评分、我的投递统计、
      演示账号等属于某个用户的私有数据，放进共享知识库既无意义也不合适。
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ----------------------------------------------------------
# 控制台编码兜底（Windows 必读）
# ----------------------------------------------------------
# ⚠️ 与 tools/graph_ingest.py 同因：本脚本的 --rebuild 提示与「灌库完成」提示用了
#    ⚠️/✅ 这类字符，Windows 控制台默认是 GBK，print 时会抛 UnicodeEncodeError。
#    若提示在写入之后，数据其实已经落库，但命令以非 0 退出，容易被误判成「灌库失败」。
#    这里把 stdout/stderr 切到 UTF-8 并允许替换无法编码的字符。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001  老版本 Python 或非文本流时静默跳过
        pass

# ----------------------------------------------------------
# 路径常量：确保脚本在任意工作目录下执行都能找到文件
# ----------------------------------------------------------
# __file__ = server/tools/rag_ingest.py
SERVER_DIR = Path(__file__).resolve().parent.parent          # server/
PROJECT_ROOT = SERVER_DIR.parent                             # ai she ji/
DEFAULT_JOBS = SERVER_DIR / "seed" / "recruit_jobs.json"      # 公司与职位
DEFAULT_CONTENT = SERVER_DIR / "seed" / "recruit_content.json"  # 面试题与页面配置
DEFAULT_CHUNKS_OUT = SERVER_DIR / "seed" / "knowledge_chunks.json"

# 来源标识：既是 metadata.source（检索时用于展示来源），也是「同来源覆盖式重灌」的键。
# ⚠️ 直接取文件名而不是另起别名：seed 文件就是这套知识的唯一真相，
#    检索结果里显示「来源 recruit_jobs.json」比显示「job_source_v2」更容易排查。
JOBS_SOURCE = DEFAULT_JOBS.name
CONTENT_SOURCE = DEFAULT_CONTENT.name

# 知识块参数
# ⚠️ 为什么上限是 700 而不是更小：本项目 45 条职位块的实测长度集中在 450~620 字
#    （最长的职位块约 620 字），取 700 能让「一个职位正好一块」，不做无谓拆分。
#    已知取舍：精排模型 CrossEncoder 的 max_length=512（中文 1 字≈1 token），
#    开启精排（RAG_RERANK_ENABLED=true）后超长块会被截断到前 512 token。
#    当前精排是关闭的，稠密向量（text-embedding-v3，8192 token）与 BM25 都用全文，
#    因此保持 700；若以后开启精排，应把这里降到 500 并接受部分职位块被拆成两块。
CHUNK_MAX_CHARS = 700
# 续块前缀（超长块被切开后，给第 2..n 块补的身份线索）最多占这么多字，
# 用于在日志/校验时估算「切开后是否仍在上限附近」。
CONTINUE_PREFIX_MAX = 60

# 招聘语义标签：数据里存的是英文枚举，知识块里必须写中文，
# 否则用户问「有哪些急招岗位」时，块里只有 urgent 三个字母，BM25 命不中。
KIND_LABELS = {
    "normal": "社招全职",
    "urgent": "急招",
    "referral": "名企内推",
    "intern": "实习",
    "campus": "校园招聘",
}
JOB_TYPE_LABELS = {"fulltime": "全职", "intern": "实习", "parttime": "兼职"}
DIFFICULTY_LABELS = {1: "简单", 2: "中等", 3: "困难"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("rag_ingest")


# ==========================================================
# 通用工具
# ==========================================================


def safe_path(raw: str, must_exist: bool = True) -> Path:
    """校验并解析文件路径（安全要求：只允许项目目录内的文件）。

    参数：
        raw:        用户传入的路径字符串
        must_exist: True 时文件必须存在
    返回:
        Path 对象（绝对路径）

    异常:
        ValueError —— 路径越界（位于项目目录之外）
        FileNotFoundError —— 文件不存在
    """
    p = Path(raw)
    if not p.is_absolute():
        p = (SERVER_DIR / p).resolve()
    else:
        p = p.resolve()

    # 目录越界校验：防止误传 C:\Windows\... 之类的路径
    try:
        p.relative_to(PROJECT_ROOT.resolve())
    except ValueError as e:
        raise ValueError(f"路径越界，只允许访问项目目录内的文件：{p}") from e

    if must_exist and not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")
    return p


def make_chunk(text: str, title: str, ctype: str, source: str) -> Dict:
    """构造统一结构的知识块。

    参数：
        text:   知识块正文（会做空白清洗）
        title:  标题，用于提示词里展示「据《标题》」
        ctype:  类型标签（job / company / category / city / question / guide …）
        source: 来源标识，用于「同来源覆盖式重灌」
    """
    clean = " ".join(str(text or "").split())
    return {"text": clean, "title": title, "type": ctype, "source": source}


def _load_json(path: Path, what: str) -> Dict:
    """读取种子 JSON，并把「文件不存在 / 格式不是对象」转成可操作的错误信息。

    ⚠️ 种子数据是灌库的唯一输入，缺文件时直接失败比静默灌出半个知识库安全：
       半库状态下 AI 会一本正经地回答「资料未涵盖」，很难排查。
    """
    if not path.exists():
        raise FileNotFoundError(f"{what}不存在：{path}（种子数据缺失，请检查 seed/ 目录）")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{what}格式不对，顶层应为 JSON 对象：{path}")
    return data


def _split_long_text(text: str, limit: int = CHUNK_MAX_CHARS) -> List[str]:
    """把超长文本按段落边界切成多段，每段不超过 limit 字符。

    ⚠️ 按「行」边界切而不是按字符硬切，避免把一句话、一个数字切两半
       （例如「25-45K·15薪」被切成「25-4」和「5K·15薪」）。
    """
    if len(text) <= limit:
        return [text]

    parts: List[str] = []
    buf = ""
    for line in text.splitlines():
        # 单行本身就超长（如超长列表项）时，退化为按字符硬切
        if len(line) > limit:
            if buf:
                parts.append(buf)
                buf = ""
            for i in range(0, len(line), limit):
                parts.append(line[i:i + limit])
            continue

        if len(buf) + len(line) + 1 > limit:
            parts.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line

    if buf:
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _emit(chunks: List[Dict], text: str, title: str, ctype: str, source: str,
          continue_prefix: str = "") -> None:
    """把一条「逻辑知识块」写进列表；只有超长时才拆成主块 + 续块。

    参数：
        text:            正文（可以含换行，make_chunk 会清洗成单行）
        title:           标题；续块会自动加「（续1）」后缀，便于人工核对切块结果
        continue_prefix: 续块要补的上下文前缀（一般写「【职位】xxx（公司·城市）」）

    ⚠️ 为什么续块要补前缀：切开后第 2 块可能只剩「任职要求：1. 本科及以上…」，
       检索命中它时模型看不出这是哪个职位、哪家公司，引用就成了无源之水。
    ⚠️ 前缀会让续块实际长度略微超过 CHUNK_MAX_CHARS（最多 CONTINUE_PREFIX_MAX 字），
       这是刻意取舍：多几十字对 embedding/BM25 无影响，但块失去归属影响很大。
    """
    pieces = _split_long_text(text)
    for idx, piece in enumerate(pieces):
        if idx > 0 and continue_prefix:
            piece = f"{continue_prefix}\n{piece}"
        suffix = "" if idx == 0 else f"（续{idx}）"
        chunks.append(make_chunk(piece, f"{title}{suffix}", ctype, source))


def _to_int(value) -> int:
    """把种子里的数字/数字字符串统一成 int（缺失或非法一律当 0）。

    ⚠️ 种子里既有 25 这样的整数，也可能出现 "25"；直接用 int() 会在脏数据上
       抛异常，把整次灌库带崩，不值得。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fmt_salary(job: Dict) -> str:
    """把 salary_min / salary_max / salary_months 拼成招聘端文案「25-45K·15薪」。

    ⚠️ 为什么必须拼：数据库里是三个裸数字（25、45、15），
       若原样写进知识块，模型看到「25 45 15」既不知道单位也不知道是月薪还是年薪，
       回答「这个岗位薪资多少」时会含糊其辞。单位按 seed 约定为「千元/月」。
    ⚠️ 12 薪是默认值，写进块里只是噪声（每条都出现会稀释关键词权重），
       因此只在 13 薪及以上时才写；这恰好也是求职者真正关心的信息。
    """
    lo, hi, months = _to_int(job.get("salary_min")), _to_int(job.get("salary_max")), _to_int(job.get("salary_months"))
    if not lo and not hi:
        return "薪资面议"
    text = f"{lo}-{hi}K" if lo and hi and lo != hi else f"{lo or hi}K"
    if months and months != 12:
        text += f"·{months}薪"
    return text


def _fmt_list(items, sep: str = "、", empty: str = "暂无") -> str:
    """把字符串列表拼成可读文本，顺便丢掉空项（种子里的 tags 可能含空串）。"""
    values = [str(x).strip() for x in (items or []) if str(x or "").strip()]
    return sep.join(values) if values else empty


def _fmt_multiline(text: str) -> str:
    """把多行职责/要求压成一句可读文本：保留「1. 2. 3.」编号，去掉换行。

    保留编号但去掉换行，是为了让「任职要求」里的每一条都能单独被 BM25 命中
    （换行在 make_chunk 里本来也会被压成空格，这里提前处理便于拼装）。
    """
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    return " ".join(lines)


# ==========================================================
# 来源 A：seed/recruit_jobs.json —— 职位 / 公司 / 职能分类 / 城市
# ==========================================================


def _job_context(job: Dict, company: Dict) -> str:
    """续块用的身份前缀，如「【职位】后端开发工程师（星野智能·北京）」。"""
    short = str(company.get("short_name") or company.get("name") or "未知公司")
    city = str(job.get("city_name") or "").strip()
    tail = f"（{short}·{city}）" if city else f"（{short}）"
    return f"【职位】{job.get('title')}{tail}"


def build_job_chunks(data: Dict) -> List[Dict]:
    """职位知识块：每条职位一个块（只有超长时才拆出续块）。

    只写求职者真正会问的字段，且都换成招聘端的中文表述：
        职位名 / 招聘公司（简称+行业+规模+融资阶段）/ 城市与区域 / 薪资 /
        经验与学历 / 职位类型（急招·内推·实习·校招）/ 职能方向 / 标签 /
        岗位职责 / 任职要求 / 招聘流程 / 招聘负责人与热度。
    ⚠️ 公司只写简称：写「星野智能科技有限公司」会让每条职位块都背上 8 个字，
       而且用户问的从来是简称。
    ⚠️ 招聘热度（浏览/投递人数）保留：这是「这个岗位竞争激烈吗」的唯一依据。
    """
    chunks: List[Dict] = []
    companies = {str(c.get("id")): c for c in (data.get("companies") or [])}
    cats = {str(c.get("id")): c for c in (data.get("jobCategories") or [])}

    for job in data.get("jobs") or []:
        company = companies.get(str(job.get("company_id"))) or {}
        cat = cats.get(str(job.get("category_id"))) or {}
        parent = cats.get(str(cat.get("parent_id"))) or {}

        # ---- 头部事实行：一行放齐「问得最多」的几个字段 ----
        city = str(job.get("city_name") or "").strip()
        district = str(job.get("district") or "").strip()
        location = f"{city}·{district}" if city and district else (city or district or "城市未标注")

        kind_label = KIND_LABELS.get(str(job.get("kind")), str(job.get("kind") or ""))
        type_label = JOB_TYPE_LABELS.get(str(job.get("job_type")), str(job.get("job_type") or ""))
        # kind 与 job_type 有重叠（normal+fulltime = 社招全职+全职、intern+intern = 实习+实习），
        # 只在前者「装不下」后者时才并列写出来，避免「社招全职 / 全职」这种啰嗦写法
        type_text = kind_label if (not type_label or type_label in kind_label) else f"{kind_label} / {type_label}"

        cat_path = " · ".join(x for x in [str(parent.get("name") or ""), str(cat.get("name") or "")] if x)
        exp_text = str(job.get("experience") or "经验不限").strip()
        edu_text = str(job.get("education") or "学历不限").strip()

        lines = [
            f"【职位】{job.get('title')}（{type_text}）",
            f"招聘公司：{company.get('short_name') or company.get('name') or '未知公司'}",
            f"工作地点：{location}｜薪资：{_fmt_salary(job)}",
            f"经验与学历：{exp_text}经验、{edu_text}",
            f"职能方向：{cat_path or '未分类'}",
            f"职位标签：{_fmt_list(job.get('tags'), empty='无')}",
            f"岗位职责：{_fmt_multiline(job.get('description'))}",
            f"任职要求：{_fmt_multiline(job.get('requirements'))}",
        ]

        process = (job.get("extra") or {}).get("process") or []
        if process:
            lines.append(f"招聘流程：{' → '.join(str(p) for p in process)}")

        hr_name = str(job.get("hr_name") or "").strip()
        if hr_name:
            hr_title = str(job.get("hr_title") or "").strip()
            active = str(job.get("hr_active") or "").strip()
            detail = "·".join(x for x in [hr_title, active] if x)
            lines.append(f"招聘负责人：{hr_name}{f'（{detail}）' if detail else ''}")

        views, applicants = _to_int(job.get("view_count")), _to_int(job.get("applicant_count"))
        if views or applicants:
            lines.append(f"岗位热度：被浏览 {views} 次，已有 {applicants} 人投递")

        title = f"{job.get('title')}（{company.get('short_name') or company.get('name') or '未知公司'}·{city or '城市未知'}）"
        _emit(chunks, "\n".join(lines), title, "job", JOBS_SOURCE,
              continue_prefix=_job_context(job, company))

    return chunks


def build_company_chunks(data: Dict) -> List[Dict]:
    """公司知识块：每家公司一个块。

    ⚠️ 必须带上「在招职位名列表」：用户问「星野智能在招什么岗位」时，
       只给公司简介是答不出来的；职位数 + 职位名是最实用的一句。
       职位名列表按 jobs 里真实存在的职位反查（不直接信任 company.job_count，
       两者不一致时以实际职位为准，避免块里写着 7 个却只列出 5 个）。
    """
    chunks: List[Dict] = []
    jobs = data.get("jobs") or []

    # 公司 → 在招职位名（保持 seed 顺序，便于人工比对）
    titles_by_company: Dict[str, List[str]] = {}
    for job in jobs:
        titles_by_company.setdefault(str(job.get("company_id")), []).append(str(job.get("title") or ""))

    for company in data.get("companies") or []:
        short = str(company.get("short_name") or company.get("name") or "").strip()
        titles = [t for t in titles_by_company.get(str(company.get("id")), []) if t]
        industry = str(company.get("industry") or "").strip()
        scale = str(company.get("scale") or "").strip()
        stage = str(company.get("stage") or "").strip()
        profile = "，".join(x for x in [industry, scale, stage] if x) or "未标注"

        lines = [
            f"【公司】{company.get('name')}" + (f"（简称：{short}）" if short and short != company.get("name") else ""),
            f"行业与规模：{profile}",
            f"所在城市：{company.get('city') or '未标注'}；办公地址：{company.get('address') or '未公开'}",
        ]
        if titles:
            lines.append(f"在招职位（{len(titles)} 个）：{_fmt_list(titles)}")
        else:
            lines.append("在招职位：当前没有在招职位")
        lines.append(f"福利待遇：{_fmt_list(company.get('benefits'), empty='未标注')}")
        if company.get("website"):
            lines.append(f"官网：{company.get('website')}")
        lines.append(f"公司简介：{_fmt_multiline(company.get('intro'))}")

        title = f"{short or company.get('name')}（公司介绍与在招职位）"
        _emit(chunks, "\n".join(lines), title, "company", JOBS_SOURCE,
              continue_prefix=f"【公司】{company.get('name')}")

    return chunks


def build_category_chunks(data: Dict) -> List[Dict]:
    """职能分类知识块：1 条总览 + 每个一级方向 1 条。

    ⚠️ 为什么不给 45 个二级职能各做一块：二级职能名本身只有 4 个字
       （「后端开发」「UI 设计师」），单独成块后任何问题都能蹭上它，
       在混合检索里靠短文本优势霸榜、把真正贴题的知识块挤出 Top-K
       （milvus_store 里记录过同类踩坑）。挂在一级方向下信息密度更高。
    ⚠️ 在招职位只举 5 个例子：一级方向（如「技术研发」）下面可能有十几个职位，
       全列出来会撑爆单块上限，反而把「这个方向有哪些职能」这个核心信息挤掉。
    """
    chunks: List[Dict] = []
    cats = data.get("jobCategories") or []
    jobs = data.get("jobs") or []

    top_cats = [c for c in cats if _to_int(c.get("level")) == 1]
    sub_cats: Dict[str, List[Dict]] = {}
    for c in cats:
        pid = str(c.get("parent_id") or "")
        if pid:
            sub_cats.setdefault(pid, []).append(c)

    # 一级方向 → 该方向下的职位（按 二级职能 的 parent 归属）
    jobs_by_parent: Dict[str, List[str]] = {}
    cat_parent = {str(c.get("id")): str(c.get("parent_id") or "") for c in cats}
    for job in jobs:
        parent_id = cat_parent.get(str(job.get("category_id")), "")
        jobs_by_parent.setdefault(parent_id, []).append(str(job.get("title") or ""))

    # ---------- 总览 ----------
    sub_total = sum(len(v) for v in sub_cats.values())      # 二级职能总数（35 个）
    overview = [f"【职能分类总览】直聘通的职位按 {len(top_cats)} 个一级领域、"
                f"{sub_total} 个二级职能方向划分，当前在招职位 {len(jobs)} 个。"]
    for top in top_cats:
        subs = [str(s.get("name") or "") for s in sub_cats.get(str(top.get("id")), [])]
        overview.append(f"· {top.get('name')}：{_fmt_list(subs, empty='（无下级职能）')}")
    _emit(chunks, "\n".join(overview), "职能分类总览（有哪些岗位方向）", "category", JOBS_SOURCE)

    # ---------- 一级方向明细 ----------
    for top in top_cats:
        top_id = str(top.get("id"))
        subs = [str(s.get("name") or "") for s in sub_cats.get(top_id, [])]
        titles = jobs_by_parent.get(top_id, [])
        lines = [
            f"【职能方向】{top.get('name')}（{top.get('description') or '暂无说明'}）",
            f"包含职能：{_fmt_list(subs, empty='（无下级职能）')}",
        ]
        if titles:
            sample = titles[:5]
            more = f" 等 {len(titles)} 个" if len(titles) > len(sample) else ""
            lines.append(f"在招职位：{_fmt_list(sample)}{more}")
        else:
            lines.append("在招职位：该方向当前没有在招职位")
        _emit(chunks, "\n".join(lines), f"{top.get('name')}方向有哪些职位",
              "category", JOBS_SOURCE, continue_prefix=f"【职能方向】{top.get('name')}")

    return chunks


def build_city_chunk(data: Dict) -> List[Dict]:
    """覆盖城市知识块（1 条）：回答「有哪些城市有岗位」。

    ⚠️ 只写城市名与省份，不写 initial / is_hot / sort_order 这些纯前端排序字段，
       它们对用户问题的区分度为零，写进去只会稀释关键词。
    """
    cities = data.get("cities") or []
    if not cities:
        return []

    names = [str(c.get("name") or "") for c in cities if str(c.get("name") or "").strip()]
    provinces = {str(c.get("name") or ""): str(c.get("province") or "") for c in cities}

    # 每个城市在招多少个职位：求职者问「成都有没有后端岗位」时会用到
    counts: Dict[str, int] = {}
    for job in data.get("jobs") or []:
        name = str(job.get("city_name") or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1

    detail = "；".join(
        f"{n}（{provinces.get(n) or '省份未标注'}，在招 {counts.get(n, 0)} 个职位）" for n in names
    )
    text = (f"【覆盖城市】直聘通当前开放的求职城市共 {len(names)} 个：{_fmt_list(names)}。"
            f"各城市在招职位数：{detail}。")
    chunks: List[Dict] = []
    # 走 _emit 而不是直接 append：城市变多时（如接入全国 300+ 城市）这块会超长，
    # 交给统一的切块逻辑处理，不用在这里单独兜底。
    _emit(chunks, text, "覆盖城市与各城市在招职位数", "city", JOBS_SOURCE,
          continue_prefix="【覆盖城市】")
    return chunks


# ==========================================================
# 来源 B：seed/recruit_content.json —— 面试题 / 平台规则与建议
# ==========================================================


def build_interview_chunks(content: Dict, cat_names: Optional[Dict[str, str]] = None) -> List[Dict]:
    """面试题知识块：每题一块，必须带参考答案。

    ⚠️ 为什么答案一定要进块：只写题干，AI 只能回答「面试会问什么」，
       答不了「这道题怎么答」——而后者才是刷题场景的全部价值。
    ⚠️ 难度/来源面经/被引用次数都保留：它们是「这题重不重要」的判断依据。
    """
    chunks: List[Dict] = []
    cat_names = cat_names or {}

    for q in content.get("interviewQuestions") or []:
        question = str(q.get("question") or "").strip()
        answer = str(q.get("answer") or "").strip()
        if not question:
            continue

        position = str(q.get("position") or "通用").strip()
        difficulty = DIFFICULTY_LABELS.get(_to_int(q.get("difficulty")), "未标注")
        cat_name = cat_names.get(str(q.get("category_id")), "")

        lines = [
            f"【面试题】{position}方向 · 难度：{difficulty}",
            f"题目：{question}",
        ]
        # 职能分类名与岗位名常常一致（后端开发 / 后端开发），一致时不再重复写；
        # 不一致的 11 道题（如「SRE」挂在「运维工程师」职能下）补一条职能标注，
        # 这样用户按职能名提问时也能命中。
        if cat_name and cat_name != position:
            lines.insert(1, f"所属职能：{cat_name}")
        if answer:
            lines.append(f"参考答案：{_fmt_multiline(answer)}")
        if q.get("tags"):
            lines.append(f"知识点：{_fmt_list(q.get('tags'))}")
        if q.get("source"):
            lines.append(f"来源面经：{q.get('source')}")
        frequency = _to_int(q.get("frequency"))
        if frequency:
            lines.append(f"热度：被 {frequency} 条面经提到")

        title = f"{position}面试题：{question[:30]}{'…' if len(question) > 30 else ''}"
        _emit(chunks, "\n".join(lines), title, "question", CONTENT_SOURCE,
              continue_prefix=f"【面试题】{position}方向：{question[:24]}")

    return chunks


def build_guide_chunks(content: Dict) -> List[Dict]:
    """平台规则与求职/招聘建议知识块（来自 pageConfig 里 rc* 开头的展示配置）。

    覆盖：内推专区与内推规则、内推 FAQ（一问一块）、求职建议、求职报告说明、
          HR 招聘建议、HR 工作台、AI 求职助手能力、求职者功能导航、
          职位筛选与列表、登录与安全提示。
    ⚠️ 刻意不录入的内容（都是「看起来能用、实际有害」的）：
       1) rcSeekerReport.funnel / radar 的分值与 rcMineStats：那是演示账号的个人
          投递数据，不是平台业务事实，录进去 AI 会把它当成通用结论讲给用户听；
       2) 各配置里的 link 字段（如 /pages/mine/deliver）：路由以
          docs/招聘改造-页面公约.md 的冻结表为准，配置里的旧路径已过期，
          录进知识库等于教模型报错路径 —— 因此功能导航只说模块名，不给路径；
       3) demoAccounts（演示手机号与验证码）：属于测试凭据，不应出现在检索结果里。
    """
    pc = content.get("pageConfig") or {}
    chunks: List[Dict] = []

    def emit(text: str, title: str, continue_prefix: str = "") -> None:
        _emit(chunks, text, title, "guide", CONTENT_SOURCE, continue_prefix=continue_prefix)

    # ---------- 名企内推专区 ----------
    referral = pc.get("rcReferralZone") or {}
    if referral:
        banners = referral.get("banners") or []
        # 标题已在块名里点明，正文不再重复「名企内推专区：名企内推专区」
        lines = [f"【名企内推专区】{referral.get('subtitle') or '在职员工帮你递简历，跳过初筛直通业务面试'}"]
        for b in banners:
            if isinstance(b, dict) and b.get("title"):
                lines.append(f"· {b.get('tag') or '内推'}：{b.get('title')}——{b.get('subtitle') or ''}")
        emit("\n".join(lines), "名企内推专区是什么")

        rules = referral.get("rules") or []
        if rules:
            lines = ["【内推规则】使用直聘通内推前必须知道的平台规则："]
            lines += [f"{i}. {r}" for i, r in enumerate(rules, start=1)]
            emit("\n".join(lines), "内推规则（谁能用、怎么用、有什么限制）")

        # FAQ 一问一块：问句本身就是最典型的检索 query，混在一起会互相稀释
        for faq in referral.get("faq") or []:
            if not isinstance(faq, dict) or not faq.get("q"):
                continue
            emit(f"【内推常见问题】{faq.get('q')}\n答：{_fmt_multiline(faq.get('a'))}",
                 f"内推答疑：{faq.get('q')}")

    # ---------- 求职报告与求职建议 ----------
    report = pc.get("rcSeekerReport") or {}
    if report:
        radar = [str(r.get("name") or "") for r in (report.get("radar") or []) if isinstance(r, dict)]
        if radar:
            emit(f"【求职报告】{report.get('title') or '我的求职报告'}：{report.get('subtitle') or ''}。"
                 f"报告从 {len(radar)} 个维度评估求职状态：{_fmt_list(radar)}。"
                 f"每个维度都会给出得分与改进方向，用于定位投递转化最弱的一环。",
                 "求职报告看哪些维度")
        tips = report.get("tips") or []
        if tips:
            lines = [f"【求职建议】{report.get('title') or '求职报告'}给出的 {len(tips)} 条实用建议："]
            lines += [f"{i}. {t}" for i, t in enumerate(tips, start=1)]
            emit("\n".join(lines), "求职建议（提高投递转化率）")

    # ---------- HR 端：招聘建议与工作台 ----------
    hr = pc.get("rcHrDashboard") or {}
    if hr:
        tips = hr.get("tips") or []
        if tips:
            lines = [f"【招聘建议（HR）】直聘通企业端给出的 {len(tips)} 条招聘建议："]
            lines += [f"{i}. {t}" for i, t in enumerate(tips, start=1)]
            emit("\n".join(lines), "HR 招聘建议")

        actions = [str(a.get("name") or "") for a in (hr.get("quickActions") or []) if isinstance(a, dict)]
        if actions:
            emit(f"【HR 工作台】企业端可用的核心操作：{_fmt_list(actions)}。"
                 f"另外还有职位管理、收到简历、面试安排、候选人沟通、公司主页、招聘数据、"
                 f"团队协作等模块，入口在「我的」页的招聘管理区。",
                 "HR 工作台能做什么")

    # ---------- AI 求职助手 ----------
    welcome = pc.get("rcAiWelcome") or {}
    caps = pc.get("rcAiCapabilities") or []
    if welcome or caps:
        lines = ["【AI 求职助手】"]
        if welcome.get("title"):
            lines.append(f"定位：{welcome.get('title')}——{welcome.get('subtitle') or ''}")
        if caps:
            desc = "；".join(
                f"{c.get('title')}（{c.get('desc')}）" for c in caps if isinstance(c, dict) and c.get("title")
            )
            lines.append(f"支持的能力：{desc}")
        # ⚠️ rcAiWelcome.suggestions 里的 prompt 正文刻意不录入：那是客户端按钮的
        #    「用户会怎么问」文案，不是平台业务事实，检索价值低；而且它把「简历/面试/
        #    岗位」这些高频词成段堆进同一条块里，会让这条块在很多无关问题上霸榜
        #    （实测：录入后问「面试会问什么」，Top1 会是这条 AI 能力介绍，
        #    真正的面试题被挤到第 3 名）。能力名与描述已足以回答「你能做什么」。
        emit("\n".join(lines), "AI 求职助手能做什么")

    # ---------- 求职者端功能导航 ----------
    groups = pc.get("rcMineGridGroups") or []
    if groups:
        parts = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            items = [str(it.get("name") or "") for it in (g.get("items") or []) if isinstance(it, dict)]
            if items:
                parts.append(f"{g.get('title') or '功能'}：{_fmt_list(items)}")
        if parts:
            emit("【求职者端功能导航】在「我的」页可以找到这些入口 —— " + "；".join(parts) +
                 "。想查看投递进度去「我的投递」，想约面试去「面试日程」，"
                 "想练题去「面试题库」，想改简历去「简历管理」。",
                 "求职者端功能在哪里（投递/收藏/面试/简历）")

    # ---------- 职位筛选与列表 ----------
    filters = pc.get("rcFilterOptions") or {}
    tabs = pc.get("rcJobListTabs") or []
    if filters or tabs:
        salary = [str(s.get("label") or "") for s in (filters.get("salary") or []) if isinstance(s, dict)]
        kinds = [str(t.get("name") or "") for t in tabs if isinstance(t, dict)]
        lines = ["【职位筛选与列表】职位列表支持按职能方向、城市、薪资、经验、学历与职位类型筛选。"]
        if salary:
            lines.append(f"薪资档位：{_fmt_list(salary)}")
        if filters.get("experience"):
            lines.append(f"经验要求：{_fmt_list(filters.get('experience'))}")
        if filters.get("education"):
            lines.append(f"学历要求：{_fmt_list(filters.get('education'))}")
        job_types = [str(t.get("label") or "") for t in (filters.get("jobType") or []) if isinstance(t, dict)]
        if job_types:
            lines.append(f"职位类型：{_fmt_list(job_types)}")
        if kinds:
            lines.append(f"列表标签页：{_fmt_list(kinds)}")
        emit("\n".join(lines), "职位筛选条件与列表标签页")

    # ---------- 登录与安全提示 ----------
    login = pc.get("rcLoginConfig") or {}
    notices = pc.get("rcHomeNotices") or []
    hot = pc.get("rcHotKeywords") or []
    if login or notices or hot:
        lines = ["【平台使用与安全提示】"]
        if login.get("subtitle"):
            lines.append(f"平台定位：{login.get('subtitle')}")
        for tip in login.get("tips") or []:
            lines.append(f"· {tip}")
        if notices:
            lines.append("近期公告：" + _fmt_list(notices, sep="；"))
        if hot:
            # 热门搜索词能反映「平台上有哪些岗位」，对「最近什么岗位热门」这类问题有用
            lines.append(f"热门搜索词：{_fmt_list(hot)}")
        emit("\n".join(lines), "平台使用与安全提示（登录/收费/防骗）")

    return chunks


# ==========================================================
# 来源 C：自定义 JSON 知识块
# ==========================================================


def load_extra_chunks(extra_path: Path) -> List[Dict]:
    """读取自定义 JSON 知识块文件，兼容两种格式。

    格式 1（本项目）：[{"text": "正文", "title": "标题", "type": "..."}]
    格式 2（旧课程示例）：[{"doc": "正文", "metadata": {"title": ..., "source": ...}}]

    ⚠️ 逐条校验：缺正文的条目跳过并计数，不让一条坏数据毁掉整次导入。
    """
    raw = json.loads(extra_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"知识块文件必须是 JSON 数组：{extra_path}")

    out: List[Dict] = []
    skipped = 0
    for item in raw:
        if not isinstance(item, dict):
            skipped += 1
            continue

        # 格式 2：旧课程示例的 doc + metadata
        if "doc" in item:
            meta = item.get("metadata") or {}
            text = item.get("doc")
            title = meta.get("title") or extra_path.stem
            ctype = meta.get("type") or "custom"
            source = meta.get("source") or extra_path.name
        else:
            text = item.get("text") or item.get("content")
            title = item.get("title") or extra_path.stem
            ctype = item.get("type") or "custom"
            source = item.get("source") or extra_path.name

        if not str(text or "").strip():
            skipped += 1
            continue

        out.append(make_chunk(str(text), str(title), str(ctype), str(source)))

    if skipped:
        logger.warning("自定义知识块跳过 %d 条（缺正文或格式不对）", skipped)
    return out


# ==========================================================
# 主流程
# ==========================================================


def collect_chunks(source: str, extra: str = "") -> List[Dict]:
    """按来源收集全部知识块。

    参数：
        source: all / jobs / content —— 选择内置来源
                （兼容旧名 mock→jobs、doc→content，便于 tools/graph_ingest.py
                  这类仍按老参数调用的脚本不至于直接报错）
        extra:  --extra 传入的额外 JSON 文件路径（可空）
    返回：
        知识块列表（已清洗文本、已去重）
    """
    # 旧来源名映射：业务从学习端改成招聘端后，来源名跟着换，
    # 但调用方（如 graph_ingest）可能还传 mock/doc，这里兜一程而不是硬失败。
    legacy = {"mock": "jobs", "doc": "content"}
    if source in legacy:
        logger.warning("来源名 %s 已废弃（对应新来源 %s），本次按新来源处理", source, legacy[source])
        source = legacy[source]

    if source not in ("all", "jobs", "content"):
        raise ValueError(f"未知知识来源：{source}（可选 all / jobs / content）")

    chunks: List[Dict] = []

    # ---------- 来源 A：职位 / 公司 / 职能分类 / 城市 ----------
    if source in ("all", "jobs"):
        jobs_data = _load_json(DEFAULT_JOBS, "招聘职位种子数据")
        job_chunks = build_job_chunks(jobs_data)
        company_chunks = build_company_chunks(jobs_data)
        category_chunks = build_category_chunks(jobs_data)
        city_chunks = build_city_chunk(jobs_data)
        logger.info("来源 %s：职位 %d 条、公司 %d 条、职能分类 %d 条、城市 %d 条",
                    JOBS_SOURCE, len(job_chunks), len(company_chunks),
                    len(category_chunks), len(city_chunks))
        chunks.extend(job_chunks + company_chunks + category_chunks + city_chunks)

    # ---------- 来源 B：面试题 / 平台规则与建议 ----------
    if source in ("all", "content"):
        content_data = _load_json(DEFAULT_CONTENT, "招聘内容种子数据")
        # 面试题的 category_id 与职位分类同源，复用职位种子把 id 翻成中文职能名
        cat_names: Dict[str, str] = {}
        try:
            cat_names = {str(c.get("id")): str(c.get("name") or "")
                         for c in (_load_json(DEFAULT_JOBS, "招聘职位种子数据").get("jobCategories") or [])}
        except FileNotFoundError as e:
            # 缺职位文件只是拿不到职能中文名，不该阻断面试题灌库
            logger.warning("无法解析职能名称，将省略职能标注：%s", e)
        question_chunks = build_interview_chunks(content_data, cat_names)
        guide_chunks = build_guide_chunks(content_data)
        logger.info("来源 %s：面试题 %d 条、平台规则与建议 %d 条",
                    CONTENT_SOURCE, len(question_chunks), len(guide_chunks))
        chunks.extend(question_chunks + guide_chunks)

    if extra:
        extra_path = safe_path(extra, must_exist=True)
        extra_chunks = load_extra_chunks(extra_path)
        logger.info("来源 %s：%d 条", extra_path.name, len(extra_chunks))
        chunks.extend(extra_chunks)

    # 全局去重：同一段文本可能在多个来源里重复出现
    seen, unique = set(), []
    for c in chunks:
        key = c["text"]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(c)

    if len(unique) != len(chunks):
        logger.info("去重：%d → %d 条", len(chunks), len(unique))
    return unique


def write_chunks_file(chunks: List[Dict], out_path: Path) -> None:
    """把知识块落盘成 JSON（便于人工检查切块效果、也便于复用）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("知识块已写入：%s", out_path)


def print_summary(chunks: List[Dict]) -> None:
    """打印知识块概览与抽样。

    ⚠️ 抽样按「类型各取一条」而不是固定打印前 3 条：
       前 3 条永远属于第一个生成的来源（职位），公司/面试题/平台规则切坏了
       在旧写法下根本看不出来。
    """
    by_type: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for c in chunks:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1

    print("\n===== 知识块概览 =====")
    print(f"共 {len(chunks)} 条")
    print("按来源：" + "、".join(f"{s} {n} 条" for s, n in sorted(by_source.items(), key=lambda x: -x[1])))
    print("按类型：" + "、".join(f"{t} {n} 条" for t, n in sorted(by_type.items(), key=lambda x: -x[1])))

    print("\n----- 抽样（每种类型 1 条）-----")
    seen = set()
    for c in chunks:
        if c["type"] in seen:
            continue
        seen.add(c["type"])
        print(f"[{c['type']}] {c['title']}（来源 {c['source']}，{len(c['text'])} 字）")
        print(f"    {c['text'][:160]}…")

    longest = max(chunks, key=lambda c: len(c["text"]))
    over = [c for c in chunks if len(c["text"]) > CHUNK_MAX_CHARS]
    abnormal = [c for c in chunks if len(c["text"]) > CHUNK_MAX_CHARS + CONTINUE_PREFIX_MAX]
    print(f"\n最长知识块 {len(longest['text'])} 字（上限 {CHUNK_MAX_CHARS}）：{longest['title']}")
    if over:
        # 超上限的只可能是「续块」（带前缀），列出来便于判断拆分是否合理
        print(f"超过上限的知识块 {len(over)} 条（均为拆分后的续块）："
              + "、".join(c["title"] for c in over[:5]) + ("…" if len(over) > 5 else ""))
    if abnormal:
        # 超过「上限 + 续块前缀容差」说明切块逻辑有问题（例如前缀本身过长），必须排查
        print(f"⚠️ 异常超长块 {len(abnormal)} 条（超过 {CHUNK_MAX_CHARS + CONTINUE_PREFIX_MAX} 字），"
              f"请检查切块逻辑：" + "、".join(c["title"] for c in abnormal[:5]))
    print("=====================\n")


def ingest(chunks: List[Dict], rebuild: bool) -> int:
    """向量化并写入 Milvus。

    参数：
        chunks:  知识块列表
        rebuild: True = 重建集合（⚠️ 清空全部旧数据）
    返回:
        实际写入条数
    """
    from app.core import embedding, milvus_store

    if not chunks:
        logger.warning("没有知识块需要灌库")
        return 0

    # 建集合：维度取真实模型输出，避免写死 1024 与模型不一致
    dim = embedding.embedding_dim()
    state = milvus_store.ensure_collection(dim=dim, recreate=rebuild)
    logger.info("集合状态：%s", state)

    # 同来源覆盖：先按 source 删除旧块，避免反复灌库产生重复数据
    # （--rebuild 已经清库，无需再删）
    if not rebuild:
        for src in sorted({c["source"] for c in chunks}):
            try:
                deleted = milvus_store.delete_by_source(src)
                if deleted:
                    logger.info("清理旧数据 source=%s，报告删除 %d 条", src, deleted)
            except Exception as e:
                # ⚠️ 删除失败不阻断：Milvus 删除是异步生效的，且重复数据不影响回答
                logger.warning("清理旧数据失败（不影响灌库，可能有重复）：source=%s，%s", src, e)

    # 向量化 + 写入：分批进行，边算边写，避免一次性占用大量内存
    batch = 32
    written = 0
    total = len(chunks)

    for start in range(0, total, batch):
        part = chunks[start:start + batch]
        vectors = embedding.embed_texts([c["text"] for c in part])
        rows = []
        for c, vec in zip(part, vectors):
            rows.append({
                "text": c["text"],
                "embedding": vec,
                # 元数据同时保留 title/type/source，供检索时过滤与展示来源
                "metadata": {
                    "title": c["title"],
                    "type": c["type"],
                    "source": c["source"],
                    "permission": "1",     # 沿用旧字段：1=公开可检索（检索侧当前不过滤，保留以兼容）
                },
            })
        written += milvus_store.insert_chunks(rows)

        done = min(start + batch, total)
        logger.info("进度 %d/%d（已写入 %d 条）", done, total, written)

    return written


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="生成招聘业务知识块并灌入 Milvus（RAG 数据准备）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", choices=["all", "jobs", "content"], default="all",
                        help="知识来源：all=全部（默认），jobs=职位/公司/职能/城市，content=面试题/平台规则与建议")
    parser.add_argument("--extra", default="",
                        help="额外 JSON 知识块文件（项目目录内路径）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成知识块文件，不连数据库（推荐先跑一次）")
    parser.add_argument("--rebuild", action="store_true",
                        help="⚠️ 先删除集合再重建（清空整个知识库，换模型/换业务时必须用）")
    parser.add_argument("--chunks-out", default=str(DEFAULT_CHUNKS_OUT),
                        help=f"知识块输出文件，默认 {DEFAULT_CHUNKS_OUT}")
    args = parser.parse_args()

    try:
        out_path = safe_path(args.chunks_out, must_exist=False)
    except ValueError as e:
        logger.error("输出路径非法：%s", e)
        return 2

    # ---- 1) 收集知识块 ----
    try:
        chunks = collect_chunks(args.source, args.extra)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        logger.error("收集知识块失败：%s", e)
        return 2

    if not chunks:
        logger.error("没有生成任何知识块，请检查数据源")
        return 2

    # 先把切块结果落盘：无论灌库成功与否，都能人工检查切得好不好
    write_chunks_file(chunks, out_path)
    print_summary(chunks)

    if args.dry_run:
        logger.info("--dry-run：仅生成知识块，未写入 Milvus")
        return 0

    # ---- 2) 灌库 ----
    if args.rebuild:
        # ⚠️ 破坏性提示：这是本脚本唯一会清空数据的分支。
        #    集合名从配置读（延迟导入只为读到 .env，不建立 Milvus 连接），
        #    打印出真实集合名，避免用户删错了不知道删的是哪个集合。
        from app.config import MILVUS_COLLECTION

        print(f"⚠️  已指定 --rebuild：集合「{MILVUS_COLLECTION}」若已存在将先被删除再重建，"
              f"该集合内已有知识库数据会全部丢失！")
        print("    （换向量化模型、或业务从课程改成招聘这类「知识库整体换血」时才用它；"
              "只想覆盖重灌请去掉 --rebuild）")

    try:
        written = ingest(chunks, rebuild=args.rebuild)
    except Exception as e:
        logger.error("灌库失败：%s", e)
        print("\n排查建议：")
        print("  1) Milvus 是否已启动：docker compose -f docker/milvus-compose.yml up -d")
        print("  2) 端口是否通：浏览器打开 http://127.0.0.1:9091/healthz 应返回 OK")
        print("  3) .env 里 MILVUS_URI 是否与容器映射端口一致")
        return 1

    logger.info("灌库完成，共写入 %d 条知识块", written)
    print(f"\n✅ 灌库完成：{written} 条。启动服务后 AI 求职助手即可检索这些招聘知识。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
