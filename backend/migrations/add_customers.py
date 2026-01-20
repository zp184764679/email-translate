"""
数据库迁移脚本：添加客户管理模块相关表

使用方法：
cd backend
python -m migrations.add_customers
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加客户管理模块相关表...")

    async with engine.begin() as conn:
        # 1. 创建 customers 表
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'customers'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            await conn.execute(text("""
                CREATE TABLE customers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL COMMENT '客户名称',
                    email_domain VARCHAR(255) DEFAULT NULL COMMENT '主邮箱域名(兼容)',
                    contact_email VARCHAR(255) DEFAULT NULL COMMENT '主联系邮箱(兼容)',
                    country VARCHAR(100) DEFAULT NULL COMMENT '国家/地区',
                    notes TEXT DEFAULT NULL COMMENT '备注',
                    category VARCHAR(50) DEFAULT NULL COMMENT 'AI分析的类别',
                    category_confidence FLOAT DEFAULT NULL COMMENT '置信度(0-1)',
                    category_reason TEXT DEFAULT NULL COMMENT '分类依据说明',
                    category_analyzed_at TIMESTAMP NULL DEFAULT NULL COMMENT '分析时间',
                    category_manual BOOLEAN DEFAULT FALSE COMMENT '是否人工修改',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_customers_name (name),
                    INDEX idx_customers_category (category)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='客户主表 - 管理客户信息'
            """))
            print("✓ 已创建 customers 表")
        else:
            print("- customers 表已存在，跳过")

        # 2. 创建 customer_domains 表
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'customer_domains'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            await conn.execute(text("""
                CREATE TABLE customer_domains (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_id INT NOT NULL,
                    email_domain VARCHAR(255) NOT NULL COMMENT '邮箱域名',
                    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否主域名',
                    description VARCHAR(100) DEFAULT NULL COMMENT '域名描述',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                    UNIQUE KEY uk_customer_email_domain (email_domain),
                    INDEX idx_customer_domains_customer (customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='客户多域名表 - 一个客户可关联多个邮箱域名'
            """))
            print("✓ 已创建 customer_domains 表")
        else:
            print("- customer_domains 表已存在，跳过")

        # 3. 创建 customer_contacts 表
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'customer_contacts'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            await conn.execute(text("""
                CREATE TABLE customer_contacts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_id INT NOT NULL,
                    name VARCHAR(100) NOT NULL COMMENT '联系人姓名',
                    email VARCHAR(255) NOT NULL COMMENT '邮箱地址',
                    phone VARCHAR(50) DEFAULT NULL COMMENT '电话号码',
                    role VARCHAR(50) DEFAULT NULL COMMENT '角色',
                    department VARCHAR(100) DEFAULT NULL COMMENT '部门',
                    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否主要联系人',
                    notes TEXT DEFAULT NULL COMMENT '备注',
                    last_contact_at TIMESTAMP NULL DEFAULT NULL COMMENT '最后联系时间',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                    INDEX idx_customer_contacts_customer (customer_id),
                    INDEX idx_customer_contacts_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='客户联系人表 - 管理客户的多个联系人'
            """))
            print("✓ 已创建 customer_contacts 表")
        else:
            print("- customer_contacts 表已存在，跳过")

        # 4. 创建 customer_tags 表
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'customer_tags'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            await conn.execute(text("""
                CREATE TABLE customer_tags (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL COMMENT '所属账户',
                    name VARCHAR(50) NOT NULL COMMENT '标签名称',
                    color VARCHAR(20) DEFAULT '#409EFF' COMMENT '标签颜色',
                    description VARCHAR(255) DEFAULT NULL COMMENT '标签描述',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_customer_tags_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='客户标签表 - 用于标记和筛选客户'
            """))
            print("✓ 已创建 customer_tags 表")
        else:
            print("- customer_tags 表已存在，跳过")

        # 5. 创建 customer_tag_mappings 关联表
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'customer_tag_mappings'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            await conn.execute(text("""
                CREATE TABLE customer_tag_mappings (
                    customer_id INT NOT NULL,
                    tag_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (customer_id, tag_id),
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES customer_tags(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='客户-标签多对多关联表'
            """))
            print("✓ 已创建 customer_tag_mappings 表")
        else:
            print("- customer_tag_mappings 表已存在，跳过")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
