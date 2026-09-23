# server/app/core · 后端核心能力

- `response.py`：统一响应信封 `{code, msg, data}` 与业务异常
- `security.py`：bcrypt + JWT + 鉴权依赖
- `query.py`：用户查询封装（统一软删过滤）
- `llm.py`：DeepSeek 流式对话
- `embedding.py`：向量化唯一出口（云端 API / 本地模型二选一）
- `milvus_store.py`：Milvus 向量库读写
- `rag.py`：RAG 检索与上下文组装（失败自动降级）
- `graph_extract.py` / `graph_store.py` / `graph_rag.py`：GraphRAG 知识图谱
- `mail.py` / `sms.py`：邮箱验证码 / 短信（预留）
