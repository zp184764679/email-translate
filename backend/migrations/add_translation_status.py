"""
数据库迁移脚本：为 emails 表添加 translation_status 字段

用于解决多进程/多worker下翻译锁不同步的问题
使用数据库状态字段替代内存中的 set

使用方法：
cd backend
python -m migrations.add_translation_status
"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def migrate():
    """为 emails 表添加 translation_status 字段"""

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

        # 检查列是否已存在
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'emails'
            AND COLUMN_NAME = 'translation_status'
        """, (database,))

        if cursor.fetchone():
            print("- translation_status 列已存在，跳过")
        else:
            # 添加 translation_status 列
            cursor.execute("""
                ALTER TABLE emails
                ADD COLUMN translation_status VARCHAR(20) DEFAULT 'none',
                ADD INDEX idx_translation_status (translation_status)
            """)
            conn.commit()
            print("✓ 已添加 translation_status 列和索引")

            # 更新已翻译邮件的状态
            cursor.execute("""
                UPDATE emails
                SET translation_status = 'completed'
                WHERE is_translated = 1
            """)
            updated = cursor.rowcount
            conn.commit()
            print(f"✓ 已更新 {updated} 封已翻译邮件的状态为 completed")

        cursor.close()
        conn.close()
        print("\n迁移完成！")

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        raise


if __name__ == "__main__":
    migrate()
