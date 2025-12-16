"""
数据库迁移脚本：添加发送邮件映射表

新建 sent_email_mappings 表：
- 保存发送邮件的 Message-ID 与原文的关联
- 用于在收到回复时还原用户发送的原文

为 drafts 表添加：
- sent_message_id: 发送后的 Message-ID

运行方式：
cd backend
python -m migrations.add_sent_email_mapping
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加发送邮件映射表和相关字段"""
    async with engine.begin() as conn:
        # 1. 检查 sent_email_mappings 表是否存在
        result = await conn.execute(text("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sent_email_mappings'
        """))

        if result.fetchone():
            print("sent_email_mappings 表已存在，跳过")
        else:
            print("开始迁移: 创建 sent_email_mappings 表...")

            await conn.execute(text("""
                CREATE TABLE sent_email_mappings (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    message_id VARCHAR(255) NOT NULL UNIQUE,
                    draft_id INT NULL,
                    account_id INT NOT NULL,
                    subject_original TEXT,
                    subject_sent TEXT,
                    body_original MEDIUMTEXT,
                    body_sent MEDIUMTEXT,
                    was_translated BOOLEAN DEFAULT FALSE,
                    to_email VARCHAR(500),
                    sent_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                    INDEX idx_message_id (message_id),
                    INDEX idx_account_id (account_id),
                    CONSTRAINT fk_sent_mapping_draft
                        FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE SET NULL,
                    CONSTRAINT fk_sent_mapping_account
                        FOREIGN KEY (account_id) REFERENCES email_accounts(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            print("  - 已创建 sent_email_mappings 表")

        # 2. 检查 drafts.sent_message_id 是否存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'drafts' AND COLUMN_NAME = 'sent_message_id'
        """))

        if result.fetchone():
            print("drafts.sent_message_id 已存在，跳过")
        else:
            print("开始迁移: 添加 drafts.sent_message_id 字段...")

            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN sent_message_id VARCHAR(255) NULL,
                ADD INDEX idx_sent_message_id (sent_message_id)
            """))
            print("  - 已添加 sent_message_id 字段")

        print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
