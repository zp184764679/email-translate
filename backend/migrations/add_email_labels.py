"""
数据库迁移脚本：添加邮件标签相关表

使用方法：
cd backend
python -m migrations.add_email_labels
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加邮件标签表...")

    async with engine.begin() as conn:
        # 检查 email_labels 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'email_labels'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 email_labels 表
            await conn.execute(text("""
                CREATE TABLE email_labels (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL,
                    name VARCHAR(50) NOT NULL,
                    color VARCHAR(20) DEFAULT '#409EFF',
                    description VARCHAR(200),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_labels_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            print("✓ 已创建 email_labels 表")
        else:
            print("- email_labels 表已存在，跳过")

        # 检查 email_label_mappings 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'email_label_mappings'
        """))
        mapping_exists = result.scalar() > 0

        if not mapping_exists:
            # 创建 email_label_mappings 关联表
            await conn.execute(text("""
                CREATE TABLE email_label_mappings (
                    email_id INT NOT NULL,
                    label_id INT NOT NULL,
                    PRIMARY KEY (email_id, label_id),
                    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
                    FOREIGN KEY (label_id) REFERENCES email_labels(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            print("✓ 已创建 email_label_mappings 表")
        else:
            print("- email_label_mappings 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
