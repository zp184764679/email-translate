"""
数据库迁移脚本：为 drafts 表添加收件人相关字段

运行方式：
cd backend
python -m migrations.add_draft_recipient_fields
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加 to_address, cc_address, subject 字段到 drafts 表"""
    async with engine.begin() as conn:
        # 检查列是否存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'drafts' AND COLUMN_NAME = 'to_address'
        """))

        if result.fetchone():
            print("字段已存在，跳过迁移")
            return

        print("开始迁移: 添加 drafts 表的收件人字段...")

        # 添加 to_address 字段
        await conn.execute(text("""
            ALTER TABLE drafts
            ADD COLUMN to_address VARCHAR(500) NULL AFTER author_id
        """))
        print("  - 已添加 to_address 字段")

        # 添加 cc_address 字段
        await conn.execute(text("""
            ALTER TABLE drafts
            ADD COLUMN cc_address VARCHAR(500) NULL AFTER to_address
        """))
        print("  - 已添加 cc_address 字段")

        # 添加 subject 字段
        await conn.execute(text("""
            ALTER TABLE drafts
            ADD COLUMN subject VARCHAR(500) NULL AFTER cc_address
        """))
        print("  - 已添加 subject 字段")

        print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
