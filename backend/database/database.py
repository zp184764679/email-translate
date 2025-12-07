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
    pool_size=5,           # 保持5个连接
    max_overflow=10,       # 最多额外10个连接
    pool_pre_ping=True,    # 检查连接是否有效
    pool_recycle=3600,     # 1小时回收连接
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
