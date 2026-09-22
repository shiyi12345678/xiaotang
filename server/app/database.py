"""异步数据库访问：单例 async_engine + async_sessionmaker。

约定：
    - 连接方言为 mysql+aiomysql（URL 见 config.DB_URL）；
    - 查询：await db.execute(select(...))；
    - 写入：await db.commit()；
    - 每个请求通过 get_db 依赖获得独立会话，请求结束自动关闭，无需手工释放。
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DB_URL


class Base(DeclarativeBase):
    """ORM 模型基类（所有模型继承它，init_db 依据 metadata 建表）。"""


# pool_pre_ping=True：取连接前先探活，避免 MySQL 空闲断开后拿到失效连接而偶发报错
engine = create_async_engine(DB_URL, pool_pre_ping=True, echo=False)

# expire_on_commit=False：
#   默认值 True 会在 commit 后让对象属性过期，之后访问属性会触发额外查询；
#   接口里 commit 后仍需读取对象字段构造响应，设为 False 可避免。
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    """FastAPI 依赖：每个请求一个会话，请求结束自动关闭。

    用法：
        async def endpoint(db: AsyncSession = Depends(get_db)): ...
    """
    async with SessionLocal() as db:
        yield db
