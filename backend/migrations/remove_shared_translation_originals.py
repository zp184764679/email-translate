"""
数据库迁移脚本：移除 shared_email_translations 表中的冗余原文字段

原因：
- body_original 和 subject_original 被写入但从未被读取
- 原文已存储在各用户的 emails 表中
- 移除冗余字段节省存储空间

使用方法：
cd backend
python -m migrations.remove_shared_translation_originals
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def migrate():
    """移除 shared_email_translations 表中的冗余原文字段"""

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
            AND TABLE_NAME = 'shared_email_translations'
        """, (database,))

        if cursor.fetchone()[0] == 0:
            print("- shared_email_translations 表不存在，跳过迁移")
            cursor.close()
            conn.close()
            return

        columns_to_remove = ['body_original', 'subject_original']

        for column in columns_to_remove:
            # 检查列是否存在
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                AND TABLE_NAME = 'shared_email_translations'
                AND COLUMN_NAME = %s
            """, (database, column))

            if cursor.fetchone():
                # 删除列
                cursor.execute(f"""
                    ALTER TABLE shared_email_translations
                    DROP COLUMN {column}
                """)
                conn.commit()
                print(f"✓ 已删除 {column} 列")
            else:
                print(f"- {column} 列不存在，跳过")

        cursor.close()
        conn.close()
        print("\n迁移完成！冗余原文字段已移除，节省了存储空间。")

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        raise


if __name__ == "__main__":
    migrate()
