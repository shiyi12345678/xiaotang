"""招聘端种子数据灌入脚本。

用途：把 server/seed/recruit_jobs.json（公司/城市/职能/职位）
      与 server/seed/recruit_content.json（面试题库/页面配置）导入数据库。

运行（工作目录 = server/）：
    python -m app.seed_recruit            # 只刷内容数据，保留用户产生的投递/收藏/会话
    python -m app.seed_recruit --full     # 连用户数据一起清空（回到全新演示态）

⚠️ 幂等性：先清空后写入，可反复执行。
⚠️ 与旧 seed.py 的边界（本次改造的核心约定）：
    - 本脚本只操作「招聘端新表」，学习端旧表（course / order_info / question …）
      一律不碰，旧数据完整保留，随时可回滚；
    - page_config 是两端共用的表，因此**只覆盖 rc_ 前缀的键**，
      旧键（banners / mineGridGroups / aiWelcome …）原样保留。
⚠️ 仅限开发 / 演示环境使用，请勿在生产库执行。
"""
import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select

from app.config import DB_NAME
from app.database import SessionLocal, engine
from app.models import (
    Application,
    City,
    Company,
    Conversation,
    Interview,
    InterviewQuestion,
    Job,
    JobCategory,
    JobFavorite,
    Message,
    PageConfig,
    QuestionRecord,
    Resume,
    User,
    UserRole,
)

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
JOBS_FILE = SEED_DIR / "recruit_jobs.json"
CONTENT_FILE = SEED_DIR / "recruit_content.json"

# 内容数据：每次灌库都重建
CLEAR_CONTENT = (Company, City, JobCategory, Job, InterviewQuestion)

# 用户产生的数据：默认保留，只有 --full 才清空
CLEAR_USER_DATA = (
    JobFavorite,
    Application,
    Interview,
    Conversation,
    Message,
    Resume,
    UserRole,
    QuestionRecord,
)

# page_config 只允许覆盖招聘端命名空间的键（rc 前缀），旧学习端的键必须留着。
# ⚠️ 前缀是 "rc"（不是 "rc_"）：招聘端的键名形如 rcHeroBanners / rcFilterOptions，
#    改造前学习端的键（banners / rankings / mineGridGroups …）没有任何一个以 "rc" 开头，
#    因此这个命名空间是安全的，不会误伤。
PAGE_CONFIG_PREFIX = "rc"


def load_json(path: Path, required: bool = True) -> dict:
    """读取种子 JSON。

    required=True  文件缺失直接报错（职位数据是招聘端的地基，缺了不该继续）
    required=False 文件缺失只告警并返回空字典 —— 便于分两批准备数据时先灌一半，
                   且末尾的汇总会明确显示「面试题 0」，不会静默装作成功。
    """
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"未找到种子数据：{path}\n请确认 server/seed/ 下的招聘种子文件是否齐全。"
            )
        print(f"  [警告] 缺少种子文件 {path.name}，本次跳过该部分数据")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build(model, item: dict):
    """按模型真实列裁剪字段后构造 ORM 对象。

    ⚠️ 为什么要裁剪：种子 JSON 是人工/脚本产出的，可能带有模型上没有的辅助键。
       直接 Company(**item) 会抛 TypeError 让整个灌库中断，
       这里静默丢弃未知键，只保留表里真实存在的列。
    """
    columns = {c.name for c in model.__table__.columns}
    unknown = set(item) - columns
    if unknown:
        print(f"  [提示] {model.__tablename__} 忽略未知字段：{sorted(unknown)}")
    return model(**{k: v for k, v in item.items() if k in columns})


async def _ensure_demo_accounts(session, companies: list) -> list:
    """确保存在两个演示账号：求职者与已绑定公司的企业 HR。

    为什么要有演示账号：
        1. 登录页可以给「一键体验」入口，面试官/自己不用先走注册收验证码；
        2. 企业端必须先绑定公司才有数据可看，演示账号直接绑好，省去手动操作；
        3. 带鉴权的接口（投递、收藏、简历、HR 全部接口）需要真实 token 才能自测。

    ⚠️ 幂等：按邮箱查询，已存在就复用且**不重置密码**，
       否则你手动改过的密码会被下一次灌库悄悄覆盖。
    ⚠️ 仅供演示环境：生产部署前必须删除本函数或加环境开关。

    返回：[{"email", "role", "label", "companyId"}]，供调用方打印。
    """
    from app.core.security import hash_password

    account_password = "demo123456"
    plan = (
        ("demo@zhipin.com", "演示求职者", "candidate", None),
        ("hr@zhipin.com", "演示招聘官", "hr", companies[0]["id"] if companies else None),
    )

    info = []
    for email, nickname, role_name, company_id in plan:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password=hash_password(account_password),
                nickname=nickname,
                signature="",
                level="求职者" if role_name == "candidate" else "招聘方",
            )
            session.add(user)
            await session.flush()
            print(f"  [新建] 演示账号 {email}")

        existing = (
            await session.execute(
                select(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role == role_name
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(UserRole(
                user_id=user.id,
                role=role_name,
                company_id=company_id,
                hr_title="招聘经理" if role_name == "hr" else "",
                is_default=1,
            ))
        elif company_id:
            # 公司可能被换过，以种子里的第一家为准
            existing.company_id = company_id

        info.append({
            "email": email,
            "password": account_password,
            "role": role_name,
            "label": nickname,
            "companyId": company_id,
        })

    await session.flush()

    # 把 HR 演示账号绑定公司名下「无人认领」的职位接管过来，
    # 否则求职者点「立即沟通」找不到聊天对象（job.hr_id 为空）
    if companies:
        company_id = companies[0]["id"]
        hr_user = (
            await session.execute(select(User).where(User.email == "hr@zhipin.com"))
        ).scalar_one()
        unowned = (
            await session.execute(
                select(Job).where(
                    Job.company_id == company_id, Job.hr_id.is_(None), Job.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        for job in unowned:
            job.hr_id = hr_user.id
            job.hr_title = job.hr_title or "招聘经理"
            job.hr_name = job.hr_name or hr_user.nickname
        if unowned:
            print(f"  [接管] {len(unowned)} 个职位已归到 {hr_user.nickname} 名下")

    return info


async def seed(full: bool) -> None:
    jobs_data = load_json(JOBS_FILE, required=True)
    content_data = load_json(CONTENT_FILE, required=False)

    companies = jobs_data.get("companies", [])
    cities = jobs_data.get("cities", [])
    categories = jobs_data.get("jobCategories", [])
    jobs = jobs_data.get("jobs", [])
    questions = content_data.get("interviewQuestions", [])
    page_config = content_data.get("pageConfig", {})

    async with SessionLocal() as session:
        # ---------- 1. 清空 ----------
        for model in CLEAR_CONTENT:
            await session.execute(delete(model))
        if full:
            for model in CLEAR_USER_DATA:
                await session.execute(delete(model))
            print("已清空用户数据（投递/收藏/会话/简历等）")
        await session.flush()

        # ---------- 2. 公司 ----------
        for item in companies:
            session.add(build(Company, item))

        # ---------- 3. 城市 ----------
        for item in cities:
            session.add(build(City, item))

        # ---------- 4. 职能分类 ----------
        for item in categories:
            session.add(build(JobCategory, item))

        # ---------- 5. 职位 ----------
        # publish_at 由脚本生成（种子 JSON 里不写时间），让「发布时间」看起来自然
        now = datetime.now()
        for idx, item in enumerate(jobs):
            job = build(Job, item)
            if job.publish_at is None:
                job.publish_at = now - timedelta(days=idx % 15, hours=idx % 24)
            session.add(job)

        # ---------- 6. 面试题 ----------
        for item in questions:
            session.add(build(InterviewQuestion, item))

        await session.flush()

        # ---------- 7. 一致性校验（灌库时就把问题暴露出来，别留到页面） ----------
        company_ids = {c["id"] for c in companies}
        category_ids = {c["id"] for c in categories}
        level2_ids = {c["id"] for c in categories if c.get("level") == 2}
        city_map = {c["id"]: c["name"] for c in cities}

        problems = []
        for item in jobs:
            if item.get("company_id") not in company_ids:
                problems.append(f"职位 {item.get('id')} 的公司 {item.get('company_id')} 不存在")
            if item.get("category_id") not in category_ids:
                problems.append(f"职位 {item.get('id')} 的职能 {item.get('category_id')} 不存在")
            elif item.get("category_id") not in level2_ids:
                problems.append(f"职位 {item.get('id')} 的职能 {item.get('category_id')} 不是二级分类")
            if item.get("city_id") not in city_map:
                problems.append(f"职位 {item.get('id')} 的城市 {item.get('city_id')} 不存在")
            elif city_map.get(item.get("city_id")) != item.get("city_name"):
                problems.append(
                    f"职位 {item.get('id')} 的 city_name「{item.get('city_name')}」"
                    f"与城市表「{city_map.get(item.get('city_id'))}」不一致"
                )
        if problems:
            print(f"\n⚠️ 发现 {len(problems)} 处数据不一致：")
            for line in problems[:20]:
                print("   -", line)

        # ---------- 8. 回填公司的在招职位数（以实际职位数为准，不信任种子里的 job_count） ----------
        counts: dict = {}
        for item in jobs:
            cid = item.get("company_id")
            if item.get("status", 1) == 1:
                counts[cid] = counts.get(cid, 0) + 1
        for company in companies:
            row = await session.get(Company, company["id"])
            if row is not None:
                row.job_count = counts.get(company["id"], 0)

        # ---------- 9. 演示账号（求职者 / 企业HR） ----------
        demo_info = await _ensure_demo_accounts(session, companies)

        # ---------- 10. 页面配置（只覆盖 rc 前缀，旧键保留） ----------
        skipped = []
        for key, value in page_config.items():
            if not key.startswith(PAGE_CONFIG_PREFIX):
                skipped.append(key)
                continue
            row = await session.get(PageConfig, key)
            if row is None:
                session.add(PageConfig(key=key, value=value))
            else:
                row.value = value
        if skipped:
            print(f"  [提示] page_config 跳过非 {PAGE_CONFIG_PREFIX} 前缀的键：{skipped}")

        await session.commit()

        # ---------- 10. 汇总 ----------
        async def count(model) -> int:
            return (await session.execute(select(func.count()).select_from(model))).scalar() or 0

        print("\n灌库完成（库 %s）：" % DB_NAME)
        for model, label in (
            (Company, "公司"),
            (City, "城市"),
            (JobCategory, "职能分类"),
            (Job, "职位"),
            (InterviewQuestion, "面试题"),
        ):
            print(f"  {label:<6} {await count(model)}")
        rc_keys = (
            await session.execute(
                select(func.count()).select_from(PageConfig).where(PageConfig.key.like("rc%"))
            )
        ).scalar()
        print(f"  招聘端页面配置键 {rc_keys} 个（旧键未受影响）")

        if demo_info:
            print("\n演示账号（可直接登录）：")
            for item in demo_info:
                role_text = "求职者" if item["role"] == "candidate" else "企业HR"
                suffix = f" / 绑定公司 {item['companyId']}" if item["companyId"] else ""
                print(f"  {role_text:<6} {item['email']} / {item['password']}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="灌入招聘端种子数据")
    parser.add_argument(
        "--full",
        action="store_true",
        help="连用户产生的数据（投递/收藏/会话/简历/角色）一起清空，回到全新演示态",
    )
    args = parser.parse_args()

    async def run() -> None:
        try:
            await seed(args.full)
        finally:
            # ⚠️ 显式释放连接池，避免解释器退出时在已关闭的事件循环上析构连接
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
