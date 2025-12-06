"""
数据库迁移脚本：添加翻译缓存表和邮件翻译共享表

使用方法：
cd backend
python -m migrations.add_translation_cache
"""

import asyncio
import aiosqlite
from pathlib import Path


async def migrate():
    db_path = Path(__file__).parent.parent / "data" / "email_translate.db"

    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        print("首次运行时会自动创建完整表结构，无需迁移")
        return

    async with aiosqlite.connect(str(db_path)) as db:
        # 检查 translation_cache 表是否存在
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='translation_cache'"
        )
        if await cursor.fetchone():
            print("- translation_cache 表已存在，跳过")
        else:
            await db.execute("""
                CREATE TABLE translation_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text_hash VARCHAR(64) UNIQUE NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang VARCHAR(10),
                    target_lang VARCHAR(10) NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("CREATE INDEX idx_translation_cache_hash ON translation_cache(text_hash)")
            print("✓ 已创建 translation_cache 表")

        # 检查 shared_email_translations 表是否存在
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_email_translations'"
        )
        if await cursor.fetchone():
            print("- shared_email_translations 表已存在，跳过")
        else:
            await db.execute("""
                CREATE TABLE shared_email_translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id VARCHAR(255) UNIQUE NOT NULL,
                    subject_original TEXT,
                    subject_translated TEXT,
                    body_original TEXT,
                    body_translated TEXT,
                    source_lang VARCHAR(10),
                    target_lang VARCHAR(10) DEFAULT 'zh',
                    translated_by INTEGER,
                    translated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (translated_by) REFERENCES email_accounts(id)
                )
            """)
            await db.execute("CREATE INDEX idx_shared_email_message_id ON shared_email_translations(message_id)")
            print("✓ 已创建 shared_email_translations 表")

        await db.commit()
        print("\n迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
