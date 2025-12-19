-- 添加项目相关字段到 task_extractions 表
-- 用于支持从邮件创建项目功能

USE email_translate;

-- 添加项目名称字段
ALTER TABLE task_extractions ADD COLUMN project_name VARCHAR(200) NULL AFTER email_id;

-- 添加客户/供应商名称字段
ALTER TABLE task_extractions ADD COLUMN customer_name VARCHAR(200) NULL AFTER project_name;

-- 添加订单号字段
ALTER TABLE task_extractions ADD COLUMN order_no VARCHAR(100) NULL AFTER customer_name;

-- 修改 part_number 字段长度以支持多个品番号
ALTER TABLE task_extractions MODIFY COLUMN part_number VARCHAR(200) NULL;

-- 添加注释
ALTER TABLE task_extractions COMMENT = '任务提取表 - 供 Portal 项目管理系统导入项目和任务使用';

SELECT '项目字段已添加到 task_extractions 表' as message;
