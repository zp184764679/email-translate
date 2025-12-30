"""
数据库迁移脚本：添加供应商 AI 分类字段

使用方法：
cd backend
python -m migrations.add_supplier_category
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加供应商 AI 分类字段...")

    async with engine.begin() as conn:
        # 检查 category 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND column_name = 'category'
        """))
        category_exists = result.scalar() > 0

        if not category_exists:
            # 添加 category 字段
            await conn.execute(text("""
                ALTER TABLE suppliers
                ADD COLUMN category VARCHAR(50) DEFAULT NULL COMMENT 'AI分析的类别'
            """))
            print("✓ 已添加 category 字段")
        else:
            print("- category 字段已存在，跳过")

        # 检查 category_confidence 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND column_name = 'category_confidence'
        """))
        confidence_exists = result.scalar() > 0

        if not confidence_exists:
            # 添加 category_confidence 字段
            await conn.execute(text("""
                ALTER TABLE suppliers
                ADD COLUMN category_confidence FLOAT DEFAULT NULL COMMENT 'AI分类置信度(0-1)'
            """))
            print("✓ 已添加 category_confidence 字段")
        else:
            print("- category_confidence 字段已存在，跳过")

        # 检查 category_reason 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND column_name = 'category_reason'
        """))
        reason_exists = result.scalar() > 0

        if not reason_exists:
            # 添加 category_reason 字段
            await conn.execute(text("""
                ALTER TABLE suppliers
                ADD COLUMN category_reason TEXT DEFAULT NULL COMMENT 'AI分类依据说明'
            """))
            print("✓ 已添加 category_reason 字段")
        else:
            print("- category_reason 字段已存在，跳过")

        # 检查 category_analyzed_at 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND column_name = 'category_analyzed_at'
        """))
        analyzed_at_exists = result.scalar() > 0

        if not analyzed_at_exists:
            # 添加 category_analyzed_at 字段
            await conn.execute(text("""
                ALTER TABLE suppliers
                ADD COLUMN category_analyzed_at DATETIME DEFAULT NULL COMMENT 'AI分析时间'
            """))
            print("✓ 已添加 category_analyzed_at 字段")
        else:
            print("- category_analyzed_at 字段已存在，跳过")

        # 检查 category_manual 字段是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND column_name = 'category_manual'
        """))
        manual_exists = result.scalar() > 0

        if not manual_exists:
            # 添加 category_manual 字段
            await conn.execute(text("""
                ALTER TABLE suppliers
                ADD COLUMN category_manual BOOLEAN DEFAULT FALSE COMMENT '是否人工修改分类'
            """))
            print("✓ 已添加 category_manual 字段")
        else:
            print("- category_manual 字段已存在，跳过")

        # 添加分类索引
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'suppliers'
            AND index_name = 'idx_suppliers_category'
        """))
        index_exists = result.scalar() > 0

        if not index_exists:
            await conn.execute(text("""
                CREATE INDEX idx_suppliers_category ON suppliers(category)
            """))
            print("✓ 已创建 category 索引")
        else:
            print("- category 索引已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
