"""
迁移脚本：为 email_signatures 表添加 category 和 sort_order 字段

运行方式：
    python -m migrations.add_signature_fields
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加 category 和 sort_order 字段到 email_signatures 表"""
    async with engine.begin() as conn:
        # 检查 category 字段是否已存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'email_signatures'
            AND COLUMN_NAME = 'category'
        """))

        if not result.fetchone():
            print("[Migration] 添加 category 字段...")
            await conn.execute(text("""
                ALTER TABLE email_signatures
                ADD COLUMN category VARCHAR(50) DEFAULT 'default'
            """))
        else:
            print("[Migration] category 字段已存在，跳过")

        # 检查 sort_order 字段是否已存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'email_signatures'
            AND COLUMN_NAME = 'sort_order'
        """))

        if not result.fetchone():
            print("[Migration] 添加 sort_order 字段...")
            await conn.execute(text("""
                ALTER TABLE email_signatures
                ADD COLUMN sort_order INT DEFAULT 0
            """))

            # 初始化现有签名的 sort_order（按创建时间排序）
            print("[Migration] 初始化现有签名的排序...")
            await conn.execute(text("""
                UPDATE email_signatures es
                JOIN (
                    SELECT id,
                           @row_num := IF(@prev_account = account_id, @row_num + 1, 1) AS sort_order,
                           @prev_account := account_id
                    FROM email_signatures, (SELECT @row_num := 0, @prev_account := NULL) vars
                    ORDER BY account_id, created_at
                ) sorted ON es.id = sorted.id
                SET es.sort_order = sorted.sort_order
            """))
        else:
            print("[Migration] sort_order 字段已存在，跳过")

        print("[Migration] email_signatures 迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
