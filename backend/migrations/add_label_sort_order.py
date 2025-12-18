"""
迁移脚本：为 email_labels 表添加 sort_order 字段

运行方式：
    python -m migrations.add_label_sort_order
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加 sort_order 字段到 email_labels 表"""
    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'email_labels'
            AND COLUMN_NAME = 'sort_order'
        """))

        if result.fetchone():
            print("[Migration] sort_order 字段已存在，跳过")
            return

        # 添加 sort_order 字段
        print("[Migration] 添加 sort_order 字段...")
        await conn.execute(text("""
            ALTER TABLE email_labels
            ADD COLUMN sort_order INT DEFAULT 0
        """))

        # 添加索引
        print("[Migration] 添加索引...")
        await conn.execute(text("""
            CREATE INDEX ix_email_labels_sort_order
            ON email_labels (sort_order)
        """))

        # 初始化现有标签的 sort_order（按创建时间排序）
        print("[Migration] 初始化现有标签的排序...")
        await conn.execute(text("""
            UPDATE email_labels el
            JOIN (
                SELECT id,
                       @row_num := IF(@prev_account = account_id, @row_num + 1, 1) AS sort_order,
                       @prev_account := account_id
                FROM email_labels, (SELECT @row_num := 0, @prev_account := NULL) vars
                ORDER BY account_id, created_at
            ) sorted ON el.id = sorted.id
            SET el.sort_order = sorted.sort_order
        """))

        print("[Migration] email_labels.sort_order 迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
