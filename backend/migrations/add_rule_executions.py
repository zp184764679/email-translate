"""
迁移脚本：添加规则执行日志表

运行方式：
    cd backend
    python -m migrations.add_rule_executions
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加 rule_executions 表"""

    async with engine.begin() as conn:
        # 检查表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'rule_executions'
        """))
        exists = result.scalar() > 0

        if exists:
            print("表 rule_executions 已存在，跳过创建")
            return

        # 创建表
        await conn.execute(text("""
            CREATE TABLE rule_executions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                rule_id INT NOT NULL,
                email_id INT NOT NULL,
                account_id INT NOT NULL,

                -- 执行结果
                matched BOOLEAN DEFAULT TRUE COMMENT '是否匹配',
                actions_applied JSON COMMENT '执行的动作列表',
                actions_success BOOLEAN DEFAULT TRUE COMMENT '所有动作是否成功',
                error_message TEXT COMMENT '错误信息',

                -- 匹配详情（用于调试）
                matched_conditions JSON COMMENT '匹配的条件详情',

                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                -- 外键
                FOREIGN KEY (rule_id) REFERENCES email_rules(id) ON DELETE CASCADE,
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,

                -- 索引
                INDEX idx_rule_id (rule_id),
                INDEX idx_email_id (email_id),
                INDEX idx_account_id (account_id),
                INDEX idx_executed_at (executed_at),
                INDEX idx_actions_success (actions_success)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            COMMENT='规则执行日志表'
        """))

        print("✓ 表 rule_executions 创建成功")


if __name__ == "__main__":
    asyncio.run(migrate())
