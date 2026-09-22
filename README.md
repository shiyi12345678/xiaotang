# 直聘通 · 招聘求职平台

一款「求职者 ↔ 企业 HR」双向的移动端招聘应用。

- **前端**：uni-app（Vue 3 · Options API），HBuilderX 工程，零图片资源（Logo/头像/图标全部 CSS + 字体图标实现）
- **后端**：FastAPI + SQLAlchemy 2.0（异步）+ MySQL，JWT 鉴权，响应信封 `{code, msg, data}`

## 功能模块

| 端 | 模块 |
| --- | --- |
| 求职者 | 首页推荐 / 职位搜索筛选 / 职位详情投递 / 收藏 / 简历管理 / 求职报告 / 笔试题库（练习·错题本）/ 在线沟通 / AI 求职助手（流式对话） |
| 企业 HR | 公司绑定 / 职位发布与管理 / 简历投递处理 / 候选人管理 / 面试邀约 |

## 目录结构

```
├── pages/         # 30 个页面（求职者端 + HR 端 + 公共）
├── components/    # 10 个公共组件（zn-* 前缀）
├── services/      # 前端接口封装层（页面不直接拼 URL）
├── common/        # 配置与工具函数
├── uni-ui/        # uni-ui 组件库（仅用到的部分）
├── server/        # FastAPI 后端
│   ├── app/       # 路由 / 模型 / 核心（LLM、RAG、邮件、安全）
│   ├── seed/      # 种子数据（recruit_*.json 招聘内容）
│   └── docs/      # RAG / 部署说明
└── docs/          # 项目文档（架构说明 / 部署手册）
```

## 快速开始

**后端**（需 Python 3.11+ 与 MySQL）：

```bash
cd server
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
# 配置 server/.env（参考 server/.env 所需变量：DB_PASSWORD / JWT_SECRET 等）
.venv/Scripts/python -m app.seed_recruit    # 灌入招聘种子数据
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

**前端**：用 HBuilderX 打开项目根目录，运行到 H5 / 小程序 / App。

演示账号（灌种子后可用）：求职者 `demo@zhipin.com` / `demo123456`；HR `hr@zhipin.com` / `demo123456`。

详细说明见 `docs/直聘通-架构说明.md` 与 `server/README.md`。
