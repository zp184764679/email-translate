"""
数据库迁移：添加日历事件重复字段

运行方式：
    cd backend
    python -m migrations.add_recurrence_fields
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

    columns_to_add = [
        ("reminded_at", "DATETIME NULL COMMENT '已提醒时间，防止重复提醒'"),
        ("recurrence_rule", "VARCHAR(255) NULL COMMENT 'RRULE 重复规则'"),
        ("recurrence_end", "DATETIME NULL COMMENT '重复结束日期'"),
        ("parent_event_id", "INT NULL COMMENT '父事件ID（重复实例）'"),
    ]

    async with engine.begin() as conn:
        for column_name, column_def in columns_to_add:
            # 检查列是否已存在
            result = await conn.execute(text("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'calendar_events' AND COLUMN_NAME = :col
            """), {"db": settings.mysql_database, "col": column_name})
            existing = result.fetchone()

            if existing:
                print(f"Column '{column_name}' already exists in calendar_events table")
            else:
                # 添加列
                await conn.execute(text(f"""
                    ALTER TABLE calendar_events
                    ADD COLUMN {column_name} {column_def}
                """))
                print(f"Added column '{column_name}' to calendar_events table")

        # 添加外键约束（如果不存在）
        try:
            result = await conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = :db
                AND TABLE_NAME = 'calendar_events'
                AND COLUMN_NAME = 'parent_event_id'
                AND REFERENCED_TABLE_NAME = 'calendar_events'
            """), {"db": settings.mysql_database})
            existing_fk = result.fetchone()

            if not existing_fk:
                await conn.execute(text("""
                    ALTER TABLE calendar_events
                    ADD CONSTRAINT fk_calendar_parent_event
                    FOREIGN KEY (parent_event_id) REFERENCES calendar_events(id)
                    ON DELETE SET NULL
                """))
                print("Added foreign key constraint for parent_event_id")
            else:
                print("Foreign key constraint already exists")
        except Exception as e:
            print(f"Foreign key constraint: {e}")

    await engine.dispose()
    print("Migration completed!")


if __name__ == "__main__":
    asyncio.run(run_migration())
