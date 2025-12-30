"""
数据库迁移脚本：添加供应商标签表

使用方法：
cd backend
python -m migrations.add_supplier_tags
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加供应商标签表...")

    async with engine.begin() as conn:
        # 检查 supplier_tags 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'supplier_tags'
        """))
        tags_exists = result.scalar() > 0

        if not tags_exists:
            # 创建 supplier_tags 表
            await conn.execute(text("""
                CREATE TABLE supplier_tags (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL COMMENT '创建者账户',
                    name VARCHAR(50) NOT NULL COMMENT '标签名称',
                    color VARCHAR(20) DEFAULT '#409EFF' COMMENT '标签颜色',
                    description VARCHAR(255) DEFAULT NULL COMMENT '标签描述',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_supplier_tags_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='供应商标签表 - 用于标记和筛选供应商'
            """))
            print("✓ 已创建 supplier_tags 表")

            # 插入预设标签（为所有现有账户创建）
            await conn.execute(text("""
                INSERT INTO supplier_tags (account_id, name, color, description)
                SELECT id, '优质供应商', '#67C23A', '优质可靠的供应商'
                FROM email_accounts
            """))
            await conn.execute(text("""
                INSERT INTO supplier_tags (account_id, name, color, description)
                SELECT id, '新供应商', '#409EFF', '新建立合作的供应商'
                FROM email_accounts
            """))
            await conn.execute(text("""
                INSERT INTO supplier_tags (account_id, name, color, description)
                SELECT id, '需关注', '#E6A23C', '需要特别关注的供应商'
                FROM email_accounts
            """))
            await conn.execute(text("""
                INSERT INTO supplier_tags (account_id, name, color, description)
                SELECT id, '风险供应商', '#F56C6C', '存在风险的供应商'
                FROM email_accounts
            """))
            print("✓ 已创建预设标签")
        else:
            print("- supplier_tags 表已存在，跳过")

        # 检查 supplier_tag_mappings 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'supplier_tag_mappings'
        """))
        mappings_exists = result.scalar() > 0

        if not mappings_exists:
            # 创建 supplier_tag_mappings 关联表
            await conn.execute(text("""
                CREATE TABLE supplier_tag_mappings (
                    supplier_id INT NOT NULL,
                    tag_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (supplier_id, tag_id),
                    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES supplier_tags(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='供应商-标签关联表'
            """))
            print("✓ 已创建 supplier_tag_mappings 表")
        else:
            print("- supplier_tag_mappings 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
