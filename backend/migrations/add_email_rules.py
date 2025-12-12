"""
数据库迁移脚本：添加邮件规则表

使用方法：
cd backend
python -m migrations.add_email_rules
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加邮件规则表...")

    async with engine.begin() as conn:
        # 检查 email_rules 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'email_rules'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 email_rules 表
            await conn.execute(text("""
                CREATE TABLE email_rules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    priority INT DEFAULT 0,
                    stop_processing BOOLEAN DEFAULT FALSE,
                    conditions JSON NOT NULL,
                    actions JSON NOT NULL,
                    match_count INT DEFAULT 0,
                    last_match_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_rules_account (account_id),
                    INDEX idx_rules_active (is_active),
                    INDEX idx_rules_priority (priority)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            print("✓ 已创建 email_rules 表")
        else:
            print("- email_rules 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
