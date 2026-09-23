# server/app/models · ORM 数据模型

SQLAlchemy ORM 模型（按域拆分）：

- `user.py`：用户 / 验证码
- `ai.py`：AI 会话 / 消息 / 图片附件
- `content.py`：分类 / 课程 / 页面配置
- `mine.py`：订单 / 优惠券 / 我的课程
- `study.py` / `study_user.py`：题库 / 错题本 / 记忆卡 / 答题记录
- `job.py` / `apply.py` / `interview_q.py` / `recruit_user.py`：招聘业务
