"""
数据库迁移脚本：添加附件 content_hash 字段

用于检测重复内容、完整性校验

使用方法：
cd backend
python -m migrations.add_attachment_hash
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def migrate():
    """添加 attachments.content_hash 字段"""

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

        # 检查表是否存在
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'attachments'
        """, (database,))

        if cursor.fetchone()[0] == 0:
            print("- attachments 表不存在，跳过迁移")
            cursor.close()
            conn.close()
            return

        # 检查列是否已存在
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'attachments'
            AND COLUMN_NAME = 'content_hash'
        """, (database,))

        if cursor.fetchone():
            print("- content_hash 列已存在，跳过")
        else:
            # 添加列
            cursor.execute("""
                ALTER TABLE attachments
                ADD COLUMN content_hash VARCHAR(64) DEFAULT NULL
            """)
            conn.commit()
            print("✓ 已添加 content_hash 列")

            # 添加索引
            cursor.execute("""
                CREATE INDEX idx_attachments_content_hash
                ON attachments(content_hash)
            """)
            conn.commit()
            print("✓ 已添加 content_hash 索引")

        cursor.close()
        conn.close()
        print("\n迁移完成！")

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        raise


if __name__ == "__main__":
    migrate()
