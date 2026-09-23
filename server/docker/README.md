# server/docker · 可选中间件编排

- `milvus-compose.yml`：Milvus 向量数据库（RAG 知识库用）
- `neo4j-compose.yml`：Neo4j 图数据库（GraphRAG 用）

均为可选项：不启动时相关功能自动降级，不影响主流程。
