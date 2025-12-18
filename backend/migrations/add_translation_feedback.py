"""
迁移脚本：添加翻译质量反馈表

运行方式：
    cd backend
    python -m migrations.add_translation_feedback
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加 translation_feedbacks 表"""

    async with engine.begin() as conn:
        # 检查表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'translation_feedbacks'
        """))
        exists = result.scalar() > 0

        if exists:
            print("表 translation_feedbacks 已存在，跳过创建")
            return

        # 创建表
        await conn.execute(text("""
            CREATE TABLE translation_feedbacks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                account_id INT NOT NULL,
                email_id INT NULL,

                -- 反馈内容
                feedback_type VARCHAR(50) NOT NULL COMMENT 'inaccurate, missing, wrong_term, other',
                original_text TEXT COMMENT '原文片段',
                translated_text TEXT COMMENT '翻译结果',
                suggested_text TEXT COMMENT '用户建议的翻译',
                comment TEXT COMMENT '用户说明',

                -- 翻译上下文
                provider VARCHAR(20) COMMENT '使用的翻译引擎',
                source_lang VARCHAR(10),
                target_lang VARCHAR(10),

                -- 状态
                status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending, reviewed, applied, dismissed',
                reviewed_by INT NULL,
                reviewed_at DATETIME NULL,
                review_comment TEXT COMMENT '审核意见',

                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                -- 外键
                FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL,
                FOREIGN KEY (reviewed_by) REFERENCES email_accounts(id) ON DELETE SET NULL,

                -- 索引
                INDEX idx_account_id (account_id),
                INDEX idx_status (status),
                INDEX idx_feedback_type (feedback_type),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            COMMENT='翻译质量反馈表'
        """))

        print("✓ 表 translation_feedbacks 创建成功")


if __name__ == "__main__":
    asyncio.run(migrate())
