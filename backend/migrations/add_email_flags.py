"""
数据库迁移脚本：为 emails 表添加 is_read 和 is_flagged 字段

使用方法：
cd backend
python -m migrations.add_email_flags
"""

import asyncio
import aiosqlite
from pathlib import Path


async def migrate():
    db_path = Path(__file__).parent.parent.parent / "data" / "app.db"

    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        print("首次运行时会自动创建完整表结构，无需迁移")
        return

    async with aiosqlite.connect(str(db_path)) as db:
        # 检查列是否已存在
        cursor = await db.execute("PRAGMA table_info(emails)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        migrations_applied = []

        # 添加 is_read 列
        if "is_read" not in column_names:
            await db.execute("ALTER TABLE emails ADD COLUMN is_read BOOLEAN DEFAULT 0")
            migrations_applied.append("is_read")
            print("✓ 已添加 is_read 列")
        else:
            print("- is_read 列已存在，跳过")

        # 添加 is_flagged 列
        if "is_flagged" not in column_names:
            await db.execute("ALTER TABLE emails ADD COLUMN is_flagged BOOLEAN DEFAULT 0")
            migrations_applied.append("is_flagged")
            print("✓ 已添加 is_flagged 列")
        else:
            print("- is_flagged 列已存在，跳过")

        if migrations_applied:
            await db.commit()
            print(f"\n迁移完成！共添加 {len(migrations_applied)} 个字段")
        else:
            print("\n无需迁移，所有字段已存在")


if __name__ == "__main__":
    asyncio.run(migrate())
