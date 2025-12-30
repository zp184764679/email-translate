"""
添加邮件归档功能字段

为 emails 表添加:
- archived_at: 归档时间
- archive_folder: 归档文件夹（年份/项目/供应商）

创建 archive_folders 表用于管理归档文件夹
"""

import asyncio
import sys
sys.path.insert(0, '.')

from database.database import engine
from sqlalchemy import text


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        # 1. 检查 emails 表的 archived_at 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND column_name = 'archived_at'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 archived_at 字段...")
            await conn.execute(text("""
                ALTER TABLE emails
                ADD COLUMN archived_at DATETIME NULL COMMENT '归档时间'
            """))
            print("✓ archived_at 字段已添加")
        else:
            print("• archived_at 字段已存在，跳过")

        # 2. 检查 archive_folder_id 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND column_name = 'archive_folder_id'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 archive_folder_id 字段...")
            await conn.execute(text("""
                ALTER TABLE emails
                ADD COLUMN archive_folder_id INT NULL COMMENT '归档文件夹ID'
            """))
            print("✓ archive_folder_id 字段已添加")
        else:
            print("• archive_folder_id 字段已存在，跳过")

        # 3. 创建 archive_folders 表
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'archive_folders'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("创建 archive_folders 表...")
            await conn.execute(text("""
                CREATE TABLE archive_folders (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    account_id INT NOT NULL COMMENT '所属账户',
                    name VARCHAR(100) NOT NULL COMMENT '文件夹名称',
                    folder_type ENUM('year', 'project', 'supplier', 'custom') DEFAULT 'custom' COMMENT '类型',
                    parent_id INT NULL COMMENT '父文件夹ID',
                    description VARCHAR(255) NULL COMMENT '描述',
                    color VARCHAR(20) DEFAULT '#409EFF' COMMENT '颜色标识',
                    email_count INT DEFAULT 0 COMMENT '邮件数量（缓存）',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES archive_folders(id) ON DELETE SET NULL,
                    INDEX idx_account (account_id),
                    INDEX idx_type (folder_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='归档文件夹'
            """))
            print("✓ archive_folders 表已创建")
        else:
            print("• archive_folders 表已存在，跳过")

        # 4. 添加归档索引
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'emails'
            AND index_name = 'idx_archived'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加归档索引...")
            await conn.execute(text("""
                CREATE INDEX idx_archived ON emails (archived_at, archive_folder_id)
            """))
            print("✓ 索引已创建")
        else:
            print("• 索引已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
