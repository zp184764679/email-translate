"""
数据库迁移脚本：添加供应商多域名表

使用方法：
cd backend
python -m migrations.add_supplier_domains
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加供应商多域名表...")

    async with engine.begin() as conn:
        # 检查 supplier_domains 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'supplier_domains'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 supplier_domains 表
            await conn.execute(text("""
                CREATE TABLE supplier_domains (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    supplier_id INT NOT NULL,
                    email_domain VARCHAR(255) NOT NULL COMMENT '邮箱域名',
                    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否主域名',
                    description VARCHAR(100) DEFAULT NULL COMMENT '域名描述，如销售部、技术支持',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
                    UNIQUE KEY uk_email_domain (email_domain),
                    INDEX idx_supplier_domains_supplier (supplier_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='供应商多域名表 - 一个供应商可关联多个邮箱域名'
            """))
            print("✓ 已创建 supplier_domains 表")

            # 迁移现有数据：将 suppliers.email_domain 迁移到新表
            await conn.execute(text("""
                INSERT INTO supplier_domains (supplier_id, email_domain, is_primary, description)
                SELECT id, email_domain, TRUE, '主域名(自动迁移)'
                FROM suppliers
                WHERE email_domain IS NOT NULL AND email_domain != ''
            """))
            print("✓ 已迁移现有供应商域名数据")
        else:
            print("- supplier_domains 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
