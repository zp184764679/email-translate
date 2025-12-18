"""
迁移脚本：为 translation_batches 表添加 account_id 字段

用途：记录批次提交者，用于完成时发送 WebSocket 通知
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def run_migration():
    """添加 account_id 字段到 translation_batches 表"""
    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # 检查表是否存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = :db AND table_name = 'translation_batches'
        """), {"db": os.getenv('MYSQL_DATABASE', 'email_translate')})

        if result.scalar() == 0:
            print("表 translation_batches 不存在，跳过迁移")
            return

        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = :db
            AND table_name = 'translation_batches'
            AND column_name = 'account_id'
        """), {"db": os.getenv('MYSQL_DATABASE', 'email_translate')})

        if result.scalar() > 0:
            print("字段 account_id 已存在，跳过迁移")
            return

        # 添加字段
        conn.execute(text("""
            ALTER TABLE translation_batches
            ADD COLUMN account_id INT NULL AFTER batch_id,
            ADD INDEX idx_batch_account (account_id),
            ADD CONSTRAINT fk_batch_account
                FOREIGN KEY (account_id) REFERENCES email_accounts(id)
                ON DELETE SET NULL
        """))
        conn.commit()
        print("成功添加 account_id 字段到 translation_batches 表")


if __name__ == "__main__":
    run_migration()
