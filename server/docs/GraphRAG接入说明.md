# GraphRAG 接入说明

面向本项目的「AI 助教 + 知识图谱」改造说明。技术栈：**Neo4j（本机 Windows 服务 / Docker 备选）+ 规则抽取 + DeepSeek 实体关系抽取 + 与 Milvus 向量检索融合**。

本文是 `docs/RAG接入说明.md`（向量 RAG）的姊妹篇：向量那套解决「哪段资料在讲这件事」，本文这套解决「实体之间到底是什么关系」。

---

## 一、这套东西解决什么问题

只做向量检索时，AI 助教能答「哪段资料在讲这件事」，但答不了**结构化的关系问题**：

| 问题类型 | 例子 | 向量检索 | 图谱检索 |
| --- | --- | --- | --- |
| 语义问答 | 「什么是 RAG？」 | ✅ 召回知识卡片原文 | ❌ 图里没有概念关系 |
| 属性问答 | 「这门课多少钱、几个课时」 | ⚠️ 能召回课程块，但要靠模型从长文本里抠 | ✅ 直接给结构化属性 |
| 关系问答 | 「27 考研英语一全程班是谁讲的？」 | ⚠️ 需要原文恰好写了讲师 | ✅ 直接答「李思远、王雨桐」 |
| 多跳推理 | 「这位老师还讲什么课」 | ❌ 跨文档，几乎召不回 | ✅ 课程 → 讲师 → 其他课程，2 跳拿到 |
| 聚合统计 | 「AI·数字技能分类下有哪些课程」 | ❌ 分类与课程的归属关系不在文本里 | ✅ 分类节点的邻居就是课程清单 |

**组合后的效果**：一次提问同时走两路，图谱事实（精确、结构化、可多跳）排在前面，知识块原文（语义细节）排在后面，一起注入提示词。两路**互相独立**——任一路挂掉都不影响另一路，两路都挂才退化为原来的纯对话。

> ⚠️ 关键取舍：图谱事实是**当作可信事实**直接喂给大模型的，所以设计上处处「宁可少召回，不可召回错」。
> 具体体现在第七节的四道闸门。

---

## 二、文件清单（本次新增 / 改动）

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `app/core/graph_store.py` | 新增 | Neo4j 封装：连接单例、约束索引、写入、**实体链接**、子图多跳扩展、统计与健康检查 |
| `app/core/graph_rag.py` | 新增 | 图谱检索编排：实体链接 → 子图扩展 → 事实文本化，含全部降级分支 |
| `app/core/graph_extract.py` | 新增 | 实体关系抽取：结构化数据走规则、非结构化文本走大模型（含反幻觉校验） |
| `tools/graph_ingest.py` | 新增 | 灌图 CLI：抽取 → 合并 → 生成溯源边 → 写入 Neo4j |
| `tools/graph_check.py` | 新增 | 图谱检索自检（只读）：不启动服务即可看「命中什么实体、产出什么事实」 |
| `tools/neo4j_init_auth.ps1` | 新增 | Neo4j 认证存储初始化（首次设密码；忘记密码时重置） |
| `docker/neo4j-compose.yml` | 新增 | Neo4j standalone 编排（**备选方案**，本机已用 Windows 服务版，见第三节说明） |
| `docs/GraphRAG接入说明.md` | 新增 | 本文档 |
| `seed/graph_preview.json` | 运行时生成 | `--dry-run` 的抽取预览（实体 / 关系 / 知识块），便于人工检查抽取质量 |
| `app/config.py` | 追加 | 仅新增 GraphRAG 配置段，**未修改任何原有配置项** |
| `app/core/rag.py` | 追加 | 检索改为「图谱 + 向量」两路合并 + 提示词两段式；**无图谱事实时输出与改造前完全一致** |
| `app/routers/ai.py` | 追加 | 两个只读运维接口，**未改动原有帧契约与业务流程** |
| `app/core/__init__.py` | 追加 | 补充三个图谱模块的说明行 |
| `requirements-rag.txt` | 追加 | 新增图数据库驱动 `neo4j==6.3.0` |
| `.env` | 追加 | 仅新增 GraphRAG 配置段（含 `NEO4J_PASSWORD`），原有配置原样保留 |

---

## 三、图模型设计

### 1) 节点

所有实体统一带 `:Entity` 标签，**具体类型作为第二标签**（如 `:Entity:Course`）。这样「统一遍历全图实体」和「按类型查」都不用改查询语句。

| 第二标签 | 业务类型 | 说明 | 本次实测 |
| --- | --- | --- | --- |
| `Course` | 课程 | 精品课 / 免费课 / 推荐课 / 直播公开课 / 分类课程 | 45 |
| `Tag` | 标签 | 课程标签 | 43 |
| `Category` | 课程分类 | 分类表 + 首页分类（同名不同叫法自动合并为别名） | 13 |
| `Feature` | 产品功能 | 学习入口、AI 能力等 | 9 |
| `KnowledgePoint` | 知识点 | 题目考查点、记忆卡复习点 | 8 |
| `Teacher` | 讲师 | 课程讲师 | 7 |
| `QuestionBank` | 题库 | 题库及其题量 | 6 |
| `Card` | 记忆卡 | 正面 / 背面 / 阶段 | 4 |
| `Question` | 题目 | 题干前 60 字作显示名，完整题干放属性 | 3 |
| `Doc` | 文档资料 | 需求文档、参考资料入口 | 3 |
| `Concept` | 兜底 | 类型没登记时用它，保证节点仍能被统一遍历 | 0 |

> 类型 → 标签的映射是代码里的白名单常量（`graph_store.TYPE_TO_LABEL`），
> Cypher 语法不允许参数化标签，所以**必须先过白名单再拼接**。

另外一类节点是知识块：

| 标签 | 主键 | 属性 | 本次实测 |
| --- | --- | --- | --- |
| `Chunk` | **正文的 MD5** | `title` / `source` / `type` / `text` | 126 |

### 2) 关系

| 关系类型 | 方向与语义 | 来源 | 本次实测 |
| --- | --- | --- | --- |
| `TAUGHT_BY` | 课程 → 讲师（授课讲师是） | 规则 | 24 |
| `BELONGS_TO` | 课程 → 分类（属于分类） | 规则 | 34 |
| `HAS_TAG` | 课程 → 标签（带有标签） | 规则 | 51 |
| `TESTS` | 题目 → 知识点（考查的知识点是） | 规则 | 3 |
| `REVIEWS` | 记忆卡 → 知识点（用于复习知识点） | 规则 | 4 |
| `IN_BANK` | 题目 → 题库（属于题库） | 规则 | 0（当前数据未产生） |
| `DESCRIBES` | 文档 → 功能（描述的功能是） | 规则 / 大模型 | 0（当前数据未产生） |
| `USES` / `INCLUDES` / `PART_OF` | 「使用 / 包含 / 是……的组成部分」 | 大模型 | 各 1 |
| `RELATES_TO` / `REQUIRES` / `PROVIDES` / `SUPPORTS` | 「相关 / 需要 / 提供 / 支持」 | 大模型 | 0（当前数据未产生） |
| `MENTIONS` | **知识块 → 实体**（某块资料提到了某实体） | 字符串匹配 | 405 |

### 3) 实体主键规则

主键形如 **`类型:归一化名称`**，例如 `course:ai大模型应用实战营`。

归一化 = **只保留「中文 + 字母 + 数字」**（空格、`·`、`-`、`（）`、`/` 等一律去掉，字母统一小写）。因此：

- 「AI·数字技能」与「AI数字技能」→ 同一个实体
- 「AI 大模型应用实战营」与「AI大模型应用实战营」→ 同一个实体

> ⚠️ 为什么不用自增 id：名称才是业务上的唯一标识。
> 用「类型 + 归一化名称」当主键，结构化数据、大模型抽取、知识块溯源**三条来源会自动 MERGE 到同一个节点上**，重复灌图也天然幂等。
>
> ⚠️ 归一化规则是全链路唯一的出口（`graph_store.normalize_name`）：
> 实体主键、实体链接、大模型抽取校验全都用它，改一处等于改全链路。

### 4) 溯源边 `(Chunk)-[:MENTIONS]->(Entity)` 的作用

1. **事实可标出处**：图谱事实末尾可以附「（出处：27 考研英语一全程班：阅读 + 写作 + 完形一次搞定）」，模型与使用者都能核对；
2. **与向量库对齐**：`Chunk` 主键就是**正文 MD5**，与 `app/core/rag.py` 里去重用的指纹算法一致 —— 图里的知识块节点与 Milvus 里的知识块是一一对应的；
3. **不参与事实渲染**：它是「出处」不是「语义关系」，子图扩展时按关系类型显式排除（`graph_store.PROVENANCE_REL`）。

---

## 四、抽取方式

两条路线对应两类数据，最后合并成同一张图（`graph_extract.merge_extractions`）。

### A. 规则抽取（结构化数据，零成本）

面向 `seed/mock_data.json`（MySQL 导出快照）里的课程、分类、讲师、标签、题库、题目、记忆卡、功能入口——这些字段本身已经是「实体 + 属性 + 关系」，用代码直接翻译即可：**不调用大模型、100% 准确、可重复、可增量**。

实测（仅规则）：**135 个实体、116 条语义关系**。

### B. 大模型抽取（非结构化文本）

面向需求文档这类纯文本：DeepSeek 按固定 JSON 结构输出实体与关系（`temperature=0`，`response_format={"type":"json_object"}`），**并做三条反幻觉校验，任一不过就丢该条**：

| # | 校验 | 落空时的计数键 | 为什么必须做 |
| --- | --- | --- | --- |
| 1 | 实体名必须**逐字出现在原文里**（归一化后比较，容忍标点差异） | `not_in_text` | 模型的改写、翻译、缩写、自造名词都会变成图里的假实体 |
| 2 | 关系两端必须都是**同一片段里**抽出的实体 | `unknown_endpoint` | 防止模型把不同片段串起来编关系 |
| 3 | 实体类型、关系类型必须在白名单内 | `bad_type` / `bad_rel` | 类型是渲染与查询的依据，脏类型会污染整张图 |

> ⚠️ 设计取向：**图宁可比真实数据「瘦」一点，也不要混入幻觉。**
> 图谱一旦写入脏实体，检索时会把错误事实当可信资料喂给模型，比没有图谱更糟。

实测（本次灌图）：

| 项 | 数值 |
| --- | --- |
| 知识块总数 | 126（`seed/mock_data.json` 118 + 需求文档 8） |
| 默认交给大模型的块 | 8（**仅非结构化文本**；结构化数据已由规则构过图，再抽一遍既费额度又不会更准） |
| 被反幻觉校验拦下 | 3 条实体名「原文里没有」→ `dropped["not_in_text"]=3`，未写入 |
| 合并后入库 | **141 个实体、119 条语义关系**（规则 135/116 + 大模型补充 6 个实体 / 3 条关系） |

想扩大范围可以加 `--llm-all`（把 126 条全部交给模型），想零成本就直接 `--no-llm`。

---

## 五、启动与灌图步骤

本机**已经装了 Windows 服务版 Neo4j**（服务名 `neo4j`，安装目录 `D:\cheng du shi xi\neo4j-community-2026.08.1`，版本 2026.08.1 community，Bolt `7687` / HTTP Browser `7474`），直接用它即可。

### 1) 确认 Neo4j 在跑

```powershell
sc query neo4j                 # STATE 应为 RUNNING
Test-NetConnection 127.0.0.1 -Port 7687 -InformationLevel Quiet   # True 即端口就绪
```

首次使用（或认证存储从未初始化过）需要先设一次密码，**用管理员 PowerShell**：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\neo4j_init_auth.ps1 -Password '你自己定的密码'
```

`docker/neo4j-compose.yml` 是**备选方案**（换机器、要隔离环境时用）：与本机服务版占用同样的 7474/7687 端口，两者不能同时启动。要用 Docker 版：

```powershell
# 管理员 PowerShell：停掉服务版并禁止自动启动（避免端口冲突）
Stop-Service neo4j; Set-Service neo4j -StartupType Manual
# 回到 server/ 目录启动容器（直接复用 .env 里的 NEO4J_PASSWORD）
docker compose --env-file .env -f docker/neo4j-compose.yml up -d
```

### 2) 装驱动

```bash
cd server
.venv/Scripts/pip.exe install -r requirements-rag.txt      # 图侧只需 neo4j==6.3.0（很轻量）
```

### 3) 填密码

`.env` 的 GraphRAG 段填上 Neo4j 密码（`config.py` 对 `NEO4J_PASSWORD` **刻意不设默认值**）：

```
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=你的密码
```

### 4) 灌图

```bash
# 先看会抽出什么（不写库；会落盘 seed/graph_preview.json 供人工检查）
.venv/Scripts/python.exe -m tools.graph_ingest --dry-run

# 正式灌图（全部 MERGE，可反复执行，不会产生重复数据）
.venv/Scripts/python.exe -m tools.graph_ingest

# 只看当前图谱规模
.venv/Scripts/python.exe -m tools.graph_ingest --stats

# 检索自检：不启动服务也能看「命中什么实体、产出什么事实」
.venv/Scripts/python.exe -m tools.graph_check
.venv/Scripts/python.exe -m tools.graph_check -q "27 考研英语一全程班是谁讲的？"
.venv/Scripts/python.exe -m tools.graph_check -q "AI·数字技能分类下有哪些课程？" --prompt
```

| 参数 | 作用 |
| --- | --- |
| `--dry-run` | 只抽取 + 落盘预览，不连 Neo4j |
| `--rebuild` | ⚠️ 先清空图谱再灌（唯一会删数据的路径，必须显式传参） |
| `--no-llm` | 完全不调用大模型，只用规则构图（零 token 成本） |
| `--llm-all` | 让大模型抽取全部知识块（默认只抽非结构化文本） |
| `--llm-limit N` | 限制交给大模型的块数（调试用） |
| `--source all\|mock\|doc` / `--extra 文件` | 限定知识块来源 |

> ⚠️ `--rebuild` 只会删除**本项目写入的 `:Entity` 与 `:Chunk` 节点**及其关系，
> **不会**动同一个 Neo4j 里其他实验数据。
> 一个库多人多用途是常态，全库 `DETACH DELETE` 是绝对不能做的操作。
> 同理，`--stats` 与 `/graph/status` 的统计口径也只覆盖本项目的数据。

---

## 六、与向量检索的融合与降级

### 1) 融合位置：`rag.retrieve()` 两路并行

```
rag.retrieve(question)
  ├─ 第 1 路 向量检索（app/core/rag.py::_vector_retrieve，逻辑与改造前完全一致）
  │    问题 → 向量化 → 混合检索（稠密 + BM25，RRF）→ 精排 → 阈值/去重/截断
  └─ 第 2 路 图谱检索（app/core/graph_rag.py::retrieve_graph）
       问题 → 实体链接 → 子图多跳扩展 → 事实文本化
  ↓
contexts = 图谱事实（kind="graph"） + 向量知识块
```

- 图谱事实的条数由 `GRAPH_TOP_K` 单独控制，**不占用** `RAG_TOP_K` 的额度；
- 顺序即注入顺序：**图谱事实在前，知识块原文在后**。

### 2) 提示词：两段式（`rag.build_system_prompt`）

| 场景 | 结构 |
| --- | --- |
| 有图谱事实 | 「知识图谱事实」（优先级最高，冲突时以它为准）+「参考资料」（知识库原文片段，补细节） |
| **没有**图谱事实 | 与原实现**完全一致**的单段结构（`=== 参考资料开始/结束 ===`），未接图谱时行为一字不变 |

事实以自然句渲染（`《课程》（课程）的授课讲师是 李思远（讲师）`），

> ⚠️ 为什么用自然句而不是 `A -> B` 箭头：
> 这段文本会直接拼进提示词喂给模型，越接近人话，模型越不容易搞错关系的**方向与语义**。

### 3) 图谱检索的四种降级情形

| 情形 | 触发条件 | 表现 |
| --- | --- | --- |
| 总开关关闭 | `GRAPH_ENABLED=false` | `error="图谱检索未启用"`，只用向量检索 |
| Neo4j 连不上 | 服务没起 / 密码错 / 驱动没装 | `error="图谱不可用：…"`，日志 `[graph]` 一行原因 |
| 问题里没有图谱实体 | 实体链接没命中（闲聊、问法太泛、图里没有这个概念） | `error="问题里没有识别到图谱实体"` |
| 图里没数据 | 还没灌图，实体索引为空 | 同上（`entities=0` 时走同一条分支） |

四者**全部只记日志、不抛异常**：`rag.retrieve()` 照常返回向量那一路的结果，对话主链路完全不受影响。

### 4) 配置项速查（`server/.env`）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `GRAPH_ENABLED` | true | 图谱检索总开关（false 不影响灌图脚本） |
| `NEO4J_URI` | bolt://127.0.0.1:7687 | Bolt 地址 |
| `NEO4J_USER` / `NEO4J_PASSWORD` | neo4j / 空 | ⚠️ 密码无默认值，缺了会在首次检索/灌图前明确报错 |
| `NEO4J_DATABASE` | neo4j | 社区版只有默认库 |
| `GRAPH_NEO4J_TIMEOUT` / `GRAPH_NEO4J_POOL_SIZE` | 8 / 20 | 单次查询超时（秒）与连接池上限 |
| `GRAPH_TOP_K` | 6 | 一次最多注入几条图谱事实 |
| `GRAPH_SEED_LIMIT` | 5 | 问题里最多识别几个起点实体 |
| `GRAPH_MAX_HOPS` | 2 | 扩展跳数（2 = 允许「课程 → 讲师 → 其他课」多跳） |
| `GRAPH_EXPAND_LIMIT` | 40 | 扩展最多取多少条边 |
| `GRAPH_FACT_MAX_CHARS` | 300 | 单条事实渲染后的字符上限 |
| `GRAPH_ENTITY_CACHE_TTL` | 300 | 实体名清单缓存秒数（灌图后想立刻生效可缩短） |
| `GRAPH_LINK_MIN_OVERLAP` | 5 | 兜底召回的「最长公共子串」闸门长度 |
| `GRAPH_EXTRACT_PROVIDER` | both | `both` 规则+大模型 / `rule` 只规则 / `llm` 只大模型 |
| `GRAPH_EXTRACT_MODEL` | 空=AI_MODEL | 抽取用模型（与对话共用 Key 与地址） |
| `GRAPH_EXTRACT_BATCH` / `GRAPH_EXTRACT_MAX_CHARS` / `GRAPH_EXTRACT_TIMEOUT` | 4 / 1200 / 120 | 每批块数 / 单块字符上限 / 单次请求超时（秒） |

---

## 七、检索质量上的几个关键设计

这一节是 GraphRAG 能不能用的分水岭：**图谱事实是当可信资料注入的，错一条比少一条危害大得多**。下面四条都是「踩到了具体问题才加的设计」。

### ① 关系方向必须取真实方向

子图扩展要从**命中实体的任一端**出发，所以 Cypher 里只能用无向匹配 `(a)-[r]-(b)`；但事实渲染对方向极其敏感——**「课程属于分类」和「分类属于课程」是完全不同的两句话**。

因此查询返回的是 `properties(startNode(r))` 与 `properties(endNode(r))`，即**关系真实的两端**，而不是「我出发的那个节点」：

```cypher
MATCH (a:Entity)-[r]-(b:Entity)
WHERE a.id IN $ids AND type(r) <> $skip_rel
RETURN properties(startNode(r)) AS s_props, type(r) AS rel, properties(endNode(r)) AS e_props
```

若图省事用出发节点当「左侧」，就会出现「「AI·数字技能」（分类）属于 某门课」这种事实性错误。

### ② 全文兜底召回必须加「最长公共子串」闸门

实体链接的主路径是**内存字典最长匹配**（问题归一化后包含实体名/别名），命中不了才走全文索引兜底。

> 问题：中文分词后，「27 考研英语一全程班」与「27 考研数学全程班」共享「考研」「全程班」，
> Lucene 分数都能很高 —— 于是问「**27 考研英语一**全程班是谁讲的」时，
> **「27 考研数学全程班」会被当成相关实体召回**，最终变成一条与问题无关的事实塞进提示词。

设计：兜底候选必须同时满足「最长公共子串 ≥ `GRAPH_LINK_MIN_OVERLAP`（默认 5）」**且**「占实体名长度的 35% 以上」才通过（`graph_store._longest_common_run` + `_MIN_OVERLAP_RATIO`）。

实测：问「27 考研英语一全程班是谁讲的？」，命中实体只有 2 个**英语一**课程，**数学那个没有被召回**。

### ③ 子图扩展按「最佳命中实体优先」分额度

> 问题：一个宽泛实体（如「AI·数字技能」分类）的邻居可能几十个；
> 若和具体实体（某门课）一起扩展，额度会被宽泛实体吃光，
> 「这门课的讲师/标签」这些最贴题的关系反而取不回来。

设计：分两阶段扩展——**阶段一先给最佳命中实体 60% 的额度**（`GRAPH_EXPAND_LIMIT`），阶段二再用剩余额度扩展其余实体（`graph_rag._expand_subgraph`）。

### ④ 事实排序：关系优先级 + 同类限额

> 问题：一门课的标签往往有 5 个，而讲师只有 1~3 个。
> 若按关系名排序（`BELONGS_TO < HAS_TAG < TAUGHT_BY`），**标签会先把事实名额占满**，
> 「这门课谁讲的」这种最高频的提问反而没进上下文。

设计（`graph_rag`）：

1. 排序键 = 「是否接在最佳命中实体上」→ 跳数（1 跳优先）→ 关系优先级 → 关系名；
2. 关系优先级 `TAUGHT_BY(1) < BELONGS_TO(2) < TESTS(3) < REVIEWS(4) < IN_BANK(5) < DESCRIBES(6) < … < HAS_TAG(20)`；
3. 同类限额 `_REL_FACT_CAP`：`HAS_TAG` 最多 2 条，把名额让给其他关系。

事实的可信度分数也按跳数递减：起点实体属性 `1.0`、1 跳关系 `0.85`、2 跳关系 `0.7`。

---

## 八、新增运维接口

两个接口都是**只读**、都需登录（`Authorization: Bearer <JWT>`），路由前缀 `/api/v1/ai`：

| 接口 | 作用 | 典型用途 |
| --- | --- | --- |
| `GET /api/v1/ai/graph/status` | 图谱连通性 + 规模 + 检索参数 | 排查「图谱没生效」：`neo4j.ok=false` 连不上 / `nodes=0` 没灌图 / `relations=0` 有实体没关系 |
| `GET /api/v1/ai/graph/search?q=你的问题` | 直接看一次图谱检索的中间结果 | 联调与答辩演示：命中了哪些实体、每条事实几跳、出处是什么 |

```bash
curl -H "Authorization: Bearer <你的JWT>" "http://127.0.0.1:8000/api/v1/ai/graph/status"
curl -H "Authorization: Bearer <你的JWT>" "http://127.0.0.1:8000/api/v1/ai/graph/search?q=27%20考研英语一全程班是谁讲的"
```

Bolt 查询是同步阻塞调用，两个接口都走 `asyncio.to_thread`，不会卡住事件循环。

### 实测数据规模（本机 Neo4j，当前图谱）

| 指标 | 数值 |
| --- | --- |
| 节点总数 | 267（实体 **141** + 知识块 **126**） |
| 关系总数 | 524 |
| 语义关系（实体↔实体） | **119** |
| 溯源关系（知识块→实体） | **405** |
| 实体类型分布 | 课程 45、标签 43、分类 13、功能 9、知识点 8、讲师 7、题库 6、记忆卡 4、题目 3、文档 3 |
| 关系类型分布 | MENTIONS 405、HAS_TAG 51、BELONGS_TO 34、TAUGHT_BY 24、REVIEWS 4、TESTS 3、USES 1、INCLUDES 1、PART_OF 1 |

> `--stats` 与 `/graph/status` 的口径一致，都只统计 `:Entity` / `:Chunk` 及其关系。

---

## 九、端到端验证记录

**场景：Milvus 未启动**（向量那一路整体不可用），验证图谱单路能否支撑问答。

提问：「27 考研英语一全程班是谁讲的？」

| 环节 | 实测结果 |
| --- | --- |
| 向量检索 | 整条失败降级（Milvus 没起），`mode=none` |
| 图谱实体链接 | 命中 **2 个**实体（两门名称相近的英语一课程，可信度均 1.00） |
| 子图扩展 | 扩展 **13 条**关系 |
| 事实产出 | **6 条**事实（起点属性 2 条 + 1 跳关系 4 条） |
| 服务端日志 | `[ai.rag] 注入 6 条知识块（方式=none，最高分=1.0000）` |
| 模型回答 | 「**李思远、王雨桐**」（与图里 `TAUGHT_BY` 关系一致） |

结论两条：

1. **图谱单路即可支撑问答** —— 向量库整条挂掉时，AI 助教仍能依据图谱事实答对关系类问题；
2. **降级策略有效** —— 向量路失败没有让对话失败，也没有让图谱路一起失败。

可复现的图谱侧验证（不启动服务、不发对话）：

```bash
.venv/Scripts/python.exe -m tools.graph_check -q "27 考研英语一全程班是谁讲的？"
```

输出（实测，节选）：

```
问题：27 考研英语一全程班是谁讲的？
  命中实体 2 个：
    · 27 考研英语一全程班：阅读 + 写作 + 完形（课程，匹配「27考研英语一全程班」，可信度 1.00）
    · 27 考研英语一全程班：阅读 + 写作 + 完形一次搞定（课程，匹配「27考研英语一全程班」，可信度 1.00）
  扩展 13 条关系，产出事实 6 条：
    [0 跳 · 1.00] 《27 考研英语一全程班：阅读 + 写作 + 完形一次搞定》（课程：类型 精品课、现价 599元、原价 1280元、课时 126讲）…
    [1 跳 · 0.85] 《…一次搞定》（课程） 的授课讲师是 李思远（讲师）…
    [1 跳 · 0.85] 《…一次搞定》（课程） 的授课讲师是 王雨桐（讲师）…
体检完成：1/1 个问题命中了图谱事实
```

---

## 十、常见问题

### Q1. 连不上 Neo4j

按三类原因排查（`/graph/status` 的 `neo4j.error` 会直接给出原因）：

1. **服务**：`sc query neo4j` 是否为 RUNNING；`Test-NetConnection 127.0.0.1 -Port 7687` 是否 True；
2. **密码**：`.env` 的 `NEO4J_PASSWORD` 与实际是否一致（改过密码忘了同步是常见情况）；
3. **驱动**：没装 `neo4j` 时 `graph_store.get_driver()` 会提示 `请执行 .venv/Scripts/pip.exe install -r requirements-rag.txt`。

### Q2. `/graph/status` 显示 `nodes=0` / `entities=0`

连上了但没灌图。跑一次：

```bash
.venv/Scripts/python.exe -m tools.graph_ingest --dry-run   # 先确认能抽出东西
.venv/Scripts/python.exe -m tools.graph_ingest             # 再正式写入
```

### Q3. 有实体但 `relations=0`

只灌了节点没灌关系，或抽取规则没覆盖到这类数据。看 `graph_ingest` 收尾打印的「关系类型」分布，对照第三节的关系表判断缺哪一类。

### Q4. 灌完图，检索却没变化

实体名清单有 **300 秒缓存**（`GRAPH_ENTITY_CACHE_TTL`），避免每次提问都全图读一遍。灌图脚本收尾会自动让缓存失效，但**已经运行中的服务进程**仍可能拿着旧清单：

- 等 300 秒，或重启服务；
- 或把 `.env` 里 `GRAPH_ENTITY_CACHE_TTL` 调小（如 `30`）后再调试。

### Q5. 不想花 token 做抽取

两种方式，等价：

```bash
# 一次性：本次灌图完全不调大模型
.venv/Scripts/python.exe -m tools.graph_ingest --no-llm
```

```
# 长期：.env 里改成只用规则
GRAPH_EXTRACT_PROVIDER=rule
```

代价：非结构化文本（需求文档等）里的实体关系不会进图，图会「瘦」一些，但结构化部分（课程/分类/讲师/标签/题库）完全不受影响。

### Q6. Neo4j 认证存储没有初始化（谁都登不进去）

现象：连接稳定报 `401 Unauthorized` / `authentication failure`，且安装目录下 `data\dbms\auth.ini` 不存在——这是「认证开着、但还没有任何账号」的状态。

处理（管理员 PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\neo4j_init_auth.ps1 -Password '你自己定的密码'
```

脚本会依次：校验管理员权限 → 若认证存储已存在则**不覆盖**并退出 → 停服务 → `neo4j-admin dbms set-initial-password` → 起服务 → 用项目虚拟环境的驱动实测登录。忘记密码时的重置办法：停服务 → 删除 `data\dbms\auth.ini` → 重跑本脚本（只影响账号，图数据不受影响）。

> ⚠️ 脚本里调用 `neo4j-admin` **必须用 `cmd.exe /c "... > 日志 2>&1"` 做重定向**，
> 不要用 PowerShell 的 `2>&1`：
> 在 Windows PowerShell 5.1 下，`neo4j-admin` 往 stderr 打的 Java 警告
> （`WARNING: Using incubator modules: jdk.incubator.vector`）会被当成
> `NativeCommandError` 抛出，**把成功的命令误报为失败**，真实的报错信息也一起被吞掉。
> 用 cmd 重定向后，退出码与完整输出都能被准确读到。

---

## 附：与向量 RAG 的关系

| 维度 | 向量 RAG（`docs/RAG接入说明.md`） | GraphRAG（本文） |
| --- | --- | --- |
| 存储 | Milvus（向量 + BM25 稀疏向量） | Neo4j（实体 / 关系 / 知识块） |
| 数据准备 | 切块 + 向量化灌库（`tools/rag_ingest.py`） | 规则 + 大模型抽取实体关系（`tools/graph_ingest.py`） |
| 擅长 | 「哪段资料在讲这件事」 | 「实体之间是什么关系、可多跳」 |
| 失效表现 | `mode=none`，图谱路照常 | `graphMode=none`，向量路照常 |
| 运维接口 | `GET /ai/rag/status`、`POST /ai/rag/warmup` | `GET /ai/graph/status`、`GET /ai/graph/search` |
| 共同点 | 都是**可选增强**：任一环节失败只降级、绝不抛异常，不影响对话主链路的可用性 | 同左 |
