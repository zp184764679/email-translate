"""
邮件文件夹功能数据库迁移脚本

添加以下表：
- email_folders: 文件夹表
- email_folder_mappings: 邮件-文件夹多对多关联表

运行方式：
cd backend
python -m migrations.add_email_folders
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
        # 1. 创建 email_folders 表
        print("Creating email_folders table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_folders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                account_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                parent_id INT,
                color VARCHAR(20) DEFAULT '#409EFF',
                icon VARCHAR(50) DEFAULT 'folder',
                sort_order INT DEFAULT 0,
                is_system BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES email_folders(id) ON DELETE CASCADE,
                UNIQUE KEY unique_folder_name (account_id, parent_id, name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✓ email_folders table created")

        # 2. 创建 email_folder_mappings 关联表
        print("Creating email_folder_mappings table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_folder_mappings (
                email_id INT NOT NULL,
                folder_id INT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (email_id, folder_id),
                FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES email_folders(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✓ email_folder_mappings table created")

        # 3. 创建索引
        print("Creating indexes...")

        # 检查索引是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'email_folders'
            AND index_name = 'idx_folder_account'
        """))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE INDEX idx_folder_account ON email_folders(account_id)"
            ))
            print("✓ idx_folder_account index created")

        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'email_folders'
            AND index_name = 'idx_folder_parent'
        """))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE INDEX idx_folder_parent ON email_folders(parent_id)"
            ))
            print("✓ idx_folder_parent index created")

    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
