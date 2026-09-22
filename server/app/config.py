"""全局配置。

读取优先级：系统环境变量 > .env 文件 > 代码内默认值（仅非敏感项有默认值）。

⚠️ 安全约定（对参考资料实现的一处加固）：
    数据库密码与 JWT 密钥【不设置任何默认值】，缺失时在应用启动阶段直接报错。
    参考资料把它们写成可用的默认串，一旦随源码分发即等于泄露。
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

# ---------- 加载 .env ----------
# .env 位于 server/ 根目录（与 app/ 同级），显式指定绝对路径，
# 避免因启动时的工作目录不同而读不到配置
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _require(key: str) -> str:
    """读取必填配置项，缺失即抛错。

    参数：
        key: 环境变量名
    返回：
        配置值（已去除首尾空白）
    异常：
        RuntimeError —— 未配置或为空。
        在 uvicorn 启动阶段就会暴露，避免上线后才发现配置缺失。
    """
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少必填配置 {key}：请在 server/.env 中配置，"
            f"或通过系统环境变量注入"
        )
    return value


# ---------- 数据库 ----------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = _require("DB_PASSWORD")  # ⚠️ 必填，不设默认值
DB_NAME = os.getenv("DB_NAME", "sheji")

# ⚠️ 用 URL.create 构造连接串，而不是 f-string 手写：
#    库名/密码中若含空格或特殊字符（如 "she ji"、"p@ss word"），
#    手写连接串会因未转义而解析失败，URL.create 会正确编码
DB_URL = URL.create(
    "mysql+aiomysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    query={"charset": "utf8mb4"},
)

# ---------- JWT ----------
JWT_SECRET = _require("JWT_SECRET")  # ⚠️ 必填，不设默认值
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

# ---------- 短信验证码 ----------
SMS_CODE_LEN = int(os.getenv("SMS_CODE_LEN", "4"))   # 位数（与客户端输入框对齐）
SMS_TTL = int(os.getenv("SMS_TTL", "300"))           # 有效期（秒）
SMS_INTERVAL = int(os.getenv("SMS_INTERVAL", "60"))  # 重发间隔（秒）
SMS_DEBUG = os.getenv("SMS_DEBUG", "true").lower() in ("1", "true", "yes")

# ---------- 安全加固 ----------
# 同一验证码允许的最大校验失败次数，超出即作废该验证码。
# 目的：4 位验证码仅 1 万种组合，若无失败次数限制，300 秒有效期内可被穷举。
SMS_MAX_VERIFY_ATTEMPTS = int(os.getenv("SMS_MAX_VERIFY_ATTEMPTS", "5"))

# ---------- 应用信息 ----------
APP_TITLE = "直聘通 API"
APP_VERSION = "1.0.0"

# ---------- 邮箱验证码（SMTP） ----------
# 说明：真实短信需云厂商资质审核，当前改用邮箱下发验证码。
# ⚠️ SMTP_USER / SMTP_PASSWORD 刻意不设默认值：
#    它们是敏感凭据；若为空且非调试模式，发送时会抛出明确错误，
#    便于快速定位「忘了填配置」而不是收到一个含糊的登录失败。
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "直聘通")

EMAIL_CODE_LEN = int(os.getenv("EMAIL_CODE_LEN", "4"))       # 验证码位数
EMAIL_TTL = int(os.getenv("EMAIL_TTL", "300"))               # 有效期（秒）
EMAIL_INTERVAL = int(os.getenv("EMAIL_INTERVAL", "60"))      # 重发间隔（秒）
EMAIL_MAX_VERIFY_ATTEMPTS = int(os.getenv("EMAIL_MAX_VERIFY_ATTEMPTS", "5"))
# true = 调试模式：验证码随接口响应返回、不发邮件；false = 真实发送
EMAIL_DEBUG = os.getenv("EMAIL_DEBUG", "false").lower() in ("1", "true", "yes")

# ---------- AI 助教（DeepSeek） ----------
# ⚠️ AI_API_KEY 刻意不设默认值：它是敏感凭据，
#    未配置时在发起对话前会抛出明确错误，便于定位「忘了填 Key」。
# 说明：AI_MODEL（deepseek-v4-flash）不支持图片输入
#      （官方会把 input_image 替换为占位文本）。
#      ⚠️ 2026-09 新增「图片附件」能力后这一事实没有改变：
#         默认仍不把图片发给模型，只在提示词里注明「用户上传了 N 张图片」；
#         真正把图片发出去需要额外配置 AI_VISION_MODEL（见下）。
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-v4-flash")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "180"))   # 单轮生成整体超时（秒）
AI_WS_IDLE = float(os.getenv("AI_WS_IDLE", "300"))   # WS 帧间空闲断连（秒）
AI_ROUNDS = int(os.getenv("AI_ROUNDS", "10"))        # 上下文滑动窗口轮数

# ---------- AI 助教：图片附件（2026-09 新增，全部有安全默认值） ----------
# ⚠️ 以下三项是新增配置，不改变任何既有配置项的语义与取值。
# 单张图片体积上限（MB）：超限在读取过程中即中断，不落盘、不占内存
AI_UPLOAD_MAX_MB = int(os.getenv("AI_UPLOAD_MAX_MB", "10"))
# 单条消息最多携带几张图：多出的直接忽略，防止提示词/存储被撑爆
AI_IMAGE_MAX_COUNT = int(os.getenv("AI_IMAGE_MAX_COUNT", "4"))
# 多模态（视觉）模型名：⚠️ 留空 = 纯文本模式，这是默认值。
#   留空时：图片照常上传、落库、回显，但【不发给模型】，
#           只在发给模型的 content 末尾附一句「[用户上传了 N 张图片]」，
#           并在文案里讲明当前模型看不到图片——不假装模型能看图。
#   填了支持 OpenAI 兼容 image_url 协议的视觉模型时：
#           最后一条 user 消息改用内容块数组，把图片以 data URL 真正发给模型。
#   ⚠️ 本项与 AI_MODEL 相互独立：不填就完全维持改造前的行为。
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "").strip()


# ==========================================================
# RAG 知识库（Milvus 向量库 + 本地向量/精排模型）
# ----------------------------------------------------------
# 说明：以下配置全部【新增】，不改变任何原有配置项的语义。
#      RAG 属于可选增强：任一环节失败都会自动降级为原来的纯对话模式，
#      不会导致 AI 助教不可用（降级逻辑见 app/core/rag.py）。
# ==========================================================


def _flag(key: str, default: str) -> bool:
    """解析布尔型环境变量（新增配置专用的小工具）。

    参数：
        key:     环境变量名
        default: 缺省值（"true" / "false"）
    返回：
        True / False；取值 1/true/yes/on 视为真（大小写不敏感）
    """
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


# ---------- 总开关 ----------
# false = 完全关闭 RAG，对话回退到「不检索知识库」的原始行为（排查问题时用）
RAG_ENABLED = _flag("RAG_ENABLED", "true")
# true = 服务启动时预热模型（首次加载+下载可达数分钟，会拖慢启动，默认关）
RAG_WARMUP = _flag("RAG_WARMUP", "false")

# ---------- Milvus 连接 ----------
# ⚠️ Docker Desktop 用 WSL2 后端时，Windows 侧用 127.0.0.1 即可直连容器
#    （Docker Desktop 自动做端口映射）；若 Milvus 装在别处，改成其实际地址
MILVUS_URI = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
# Milvus 未开启鉴权时为空的（格式 user:password）；开启后需填写
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
# 集合名：⚠️ 换向量化模型导致维度变化时必须重建集合并重新灌库
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "course_kb_v1")
# BM25 分词器：chinese = jieba 中文分词（推荐，中文库必须）；
# 留空 = 用服务端默认分词器（中文检索质量会明显变差，仅服务端不支持时的兜底）
RAG_ANALYZER_TYPE = os.getenv("RAG_ANALYZER_TYPE", "chinese").strip()
# 单次请求超时（秒）：Milvus 打不开时不要长时间挂住对话
RAG_MILVUS_TIMEOUT = float(os.getenv("RAG_MILVUS_TIMEOUT", "10"))

# ---------- 模型 ----------
# 向量化方式：local = 本地模型（需下载，离线可用）；api = 调用云端 Embedding 接口（零下载）
RAG_EMBED_PROVIDER = os.getenv("RAG_EMBED_PROVIDER", "local").strip().lower()
# 向量化模型：gte-large-zh 输出 1024 维，中文语义效果好、体积适中
# ⚠️ 仅当 RAG_EMBED_PROVIDER=local 时生效；可填 HF 模型名或本地目录
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "thenlper/gte-large-zh")

# ---------- 云端 Embedding（RAG_EMBED_PROVIDER=api 时生效） ----------
# ⚠️ RAG_EMBED_API_KEY 刻意不设默认值：属于敏感凭据，缺失时在首次检索前报错，
#    文案直接指明去 .env 里填，避免只看到一句含糊的「检索失败」。
# 各服务商 OpenAI 兼容地址（均可用下方同一套配置）：
#   硅基流动   https://api.siliconflow.cn/v1         模型 BAAI/bge-m3（1024 维，有免费额度）
#   智谱 AI    https://open.bigmodel.cn/api/paas/v4 模型 embedding-3（2048 维，可传 dimensions 降维）
#   阿里百炼   https://dashscope.aliyuncs.com/compatible-mode/v1  模型 text-embedding-v3（1024 维）
RAG_EMBED_API_KEY = os.getenv("RAG_EMBED_API_KEY", "").strip()
RAG_EMBED_API_BASE = os.getenv("RAG_EMBED_API_BASE", "https://api.siliconflow.cn/v1").strip()
RAG_EMBED_API_MODEL = os.getenv("RAG_EMBED_API_MODEL", "BAAI/bge-m3").strip()
# 向量维度：填 0 = 首次自动探测（发一条探测文本，用返回长度作为维度，结果会缓存）
# ⚠️ 探测结果是「当前接口真实返回的维度」，比照抄文档更可靠（部分服务商会按
#    参数返回不同维度）。若服务商支持 dim 参数，也可在下方显式指定以省一次请求。
RAG_EMBED_API_DIM = int(os.getenv("RAG_EMBED_API_DIM", "0"))
# 单次请求的最大条数（各服务商上限不同：硅基流动 32、百炼 25、智谱 64）
RAG_EMBED_API_BATCH = int(os.getenv("RAG_EMBED_API_BATCH", "16"))
# 单次请求超时（秒）与失败重试次数
RAG_EMBED_API_TIMEOUT = float(os.getenv("RAG_EMBED_API_TIMEOUT", "60"))
RAG_EMBED_API_RETRIES = int(os.getenv("RAG_EMBED_API_RETRIES", "3"))

# 精排模型：可填 HF 上的模型名（自动下载），也可填本地目录（如 ./models/bge-reranker-base）
# ⚠️ 仅当 RAG_RERANK_ENABLED=true 时才会加载，关闭时完全不读这一项
RAG_RERANK_MODEL = os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base")
# 推理设备：留空 = 自动（有 GPU 用 GPU）；也可显式写 cpu / cuda / cuda:0
RAG_DEVICE = os.getenv("RAG_DEVICE", "").strip()
# 模型缓存目录：放在项目内便于备份迁移，不污染系统用户目录
# ⚠️ 用 `or` 而不是直接取 getenv：.env 里写成 `RAG_MODEL_CACHE=`（空值）时，
#    空串会覆盖掉这里的默认值，导致模型被下到系统用户缓存目录 C:\Users\xx\.cache
RAG_MODEL_CACHE = os.getenv("RAG_MODEL_CACHE", "").strip() or str(BASE_DIR / "models_cache")
# HuggingFace 镜像：国内建议填 https://hf-mirror.com（留空则不覆盖系统已有设置）
RAG_HF_MIRROR = os.getenv("RAG_HF_MIRROR", "").strip()
# 离线模式：模型已下好后可设为 true，避免每次启动联网检查更新
RAG_HF_OFFLINE = _flag("RAG_HF_OFFLINE", "false")
# 单个文件的下载超时（秒）：HF 默认仅 10 秒，国内走镜像很容易超时并写坏临时文件，
# 表现是 "Expecting value: line 1 column 1 (char 0)" 这类 JSON 解析错误。建议 60~120。
RAG_HF_DOWNLOAD_TIMEOUT = int(os.getenv("RAG_HF_DOWNLOAD_TIMEOUT", "60"))

# ---------- 检索参数 ----------
# 最终注入提示词的知识块条数
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# 融合后保留的候选数（精排在此范围内挑选）
RAG_SEARCH_LIMIT = int(os.getenv("RAG_SEARCH_LIMIT", "20"))
# 每一路（稠密 / BM25）各自先召回的条数，必须 ≥ RAG_SEARCH_LIMIT
RAG_CANDIDATE_LIMIT = int(os.getenv("RAG_CANDIDATE_LIMIT", "30"))

# ---------- 精排 ----------
# false = 只用「混合检索 + RRF 融合」的结果，不加载精排模型（省内存、响应更快）
RAG_RERANK_ENABLED = _flag("RAG_RERANK_ENABLED", "true")
# 相关性阈值：⚠️ 口径为 Sigmoid 归一化后的概率（0~1），
#    推荐 0.3~0.5；课程示例里的 0.8 是套在原始 logits 上比对，口径不对
RAG_RERANK_THRESHOLD = float(os.getenv("RAG_RERANK_THRESHOLD", "0.35"))
# 全部候选都低于阈值时是否保留 Top1（true=保留，避免完全没依据；false=宁缺勿滥）
RAG_KEEP_WHEN_EMPTY = _flag("RAG_KEEP_WHEN_EMPTY", "true")

# ---------- 上下文长度保护 ----------
# 单个知识块注入提示词时的字符上限
RAG_CONTEXT_MAX_CHARS = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "800"))
# 拼装后的 RAG 提示词总长度上限，超出即截断（防止撑爆上游模型上下文窗口）
RAG_PROMPT_MAX_CHARS = int(os.getenv("RAG_PROMPT_MAX_CHARS", "4000"))


# ==========================================================
# GraphRAG 知识图谱（Neo4j 图数据库）
# ----------------------------------------------------------
# 说明：与上面的 RAG 段一样，本段全部【新增】，不改变任何原有配置项的语义。
#      图谱检索同样属于「可选增强」：Neo4j 没启动、密码没填、图里还没灌数据，
#      都只记日志并降级为「只用向量检索」，不会让 AI 助教不可用
#      （降级逻辑见 app/core/graph_rag.py）。
#
# 与 RAG 的分工：
#     向量检索（Milvus）—— 擅长「哪段资料在讲这件事」，非结构化文本的语义召回；
#     图谱检索（Neo4j） —— 擅长「实体之间是什么关系」，结构化事实与多跳推理，
#                          例如「这门课属于哪个分类 / 谁讲的 / 这位老师还讲什么课」。
# ==========================================================

# ---------- 总开关 ----------
# false = 关闭图谱检索（灌图脚本不受影响，仍可正常写图、查图）
GRAPH_ENABLED = _flag("GRAPH_ENABLED", "true")

# ---------- Neo4j 连接 ----------
# Bolt 地址：本机 Neo4j（Windows 服务或 Docker 容器）都是 127.0.0.1:7687
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
# 默认管理员账号
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
# ⚠️ NEO4J_PASSWORD 刻意不设默认值：属于敏感凭据，
#    缺失时在首次检索 / 灌图前抛出明确错误，文案直接指明去 .env 里填。
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "").strip()
# 数据库名：社区版只有默认库 neo4j（新建库是企业版特性）
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
# 连接超时与单次查询超时（秒）：Neo4j 打不开时不要长时间挂住对话
GRAPH_NEO4J_TIMEOUT = float(os.getenv("GRAPH_NEO4J_TIMEOUT", "8"))
# 连接池上限（并发对话时复用连接，避免每次重连）
GRAPH_NEO4J_POOL_SIZE = int(os.getenv("GRAPH_NEO4J_POOL_SIZE", "20"))

# ---------- 图检索参数 ----------
# 一次检索最多注入几条图谱事实（图谱事实与向量知识块各自独立计数）
GRAPH_TOP_K = int(os.getenv("GRAPH_TOP_K", "6"))
# 问题里最多识别几个实体作为「起点」
GRAPH_SEED_LIMIT = int(os.getenv("GRAPH_SEED_LIMIT", "5"))
# 起点向外扩展的跳数：1 = 只看直接邻居；
# 2 = 允许多跳推理（如「课程 → 讲师 → 这位老师的其他课」）
GRAPH_MAX_HOPS = int(os.getenv("GRAPH_MAX_HOPS", "2"))
# 扩展时最多取多少条边，防止热门实体（如「AI」）把候选撑爆
GRAPH_EXPAND_LIMIT = int(os.getenv("GRAPH_EXPAND_LIMIT", "40"))
# 单条事实渲染后的字符上限
GRAPH_FACT_MAX_CHARS = int(os.getenv("GRAPH_FACT_MAX_CHARS", "300"))
# 实体名缓存时间（秒）：实体链接需要把全图实体名读进内存，
# 缓存避免每次提问都查库；灌完图想立刻生效可重启服务或等缓存过期
GRAPH_ENTITY_CACHE_TTL = int(os.getenv("GRAPH_ENTITY_CACHE_TTL", "300"))
# 兜底召回的闸门：问题与候选实体名的「最长公共子串」至少要这么长，
# 否则宁可不召回 —— 图谱事实是当作可信事实注入提示词的，
# 混进无关实体比少召回几条危害更大
GRAPH_LINK_MIN_OVERLAP = int(os.getenv("GRAPH_LINK_MIN_OVERLAP", "5"))

# ---------- 实体关系抽取（灌图脚本 tools/graph_ingest.py 使用） ----------
# both = 结构化数据走规则 + 非结构化知识块走大模型（推荐）
# rule = 完全不调用大模型，零 token 成本
# llm  = 只做模型抽取
GRAPH_EXTRACT_PROVIDER = os.getenv("GRAPH_EXTRACT_PROVIDER", "both").strip().lower()
# 抽取用的模型：留空 = 复用 AI_MODEL（同一套 Key 与地址）
GRAPH_EXTRACT_MODEL = os.getenv("GRAPH_EXTRACT_MODEL", "").strip() or AI_MODEL
# 每次请求塞几个知识块（太大容易超时，太小则请求数变多）
GRAPH_EXTRACT_BATCH = int(os.getenv("GRAPH_EXTRACT_BATCH", "4"))
# 单个知识块喂给模型时的字符上限
GRAPH_EXTRACT_MAX_CHARS = int(os.getenv("GRAPH_EXTRACT_MAX_CHARS", "1200"))
# 单次抽取请求的超时（秒）与失败重试次数
GRAPH_EXTRACT_TIMEOUT = float(os.getenv("GRAPH_EXTRACT_TIMEOUT", "120"))
GRAPH_EXTRACT_RETRIES = int(os.getenv("GRAPH_EXTRACT_RETRIES", "2"))
