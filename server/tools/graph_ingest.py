"""图谱构建与灌库脚本（GraphRAG 的「数据准备层」）。

作用：把招聘 App「直聘通」的内容抽成「实体 + 关系」，写入 Neo4j，供 AI 求职助手做图谱检索。
    来源 A（结构化）—— seed/recruit_jobs.json（职位 45 / 公司 10 / 城市 16 / 职能 45）
                        用规则直接翻译成图：零成本、100% 准确、可重复
    来源 B（结构化）—— seed/recruit_content.json（面试题 55 / 平台规则与建议）
                        面试题同样走规则（题干、答案、难度、技能标签都是明确字段），
                        只有「平台规则与求职建议」这类整段散文才交给 DeepSeek 抽，
                        并对每条结果做「实体名必须出现在原文里」的反幻觉校验
    另外：每个知识块都会生成一个 Chunk 节点，并连上它提到的实体（MENTIONS），
          这样图谱事实能标注「出处」，也把图和向量库（Milvus）对上了。

⚠️ 为什么必须重灌（而不是增量补）：改造前整张图是课程域（课程/讲师/题库/记忆卡），
   与已换血的招聘向量库口径不一致，问「AI 数字技能是什么」会把课程事实
   当成招聘事实注入提示词。因此本次用 --rebuild 把整张图换成招聘域。

用法（在 server/ 目录下执行）：
    # 1) 先看会抽出什么（不连数据库；加 --no-llm 则连模型也不调，最安全）
    .venv/Scripts/python.exe -m tools.graph_ingest --dry-run

    # 2) 正式灌图（全部 MERGE，可反复执行，不会产生重复数据）
    .venv/Scripts/python.exe -m tools.graph_ingest

    # 3) ⚠️ 重建图谱（清空全图后重灌；改了抽取规则、或想让图彻底干净时用）
    .venv/Scripts/python.exe -m tools.graph_ingest --rebuild

    # 4) 完全不调用大模型（零 token 成本，只靠规则构图）
    .venv/Scripts/python.exe -m tools.graph_ingest --no-llm

    # 5) 让大模型把所有知识块都抽一遍（默认只抽「平台规则与建议」，省额度）
    .venv/Scripts/python.exe -m tools.graph_ingest --llm-all

    # 6) 只看当前图谱规模，不灌数据（--check 是同一件事的别名）
    .venv/Scripts/python.exe -m tools.graph_ingest --stats

⚠️ 边界说明：
    - 唯一会清空数据的路径是 --rebuild（必须显式传参，且会打印醒目提示）；
    - 灌图失败不会影响向量库与对话功能：图谱只是检索的一路，坏了就自动降级。
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

# ----------------------------------------------------------
# 控制台编码兜底（Windows 必读）
# ----------------------------------------------------------
# ⚠️ 踩过的坑：本脚本的 --rebuild 提示里用了「⚠️」这类字符，而 Windows 控制台默认是 GBK，
#    Python 在 print 时直接抛 UnicodeEncodeError —— 而且它出现在**清空动作之前**，
#    结果是「命令报错退出、图却没被清」：用户以为重建过了，其实一步没动。
#    这里把 stdout/stderr 切到 UTF-8 并允许替换无法编码的字符，
#    让提示再也不会变成中断（Windows 的 cmd/PowerShell 均适用）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001  老版本 Python 或非文本流时静默跳过
        pass

# ----------------------------------------------------------
# 路径常量（与 tools/rag_ingest.py 保持一致，两个脚本共用同一份种子数据）
# ----------------------------------------------------------
# __file__ = server/tools/graph_ingest.py
SERVER_DIR = Path(__file__).resolve().parent.parent          # server/
DEFAULT_JOBS = SERVER_DIR / "seed" / "recruit_jobs.json"      # 职位 / 公司 / 城市 / 职能
DEFAULT_CONTENT = SERVER_DIR / "seed" / "recruit_content.json"  # 面试题 / 平台规则与建议
DEFAULT_PREVIEW_OUT = SERVER_DIR / "seed" / "graph_preview.json"

# 默认交给大模型抽取的知识块类型。
# ⚠️ 为什么只有 guide：招聘侧的知识块里，职位 / 公司 / 职能 / 城市 / 面试题
#    这几类都已经由 extract_structural 用规则 100% 构过图了（字段本身就是结构化事实），
#    再送模型抽一遍既费额度又不会更准；只有「平台规则与求职建议」是整段散文，
#    规则抽不出里面的内容。
#    ⚠️ 改造前这里的条件是 source != "mock_data.json"，换来源后该条件恒为真，
#    会把全部 136 条知识块都送去抽取（白烧额度），因此必须改成按【类型】过滤。
LLM_CHUNK_TYPES = ("guide",)
# 再按正文标记收窄一次：guide 类知识块里还有「内推专区横幅 / AI 能力介绍 /
# 求职者功能导航 / 职位筛选说明 / 平台公告」这些前端展示配置，
# 它们不是平台规则，抽出来只会得到「我的投递」这种伪实体。
# 这里只留与 extract_structural 建 guide 节点同源的那几类正文，
# 标记与 tools/rag_ingest.py 的 _emit 正文开头保持一致。
LLM_CHUNK_MARKERS = ("【内推规则】", "【内推常见问题】", "【求职建议】",
                     "【招聘建议（HR）】", "【平台使用与安全提示】")
# 默认路径的硬上限：平台规则块理论上会随 pageConfig 增长，
# 这里封一个上限，避免将来页面配置膨胀后不知不觉把额度烧掉。
LLM_MAX_CHUNKS = 20

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("graph_ingest")


# ==========================================================
# 数据准备
# ==========================================================


def _read_json(path: Path, what: str) -> Dict:
    """读取种子 JSON，并把「文件不存在 / 顶层不是对象」转成可操作的错误信息。"""
    if not path.exists():
        raise FileNotFoundError(f"{what}不存在：{path}（请检查 server/seed/ 目录）")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{what}格式不对，顶层应为 JSON 对象：{path}")
    return data


def load_seed_data() -> Dict:
    """读取招聘种子数据（与向量侧 rag_ingest 同源同口径）。

    返回：
        {"jobs": recruit_jobs.json 的内容, "content": recruit_content.json 的内容}

    异常：
        FileNotFoundError —— 种子文件不存在（提示去哪里找）
        json.JSONDecodeError —— 文件损坏

    ⚠️ 为什么两份都读：职位/公司/职能/城市来自 jobs 文件，面试题与平台规则来自
       content 文件；只读其中一份会灌出「半个知识图」（例如有职位没有面试题），
       而半张图排查起来比没有图更费劲。
    """
    return {
        "jobs": _read_json(DEFAULT_JOBS, "招聘职位种子数据"),
        "content": _read_json(DEFAULT_CONTENT, "招聘内容种子数据"),
    }


def pick_llm_chunks(chunks: List[Dict], llm_all: bool, limit: int) -> List[Dict]:
    """挑出要交给大模型抽取的知识块。

    默认只挑【平台规则与求职建议】：结构化数据已经用规则构过图了，
    再让模型抽一遍既费额度又不会更准。

    ⚠️ 额度控制一共四道闸（按顺序生效）：
        ① 类型闸：只留 chunk type=guide（职位/公司/职能/城市/面试题一律不送模型）；
        ② 正文闸：只留带规则/建议标记的那几块（功能导航、公告等展示配置不送）；
        ③ 数量闸：再套一层 LLM_MAX_CHUNKS 硬上限；
        ④ --llm-limit 可继续收紧，调试抽取效果时用。
        本文这套数据实测只剩 8 条（改造前会把 136 条全部送去），
        批次由 GRAPH_EXTRACT_BATCH（默认 4）决定，也就是 2 次请求。
        --llm-all 是运维显式要求「全抽」，只跳过 ①②③（仍受 ④ 约束）。
    """
    if llm_all:
        picked = list(chunks)
    else:
        picked = [c for c in chunks
                  if str(c.get("type") or "") in LLM_CHUNK_TYPES
                  and any(mark in str(c.get("text") or "") for mark in LLM_CHUNK_MARKERS)]
        picked = picked[:LLM_MAX_CHUNKS]
    if limit > 0:
        picked = picked[:limit]
    return picked


# ==========================================================
# 预览（--dry-run）
# ==========================================================


def write_preview(nodes: List[Dict], edges: List[Dict], chunks: List[Dict],
                  out_path: Path) -> None:
    """把抽取结果落盘成 JSON，便于人工检查（不连数据库时也留得下证据）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"nodes": nodes, "edges": edges, "chunks": chunks},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("抽取结果已写入：%s", out_path)


def print_summary(nodes: List[Dict], edges: List[Dict], chunks: List[Dict],
                  mention_edges: List[Dict]) -> None:
    """打印图谱概览：实体类型分布、关系类型分布、抽样渲染。"""
    from app.core import graph_rag

    by_type: Dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1

    by_rel: Dict[str, int] = {}
    for e in list(edges) + list(mention_edges):
        by_rel[e["type"]] = by_rel.get(e["type"], 0) + 1

    print("\n===== 图谱概览 =====")
    print(f"实体 {len(nodes)} 个：", "、".join(
        f"{graph_rag.type_zh(t)} {c}" for t, c in sorted(by_type.items(), key=lambda x: -x[1])))
    print(f"语义关系 {len(edges)} 条：", "、".join(
        f"{r} {c}" for r, c in sorted(by_rel.items(), key=lambda x: -x[1]) if r != "MENTIONS"))
    print(f"溯源边 {len(mention_edges)} 条（知识块 → 实体）")
    print(f"知识块节点 {len(chunks)} 个")

    # 抽样渲染：用与线上完全一致的渲染函数，所见即模型所见
    props_by_id = {n["id"]: {**n.get("props", {}), "id": n["id"],
                             "name": n["name"], "type": n["type"]} for n in nodes}
    # ⚠️ 抽样按「每种关系各取一条」「每种实体类型各取一个」：
    #    固定打印前 6 条只会看到最先入库的那一类（旧写法每次都只显示课程分类），
    #    职位/公司/面试题这些真正关键的关系反而从来没被人工看过。
    print("\n----- 关系抽样（每种关系一条，与注入提示词的写法一致）-----")
    seen_rel = set()
    for e in edges:
        if e["type"] in seen_rel:
            continue
        start, end = props_by_id.get(e["start"]), props_by_id.get(e["end"])
        if not start or not end:
            continue
        seen_rel.add(e["type"])
        print("  ·", graph_rag.describe_edge(
            {"start_props": start, "end_props": end, "rel": e["type"]}, with_attrs=False))
        if len(seen_rel) >= 9:
            break
    print("----- 实体属性抽样（每种类型一个）-----")
    seen_type = set()
    for n in nodes:
        if n["type"] in seen_type:
            continue
        seen_type.add(n["type"])
        print("  ·", graph_rag.describe_node(props_by_id[n["id"]]))
    print()


# ==========================================================
# 灌图
# ==========================================================


def ingest(nodes: List[Dict], edges: List[Dict], chunks: List[Dict],
           mention_edges: List[Dict], rebuild: bool) -> Dict:
    """写入 Neo4j。

    参数：
        nodes:        实体节点
        edges:        语义关系
        chunks:       知识块节点
        mention_edges: 溯源边（Chunk → MENTIONS → Entity）
        rebuild:      True = 先清空全图（⚠️ 破坏性）
    返回：
        graph_store.upsert 的统计结果
    """
    from app.core import graph_store

    if rebuild:
        removed = graph_store.reset_graph()
        print(f"⚠️  已清空原图谱（删除节点 {removed} 个）")
        graph_store.clear_entity_cache()

    result = graph_store.upsert(nodes, edges, chunks=chunks)
    # 溯源边单独写（它的一端是 Chunk，不是 Entity）
    if mention_edges:
        detail = graph_store.upsert([], mention_edges)
        result["edges"] += detail.get("edges", 0)

    # 灌完立刻让实体缓存失效，免得检索还用着旧实体表
    graph_store.clear_entity_cache()
    return result


def print_graph_stats() -> Dict:
    """打印当前图谱规模（--stats 与灌图收尾都用它）。"""
    from app.core import graph_store, graph_rag

    st = graph_store.stats()
    print("\n===== 图谱现状（Neo4j）=====")
    print(f"节点总数 {st['nodes']}（实体 {st['entities']} + 知识块 {st['chunks']}）")
    print(f"关系总数 {st['relations']}")
    print("实体类型：", "、".join(
        f"{graph_rag.type_zh(t)} {c}" for t, c in st["entityTypes"].items()) or "（空）")
    print("关系类型：", "、".join(
        f"{t} {c}" for t, c in st["relations_by_type"].items()) or "（空）")
    print()
    return st


# ==========================================================
# 主流程
# ==========================================================


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="抽取实体关系并灌入 Neo4j（GraphRAG 数据准备）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", choices=["all", "jobs", "content", "mock", "doc"], default="all",
                        help="知识块来源：all=全部（默认）；jobs=职位/公司/职能/城市；"
                             "content=面试题/平台规则（mock/doc 是从前课程端的旧名，仍兼容）")
    parser.add_argument("--extra", default="",
                        help="额外 JSON 知识块文件（项目目录内路径）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只抽取并落盘预览，不连 Neo4j（推荐先跑一次）")
    parser.add_argument("--rebuild", action="store_true",
                        help="⚠️ 先清空整张图再灌（破坏性操作）")
    parser.add_argument("--no-llm", action="store_true",
                        help="完全不调用大模型，只用规则从结构化数据构图")
    parser.add_argument("--llm-all", action="store_true",
                        help="让大模型抽取全部知识块（默认只抽平台规则与建议）")
    parser.add_argument("--llm-limit", type=int, default=0,
                        help="限制交给大模型的知识块条数（0=不限，调试时很有用）")
    parser.add_argument("--stats", action="store_true",
                        help="只打印当前图谱规模，不做任何抽取与写入")
    parser.add_argument("--check", action="store_true",
                        help="等价于 --stats：体检当前图谱（实体类型分布是否只剩招聘域）")
    parser.add_argument("--out", default=str(DEFAULT_PREVIEW_OUT),
                        help=f"预览输出文件，默认 {DEFAULT_PREVIEW_OUT}")
    args = parser.parse_args()

    from app.core import graph_extract, graph_store

    # ---- 0) 只看规模 ----
    if args.stats or args.check:
        try:
            print_graph_stats()
            return 0
        except Exception as e:                   # noqa: BLE001
            logger.error("读取图谱失败：%s", e)
            print("\n排查建议：")
            print("  1) Neo4j 服务是否在跑：sc query neo4j（或用 Neo4j Desktop 启动）")
            print("  2) .env 里 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 是否正确")
            return 1

    # ---- 1) 结构化数据 → 规则构图 ----
    print("\n[1/4] 规则抽取：招聘种子数据（职位/公司/城市/职能/技能/面试题/规则）")
    try:
        seed = load_seed_data()
    except Exception as e:                       # noqa: BLE001
        logger.error("读取种子数据失败：%s", e)
        return 2

    struct = graph_extract.extract_structural(seed["jobs"], seed["content"])
    print(f"      共 {len(struct['nodes'])} 个实体、{len(struct['edges'])} 条关系")

    # ---- 2) 知识块 → 大模型抽取 ----
    print("\n[2/4] 收集知识块")
    from tools.rag_ingest import collect_chunks

    try:
        chunks = collect_chunks(args.source, args.extra)
    except Exception as e:                       # noqa: BLE001
        logger.error("收集知识块失败：%s", e)
        return 2
    print(f"      共 {len(chunks)} 条知识块")

    llm_result: Dict = {"nodes": [], "edges": [], "failed": 0, "dropped": {}}
    if args.no_llm:
        print("\n[3/4] 大模型抽取：已用 --no-llm 跳过")
    else:
        picked = pick_llm_chunks(chunks, args.llm_all, args.llm_limit)
        print(f"\n[3/4] 大模型抽取：{len(picked)} 条知识块"
              f"（{'全部（--llm-all）' if args.llm_all else '仅平台规则与建议，其余已由规则构图'}）")
        if not picked and not args.llm_all:
            print("      ⚠️ 没有匹配到「平台规则与建议」类知识块：知识块格式或来源可能变了，"
                  "本次只写规则抽取的部分（确需全抽请用 --llm-all）")
        if picked:
            started = time.time()

            def on_progress(done, total, n_nodes, n_edges):
                print(f"\r      进度 {done}/{total} 批，已抽到实体 {n_nodes} 个、"
                      f"关系 {n_edges} 条", end="", flush=True)

            llm_result = graph_extract.extract_llm(picked, on_progress=on_progress)
            print(f"\r      完成：实体 {len(llm_result['nodes'])} 个、"
                  f"关系 {len(llm_result['edges'])} 条，"
                  f"失败批次 {llm_result['failed']}，耗时 {time.time() - started:.1f}s")
            dropped = {k: v for k, v in (llm_result.get("dropped") or {}).items() if v}
            if dropped:
                # 这些是被反幻觉校验拦下来的条目，打印出来便于判断抽取质量
                print(f"      被校验拦下（未写入）：{dropped}")
            if llm_result.get("skipped"):
                print(f"      ⚠️ 已跳过：{llm_result['skipped']}")

    # ---- 3) 合并 + 溯源边 ----
    print("\n[4/4] 合并结果并生成溯源边")
    merged = graph_extract.merge_extractions(struct, llm_result)
    nodes, edges = merged["nodes"], merged["edges"]
    link = graph_extract.link_chunks_to_entities(chunks, nodes)
    print(f"      合并后：实体 {len(nodes)} 个、语义关系 {len(edges)} 条、"
          f"知识块 {len(link['chunks'])} 个、溯源边 {len(link['edges'])} 条")

    print_summary(nodes, edges, link["chunks"], link["edges"])

    # ---- 4) 落盘 / 写库 ----
    out_path = Path(args.out)
    if args.dry_run:
        write_preview(nodes, edges, link["chunks"], out_path)
        logger.info("--dry-run：仅生成预览文件，未写入 Neo4j")
        print("提示：确认概览没问题后，去掉 --dry-run 再跑一次即会写入 Neo4j。")
        return 0

    if args.rebuild:
        print("⚠️  已指定 --rebuild：将清空 Neo4j 中的全部图谱节点（:Entity / :Chunk）后重灌！")
        print("    （仅在你改了抽取规则、或想让图谱彻底干净时使用；")
        print("      这是本项目唯一的清空路径，不带 --rebuild 时只做 MERGE 增量写入）")

    try:
        result = ingest(nodes, edges, link["chunks"], link["edges"], rebuild=args.rebuild)
    except Exception as e:                       # noqa: BLE001
        logger.error("灌图失败：%s", e)
        print("\n排查建议：")
        print("  1) Neo4j 服务是否在跑：sc query neo4j")
        print("  2) 账号密码是否正确：.env 里 NEO4J_USER / NEO4J_PASSWORD")
        print("  3) 驱动是否装了：pip install -r requirements-rag.txt")
        return 1
    finally:
        graph_store.close_driver()

    logger.info("灌图完成：%s", result)
    print(f"\n✅ 灌图完成：实体 {result['nodes']} 个、关系 {result['edges']} 条、"
          f"知识块 {result['chunks']} 个")
    print("   启动服务后，问一句和职位/公司/面试题有关的问题即可看到图谱事实被引用。")
    print("   想直接验证线上检索效果：GET /api/v1/ai/graph/search?q=你的问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
