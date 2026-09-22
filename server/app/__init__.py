"""服务端应用包（用户体系模块）。

目录结构：
    app/
    ├── main.py      应用入口（CORS、路由注册、全局异常处理）
    ├── config.py    全局配置（读取 .env）
    ├── database.py  异步数据库引擎与会话
    ├── init_db.py   建表脚本（DDL 单源）
    ├── core/        核心能力层（响应封装、鉴权、查询、短信）
    ├── models/      ORM 模型
    ├── schemas/     Pydantic 出入参
    └── routers/     路由层
"""
