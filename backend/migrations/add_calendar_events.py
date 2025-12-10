"""
日历事件和 AI 邮件提取功能数据库迁移脚本

添加以下表：
- calendar_events: 日历事件表
- email_extractions: AI 邮件信息提取表

运行方式：
cd backend
python -m migrations.add_calendar_events
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def run_migration():
    """执行数据库迁移"""
    async with engine.begin() as conn:
        # 1. 创建 calendar_events 表
        print("Creating calendar_events table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                account_id INT NOT NULL,
                email_id INT,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                location VARCHAR(200),
                start_time DATETIME NOT NULL,
                end_time DATETIME NOT NULL,
                all_day BOOLEAN DEFAULT FALSE,
                color VARCHAR(20) DEFAULT '#409EFF',
                reminder_minutes INT DEFAULT 15,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
                INDEX idx_calendar_account (account_id),
                INDEX idx_calendar_time (start_time, end_time),
                INDEX idx_calendar_email (email_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✓ calendar_events table created")

        # 2. 创建 email_extractions 表
        print("Creating email_extractions table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_extractions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email_id INT NOT NULL UNIQUE,
                summary TEXT,
                dates JSON,
                amounts JSON,
                contacts JSON,
                action_items JSON,
                key_points JSON,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
                INDEX idx_extraction_email (email_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✓ email_extractions table created")

    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
