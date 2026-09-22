# 后端服务（用户体系 + AI 助教 + 内容 / 我的 / 学习）

基于 FastAPI 的后端服务，为 uni-app 客户端提供五类能力：

- **用户体系**：注册、登录、资料管理、改密、注销（8 个接口）
- **AI 助教**：会话管理、WebSocket 流式对话、**图片附件**（上传/落库/回显）、RAG 知识库检索
- **内容域**（公开）：首页聚合、分类、课程列表/详情、页面配置（5 个接口）
- **我的域**（🔒）：订单、优惠券、我的课程/收藏、统计（11 个接口）
- **学习域**（🔒）：题库、题目、记忆卡、错题本、答题记录、统计、概览、周报（14 个接口）

技术选型与参考资料《02.服务器》保持一致：FastAPI + SQLAlchemy 2.0(async) + aiomysql + MySQL 8 + JWT(HS256) + bcrypt。

> ⚠️ **客户端对接现状**：19 个页面中，登录 / 个人中心 / 设置 / AI 助教 / 首页 / 分类 / 搜索 /
> 课程详情 / 订单 / 我的课程 / 学习模块 6 页 **均已切换为真实接口**（2026-09 完成）；
> 消息中心、用户协议等纯展示页仍为本地数据。

---

## 一、环境要求

| 项 | 要求 | 本机实测 |
| --- | --- | --- |
| Python | 3.12+ | 3.12.3（已建 `.venv`） |
| MySQL | 8.x | 8.0.43 |
| 数据库 | `sheji`（utf8mb4） | 已创建 |

## 二、快速开始

以下命令均在工作目录 `server/` 下执行。

```bash
# 1) 安装依赖（首次）
.venv/Scripts/pip.exe install -r requirements.txt

# 2) 建表（DDL 单源；改完 models 后重新执行）
.venv/Scripts/python.exe -m app.init_db

# 3) 启动服务
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

- 接口文档（自动生成）：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/

> ⚠️ `--host 0.0.0.0` 不能省。真机调试时客户端要填电脑的局域网 IP，
> 只监听 `127.0.0.1` 会导致手机连接超时。

## 三、配置说明

所有配置集中在 `.env`（已在 `.gitignore` 中排除）：

| 变量 | 说明 |
| --- | --- |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | 数据库连接 |
| `JWT_SECRET` | JWT 签名密钥（32 字节随机串，**生产必须重新生成**） |
| `JWT_EXPIRE_DAYS` | token 有效期，默认 7 天 |
| `EMAIL_CODE_LEN` | 验证码位数，默认 4（需与客户端输入框 maxlength 一致） |
| `EMAIL_TTL` | 验证码有效期秒数，默认 300 |
| `EMAIL_INTERVAL` | 重发间隔秒数，默认 60 |
| `EMAIL_DEBUG` | `true` 时验证码随响应以 `dev_code` 返回、不发邮件；`false` 走 SMTP 真实发送 |
| `EMAIL_MAX_VERIFY_ATTEMPTS` | 验证码最大校验失败次数，默认 5（防暴力枚举） |
| `SMTP_HOST` / `SMTP_PORT` | 邮件服务器（默认 `smtp.qq.com:465`，SSL 直连） |
| `SMTP_USER` / `SMTP_PASSWORD` | 发信账号与授权码（`EMAIL_DEBUG=false` 时必填，否则发送即报错） |
| `SMTP_FROM_NAME` | 发件人显示名 |
| `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` | AI 助教（DeepSeek）接入 |
| `AI_TIMEOUT` / `AI_WS_IDLE` / `AI_ROUNDS` | 单轮超时 / WS 空闲断连 / 上下文轮数 |
| `AI_UPLOAD_MAX_MB` | 图片附件单张体积上限，默认 10（MB）——见第九节 |
| `AI_IMAGE_MAX_COUNT` | 单条消息最多携带几张图，默认 4——见第九节 |
| `AI_VISION_MODEL` | 多模态模型名；**留空 = 纯文本模式**（默认）——见第九节 |

> ⚠️ **验证码相关配置的真实名字是 `EMAIL_*` / `SMTP_*`，不是 `SMS_*`。**
> `.env` 里仍保留着 `SMS_CODE_LEN` / `SMS_TTL` / `SMS_INTERVAL` / `SMS_DEBUG` /
> `SMS_MAX_VERIFY_ATTEMPTS`，`config.py` 也会读取它们，但**除此之外没有任何代码使用**：
> 本期登录凭据走邮箱，下发逻辑在 `routers/user.py`（读 `EMAIL_*`）与 `core/mail.py`
> （读 `SMTP_*`），`core/sms.py` 的 `send_sms()` 没有任何调用方。
> 将来接入真实短信通道时这几个 `SMS_*` 项可直接启用。

⚠️ `DB_PASSWORD` 与 `JWT_SECRET` **没有默认值**，缺失时服务启动即报错——这是刻意设计，避免敏感信息硬编码进源码。

## 四、接口清单

统一响应格式（与客户端 `common/utils/format.js` 的 `mockRequest` 一致）：

```json
{ "code": 0, "msg": "ok", "data": {} }
```

成功码为 **0**，消息字段名为 **msg**。

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/user/email/code` | 公开 | 发送邮箱验证码 |
| POST | `/api/v1/user/reg` | 公开 | 注册（邮箱 + 验证码） |
| POST | `/api/v1/user/login` | 公开 | 登录（`mode=code` / `mode=pwd`） |
| GET | `/api/v1/user/info` | 🔒 | 查询我的资料 |
| PUT | `/api/v1/user/info` | 🔒 | 更新我的资料 |
| PUT | `/api/v1/user/password` | 🔒 | 修改密码 |
| POST | `/api/v1/user/logout` | 🔒 | 退出登录 |
| DELETE | `/api/v1/user` | 🔒 | 注销账号（逻辑删除） |
| GET | `/api/v1/ai/sessions` | 🔒 | AI 会话列表 |
| GET | `/api/v1/ai/sessions/{sid}/messages` | 🔒 | 会话全部消息（含 `images` 字段） |
| DELETE | `/api/v1/ai/sessions/{sid}` | 🔒 | 删除会话（含其消息与图片关联） |
| POST | `/api/v1/ai/upload` | 🔒 | **上传图片附件**（multipart，字段名 `file`）——见第九节 |
| GET | `/api/v1/ai/rag/status` | 🔒 | 知识库连通性与条数 |
| POST | `/api/v1/ai/rag/warmup` | 🔒 | 预热/自检向量与精排模型 |
| WS | `/api/v1/ai/chat?token=<JWT>` | 🔒 | AI 流式对话（帧协议见第九节） |

### 4.1 内容域（公开只读，无需登录）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/content/home` | **首页聚合**：一次请求返回 11 个键（见下方说明） |
| GET | `/api/v1/content/config/{key}` | 读取单条页面配置的原始 JSON |
| GET | `/api/v1/content/categories` | 分类列表（`?kind=home` 首页入口 / `main` 分类页） |
| GET | `/api/v1/content/courses` | 课程列表（`category_id`/`kind`/`keyword`/`sort`/`page`/`size`） |
| GET | `/api/v1/content/courses/{id}` | 课程详情 |

`GET /content/home` 返回的 11 个键与 `common/mock/index.js` 的导出名**一一对应**：

```
banners homeNotices homeCategories adBanners seckill
checkinInfo dailyQuote rankings liveCourses qualityCourses guessYouLike
```

> ⚠️ 其中 `homeCategories` / `liveCourses` / `qualityCourses` / `guessYouLike` 是**从表里现算**的，
> 其余 7 个是 `page_config` 的原始 JSON。配置缺失时统一给 `[]` / `{}`，
> 保证这 11 个键**永远存在**，前端可直接解构。
>
> ⚠️ **没有** `/courses/{id}/lessons`（课表）：数据库没有课时明细表，
> 全项目唯一一份章节目录在 `page_config` 的 `courseDetail` 键里，且只覆盖 c1001 一门课。
>
> ⚠️ `kind=free` 会返回 `42002`：免费好课**不在** `course` 表，而是 `page_config.freeCourses`，
> 请改读 `GET /content/config/freeCourses`。

### 4.2 我的域（🔒 全部需登录）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/mine/orders` | 订单列表（`?status=` 过滤） |
| POST | `/api/v1/mine/orders` | 下单（报名课程，幂等） |
| POST | `/api/v1/mine/orders/{id}/pay` | 支付：待付款 → 已完成 |
| POST | `/api/v1/mine/orders/{id}/cancel` | 取消：待付款 → 已取消 |
| DELETE | `/api/v1/mine/orders/{id}` | 删除订单（物理删除） |
| GET | `/api/v1/mine/coupons` | 优惠券列表（`?status=unused\\|expired`，**只读**） |
| GET | `/api/v1/mine/courses` | 我的课程（`?kind=learning\\|finished\\|collect`） |
| POST | `/api/v1/mine/courses` | 加入我的课程 / 收藏（幂等 upsert） |
| DELETE | `/api/v1/mine/courses/{id}` | 移出我的课程 / 取消收藏 |
| PUT | `/api/v1/mine/courses/{id}/progress` | 上报学习进度 |
| GET | `/api/v1/mine/stats` | 四宫格计数（真实数据） |

> ⚠️ `uid` 一律取自 token（`get_current_user`），**绝不接受客户端传 uid**；
> 对不属于自己的 id 统一返回「不存在或无权访问」，不区分二者，避免探测他人数据。
>
> ⚠️ **新增「已取消」订单状态**：mock 的订单词表里只有 待付款/已完成/已退款，
> 服务端新增了该状态，客户端订单页的筛选 tab 需相应包含它，否则取消后的订单会「消失」。
>
> ⚠️ `user_course` 表**没有 course_id 列**（本期不加字段、不 ALTER 既有表）：
> 一条记录用它**自己的 id** 作为标识，与课程行的关联靠 `(uid, kind, title)` 去重。
> 因此 `POST /courses` 传的是 `course_id`（用于复制标题/讲师），
> 而 `DELETE /courses/{id}` 与 `PUT /courses/{id}/progress` 传的是**记录 id**。
> 客户端「点课程进详情」需要用标题反查课程 id（前端已在页面里实现并缓存）。

### 4.3 学习域（🔒 全部需登录）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/study/banks` | 题库列表（含**本人**已做 / 正确率） |
| GET | `/api/v1/study/banks/{id}/questions` | 题库下的题目（含答案与解析，供本地判卷） |
| GET | `/api/v1/study/memory/cards` | 记忆卡（内容 + 本人调度状态） |
| GET | `/api/v1/study/memory/progress` | 记忆卡进度列表 |
| POST | `/api/v1/study/memory/progress` | 复习一张卡（推进调度，upsert） |
| GET | `/api/v1/study/wrong` | 错题本（`?mastered=&bank_id=&bank=`） |
| POST | `/api/v1/study/wrong` | 收录错题（幂等：重复收录则次数 +1） |
| POST | `/api/v1/study/wrong/{id}/master` | 标记已掌握 |
| DELETE | `/api/v1/study/wrong/{id}` | 删除一条错题 |
| DELETE | `/api/v1/study/wrong` | 清空错题本 |
| POST | `/api/v1/study/answers` | 记录一组已结算的答题（交卷） |
| GET | `/api/v1/study/stats` | 题库维度统计 + 汇总 |
| GET | `/api/v1/study/overview` | 学习页概览 |
| GET | `/api/v1/study/report` | 学习周报 |

> ⚠️ **数据一致性口径**：本模块所有数字只有**一个来源** —— `answer_record`。
> 「学习天数 / 本周刷题数 / 正确率 / 柱状图」全部由它聚合，
> 因此 `/overview` 与 `/report` 互相自洽（不会出现「总计 268 分钟、七天相加只有 236 分钟」）。
>
> ⚠️ **已知边界**：只有「交卷」（`POST /answers`）会写 `answer_record`。
> 单纯复习记忆卡、看错题**不产生学习天数**（没有活动上报端点）。
> 学习时长（`minutes`）由客户端上报，不上报即为 0 —— **服务端不估算**，宁缺毋滥。
>
> ⚠️ 记忆卡的调度规则（阶段上限 6、间隔表 `[1,1,2,4,7,10,15]`、
> 三档评价 `know/vague/forget`）与前端 `common/utils/study-store.js` 的
> `rateMemoryCard()` **逐条一致**，避免两边算法漂移。
>
> ⚠️ 日期一律用 `YYYY-MM-DD` 字符串（不用时间戳、不用中文），
> 一周从**周一**开始共 7 天；展示文案（「3 月 10 日」「周一」）也由服务端给出，
> 与前端 `dateLabel` / `weekdayLabel` 的输出逐字符一致。

### 4.4 鉴权约定

🔒 端点需在请求头携带：`Authorization: Bearer <token>`
（WebSocket 无法自定义请求头，token 走查询串 `?token=`）

### 错误码表

| 码 | 含义 | | 码 | 含义 |
| --- | --- | --- | --- | --- |
| 40001 | 邮箱格式不正确 | | 40008 | 未设置密码 / 原密码错误 |
| 40002 | 验证码错误 / 失败次数超限 | | 40009 | 长度或格式不合法 |
| 40003 | 验证码已过期 | | 40100 | 未登录 / token 无效 |
| 40004 | 发送过于频繁 | | 40101 | 登录已过期 |
| 40005 | 该邮箱已注册 | | 40102 | 账号不存在或已注销 |
| 40006 | 该邮箱未注册 | | 41001 | AI：消息内容为空 |
| 40007 | 密码错误 | | 41002 | AI：会话不存在或无权访问 |
| 50001 | 邮件发送失败（SMTP 未配置 / 认证失败） | | 41006 | AI：模型服务不可用 |
| 41007 | AI：生成超时或已取消 | | 41008 | AI：参数不合法 |
| 41009 | AI：图片格式不支持（非 jpg/jpeg/png/webp/gif，或文件头不是图片） | | 41010 | AI：图片过大（超过 `AI_UPLOAD_MAX_MB`） |
| 41011 | AI：未收到文件 / 文件内容为空 | | 50000 | 服务器内部错误 |

内容域 / 我的域 / 学习域的错误码：

| 码 | 归属 | 含义 |
| --- | --- | --- |
| 42001 | 内容 | 内容不存在（课程 / 分类 / 配置键） |
| 42002 | 内容 | 参数不合法（kind / sort / page / size） |
| 43001 | 我的 | 订单不存在或无权访问 |
| 43002 | 我的 | 订单状态不允许此操作 |
| 43003 | 我的 | 课程不存在 |
| 43004 | 我的 | 学习记录不存在或无权访问 |
| 43005 | 我的 | 参数不合法（kind 取值错误等） |
| 44001 | 学习 | 题库不存在 |
| 44002 | 学习 | 题目不存在 |
| 44003 | 学习 | 错题记录不存在或无权访问 |
| 44004 | 学习 | 参数不合法（level / stage / total / correct / minutes） |
| 44005 | 学习 | 记忆卡不存在 |

> 说明：`40001`~`40009` 的文案已按「邮箱登录」口径更正——本期注册/登录凭据是
> **邮箱**，`user.phone` 字段虽保留但注册流程不会写入。

## 五、目录结构

```
server/
├── app/
│   ├── main.py        应用入口：CORS、6 个路由注册、三个异常处理器、/uploads 静态目录
│   ├── config.py      配置读取（.env → 环境变量）
│   ├── database.py    异步引擎与会话
│   ├── init_db.py     建表脚本（DDL 单源）
│   ├── seed.py        种子数据灌入（读 seed/mock_data.json，先清后写，可反复执行）
│   ├── core/
│   │   ├── response.py  ok() 统一响应 + BizError
│   │   ├── security.py  bcrypt + JWT + 鉴权依赖
│   │   ├── query.py     用户查询封装（统一软删过滤）
│   │   ├── sms.py       短信发送抽象（当前无调用方，预留）
│   │   ├── mail.py      邮箱验证码下发（SMTP）
│   │   ├── llm.py       DeepSeek 流式对话
│   │   ├── embedding.py 向量化唯一出口（云端 API / 本地模型二选一）
│   │   ├── milvus_store.py Milvus 集合读写
│   │   └── rag.py       检索 + 上下文组装（失败自动降级为纯对话）
│   ├── models/
│   │   ├── user.py       User / SmsCode / EmailCode
│   │   ├── ai.py         AiSession / AiMessage / AiMessageImage（图片附件）
│   │   ├── content.py    Category / Course / PageConfig
│   │   ├── mine.py       Order / Coupon / UserCourse
│   │   ├── study.py      QuestionBank / Question / MemoryCard（可复用内容）
│   │   └── study_user.py WrongQuestion / AnswerRecord / MemoryProgress（用户数据）
│   ├── schemas/
│   │   ├── user.py       Pydantic 出入参
│   │   ├── content.py    内容域出入参 + ORM→前端字段映射
│   │   ├── mine.py       我的域出入参 + 映射
│   │   └── study.py      学习域出入参 + 日期口径 + 映射
│   └── routers/
│       ├── user.py      用户体系 8 个端点（🔒 部分）
│       ├── ai.py        会话管理 + WS 对话 + RAG 运维
│       ├── ai_upload.py 图片上传端点 + 附件工具 + 可选多模态通路
│       ├── content.py   内容域 5 个端点（公开）
│       ├── mine.py      我的域 11 个端点（🔒）
│       └── study.py     学习域 14 个端点（🔒）
├── seed/
│   ├── mock_data.json     种子数据（由 tools/export_mock_data.mjs 从前端 Mock 导出）
│   └── knowledge_chunks.json RAG 知识库切块
├── tools/
│   ├── export_mock_data.mjs 前端 Mock → JSON
│   ├── rag_ingest.py        RAG 灌库（支持 --dry-run / --rebuild）
│   └── download_models.py   本地向量化/精排模型下载
├── docs/RAG接入说明.md
├── uploads/ai/         图片附件落盘目录（运行时创建；已加入 .gitignore）
├── .env                配置（含密码，不提交版本库）
├── .gitignore
├── requirements.txt
└── requirements-rag.txt  RAG 依赖（不装不影响原有功能）
```

### 建表与灌库（首次或重建时）

```bash
.venv/Scripts/python.exe -m app.init_db   # 建表（18 张）
.venv/Scripts/python.exe -m app.seed      # 灌种子数据（可反复执行）
```

## 六、设计要点

1. **逻辑删除**：用户注销只置 `deleted_at`，绝无物理 DELETE；同号可经「复活策略」重新注册，且保留原 `created_at`。
2. **软删过滤收敛**：所有按邮箱查询统一走 `core/query.py`，避免各业务处漏加 `deleted_at IS NULL` 条件。
3. **验证码失败计数**：4 位验证码仅 1 万种组合，连续失败达上限即作废，防穷举。
4. **密钥不落源码**：`DB_PASSWORD` / `JWT_SECRET` 无默认值，缺失即启动失败。
5. **异常不泄露**：422 与未捕获异常统一归一为 50000，堆栈只进服务端日志。

## 七、常见问题

**Q：改完 `models` 后建表没生效？**
`create_all` 只建「不存在」的表，**不会修改已有表结构**。加字段需手动 `ALTER TABLE`，或删表重建（数据会丢失）。

**Q：真机连接不上？**
1. 启动命令是否带 `--host 0.0.0.0`；
2. 客户端 `BASE_URL` 是否用了局域网 IP（`ipconfig` 查看），不能用 `localhost`；
3. Windows 防火墙是否放行 8000 端口。

**Q：H5 端请求被浏览器拦截？**
服务端已开启 CORS 演示配置；如遇问题请检查是否有代理层改写了请求头。

**Q：忘记密码？**
当前可用 `PUT /api/v1/user/password` 配合 `verify=code` 重置：先用 `POST /api/v1/user/email/code`
获取邮箱验证码，再提交 `{"verify":"code","code":"1234","new_password":"..."}`。
> ⚠️ 更正：`verify` 的合法取值只有 **`"old"` 和 `"code"`**（见 `schemas/user.py` 的
> `Literal["old", "code"]`）。旧文档里写的 `verify=sms` 并不存在，传 `"sms"` 会被框架
> 判为非法取值并归一成 50000，客户端只会看到「服务器开小差了」。
> 另外 `verify=old` 用于已设密码的账号改密；未设密码的账号只能用 `verify=code` 补设。

## 八、RAG 知识库（AI 助教增强，可选）

给 AI 助教加了一层「课程知识库检索」，让回答有据可依，而不是全靠模型自由发挥。

技术栈：**WSL2 + Docker Desktop + Milvus + 向量化（云端 API / 本地模型二选一）+ DeepSeek 生成**。

### 快速启动

```bash
# 1) 启动向量库（首次拉镜像约 1.5GB）
cd docker && docker compose -f milvus-compose.yml up -d && cd ..

# 2) 安装依赖（云端向量化模式只需 pymilvus）
.venv/Scripts/pip.exe install -r requirements-rag.txt

# 3) 填 API Key：.env 中 RAG_EMBED_API_KEY=（服务商见 docs/RAG接入说明.md 第三节）

# 4) 灌库（先 --dry-run 看切块效果，再正式灌）
.venv/Scripts/python.exe -m tools.rag_ingest --dry-run
.venv/Scripts/python.exe -m tools.rag_ingest
```

### 两种向量化方式（`.env` 一行切换）

| 方式 | 配置 | 下载量 | 说明 |
| --- | --- | --- | --- |
| 云端 API（当前） | `RAG_EMBED_PROVIDER=api` | **0** | 需 API Key；复用已有的 openai SDK，无新增依赖 |
| 本地模型 | `RAG_EMBED_PROVIDER=local` | 约 1GB | 免费、离线可用；用 `tools/download_models.py` 下载 |

> ⚠️ 切换方式或换模型会改变向量维度，必须 `tools.rag_ingest --rebuild` 重建集合并重灌。

### 新增接口

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/ai/rag/status` | 🔒 | 知识库连通性与条数（排查「AI 答不上来」） |
| POST | `/api/v1/ai/rag/warmup` | 🔒 | 预热/自检：API 模式会返回向量维度并验证 Key 是否有效 |

> 原有 AI 接口（会话列表、消息列表、删除会话、WebSocket 对话）的**出入参与帧契约均未改动**，
> 客户端无需任何调整；检索结果通过 system 提示词注入，客户端无感知。

### 关键约定

1. **失败自动降级**：Milvus 没启动、Key 无效、检索异常……一律降级为原纯对话，`AI 助教不会整体不可用`。
2. **原依赖清单未动**：RAG 依赖独立放在 `requirements-rag.txt`，不安装也不影响原有功能。
3. **总开关**：`.env` 里 `RAG_ENABLED=false` 即可完全回到改造前行为。
4. **精排默认关闭**：`RAG_RERANK_ENABLED=false`，省约 1GB 模型与内存；知识库规模大了再开。
5. **中文分词器**：集合建表时指定 `RAG_ANALYZER_TYPE=chinese`（jieba）。**中文知识库必须**，否则服务端默认分词器会把中文切碎，导致二三十字的短块靠长度优势霸榜、把正确答案挤出候选（改这一项需 `--rebuild` 重建集合）。
6. **可调阈值**：`RAG_RERANK_THRESHOLD` 默认 0.35（口径为 Sigmoid 归一化后的概率，**不是**课程示例里的 logits 0.8）。

📖 详细说明（含排查手册、配置速查、与课程示例代码的差异对比）见 [`docs/RAG接入说明.md`](docs/RAG接入说明.md)。

## 九、AI 助教图片附件

对应需求文档里 AI 助教页的「**有个+：点击可以上传图片，支持拍照**」。
上传、存储、落库、回显全链路已实现；**图片能否被模型「看到」取决于是否配置了视觉模型**，
默认配置下**不发送图片给模型**（详见下方「纯文本 vs 多模态」）。

### 9.1 上传接口

`POST /api/v1/ai/upload`　🔒（需 `Authorization: Bearer <token>`）

- 请求：`multipart/form-data`，**唯一字段名必须是 `file`**（单张图，一次一个请求）
- 成功响应（与全局 `{code,msg,data}` 信封一致）：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "id": "9f3c1b2a4d5e4f6087a9b0c1d2e3f4a5.png",
    "url": "/uploads/ai/9f3c1b2a4d5e4f6087a9b0c1d2e3f4a5.png",
    "name": "作业照片.png",
    "size": 20480,
    "mime": "image/png"
  }
}
```

- `id` 就是落盘文件名（uuid），也是后续聊天帧 `images` 数组里应当回传的值
- `url` 是**站点 origin 之后的路径**。客户端要自己补 origin：
  `BASE_URL` 是 `http://192.168.6.25:8000/api/v1`，去掉末尾的 `/api/v1` 得到
  `http://192.168.6.25:8000`，再拼 `url` 即为可直接展示的图片地址
- 失败：`41011` 未收到文件/内容为空、`41009` 格式不支持或文件头不是图片、`41010` 超过 `AI_UPLOAD_MAX_MB`

校验与存储要点：

1. **三重校验**：扩展名白名单（`jpg/jpeg/png/webp/gif`）→ 客户端声明的 `Content-Type` 必须是 `image/*`
   → **文件头魔数校验**（`\xff\xd8\xff` / `\x89PNG` / `GIF8` / `RIFF..WEBP`）。
   扩展名与真实内容不一致时以文件头为准；MIME 最终由服务端按文件头判定，不信客户端。
2. **落盘名一律 `uuid4().hex`**，客户端文件名只作为展示名存库，绝不参与磁盘路径。
3. **边读边计体积**，超过上限立即中断并删除半截文件，不会把大文件读进内存。
4. 上传**不写数据库**：此刻还没有消息行可挂，附件在聊天落库时才写 `ai_message_image`。
   因此「上传了但没发出去」的图片会成为 `server/uploads/ai/` 下的孤儿文件（见 9.5）。

### 9.2 聊天帧新增可选字段 `images`（向后兼容）

客户端 → 服务端（`type:"chat"`）：

```json
{ "type": "chat", "content": "帮我看看这道题", "session_id": "12",
  "images": ["9f3c1b2a4d5e4f6087a9b0c1d2e3f4a5.png"] }
```

- `images` **可省略**；省略时服务端行为与改造前逐行一致
- 数组元素可以是上传返回的 `id`，也可以是 `url`（`/uploads/ai/xxx.png`，带域名也认），
  还可以是 `{"id": "...", "name": "作业.png"}`（想保留原始文件名时用）
- 服务端不会新增/修改任何响应帧：`session` / `delta` / `done` / `error` 四种帧形态**完全不变**
- 容错策略：`images` 不是数组、元素无法解析、引用了不存在的图、超过 `AI_IMAGE_MAX_COUNT` 张，
  一律**只记日志并跳过**，绝不因此让整轮对话失败

### 9.3 纯文本 vs 多模态（⚠️ 请务必读这一节）

当前 `AI_MODEL=deepseek-v4-flash` 是**纯文本模型**，官方会把 `input_image` 替换成占位文本，
所以**默认不把图片发给模型**，只把一句注记拼进提示词：

```
帮我看看这道题

[用户上传了 1 张图片；当前模型为纯文本模型，无法查看图片内容，请如实说明看不到图片，需要时让用户用文字描述图片里的关键信息]
```

这样做的理由：与其让模型假装看懂了图、编出一段看似合理的描述（幻觉），
不如让它如实说明看不到——**注记里刻意写明「无法查看图片内容」**。

如果换成支持 OpenAI 兼容 `image_url` 协议的视觉模型，在 `.env` 里填一项即可切换：

```bash
AI_VISION_MODEL=某视觉模型名      # 留空（默认）= 纯文本模式
```

填了之后，最后一条 user 消息的 `content` 会从字符串变成内容块数组
（`[{"type":"text",...}, {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]`），
图片真正发给模型；`AI_MODEL` 与 `AI_VISION_MODEL` 相互独立，互不影响。

> ⚠️ 体积提醒：图片以 base64 内联，约放大 1.33 倍。`AI_UPLOAD_MAX_MB`（默认 10MB）×
> `AI_IMAGE_MAX_COUNT`（默认 4）最坏可达 50MB+ 的单次请求，超出多数服务商上限。
> 真要启用多模态，建议同时把这两项调小（例如 3MB / 2 张）。

### 9.4 历史消息回显

`GET /api/v1/ai/sessions/{sid}/messages` 的每个元素**新增 `images` 字段**（没图时为空数组）：

```json
{ "id": "15", "role": "user", "content": "帮我看看这道题",
  "createdAt": "2026-09-12 15:11:55",
  "images": [{ "url": "/uploads/ai/9f3c....png", "name": "作业照片.png" }] }
```

`id` / `role` / `content` / `createdAt` 四个既有字段的名称、顺序与含义均未改动，
老客户端不做任何调整也能正常解析。

### 9.5 新表与文件清理

图片与消息的关联存在**新表 `ai_message_image`**（`python -m app.init_db` 创建）：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT UNSIGNED PK | 附件 ID |
| `message_id` | BIGINT UNSIGNED，FK→`ai_message.id`，ON DELETE CASCADE | 所属消息 |
| `url` | VARCHAR(255) | 访问路径 |
| `name` | VARCHAR(120) | 展示用文件名（不参与磁盘路径） |
| `size` | INT | 字节数 |
| `mime` | VARCHAR(50) | 服务端判定的 MIME |
| `sort_order` | INT | 同一条消息内的顺序，从 0 起 |
| `created_at` | DATETIME | 关联时间 |

> ⚠️ 为什么是**新表**而不是给 `ai_message` 加字段：`create_all` 只创建「不存在」的表，
> **不会 ALTER 已有表**。给 `ai_message` 加列在已有库上永远不生效，必须先手工
> `ALTER TABLE` 或删表重建（丢数据）。独立成表则能被 `create_all` 干净地创建，
> 且天然支持「一条消息多张图」。

- **删会话**（`DELETE /api/v1/ai/sessions/{sid}`）会显式删掉这些关联行，不残留孤儿记录。
- **磁盘上的图片文件不会被自动删除**：同一张上传图可能被多条消息引用，直接删会打断其他消息的显示。
  需要清理时手动处理 `server/uploads/ai/`（该目录已加入 `.gitignore`，含用户隐私，不会进版本库）。

### 9.6 依赖注意

图片上传用到 `multipart/form-data` 解析，FastAPI 需要 **`python-multipart`**；
已加入 `requirements.txt`（`python-multipart==0.0.32`）。
装依赖后**必须重启服务**：缺失时 FastAPI 在注册路由阶段就会抛错，服务起不来。

```bash
.venv/Scripts/pip.exe install -r requirements.txt
```

## 十、GraphRAG 知识图谱（AI 助教增强，可选）

向量检索（第八章）回答的是「哪段资料在讲这件事」；图谱检索回答的是
「这些实体之间是什么关系」—— 课程属于哪个分类、谁讲的、这位老师还讲什么课。
两者互相独立、结果合并注入提示词：**任一路挂掉都不影响另一路**。

技术栈：**Neo4j 图数据库（本机 Windows 服务，Bolt 7687）+ 规则抽取 + DeepSeek 实体关系抽取**。
完整说明见 `docs/GraphRAG接入说明.md`。

### 快速启动

```bash
# 1) 确认 Neo4j 在跑（服务名 neo4j，端口 7687）
sc query neo4j

# 2) 装驱动（只需 neo4j 一项，很轻量）
.venv/Scripts/pip.exe install -r requirements-rag.txt

# 3) .env 里填 NEO4J_PASSWORD=（数据库密码）

# 4) 先看会抽出什么（不连库、不调模型）
.venv/Scripts/python.exe -m tools.graph_ingest --dry-run

# 5) 正式灌图（全部 MERGE，可反复执行；--rebuild 只清本项目的数据）
.venv/Scripts/python.exe -m tools.graph_ingest

# 6) 检索自检：看问题命中了哪些实体、产出了哪些事实
.venv/Scripts/python.exe -m tools.graph_check
```

### 图模型

| 元素 | 说明 |
| --- | --- |
| `(:Entity:Course/Category/Teacher/Tag/Question/KnowledgePoint/QuestionBank/Card/Feature/Doc)` | 实体节点，统一带 `:Entity` 标签便于统一遍历 |
| `(:Chunk)` | 知识块节点，主键是正文 MD5，与 Milvus 里的知识块一一对应 |
| `BELONGS_TO / TAUGHT_BY / HAS_TAG / TESTS / IN_BANK / REVIEWS / DESCRIBES` | 规则抽取出的语义关系 |
| `(Chunk)-[:MENTIONS]->(Entity)` | 溯源边：某条事实出自哪个知识块 |
| 关系类型一律过白名单 | Cypher 无法参数化标签/关系类型，只能白名单校验后再拼 |

### 新增接口（均为只读诊断，需登录）

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/ai/graph/status` | 图谱连通性与规模（实体/知识块/关系数、类型分布） |
| `GET /api/v1/ai/graph/search?q=` | 直接看某个问题命中哪些实体、产出哪些事实（联调与演示用） |

### 关键约定

1. **图谱是增强项，不是必需项**：`GRAPH_ENABLED=false`、Neo4j 没启动、密码没填、
   问题里没有图谱实体 —— 四种情况都只降级为「只用向量检索」，对话不受影响。
2. **不改变既有接口契约**：`rag.retrieve()` 的返回里新增 `graphMode` / `graph` 字段，
   原有 `contexts` / `mode` / `used` / `error` 语义不变；没有图谱事实时
   `build_system_prompt()` 的输出与改造前完全一致。
3. **灌图只增不改**：正常路径全部是 `MERGE`；`--rebuild` 只删除本项目写入的
   `:Entity` 与 `:Chunk`，不会动同一个 Neo4j 里其他实验数据。
4. **抽取宁缺勿滥**：大模型抽出的实体名必须逐字出现在原文里，关系两端必须是同片段实体，
   否则该条直接丢弃 —— 图谱里混进错误事实比少几条事实危害更大。
5. **灌图后实体缓存**：实体名清单有 300 秒缓存（`GRAPH_ENTITY_CACHE_TTL`），
   灌完图想立刻生效可重启服务。
