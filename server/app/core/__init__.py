"""核心能力层：跨模块复用的基础能力。

- response.py  统一响应封装（ok）与业务异常（BizError）
- security.py  bcrypt 密码哈希 + JWT 签发/校验 + 鉴权依赖
- query.py     用户查询封装（统一带逻辑删除过滤）
- sms.py       短信发送抽象（演示期空操作）
- mail.py      邮箱验证码（SMTP）
- llm.py       大模型接入（DeepSeek，流式）
- embedding.py 向量化（本地模型 / 云端 API 双模式）+ 精排
- milvus_store.py  Milvus 封装：向量检索（RAG 的存储层）
- rag.py       检索编排：向量混合检索 + 提示词拼装（RAG 的编排层）
- graph_store.py   Neo4j 封装：实体链接、子图扩展（GraphRAG 的存储层）
- graph_rag.py     图谱检索编排：实体链接 → 多跳扩展 → 事实文本化
- graph_extract.py 实体关系抽取：结构化数据走规则、文本走大模型
"""
