"""
添加定时发送功能字段

为 drafts 表添加:
- scheduled_at: 预定发送时间
- scheduled_status: 定时状态 (pending/sent/cancelled/failed)
"""

import asyncio
import sys
sys.path.insert(0, '.')

from database.database import engine
from sqlalchemy import text


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        # 检查 scheduled_at 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'drafts'
            AND column_name = 'scheduled_at'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 scheduled_at 字段...")
            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN scheduled_at DATETIME NULL COMMENT '预定发送时间'
            """))
            print("✓ scheduled_at 字段已添加")
        else:
            print("• scheduled_at 字段已存在，跳过")

        # 检查 scheduled_status 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'drafts'
            AND column_name = 'scheduled_status'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 scheduled_status 字段...")
            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN scheduled_status ENUM('pending', 'sent', 'cancelled', 'failed')
                NULL COMMENT '定时发送状态'
            """))
            print("✓ scheduled_status 字段已添加")
        else:
            print("• scheduled_status 字段已存在，跳过")

        # 添加索引以便快速查询待发送的定时邮件
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'drafts'
            AND index_name = 'idx_scheduled_pending'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加定时发送索引...")
            await conn.execute(text("""
                CREATE INDEX idx_scheduled_pending
                ON drafts (scheduled_status, scheduled_at)
            """))
            print("✓ 索引已创建")
        else:
            print("• 索引已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
