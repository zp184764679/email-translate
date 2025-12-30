"""
添加 AI 邮件分类字段

为 emails 表添加:
- ai_category: AI分类结果
- ai_category_confidence: 分类置信度
- ai_categorized_at: 分类时间
"""

import asyncio
import sys
sys.path.insert(0, '.')

from database.database import engine
from sqlalchemy import text


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        # 1. 检查 ai_category 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND column_name = 'ai_category'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 ai_category 字段...")
            await conn.execute(text("""
                ALTER TABLE emails
                ADD COLUMN ai_category VARCHAR(50) NULL COMMENT 'AI分类结果'
            """))
            print("✓ ai_category 字段已添加")
        else:
            print("• ai_category 字段已存在，跳过")

        # 2. 检查 ai_category_confidence 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND column_name = 'ai_category_confidence'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 ai_category_confidence 字段...")
            await conn.execute(text("""
                ALTER TABLE emails
                ADD COLUMN ai_category_confidence FLOAT NULL COMMENT 'AI分类置信度'
            """))
            print("✓ ai_category_confidence 字段已添加")
        else:
            print("• ai_category_confidence 字段已存在，跳过")

        # 3. 检查 ai_categorized_at 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND column_name = 'ai_categorized_at'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 ai_categorized_at 字段...")
            await conn.execute(text("""
                ALTER TABLE emails
                ADD COLUMN ai_categorized_at DATETIME NULL COMMENT 'AI分类时间'
            """))
            print("✓ ai_categorized_at 字段已添加")
        else:
            print("• ai_categorized_at 字段已存在，跳过")

        # 4. 添加分类索引
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND index_name = 'idx_ai_category'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加分类索引...")
            await conn.execute(text("""
                CREATE INDEX idx_ai_category ON emails (ai_category, account_id)
            """))
            print("✓ 索引已创建")
        else:
            print("• 索引已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
