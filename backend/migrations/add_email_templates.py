"""
数据库迁移脚本：添加邮件模板表

使用方法：
cd backend
python -m migrations.add_email_templates
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加邮件模板表...")

    async with engine.begin() as conn:
        # 检查 email_templates 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'email_templates'
        """))
        templates_exists = result.scalar() > 0

        if not templates_exists:
            # 创建 email_templates 表
            await conn.execute(text("""
                CREATE TABLE email_templates (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL COMMENT '创建者账户',
                    name VARCHAR(100) NOT NULL COMMENT '模板名称',
                    description VARCHAR(255) DEFAULT NULL COMMENT '模板描述',
                    category VARCHAR(50) DEFAULT NULL COMMENT '分类（询价/订单/物流/付款等）',
                    subject_cn VARCHAR(255) DEFAULT NULL COMMENT '中文主题',
                    body_cn TEXT NOT NULL COMMENT '中文正文',
                    variables JSON DEFAULT NULL COMMENT '可用变量列表',
                    is_shared BOOLEAN DEFAULT FALSE COMMENT '是否共享',
                    use_count INT DEFAULT 0 COMMENT '使用次数',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES email_accounts(id) ON DELETE CASCADE,
                    INDEX idx_email_templates_account (account_id),
                    INDEX idx_email_templates_category (category),
                    INDEX idx_email_templates_shared (is_shared)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='邮件模板表'
            """))
            print("✓ 已创建 email_templates 表")
        else:
            print("- email_templates 表已存在，跳过")

        # 检查 email_template_translations 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'email_template_translations'
        """))
        translations_exists = result.scalar() > 0

        if not translations_exists:
            # 创建 email_template_translations 表
            await conn.execute(text("""
                CREATE TABLE email_template_translations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    template_id INT NOT NULL COMMENT '关联模板',
                    target_lang VARCHAR(10) NOT NULL COMMENT '目标语言（en/ja/ko/de等）',
                    subject_translated VARCHAR(255) DEFAULT NULL COMMENT '翻译后主题',
                    body_translated TEXT DEFAULT NULL COMMENT '翻译后正文',
                    translated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '翻译时间',
                    FOREIGN KEY (template_id) REFERENCES email_templates(id) ON DELETE CASCADE,
                    UNIQUE KEY uk_template_lang (template_id, target_lang),
                    INDEX idx_template_translations_lang (target_lang)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='邮件模板翻译版本表'
            """))
            print("✓ 已创建 email_template_translations 表")
        else:
            print("- email_template_translations 表已存在，跳过")

        # 插入预设模板分类
        print("\n预设模板分类：")
        print("  - inquiry: 询价")
        print("  - order: 订单确认")
        print("  - logistics: 物流跟踪")
        print("  - payment: 付款相关")
        print("  - quality: 质量问题")
        print("  - general: 日常沟通")

    print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
