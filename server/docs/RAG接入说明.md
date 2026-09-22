# RAG 知识库接入说明

面向本项目的「AI 求职助手 + 招聘知识库」接入说明。技术栈：**WSL2 + Docker Desktop + Milvus + 向量化 + DeepSeek**。

> 检索链路与配置项本身自接入以来没有变过，**变的是知识来源**：
> 改造前装的是课程/讲师/题库知识，招聘改造（2026-09-19）后换成职位 / 公司 / 面试题 / 平台规则，
> 集合名与灌库脚本都跟着换了（见第四节的来源表）。
> 文中标注「改造前实测」的数据是课程知识库时期的记录，保留下来用于说明分词器与短块霸榜的原理。

---

## 一、这套东西解决什么问题

没有 RAG 时，AI 是**纯大模型对话**：模型不知道项目里有哪些职位、薪资多少、面试题怎么答、
内推有什么限制，问到具体岗位就容易胡编。

接入 RAG（检索增强生成）后，对话链路变成：

```
用户提问
  → 问题向量化（本地模型 或 云端 Embedding API）
  → 混合检索：稠密向量（语义）+ BM25（关键词），RRF 融合
  →（可选）二次精排
  → 取 Top N 知识块拼成 system 提示词
  → 交给 DeepSeek 生成答案（答案有据可依）
```

**两个关键设计：**

1. **RAG 是可选增强项**：检索、向量化、精排任一环节失败，都只记日志并降级为原来的纯对话，不会让 AI 求职助手整个不可用。
2. **向量化方式可切换**（`.env` 一行配置）：

| 方式     | 配置值                        | 下载量   | 费用               | 适用场景        |
| ------ | -------------------------- | ----- | ---------------- | ----------- |
| 本地模型   | `RAG_EMBED_PROVIDER=local` | 约 1GB | 免费               | 断网可用、数据不出本机 |
| 云端 API | `RAG_EMBED_PROVIDER=api`   | **0** | 按量付费（通常极低，有免费额度） | 机器配置低、想快速跑通 |

> **当前项目采用 `api` 方式 + 关闭精排**，因此**不需要下载任何模型**，  
> 只需一个 Embedding 服务的 API Key（见第三节）。
> `.env` 里实际填的是**阿里百炼 `text-embedding-v3`**（1024 维，实测数据见第七节）。

---

## 二、文件清单（接入时新增 / 改动）

| 文件                           | 类型    | 说明                                                     |
| ---------------------------- | ----- | ------------------------------------------------------ |
| `docker/milvus-compose.yml`  | 新增    | Milvus standalone 编排（etcd + MinIO + Milvus，可选 Attu 界面） |
| `docker/volumes/`            | 运行时生成 | 向量库数据持久化目录（删容器不丢数据）                                    |
| `app/core/embedding.py`      | 新增    | 向量化（本地/云端双模式）+ 精排模型，懒加载、双检锁、重试                         |
| `app/core/milvus_store.py`   | 新增    | Milvus 封装：建表、索引、写入、混合检索、过滤表达式消毒                        |
| `app/core/rag.py`            | 新增    | 检索编排：降级策略、阈值过滤、去重、提示词拼装                                |
| `tools/rag_ingest.py`        | 新增    | 知识块生成 + 灌库 CLI（招聘改造后来源换成 `seed/recruit_*.json`）         |
| `tools/download_models.py`   | 新增    | 本地方案专用：直连镜像下载模型（绕开 HF 缓存软链问题）                          |
| `requirements-rag.txt`       | 新增    | RAG 专属依赖（**原 `requirements.txt` 一字未动**）                |
| `seed/knowledge_chunks.json` | 生成    | 切好的知识块，便于人工检查切块质量                                      |
| `models/`                    | 运行时生成 | 仅「本地模型」模式使用，当前 API 模式为空                                |
| `app/config.py`              | 追加    | 仅新增 RAG 配置段，**未修改任何原有配置项**                             |
| `app/routers/ai.py`          | 追加    | 对话前注入检索结果 + 4 个运维/调试接口（`rag/status`、`rag/warmup`、`graph/status`、`graph/search`），**未改动原有帧契约与业务流程** |
| `.env`                       | 追加    | 仅新增 RAG 配置段，原有配置原样保留                                   |

---

## 三、启动步骤

### 1) 启动 Milvus（WSL2 + Docker Desktop）

```bash
cd server/docker
docker compose -f milvus-compose.yml up -d
```

验证：

```bash
docker compose -f milvus-compose.yml ps      # 容器应为 running / healthy
curl http://127.0.0.1:9091/healthz           # 返回 OK 即服务就绪
```



> ⚠️ 若本机已有同名容器（`milvus-standalone` / `milvus-etcd` / `milvus-minio`），  
> 直接 `docker start milvus-etcd milvus-minio && docker start milvus-standalone` 复用即可，  
> 不要重复创建。需要图形化管理界面时加 `--profile gui`，访问 <http://localhost:8001>。

### 2) 安装依赖

```bash
cd server
.venv/Scripts/pip.exe install -r requirements-rag.txt
```

**API 模式（当前选择）**：本文件实际只需装 `pymilvus`（云端向量化复用已有的 openai SDK）。

**本地方案**：额外需要 `sentence-transformers`（连带 PyTorch 约 200MB+），  
把 `requirements-rag.txt` 里那一行取消注释再装。

### 3) 填 API Key（仅 API 模式）

`.env` 中填 `RAG_EMBED_API_KEY`，并确认服务商地址与模型名。三家可选：

| 服务商   | 注册地址                                 | BASE / 模型                                                                 | 备注                 |
| ----- | ------------------------------------ | ------------------------------------------------------------------------- | ------------------ |
| 硅基流动  | <https://cloud.siliconflow.cn>       | `https://api.siliconflow.cn/v1` + `BAAI/bge-m3`                           | 1024 维，有免费额度（**代码里的兜底默认**） |
| 智谱 AI | <https://open.bigmodel.cn>           | `https://open.bigmodel.cn/api/paas/v4` + `embedding-3`                    | 2048 维             |
| 阿里百炼  | <https://bailian.console.aliyun.com> | `https://dashscope.aliyuncs.com/compatible-mode/v1` + `text-embedding-v3` | 1024 维（**`.env` 当前实际在用这家**） |

> 向量维度无需自己算：`RAG_EMBED_API_DIM=0` 时首次会自动探测接口真实返回的维度，  
> 比照抄文档更可靠（部分服务商会按参数返回不同维度）。
> 当前 `.env` 已把它显式写成 `1024`（与阿里百炼 `text-embedding-v3` 的实测维度一致）。

### 4) 灌库

```bash
cd server
.venv/Scripts/python.exe -m tools.rag_ingest --dry-run   # 先看切块效果，不写库
.venv/Scripts/python.exe -m tools.rag_ingest             # 正式灌库
```

灌库来源与规模（当前项目，实测）：

| 来源                     | 条数  | 内容                                                             |
| ---------------------- | --- | -------------------------------------------------------------- |
| `seed/recruit_jobs.json`  | 67  | 职位 45（每条职位一个块）/ 公司 10 / 职能分类 11 / 城市汇总 1                        |
| `seed/recruit_content.json` | 69  | 面试题 55（含参考答案、难度、知识点、来源面经）/ 平台规则与求职·招聘建议 14（内推规则、求职建议、HR 建议、筛选条件、平台使用与安全提示、功能导航…） |
| 合计                     | **136** | 最长单块 559 字（上限 700 字）                                           |

- 只灌其中一半：`--source jobs` 或 `--source content`（旧的来源名 `mock` / `doc` 已废弃，脚本会提示并按新来源处理）；
- 追加外部块：`--extra ./seed/my_chunks.json`；
- 按来源覆盖式重灌：脚本先 `delete_by_source` 再写入，所以反复灌库不会产生重复数据。

---

## 四、验证

### 1) 查知识库状态（需登录态）

```bash
curl -H "Authorization: Bearer <你的JWT>" http://127.0.0.1:8000/api/v1/ai/rag/status
```

| 现象                | 含义         | 处理                                                       |
| ----------------- | ---------- | -------------------------------------------------------- |
| `milvus.ok=false` | 连不上 Milvus | 检查容器是否 running、`MILVUS_URI` 是否为 `http://127.0.0.1:19530` |
| `milvus.count=0`  | 连上了但没数据    | 跑第 4 步灌库                                                 |
| `enabled=false`   | RAG 总开关关了  | `.env` 里 `RAG_ENABLED=true`                              |

（当前实测：`ok=true`、`collection=job_kb_v1`、`count=136`、`load_state=Loaded`。）

### 2) 预热（API 模式也建议做一次）

```bash
curl -X POST -H "Authorization: Bearer <你的JWT>" http://127.0.0.1:8000/api/v1/ai/rag/warmup
```

API 模式会立即返回向量维度（如 1024），**顺便验证 Key 是否有效**；  
本地方案则会加载模型（首次可能下载数百 MB）。

### 3) 提问验证

用 App 的 AI 求职助手问招聘知识库里的具体信息（下面 4 条都是实测命中 Top1 的问法）：

- 「星野智能科技是一家什么公司？」→ 命中《星野智能（公司介绍与在招职位）》，答出行业、规模、福利与在招职位
- 「内推有什么规则和限制？」→ 命中《内推规则（谁能用、怎么用、有什么限制）》：实名认证 + 简历完整度 70%、同一公司最多 2 个内推名额、平台不承诺面试或录用结果
- 「面试题库覆盖多少个职能方向、多少道题？」→ 命中《职能分类总览（有哪些岗位方向）》：21 个二级职能方向、55 道高频真题（职位侧是 10 个一级领域、35 个二级方向、当前在招 45 个职位）
- 「职位列表支持哪些筛选条件？」→ 命中《职位筛选条件与列表标签页》：职能 / 城市 / 薪资 / 经验 / 学历 / 职位类型，以及 6 个列表标签页

答非所问说明检索没命中，看服务端日志里的 `[ai.rag]` 行（打印注入条数、检索方式与最高分）。

---

## 五、配置项速查（`server/.env`）

### 向量化

| 变量                    | 默认                    | 说明                        |
| --------------------- | --------------------- | ------------------------- |
| `RAG_ENABLED`         | true                  | 总开关，false 即回到纯对话          |
| `RAG_EMBED_PROVIDER`  | local                 | `local` 本地模型 / `api` 云端接口（当前用 `api`） |
| `RAG_EMBED_API_KEY`   | 空                     | 云端模式的 Key（必填）             |
| `RAG_EMBED_API_BASE`  | 硅基流动                  | 服务商 OpenAI 兼容地址（当前是阿里百炼）  |
| `RAG_EMBED_API_MODEL` | BAAI/bge-m3           | 模型名（当前是 `text-embedding-v3`） |
| `RAG_EMBED_API_DIM`   | 0                     | 0 = 自动探测维度（当前显式 1024）     |
| `RAG_EMBED_API_BATCH` | 16                    | 单请求条数（注意服务商上限）            |
| `RAG_EMBED_MODEL`     | thenlper/gte-large-zh | 仅 local 模式使用              |

### 检索与精排

| 变量                      | 默认   | 说明                               |
| ----------------------- | ---- | -------------------------------- |
| `RAG_TOP_K`             | 4    | 最终注入的知识块条数                       |
| `RAG_SEARCH_LIMIT`      | 20   | 融合后保留的候选数                        |
| `RAG_CANDIDATE_LIMIT`   | 30   | 每路各自召回条数                         |
| `RAG_RERANK_ENABLED`    | true | 精排开关（**当前项目设为 false**，省约 1GB 模型） |
| `RAG_RERANK_THRESHOLD`  | 0.35 | 相关性阈值，**口径是 0~1 概率**             |
| `RAG_CONTEXT_MAX_CHARS` | 800  | 单块注入上限                           |

### Milvus

| 变量                   | 默认                       | 说明       |
| -------------------- | ------------------------ | -------- |
| `MILVUS_URI`         | <http://127.0.0.1:19530> | 向量库地址    |
| `MILVUS_COLLECTION`  | `job_kb_v1`              | 集合名（`.env` 实际值；`app/config.py` 里的兜底默认仍是改造前的 `course_kb_v1`，正常情况下不需要动它） |
| `RAG_ANALYZER_TYPE`  | chinese                  | BM25 分词器：`chinese` = jieba 中文分词（**中文知识库必须**，否则短文本块会霸榜）；留空 = 服务端默认分词器 |
| `RAG_MILVUS_TIMEOUT` | 10                       | 单请求超时（秒） |
| `RAG_WARMUP`         | false                    | 服务启动时是否预热（`.env` 中另有此项，开启后可提前发现 Key 无效等问题） |

---

## 六、常见问题排查

### Q1. 报「RAG_EMBED_API_KEY 未配置」

`.env` 里 `RAG_EMBED_API_KEY=` 是空的。填上 Key 后重启服务（`.env` 在启动时读取）。

### Q2. 报「云端向量化失败：401 / 403」

Key 无效、过期，或与 `RAG_EMBED_API_BASE` 不匹配（比如拿了智谱的 Key 却配硅基流动的地址）。  
注意有些服务商的 Key 需要先完成实名/开通才会生效。

### Q3. 报「云端向量化失败：返回条数不符」

服务商单请求条数上限制约，把 `RAG_EMBED_API_BATCH` 调小（如 8）再试。

### Q4. 报「向量维度与建表时不符」

换了服务商或换了模型（维度变了），旧集合维度对不上。处理：

```bash
.venv/Scripts/python.exe -m tools.rag_ingest --rebuild   # ⚠️ 清空后重灌
```

同时建议 `.env` 里 `MILVUS_COLLECTION` 换个新名字（如 `job_kb_v2`），保留旧集合备查。

> 改造前后知识来源不同，也会遇到同一个集合里混着课程块与职位块的情况：
> 那时换个新集合名重灌即可，不要试图按 id 逐条删。

### Q5. 本地方案下载失败（SSLError / 超时 / `Expecting value: line 1 column 1`）

后者是文件被下载坏了（典型的软链接/截断问题）。改用直连下载脚本，并确保镜像配置正确：

```bash
# .env 中：RAG_HF_MIRROR=https://hf-mirror.com
.venv/Scripts/python.exe -m tools.download_models            # 断点续传，可反复执行
```

下载完成后把 `.env` 改成指向本地目录，避免每次联网检查：

```
RAG_EMBED_MODEL=./models/gte-large-zh
RAG_RERANK_MODEL=./models/bge-reranker-base
RAG_HF_OFFLINE=true
```

### Q6. 容器起来但 Windows 侧连不上

1. 确认 Docker Desktop 用的是 **WSL2 后端**（Settings → General → Use WSL 2 based engine）
2. `docker compose ps` 看 `milvus-standalone` 是否 healthy（首次启动约需 1~2 分钟）
3. `netstat -ano | findstr 19530` 确认端口已监听
4. 若改过端口映射，同步改 `.env` 的 `MILVUS_URI`

### Q7. 检索没命中，AI 还是瞎答

按顺序查：

1. `count` 是否为 0（没灌库）
2. 日志里 `[ai.rag] 未检索到可用知识块` 后面跟的原因
3. 知识块里到底有没有这个知识点 —— 打开 `seed/knowledge_chunks.json` 搜一下
4. 阈值过高：`RAG_RERANK_THRESHOLD` 调到 `0.2` 试试
5. 精排误杀：临时 `RAG_RERANK_ENABLED=false` 对比效果
6. 问的是不是**改造前的课程知识**：当前集合里是职位/公司/面试题块，不再有课程块
   （图谱里还有旧课程数据，见文末「与图谱的现状差异」）

### Q8. 明明库里有关键信息，检索却给出不相关的短文本块

典型的 **BM25 中毒词/短块霸榜**。判断与处理：

1. 用纯向量检索对照 —— 若纯向量第 1 名是正确答案，说明向量模型没问题，是 BM25 在捣乱：

   ```python
   from app.core import embedding, milvus_store
   qv = embedding.embed_text("你的问题")
   print(milvus_store.dense_search(qv, limit=5))     # 纯向量
   print(milvus_store.hybrid_search("你的问题", qv, limit=5))   # 混合
   ```

2. 检查集合是否真的用了中文分词器（`params.analyzer_params` 应为 `{"type":"chinese"}`）：

   ```python
   from app.core import milvus_store
   from app.config import MILVUS_COLLECTION
   desc = milvus_store.get_client().describe_collection(collection_name=MILVUS_COLLECTION)
   for f in desc["fields"]:
       if f["name"] == "chunks":
           print(f["params"])
   ```

3. 若分词器是默认值，说明建表时 `.env` 里 `RAG_ANALYZER_TYPE` 为空或服务端不支持。
   改好配置后**必须重建集合**（分词器是建表属性，改不了）：
   `.venv/Scripts/python.exe -m tools.rag_ingest --rebuild`

4. 仍不理想时可提高 `RAG_TOP_K`（如 6），给大模型更多候选，容错更高。

---

## 七、与课程示例代码的差异（已修正的坑）

课程包 `06.入库和检索.zip` 的代码可直接参考逻辑，但有 6 处必须改，本项目已处理
（这部分是**检索链路**的坑，与知识来源无关，招聘改造后依然适用）：

| # | 课程示例写法                                 | 问题                                                         | 本项目做法                            |
| - | -------------------------------------- | ---------------------------------------------------------- | -------------------------------- |
| 1 | `threshold = 0.8` 直接比对 CrossEncoder 输出 | bge-reranker-base 默认输出 **logits**（约 -10~10）而非概率，0.8 阈值口径错误 | 显式套 `Sigmoid` 归一化到 0~1，默认阈值 0.35 |
| 2 | `chunks like "%病假%"` 做硬过滤              | 关键词不在原文里就一条都搜不到，召回反而变差                                     | 默认不过滤，关键词约束交给 BM25 那一路表达         |
| 3 | 每段脚本里 `MilvusClient(...)` 硬编码内网 IP     | 换环境必改、且每次调用重建连接                                            | 单例连接 + 配置化地址（`.env`）             |
| 4 | 同步检索直接放在 async 链路里                     | 阻塞事件循环，WebSocket 对话整体卡住                                    | `asyncio.to_thread` 包一层          |
| 5 | `hit.entity.get("chunks")`（ORM 风格）     | MilvusClient 返回的是 dict，会 AttributeError                    | `_normalize_hits` 两种结构都兼容        |
| 6 | 建表只写 `enable_analyzer=True`，未指定分词器 | **服务端默认分词器按空白/标点切分，中文长句会被切碎**：BM25 只靠「AI」这类短词命中，**二三十字的短块靠长度优势霸榜**，把真正相关的长块挤出候选 | 指定 `analyzer_params={"type": "chinese"}`（jieba 分词）；服务端不支持时自动降级为默认分词器 |

另外，招聘改造后切块时特意处理的三个细节（都写在 `tools/rag_ingest.py` 的注释里）：

- **`rcAiWelcome.suggestions` 里的 `prompt` 正文刻意不录入知识库**：那是客户端按钮的「用户会怎么问」文案，
  不是平台业务事实；实测录入后问「面试会问什么」，Top1 会变成这条 AI 能力介绍，真正的面试题被挤到第 3 名。
- **职位形态标签去重**：`kind` 与 `job_type` 有重叠（`normal + fulltime` = 社招全职+全职、`intern + intern` = 实习+实习），
  只在前者「装不下」后者时才并列，避免「社招全职 / 全职」这种啰嗦写法。
- **薪资与地点口径统一**：职位块里的薪资按与列表页/详情页相同的规则拼装
  （`25-45K·15薪`，12 薪不写出来，两端都是 0 则写「薪资面议」），地点写成 `城市·区`，
  避免同一职位在不同页面出现两种说法。

### 实测效果对比（修正中文分词器前后，改造前课程知识库上的记录）

| 问题 | 修正前 | 修正后 |
| --- | --- | --- |
| 题库里 AI 基础能力测验有多少题？ | 正确答案排第 4，未进上下文 | **排第 1** |
| 办公软件课程有哪些？ | 命中的是分类短块 | 命中《Excel 高效办公》等课程块 |

> 排查「短块霸榜」的通用方法：同一问题分别跑 `dense_search`（纯向量）与 `hybrid_search`（混合）。
> 若纯向量第 1 名是正确答案、混合结果却被挤走，问题出在 BM25 分词，而不是向量模型。
> 这套方法与知识来源无关，换成招聘知识库后同样适用。

### 其他实测数据（阿里百炼）

- `text-embedding-v3` 返回 **1024 维**（当前 `.env` 用的就是这家）；
- 单请求输入条数**上限为 10**（11 条即报 `batch size is invalid, it should not be larger than 10`）。
  代码已做自适应：配置超过上限时自动对半缩小并重试，无需手工改配置。
  排查时注意：**缩小批大小后必须重新切片**，否则「已降到 1 条仍报超限」——这是本项目踩过的坑。

---

## 八、二期可做的优化（当前未做，按需再确认）

以下都不影响现在可用，属【建议】项：

1. **引用回传客户端**：现在检索结果只用于提示词，客户端看不到「参考了哪几个职位/哪道题」。要做需要在 WebSocket 帧契约里新增一种帧（如 `references`），**会改动接口契约，需你确认后再动**。
2. **打开精排**：知识库涨到千条以上、发现召回质量不够时，再下载 bge-reranker-base 并置 `RAG_RERANK_ENABLED=true`。
3. **增量灌库**：目前是全量覆盖（按 source 删旧再写）。职位数据每天变化时，建议按 `job_id` 做 upsert 而非全量重灌。
4. **按身份过滤**：`rag.retrieve(filter_extra=...)` 已支持传过滤表达式，可结合求职者的投递/收藏，或 HR 绑定的公司，做「只看与自己相关」的检索。
5. **切块策略细化**：目前一个职位就是一块（含职责、要求、招聘流程、HR 信息）。若发现长块召回不准，可拆成「岗位职责 / 任职要求 / 招聘流程」多块，用同一 `job_id` 关联。

---

## 与图谱的现状差异（截至本文最后更新）

向量检索与图谱检索是两条独立的通路，**当前状态并不一致**：

- **向量检索（本文）**：已换成招聘知识库，集合 `job_kb_v1`，136 条知识块，第四节 4 条问法实测命中；
- **图谱检索（Neo4j）**：仍是**改造前的课程图谱**（141 个实体 / 126 个知识块节点 / 119 条语义关系），
  `tools/graph_ingest.py` 的结构化来源还写死为旧快照 `seed/mock_data.json`，尚未切到招聘种子。

所以现在问 AI 求职助手时，可能命中「向量检索给出的职位/面试题块」+「图谱里残留的课程事实」这种混合结果。
把图谱切到招聘语境的做法见 `docs/直聘通-架构说明.md` 与根目录 `README.md` 第十节；
排查「AI 又讲起课程来了」时，这是第一个要查的地方。
