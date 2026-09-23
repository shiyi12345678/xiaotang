# server/app · 后端应用主体

FastAPI 应用主体：

- `main.py`：应用入口（CORS、路由注册、异常处理器、静态目录）
- `config.py`：配置读取（.env → 环境变量）
- `database.py`：异步数据库引擎与会话
- `init_db.py`：建表脚本（DDL 单源）
- `core/`：核心能力（响应信封、鉴权、AI、RAG、GraphRAG、邮件/短信）
- `models/`：SQLAlchemy ORM 模型
- `schemas/`：Pydantic 出入参 + ORM→前端字段映射
- `routers/`：API 路由
