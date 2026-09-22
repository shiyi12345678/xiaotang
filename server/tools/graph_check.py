"""图谱检索自检（GraphRAG 的「体检脚本」）。

作用：不启动服务、不发对话，直接验证「问题 → 实体链接 → 多跳扩展 → 提示词」
      这条链路是否正常，一眼看出图谱检索到底命中了什么。

用法（在 server/ 目录下执行）：
    # 1) 用内置的几个样例问题体检
    .venv/Scripts/python.exe -m tools.graph_check

    # 2) 指定自己的问题（可写多个）
    .venv/Scripts/python.exe -m tools.graph_check -q "AI 大模型应用实战营多少钱" -q "谁讲的"

    # 3) 打印最终注入大模型的完整提示词（验收注入格式时用）
    .venv/Scripts/python.exe -m tools.graph_check -q "AI 大模型应用实战营" --prompt

    # 4) 只看图谱规模
    .venv/Scripts/python.exe -m tools.graph_check --stats

⚠️ 只读脚本：只做查询与渲染，不写任何数据。
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

# 内置样例：覆盖「属性问答 / 多跳推理 / 分类聚合 / 概念问答」四种典型问法
DEFAULT_QUESTIONS = [
    "AI 大模型应用实战：从提示词到智能体全流程 这门课多少钱？",
    "27 考研英语一全程班是谁讲的？",
    "AI·数字技能分类下有哪些课程？",
    "什么是 RAG？",
]


def check_one(question: str, show_prompt: bool = False) -> bool:
    """体检单个问题，返回是否命中图谱事实。"""
    from app.core import graph_rag

    print("=" * 72)
    print(f"问题：{question}")

    result = graph_rag.retrieve_graph(question)
    if not result.get("used"):
        print(f"  ✗ 未命中：{result.get('error') or '图谱无相关事实'}")
        return False

    print(f"  命中实体 {len(result['entities'])} 个：")
    for e in result["entities"]:
        print(f"    · {e['name']}（{graph_rag.type_zh(e['type'])}，"
              f"匹配「{e['matched']}」，可信度 {e['score']:.2f}）")

    stats = result.get("stats") or {}
    print(f"  扩展 {stats.get('edges', 0)} 条关系"
          f"{'（已截断）' if stats.get('truncated') else ''}，"
          f"产出事实 {len(result['facts'])} 条：")
    for f in result["facts"]:
        cite = f"（出处：{'、'.join(f['sources'])}）" if f.get("sources") else ""
        print(f"    [{f['hop']} 跳 · {f['score']:.2f}] {f['text']}{cite}")

    if show_prompt:
        from app.core import rag

        contexts = graph_rag.to_contexts(result["facts"])
        prompt = rag.build_system_prompt(contexts)
        print("\n  ----- 注入大模型的提示词（仅图谱部分）-----")
        for line in prompt.splitlines():
            print(f"  | {line}")
        print("  ----- 提示词结束 -----")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="图谱检索自检（只读）")
    parser.add_argument("-q", "--question", action="append", default=[],
                        help="要体检的问题，可重复传；不传则用内置样例")
    parser.add_argument("--prompt", action="store_true",
                        help="打印最终注入大模型的提示词")
    parser.add_argument("--stats", action="store_true", help="只打印图谱规模")
    args = parser.parse_args()

    from app.core import graph_store

    if args.stats:
        try:
            st = graph_store.stats()
        except Exception as e:                   # noqa: BLE001
            print(f"✗ 读取图谱失败：{e}")
            return 1
        print(f"实体 {st['entities']} 个、知识块 {st['chunks']} 个、关系 {st['relations']} 条")
        print("实体类型：", st["entityTypes"])
        print("关系类型：", st["relations_by_type"])
        return 0

    questions = args.question or DEFAULT_QUESTIONS
    hit = 0
    try:
        for q in questions:
            hit += 1 if check_one(q, show_prompt=args.prompt) else 0
    except Exception as e:                       # noqa: BLE001
        print(f"\n✗ 体检中断：{e}")
        print("\n排查建议：")
        print("  1) Neo4j 服务是否在跑：sc query neo4j")
        print("  2) .env 里 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 是否正确")
        print("  3) 图谱是否已灌数据：python -m tools.graph_ingest --stats")
        return 1
    finally:
        graph_store.close_driver()

    print("=" * 72)
    print(f"体检完成：{hit}/{len(questions)} 个问题命中了图谱事实")
    if hit < len(questions):
        print("提示：未命中的问题通常有两种原因 —— ")
        print("  · 问题里没有出现图里的实体名（实体链接是子串匹配，靠名字对齐）；")
        print("  · 该实体在图里只有属性没有关系（可以扩充抽取规则或灌更多资料）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
