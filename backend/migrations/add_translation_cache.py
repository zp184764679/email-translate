"""
数据库迁移脚本：添加翻译缓存表和邮件翻译共享表

使用方法：
cd backend
python -m migrations.add_translation_cache
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def migrate():
    """添加翻译缓存相关表"""

    # 获取数据库配置
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "email_translate")

    print(f"连接数据库: {host}:{port}/{database}")

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()

        # 检查 translation_cache 表是否存在
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'translation_cache'
        """, (database,))

        if cursor.fetchone():
            print("- translation_cache 表已存在，跳过")
        else:
            cursor.execute("""
                CREATE TABLE translation_cache (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    text_hash VARCHAR(64) NOT NULL UNIQUE,
                    source_text MEDIUMTEXT NOT NULL,
                    translated_text MEDIUMTEXT NOT NULL,
                    source_lang VARCHAR(10),
                    target_lang VARCHAR(10) NOT NULL,
                    hit_count INT DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_translation_cache_hash (text_hash)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            print("✓ 已创建 translation_cache 表")

        # 检查 shared_email_translations 表是否存在
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'shared_email_translations'
        """, (database,))

        if cursor.fetchone():
            print("- shared_email_translations 表已存在，跳过")
        else:
            cursor.execute("""
                CREATE TABLE shared_email_translations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    message_id VARCHAR(255) NOT NULL UNIQUE,
                    subject_original TEXT,
                    subject_translated TEXT,
                    body_original MEDIUMTEXT,
                    body_translated MEDIUMTEXT,
                    source_lang VARCHAR(10),
                    target_lang VARCHAR(10) DEFAULT 'zh',
                    translated_by INT,
                    translated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_shared_email_message_id (message_id),
                    FOREIGN KEY (translated_by) REFERENCES email_accounts(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            print("✓ 已创建 shared_email_translations 表")

        cursor.close()
        conn.close()
        print("\n迁移完成！")

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        raise


if __name__ == "__main__":
    migrate()
