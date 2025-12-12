"""
数据库迁移脚本：添加审批相关字段

为 drafts 表添加：
- approver_id: 审批人 ID
- submitted_at: 提交审批时间
- reject_reason: 驳回原因

为 email_accounts 表添加：
- default_approver_id: 默认审批人 ID

运行方式：
cd backend
python -m migrations.add_approval_fields
"""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine


async def migrate():
    """添加审批相关字段"""
    async with engine.begin() as conn:
        # 检查 drafts.approver_id 是否存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'drafts' AND COLUMN_NAME = 'approver_id'
        """))

        if result.fetchone():
            print("drafts.approver_id 已存在，跳过")
        else:
            print("开始迁移: 添加 drafts 表的审批字段...")

            # 添加 approver_id 字段
            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN approver_id INT NULL,
                ADD CONSTRAINT fk_drafts_approver
                    FOREIGN KEY (approver_id) REFERENCES email_accounts(id)
            """))
            print("  - 已添加 approver_id 字段")

            # 添加 submitted_at 字段
            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN submitted_at DATETIME NULL
            """))
            print("  - 已添加 submitted_at 字段")

            # 添加 reject_reason 字段
            await conn.execute(text("""
                ALTER TABLE drafts
                ADD COLUMN reject_reason TEXT NULL
            """))
            print("  - 已添加 reject_reason 字段")

        # 检查 email_accounts.default_approver_id 是否存在
        result = await conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'email_accounts' AND COLUMN_NAME = 'default_approver_id'
        """))

        if result.fetchone():
            print("email_accounts.default_approver_id 已存在，跳过")
        else:
            print("开始迁移: 添加 email_accounts 表的默认审批人字段...")

            # 添加 default_approver_id 字段
            await conn.execute(text("""
                ALTER TABLE email_accounts
                ADD COLUMN default_approver_id INT NULL,
                ADD CONSTRAINT fk_accounts_default_approver
                    FOREIGN KEY (default_approver_id) REFERENCES email_accounts(id)
            """))
            print("  - 已添加 default_approver_id 字段")

        print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
