"""
添加 Portal 集成相关字段到 TaskExtraction 表

运行方式：
cd backend
python -m migrations.add_portal_integration_fields
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine
from sqlalchemy import text


async def migrate():
    """添加 Portal 集成字段"""
    async with engine.begin() as conn:
        # 检查表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = 'task_extractions'
        """))
        if result.scalar() == 0:
            print("task_extractions 表不存在，跳过迁移")
            return

        # 要添加的字段列表
        columns_to_add = [
            ("matched_project_id", "INT", "Portal 中匹配到的项目 ID"),
            ("matched_project_name", "VARCHAR(200)", "匹配到的项目名称"),
            ("should_create_project", "BOOLEAN DEFAULT FALSE", "是否需要创建新项目"),
            ("suggested_project_name", "VARCHAR(200)", "AI 建议的新项目名称"),
            ("imported_to_portal", "BOOLEAN DEFAULT FALSE", "是否已导入到 Portal"),
            ("portal_task_id", "INT", "Portal 中创建的任务 ID"),
            ("portal_project_id", "INT", "Portal 中关联的项目 ID"),
            ("imported_at", "DATETIME", "导入时间"),
        ]

        for column_name, column_type, comment in columns_to_add:
            # 检查字段是否已存在
            result = await conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'task_extractions'
                AND column_name = '{column_name}'
            """))

            if result.scalar() == 0:
                await conn.execute(text(f"""
                    ALTER TABLE task_extractions
                    ADD COLUMN {column_name} {column_type} COMMENT '{comment}'
                """))
                print(f"✓ 添加字段: {column_name}")
            else:
                print(f"- 字段已存在: {column_name}")

        # 添加索引
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'task_extractions'
            AND index_name = 'ix_task_extractions_imported_to_portal'
        """))

        if result.scalar() == 0:
            await conn.execute(text("""
                CREATE INDEX ix_task_extractions_imported_to_portal
                ON task_extractions(imported_to_portal)
            """))
            print("✓ 创建索引: ix_task_extractions_imported_to_portal")
        else:
            print("- 索引已存在: ix_task_extractions_imported_to_portal")

        print("\n迁移完成!")


if __name__ == "__main__":
    asyncio.run(migrate())
