from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import get_settings, get_database_url

settings = get_settings()

# 使用动态生成的数据库URL（支持 DATA_DIR 环境变量）
database_url = get_database_url()
print(f"Database URL: {database_url}")

engine = create_async_engine(
    database_url,
    echo=settings.debug,
    future=True,
    # 连接池优化
    pool_size=10,          # 保持10个常驻连接
    max_overflow=20,       # 最多额外20个连接（峰值30）
    pool_pre_ping=True,    # 使用前检查连接有效性
    pool_recycle=1800,     # 30分钟回收连接（避免MySQL wait_timeout）
    pool_timeout=30,       # 获取连接超时时间（秒）
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    from .models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
