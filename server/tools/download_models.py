"""模型下载脚本（绕开 HuggingFace 缓存机制，直连镜像下载到项目目录）。

为什么要单独写这个脚本：
    默认的 HF 下载流程是「blob + snapshots 软链接」结构。在 Windows 上若未开启
    开发者模式（无创建符号链接权限），或运行环境对文件操作做了拦截，
    会出现 snapshots 下的文件是 0 字节、加载时报
    `Expecting value: line 1 column 1 (char 0)` 的诡异错误。
    本脚本改用纯 HTTP 直连下载到普通目录，不依赖缓存、不建软链、可重复执行。

用法（在 server/ 目录下执行）：
    # 下载全部模型（向量化 + 精排）
    .venv/Scripts/python.exe -m tools.download_models

    # 只下向量化模型 / 只下精排模型
    .venv/Scripts/python.exe -m tools.download_models --model embed
    .venv/Scripts/python.exe -m tools.download_models --model rerank

    # 强制重新下载（覆盖已有文件）
    .venv/Scripts/python.exe -m tools.download_models --force

下载完成后，把 .env 改成指向本地目录（脚本会自动提示）：
    RAG_EMBED_MODEL=./models/gte-large-zh
    RAG_RERANK_MODEL=./models/bge-reranker-base
    RAG_HF_OFFLINE=true

⚠️ 说明：
    - 只下载模型推理必需的 12 个左右小文件 + 1 个权重文件，
      不会拉取 .gitattributes 等无关文件；
    - 每个文件下载后校验：JSON 必须能被解析、权重文件必须非空，
      校验不通过则视为失败并重试，避免把坏文件留在本地；
    - 全程只写 server/models/ 目录，不动系统缓存与用户目录。
"""
import argparse
import json
import logging
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# ----------------------------------------------------------
# 路径与常量
# ----------------------------------------------------------
SERVER_DIR = Path(__file__).resolve().parent.parent       # server/
PROJECT_ROOT = SERVER_DIR.parent                          # ai she ji/
MODELS_DIR = SERVER_DIR / "models"                        # 模型落盘根目录

# 镜像地址：与 .env 的 RAG_HF_MIRROR 保持一致，国内直连 hf-mirror 可用
DEFAULT_ENDPOINT = "https://hf-mirror.com"
# 备用源：主源握手失败时依次尝试（国内官方源通常不通，仅作保底）
FALLBACK_ENDPOINTS = ["https://hf-mirror.com", "https://huggingface.co"]

# 单个模型的下载规格
MODEL_SPECS: Dict[str, Dict] = {
    "embed": {
        "repo": "thenlper/gte-large-zh",
        "dir": "gte-large-zh",
        "desc": "向量化模型（1024 维，中文语义编码）",
        # 必需文件（若仓库里不存在会被自动跳过，不会报错）
        "files": [
            "config.json",
            "modules.json",                 # sentence-transformers 的模块拓扑，必需
            "sentence_bert_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
            "special_tokens_map.json",
            "1_Pooling/config.json",        # 池化层配置
            "2_Normalize/config.json",
            "README.md",                    # 可选，仅便于确认版本
        ],
        # 权重文件按优先级取第一个存在的（safetensors 更安全，bin 兼容性更广）
        "weights": ["model.safetensors", "pytorch_model.bin"],
    },
    "rerank": {
        "repo": "BAAI/bge-reranker-base",
        "dir": "bge-reranker-base",
        "desc": "精排模型（CrossEncoder 交叉编码）",
        "files": [
            "config.json",
            "sentence_bert_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
            "special_tokens_map.json",
            "README.md",
        ],
        "weights": ["model.safetensors", "pytorch_model.bin"],
    },
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("download_models")


# ==========================================================
# 基础工具
# ==========================================================


def http_json(url: str, timeout: int = 60, retries: int = 6) -> dict:
    """GET 一个 JSON 接口，带重试（镜像偶发抖动很常见）。

    参数：
        url:     完整地址
        timeout: 单次超时（秒）
        retries: 最大尝试次数
    返回：
        解析后的 dict
    异常：
        RuntimeError —— 全部重试失败

    ⚠️ 国内访问镜像时 TLS 握手偶发超时（WinError 10060 / 10054），
       表现为「刚才还好好的，突然连不上」。故默认重试 6 次、退避递增，
       而不是一失败就报错退出。
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "workbuddy-model-downloader"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            last_err = e
            logger.warning("接口请求失败（第 %d/%d 次）：%s", attempt, retries, e)
            time.sleep(min(3 * attempt, 15))
    raise RuntimeError(f"接口请求最终失败：{url} —— {last_err}")


def download_file(url: str, dst: Path, timeout: int = 300, retries: int = 5) -> int:
    """流式下载单个文件（先写 .part 临时文件，成功后再改名）。

    参数：
        url:     文件地址
        dst:     目标路径
        timeout: 单文件超时（秒）；大权重文件需要放宽
        retries: 最大尝试次数（网络中断自动重试）
    返回：
        下载的字节数
    异常：
        RuntimeError —— 全部重试失败

    ⚠️ 先写 .part 再 rename：避免「下载到一半失败」留下一个长度不对的文件，
       下次运行时会误以为已完成。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")

    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "workbuddy-model-downloader"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
                total = 0
                while True:
                    block = resp.read(1024 * 512)      # 512KB 一块，兼顾速度与内存
                    if not block:
                        break
                    f.write(block)
                    total += len(block)

            if total <= 0:
                raise RuntimeError("下载内容为空")

            # 覆盖已存在的旧文件：用 replace 保证原子性
            tmp.replace(dst)
            return total
        except Exception as e:
            last_err = e
            logger.warning("下载失败（第 %d/%d 次）%s：%s", attempt, retries, dst.name, e)
            time.sleep(min(2 * attempt, 10))

    # 清理残留的临时文件（失败退出时不留下垃圾）
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass
    raise RuntimeError(f"文件下载最终失败：{url} —— {last_err}")


def verify_file(path: Path) -> None:
    """校验下载结果：JSON 必须能解析，其余文件必须非空。

    参数：
        path: 待校验文件
    异常：
        RuntimeError —— 校验不通过（调用方会重试）
    """
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"文件为空：{path.name}")

    if path.suffix == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuntimeError(f"JSON 解析失败（文件可能被截断）：{path.name} —— {e}") from e


# ==========================================================
# 下载主流程
# ==========================================================


def fetch_remote_files(repo: str, endpoint: str) -> List[str]:
    """查询仓库的在线文件清单。

    返回：
        文件名列表（相对仓库根目录的路径）
    """
    url = f"{endpoint}/api/models/{repo}"
    info = http_json(url)
    files = [s.get("rfilename") for s in (info.get("siblings") or []) if s.get("rfilename")]
    if not files:
        raise RuntimeError(f"仓库文件清单为空：{repo}（检查模型名是否正确、镜像是否可用）")
    return files


def download_model(key: str, endpoint: str, force: bool = False) -> Dict:
    """下载一个模型的全套文件。

    参数：
        key:      MODEL_SPECS 的键（embed / rerank）
        endpoint: 镜像地址
        force:    True = 即使文件已存在也重新下载
    返回：
        {"repo":..., "dir":..., "files": 成功数, "skipped": 跳过数, "bytes": 总字节}
    """
    spec = MODEL_SPECS[key]
    repo = spec["repo"]
    target = MODELS_DIR / spec["dir"]

    logger.info("=" * 70)
    logger.info("开始下载：%s（%s）", repo, spec["desc"])
    logger.info("目标目录：%s", target)

    remote = set(fetch_remote_files(repo, endpoint))
    logger.info("仓库共 %d 个文件，按需下载", len(remote))

    # 组装待下载清单：必需文件 + 优先级最高的权重文件
    plan: List[str] = [f for f in spec["files"] if f in remote]
    weight = next((w for w in spec["weights"] if w in remote), None)
    if weight is None:
        raise RuntimeError(f"仓库里找不到权重文件（尝试过 {spec['weights']}）：{repo}")
    plan.append(weight)

    logger.info("权重文件：%s", weight)
    logger.info("待下载：%d 个文件", len(plan))

    ok, skipped, total_bytes = 0, 0, 0
    for name in plan:
        dst = target / name
        url = f"{endpoint}/{repo}/resolve/main/{name}"

        # 断点续传式跳过：已存在且校验通过就不再下载
        if dst.exists() and not force:
            try:
                verify_file(dst)
                skipped += 1
                logger.info("已存在，跳过：%s", name)
                continue
            except RuntimeError:
                logger.warning("本地文件损坏，重新下载：%s", name)

        for attempt in (1, 2):
            try:
                size = download_file(url, dst)
                verify_file(dst)                       # 校验：坏文件立刻发现
                total_bytes += size
                ok += 1
                logger.info("完成 %s（%.2f MB）", name, size / 1024 / 1024)
                break
            except RuntimeError as e:
                if attempt == 2:
                    raise
                logger.warning("重试该文件：%s —— %s", name, e)

    logger.info("完成：成功 %d，跳过 %d，共 %.2f MB", ok, skipped, total_bytes / 1024 / 1024)
    return {"repo": repo, "dir": str(target), "files": ok, "skipped": skipped, "bytes": total_bytes}


def pick_endpoint(preferred: str) -> str:
    """挑一个可用的下载源：优先用传入的地址，不通则依次尝试备用源。

    参数：
        preferred: 用户指定的地址（默认 hf-mirror）
    返回：
        首个能正常返回模型清单的地址

    异常：
        RuntimeError —— 所有源都不可用
    """
    candidates = [preferred] + [e for e in FALLBACK_ENDPOINTS if e != preferred]
    last_err: Optional[Exception] = None

    for ep in candidates:
        try:
            # 用最小的探测请求判断连通性（列表接口，不下载大文件）
            http_json(f"{ep}/api/models/{MODEL_SPECS['embed']['repo']}", timeout=30, retries=2)
            logger.info("使用下载源：%s", ep)
            return ep
        except Exception as e:
            last_err = e
            logger.warning("下载源不可用：%s —— %s", ep, e)
    raise RuntimeError(f"所有下载源均不可用（{candidates}）：{last_err}")


def check_disk_space() -> None:
    """下载前粗略检查磁盘剩余空间（权重文件较大，避免下到一半爆盘）。"""
    try:
        usage = shutil.disk_usage(str(SERVER_DIR))
        free_gb = usage.free / 1024 / 1024 / 1024
        logger.info("磁盘剩余空间：%.1f GB", free_gb)
        if free_gb < 3:
            logger.warning("⚠️ 剩余空间不足 3GB，两个模型合计约需 1.5~2GB")
    except OSError as e:
        logger.warning("无法获取磁盘空间信息：%s", e)


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="直连镜像下载 RAG 所需模型到 server/models/（不依赖 HF 缓存机制）",
    )
    parser.add_argument("--model", choices=["all", "embed", "rerank"], default="all",
                        help="下载哪个模型：all=全部（默认），embed=仅向量化，rerank=仅精排")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                        help=f"下载源地址，默认 {DEFAULT_ENDPOINT}")
    parser.add_argument("--force", action="store_true",
                        help="强制重新下载（即使本地已有且校验通过）")
    args = parser.parse_args()

    check_disk_space()

    # 先挑一个可用下载源，避免中途反复失败
    try:
        endpoint = pick_endpoint(args.endpoint.rstrip("/"))
    except Exception as e:
        logger.error("无法连接任何下载源：%s", e)
        print("\n排查建议：")
        print("  1) 检查网络能否打开 https://hf-mirror.com")
        print("  2) 稍后重试（镜像偶发握手超时）")
        print("  3) 指定其他源：--endpoint <地址>")
        return 1

    keys = ["embed", "rerank"] if args.model == "all" else [args.model]
    results = []
    for key in keys:
        try:
            results.append(download_model(key, endpoint, force=args.force))
        except Exception as e:
            logger.error("下载失败：%s —— %s", MODEL_SPECS[key]["repo"], e)
            print("\n排查建议：")
            print("  1) 网络是否可访问镜像：浏览器打开 " + endpoint)
            print("  2) 换一个镜像源重试，例如 --endpoint https://hf-mirror.com")
            print("  3) 磁盘空间是否充足（两个模型约需 1.5~2GB）")
            return 1

    print("\n" + "=" * 70)
    print("✅ 模型下载完成，请把 server/.env 改成使用本地目录：")
    print("    RAG_EMBED_MODEL=./models/gte-large-zh")
    print("    RAG_RERANK_MODEL=./models/bge-reranker-base")
    print("    RAG_HF_OFFLINE=true          # 不再联网检查更新")
    print("=" * 70)
    for r in results:
        print(f"  {r['repo']} → {r['dir']}（本次下载 {r['files']} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
