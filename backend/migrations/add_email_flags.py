"""
数据库迁移脚本：为 emails 表添加 is_read 和 is_flagged 字段

使用方法：
cd backend
python -m migrations.add_email_flags
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def migrate():
    """为 emails 表添加 is_read 和 is_flagged 字段"""

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

        # 检查 is_read 列是否已存在
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'emails'
            AND COLUMN_NAME = 'is_read'
        """, (database,))

        migrations_applied = []

        if cursor.fetchone():
            print("- is_read 列已存在，跳过")
        else:
            cursor.execute("ALTER TABLE emails ADD COLUMN is_read BOOLEAN DEFAULT FALSE")
            conn.commit()
            migrations_applied.append("is_read")
            print("✓ 已添加 is_read 列")

        # 检查 is_flagged 列是否已存在
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'emails'
            AND COLUMN_NAME = 'is_flagged'
        """, (database,))

        if cursor.fetchone():
            print("- is_flagged 列已存在，跳过")
        else:
            cursor.execute("ALTER TABLE emails ADD COLUMN is_flagged BOOLEAN DEFAULT FALSE")
            conn.commit()
            migrations_applied.append("is_flagged")
            print("✓ 已添加 is_flagged 列")

        cursor.close()
        conn.close()

        if migrations_applied:
            print(f"\n迁移完成！共添加 {len(migrations_applied)} 个字段")
        else:
            print("\n无需迁移，所有字段已存在")

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        raise


if __name__ == "__main__":
    migrate()
