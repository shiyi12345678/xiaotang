"""建表脚本（DDL 单源）。

用法（工作目录 = server/）：
    python -m app.init_db

说明：
    - 使用 Base.metadata.create_all，只创建「尚不存在」的表；
    - ⚠️ 它不会修改已有表的结构。后续给表加字段时，create_all 不会生效，
      需要手动执行 ALTER TABLE，或先删表再重建（会导致数据丢失）；
    - 数据库本身（sheji）需提前存在，创建方式见同目录 README 或建库记录。
"""
import asyncio

from app import models  # noqa: F401  确保模型注册进 Base.metadata
from app.config import DB_NAME
from app.database import Base, engine


async def init() -> None:
    """创建所有尚未存在的表，并打印结果。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    names = ", ".join(sorted(Base.metadata.tables))
    print(f"建表完成（库 {DB_NAME}）：{names}")
    # ⚠️ 显式释放连接池：
    #    否则解释器退出时，aiomysql 连接对象会在已关闭的事件循环上执行析构，
    #    抛出 "RuntimeError: Event loop is closed" 的无害告警，干扰使用者判断是否成功。
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init())
