"""
添加术语表版本历史表

记录术语表每次修改的历史，支持查看变更和回滚

python -m migrations.add_glossary_history
"""
import asyncio
import sys
sys.path.insert(0, '.')

from database.database import engine
from sqlalchemy import text


async def migrate():
    """执行迁移"""
    async with engine.begin() as conn:
        # 1. 检查 glossary_history 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'glossary_history'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("创建 glossary_history 表...")
            await conn.execute(text("""
                CREATE TABLE glossary_history (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    glossary_id INT NOT NULL,
                    supplier_id INT,
                    term_source VARCHAR(255) NOT NULL,
                    term_target VARCHAR(255) NOT NULL,
                    term_source_old VARCHAR(255),
                    term_target_old VARCHAR(255),
                    source_lang VARCHAR(10),
                    target_lang VARCHAR(10),
                    context TEXT,
                    action ENUM('create', 'update', 'delete') NOT NULL,
                    changed_by INT,
                    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    change_reason VARCHAR(255),
                    INDEX idx_glossary_id (glossary_id),
                    INDEX idx_supplier_id (supplier_id),
                    INDEX idx_changed_at (changed_at),
                    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
                    FOREIGN KEY (changed_by) REFERENCES email_accounts(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='术语表修改历史'
            """))
            print("✓ glossary_history 表已创建")
        else:
            print("• glossary_history 表已存在，跳过")

        # 2. 检查 glossary 表的 updated_at 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'glossary'
            AND column_name = 'updated_at'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 updated_at 字段到 glossary 表...")
            await conn.execute(text("""
                ALTER TABLE glossary
                ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            """))
            print("✓ updated_at 字段已添加")
        else:
            print("• updated_at 字段已存在，跳过")

        # 3. 检查 glossary 表的 created_by 字段
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'glossary'
            AND column_name = 'created_by'
        """))
        row = result.fetchone()

        if row[0] == 0:
            print("添加 created_by 字段到 glossary 表...")
            await conn.execute(text("""
                ALTER TABLE glossary
                ADD COLUMN created_by INT,
                ADD CONSTRAINT fk_glossary_created_by
                    FOREIGN KEY (created_by) REFERENCES email_accounts(id) ON DELETE SET NULL
            """))
            print("✓ created_by 字段已添加")
        else:
            print("• created_by 字段已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
