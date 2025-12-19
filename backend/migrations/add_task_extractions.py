"""
数据库迁移脚本：添加任务提取表

用于 Portal 项目管理系统导入任务功能
翻译完成后异步提取任务信息，存储结构化数据

使用方法：
cd backend
python -m migrations.add_task_extractions
"""

import asyncio
from sqlalchemy import text
from database.database import engine


async def migrate():
    print("开始迁移：添加任务提取表...")

    async with engine.begin() as conn:
        # 检查 task_extractions 表是否存在
        result = await conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'task_extractions'
        """))
        table_exists = result.scalar() > 0

        if not table_exists:
            # 创建 task_extractions 表
            await conn.execute(text("""
                CREATE TABLE task_extractions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email_id INT NOT NULL UNIQUE,

                    -- 提取的项目字段
                    project_name VARCHAR(200) COMMENT '项目名称',
                    customer_name VARCHAR(200) COMMENT '客户/供应商名称',
                    order_no VARCHAR(100) COMMENT '订单号/PO号',

                    -- 提取的任务字段
                    title VARCHAR(200) COMMENT '任务标题',
                    description TEXT COMMENT '任务描述',
                    task_type VARCHAR(50) DEFAULT 'general' COMMENT '任务类型: general/design/development/testing/review/deployment/documentation/meeting/other',
                    priority VARCHAR(20) DEFAULT 'normal' COMMENT '优先级: low/normal/high/urgent',
                    due_date DATETIME COMMENT '截止日期',
                    start_date DATETIME COMMENT '开始日期',
                    part_number VARCHAR(200) COMMENT '品番号/部件号（用于匹配Portal项目）',
                    assignee_name VARCHAR(100) COMMENT '负责人姓名（用于匹配HR员工）',
                    action_items JSON COMMENT '待办事项列表',

                    -- AI 置信度评分
                    confidence JSON COMMENT '各字段置信度评分',

                    -- 提取状态
                    status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending' COMMENT '提取状态',
                    error_message TEXT COMMENT '失败时的错误信息',

                    -- 时间戳
                    extracted_at DATETIME COMMENT '提取完成时间',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    -- 外键和索引
                    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
                    INDEX idx_task_extraction_email (email_id),
                    INDEX idx_task_extraction_status (status),
                    INDEX idx_task_extraction_part_number (part_number)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='任务提取表 - 供Portal项目管理系统导入任务使用'
            """))
            print("✓ 已创建 task_extractions 表")
        else:
            print("- task_extractions 表已存在，跳过")

    print("\n迁移完成！")
    print("\n表结构说明：")
    print("- email_id: 关联的邮件ID（唯一，一封邮件只有一条提取记录）")
    print("- project_name: AI提取的项目名称")
    print("- customer_name: 客户/供应商名称")
    print("- order_no: 订单号/PO号")
    print("- title/description: AI提取的任务标题和描述")
    print("- task_type: 任务类型（general/design/development等）")
    print("- priority: 优先级（low/normal/high/urgent）")
    print("- due_date/start_date: 截止日期和开始日期")
    print("- part_number: 品番号，用于自动匹配Portal项目")
    print("- assignee_name: 负责人姓名，用于自动匹配HR员工")
    print("- status: 提取状态（pending/processing/completed/failed）")


if __name__ == "__main__":
    asyncio.run(migrate())
