"""
数据库迁移脚本：添加供应商联系人表

使用方法：
cd backend
python -m migrations.add_supplier_contacts
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加供应商联系人表...")

    async with engine.begin() as conn:
        # 检查 supplier_contacts 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'supplier_contacts'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 supplier_contacts 表
            await conn.execute(text("""
                CREATE TABLE supplier_contacts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    supplier_id INT NOT NULL,
                    name VARCHAR(100) NOT NULL COMMENT '联系人姓名',
                    email VARCHAR(255) NOT NULL COMMENT '邮箱地址',
                    phone VARCHAR(50) DEFAULT NULL COMMENT '电话号码',
                    role VARCHAR(50) DEFAULT NULL COMMENT '角色：sales/tech/finance/logistics/manager/other',
                    department VARCHAR(100) DEFAULT NULL COMMENT '部门',
                    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否主要联系人',
                    notes TEXT DEFAULT NULL COMMENT '备注',
                    last_contact_at DATETIME DEFAULT NULL COMMENT '最后联系时间',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
                    INDEX idx_supplier_contacts_supplier (supplier_id),
                    INDEX idx_supplier_contacts_email (email),
                    INDEX idx_supplier_contacts_role (role)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='供应商联系人表 - 管理供应商的多个联系人'
            """))
            print("✓ 已创建 supplier_contacts 表")

            # 迁移现有数据：将 suppliers.contact_email 迁移到新表
            await conn.execute(text("""
                INSERT INTO supplier_contacts (supplier_id, name, email, is_primary, notes)
                SELECT id,
                       CONCAT(name, ' (主联系人)'),
                       contact_email,
                       TRUE,
                       '自动迁移自供应商表'
                FROM suppliers
                WHERE contact_email IS NOT NULL AND contact_email != ''
            """))
            print("✓ 已迁移现有供应商联系人数据")
        else:
            print("- supplier_contacts 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
