"""
数据库迁移：添加日历事件提醒字段

运行方式：
    cd backend
    python -m migrations.add_event_reminder
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run_migration():
    """运行迁移"""
    from config import get_settings
    settings = get_settings()

    # 创建数据库连接
    db_url = f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}?charset=utf8mb4"
    engine = create_async_engine(db_url, pool_pre_ping=True)

    async with engine.begin() as conn:
        # 检查列是否已存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'calendar_events' AND COLUMN_NAME = 'reminded_at'
        """), {"db": settings.mysql_database})
        existing = result.fetchone()

        if existing:
            print("Column 'reminded_at' already exists in calendar_events table")
        else:
            # 添加列
            await conn.execute(text("""
                ALTER TABLE calendar_events
                ADD COLUMN reminded_at DATETIME NULL COMMENT '已提醒时间，防止重复提醒'
            """))
            print("Added column 'reminded_at' to calendar_events table")

    await engine.dispose()
    print("Migration completed!")


if __name__ == "__main__":
    asyncio.run(run_migration())
