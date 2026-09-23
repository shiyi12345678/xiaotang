# server/app/routers · API 路由

按业务域划分：

- `user.py`：用户体系（注册 / 登录 / 资料 / 改密 / 注销）
- `ai.py` / `ai_upload.py`：AI 求职助手（会话、WS 流式对话、图片上传、RAG/图谱诊断）
- `chat.py` / `im.py`：在线沟通
- `job.py` / `apply.py` / `interview.py` / `hr.py`：招聘业务（职位、投递、面试、HR 端）
- `content.py` / `mine.py` / `study.py`：内容 / 我的 / 学习域
