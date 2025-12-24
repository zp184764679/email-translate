"""
数据库迁移脚本：添加通知表

使用方法：
cd backend
python -m migrations.add_notifications
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加通知表...")

    async with engine.begin() as conn:
        # 检查 notifications 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'notifications'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 notifications 表
            await conn.execute(text("""
                CREATE TABLE notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT,
                    related_id INT,
                    related_type VARCHAR(50),
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read_at TIMESTAMP NULL,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_notifications_account (account_id),
                    INDEX idx_notifications_type (type),
                    INDEX idx_notifications_is_read (is_read),
                    INDEX idx_notifications_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            print("✓ 已创建 notifications 表")
        else:
            print("- notifications 表已存在，跳过")

    print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
