# shared/operation_history.py
# -*- coding: utf-8 -*-
"""
统一操作历史记录工具

用于记录各系统的操作日志，支持追溯审计。

数据库表结构（需在各系统数据库中创建）:
    CREATE TABLE operation_history (
        id INT PRIMARY KEY AUTO_INCREMENT,
        system VARCHAR(50) NOT NULL COMMENT '系统标识',
        module VARCHAR(100) NOT NULL COMMENT '模块名称',
        action VARCHAR(100) NOT NULL COMMENT '操作类型',
        target_type VARCHAR(100) COMMENT '目标类型',
        target_id VARCHAR(100) COMMENT '目标ID',
        target_name VARCHAR(255) COMMENT '目标名称',
        operator_id INT COMMENT '操作人ID',
        operator_name VARCHAR(100) COMMENT '操作人姓名',
        operator_role VARCHAR(50) COMMENT '操作人角色',
        ip_address VARCHAR(50) COMMENT 'IP地址',
        old_value TEXT COMMENT '旧值（JSON）',
        new_value TEXT COMMENT '新值（JSON）',
        description TEXT COMMENT '操作描述',
        extra_data TEXT COMMENT '附加数据（JSON）',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_system (system),
        INDEX idx_module (module),
        INDEX idx_action (action),
        INDEX idx_target (target_type, target_id),
        INDEX idx_operator (operator_id),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作历史记录';

使用方法:
    from shared.operation_history import OperationHistory, log_operation

    # 方法1: 使用类
    history = OperationHistory(db_session)
    history.log(
        system="caigou",
        module="pr",
        action="create",
        target_type="PR",
        target_id="1",
        target_name="PR-2025-0001",
        operator_id=1,
        operator_name="admin",
        description="创建采购申请",
        new_value={"title": "办公用品采购", "items": [...]}
    )

    # 方法2: 使用装饰器
    @log_operation(system="caigou", module="pr", action="approve")
    def approve_pr(pr_id):
        ...

    # 查询历史记录
    records = history.query(
        system="caigou",
        target_type="PR",
        target_id="1",
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 12, 31)
    )
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from functools import wraps

logger = logging.getLogger(__name__)

# 操作类型常量
class Actions:
    # 通用操作
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    EXPORT = "export"
    IMPORT = "import"

    # 审批相关
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    WITHDRAW = "withdraw"
    FORWARD = "forward"

    # 状态变更
    STATUS_CHANGE = "status_change"
    ASSIGN = "assign"
    TRANSFER = "transfer"

    # 文件相关
    UPLOAD = "upload"
    DOWNLOAD = "download"
    FILE_DELETE = "file_delete"

    # 用户相关
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    PERMISSION_CHANGE = "permission_change"


# 中文操作名称映射
ACTION_LABELS = {
    Actions.CREATE: "创建",
    Actions.UPDATE: "修改",
    Actions.DELETE: "删除",
    Actions.VIEW: "查看",
    Actions.EXPORT: "导出",
    Actions.IMPORT: "导入",
    Actions.SUBMIT: "提交",
    Actions.APPROVE: "审批通过",
    Actions.REJECT: "驳回",
    Actions.WITHDRAW: "撤回",
    Actions.FORWARD: "转发",
    Actions.STATUS_CHANGE: "状态变更",
    Actions.ASSIGN: "分配",
    Actions.TRANSFER: "转交",
    Actions.UPLOAD: "上传文件",
    Actions.DOWNLOAD: "下载文件",
    Actions.FILE_DELETE: "删除文件",
    Actions.LOGIN: "登录",
    Actions.LOGOUT: "登出",
    Actions.PASSWORD_CHANGE: "修改密码",
    Actions.PERMISSION_CHANGE: "权限变更",
}


def get_action_label(action: str) -> str:
    """获取操作的中文名称"""
    return ACTION_LABELS.get(action, action)


class OperationHistory:
    """操作历史记录管理器"""

    def __init__(self, db_session=None, model_class=None):
        """
        初始化操作历史管理器

        Args:
            db_session: SQLAlchemy数据库会话
            model_class: 操作历史模型类（如果使用ORM）
        """
        self.db_session = db_session
        self.model_class = model_class

    def log(
        self,
        system: str,
        module: str,
        action: str,
        target_type: str = None,
        target_id: str = None,
        target_name: str = None,
        operator_id: int = None,
        operator_name: str = None,
        operator_role: str = None,
        ip_address: str = None,
        old_value: Any = None,
        new_value: Any = None,
        description: str = None,
        extra_data: Dict = None,
        commit: bool = True
    ) -> Optional[int]:
        """
        记录操作历史

        Args:
            system: 系统标识 (caigou, quotation, hr, etc.)
            module: 模块名称 (pr, rfq, supplier, employee, etc.)
            action: 操作类型 (create, update, delete, approve, etc.)
            target_type: 目标类型 (PR, RFQ, Supplier, Employee, etc.)
            target_id: 目标ID
            target_name: 目标名称（便于显示）
            operator_id: 操作人ID
            operator_name: 操作人姓名
            operator_role: 操作人角色
            ip_address: IP地址
            old_value: 修改前的值（会自动JSON序列化）
            new_value: 修改后的值（会自动JSON序列化）
            description: 操作描述
            extra_data: 附加数据
            commit: 是否立即提交事务

        Returns:
            记录ID，失败返回None
        """
        try:
            # 序列化JSON字段
            old_value_json = json.dumps(old_value, ensure_ascii=False, default=str) if old_value else None
            new_value_json = json.dumps(new_value, ensure_ascii=False, default=str) if new_value else None
            extra_data_json = json.dumps(extra_data, ensure_ascii=False, default=str) if extra_data else None

            # 自动生成描述
            if not description:
                action_label = get_action_label(action)
                if target_name:
                    description = f"{action_label} {target_type or ''} {target_name}"
                elif target_id:
                    description = f"{action_label} {target_type or ''} #{target_id}"
                else:
                    description = f"{action_label}"

            if self.model_class and self.db_session:
                # 使用ORM方式
                record = self.model_class(
                    system=system,
                    module=module,
                    action=action,
                    target_type=target_type,
                    target_id=str(target_id) if target_id else None,
                    target_name=target_name,
                    operator_id=operator_id,
                    operator_name=operator_name,
                    operator_role=operator_role,
                    ip_address=ip_address,
                    old_value=old_value_json,
                    new_value=new_value_json,
                    description=description,
                    extra_data=extra_data_json
                )
                self.db_session.add(record)
                if commit:
                    self.db_session.commit()
                return record.id

            elif self.db_session:
                # 使用原生SQL
                from sqlalchemy import text

                sql = text("""
                    INSERT INTO operation_history
                    (system, module, action, target_type, target_id, target_name,
                     operator_id, operator_name, operator_role, ip_address,
                     old_value, new_value, description, extra_data)
                    VALUES
                    (:system, :module, :action, :target_type, :target_id, :target_name,
                     :operator_id, :operator_name, :operator_role, :ip_address,
                     :old_value, :new_value, :description, :extra_data)
                """)

                result = self.db_session.execute(sql, {
                    "system": system,
                    "module": module,
                    "action": action,
                    "target_type": target_type,
                    "target_id": str(target_id) if target_id else None,
                    "target_name": target_name,
                    "operator_id": operator_id,
                    "operator_name": operator_name,
                    "operator_role": operator_role,
                    "ip_address": ip_address,
                    "old_value": old_value_json,
                    "new_value": new_value_json,
                    "description": description,
                    "extra_data": extra_data_json
                })

                if commit:
                    self.db_session.commit()

                return result.lastrowid

            else:
                # 仅记录日志（开发/测试用）
                logger.info(
                    f"[OperationHistory] system={system}, module={module}, action={action}, "
                    f"target={target_type}#{target_id}, operator={operator_name}({operator_id}), "
                    f"desc={description}"
                )
                return 0

        except Exception as e:
            logger.error(f"记录操作历史失败: {str(e)}")
            if self.db_session:
                self.db_session.rollback()
            return None

    def query(
        self,
        system: str = None,
        module: str = None,
        action: str = None,
        target_type: str = None,
        target_id: str = None,
        operator_id: int = None,
        start_date: datetime = None,
        end_date: datetime = None,
        keyword: str = None,
        page: int = 1,
        page_size: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True
    ) -> Dict[str, Any]:
        """
        查询操作历史

        Args:
            system: 系统标识
            module: 模块名称
            action: 操作类型
            target_type: 目标类型
            target_id: 目标ID
            operator_id: 操作人ID
            start_date: 开始日期
            end_date: 结束日期
            keyword: 关键词搜索（搜索描述和目标名称）
            page: 页码
            page_size: 每页数量
            order_by: 排序字段
            order_desc: 是否倒序

        Returns:
            {
                "data": [...],
                "total": 总数,
                "page": 当前页,
                "page_size": 每页数量,
                "total_pages": 总页数
            }
        """
        if not self.db_session:
            return {"data": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

        try:
            from sqlalchemy import text

            # 构建WHERE条件
            conditions = []
            params = {}

            if system:
                conditions.append("system = :system")
                params["system"] = system
            if module:
                conditions.append("module = :module")
                params["module"] = module
            if action:
                conditions.append("action = :action")
                params["action"] = action
            if target_type:
                conditions.append("target_type = :target_type")
                params["target_type"] = target_type
            if target_id:
                conditions.append("target_id = :target_id")
                params["target_id"] = str(target_id)
            if operator_id:
                conditions.append("operator_id = :operator_id")
                params["operator_id"] = operator_id
            if start_date:
                conditions.append("created_at >= :start_date")
                params["start_date"] = start_date
            if end_date:
                conditions.append("created_at <= :end_date")
                params["end_date"] = end_date
            if keyword:
                conditions.append("(description LIKE :keyword OR target_name LIKE :keyword)")
                params["keyword"] = f"%{keyword}%"

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 统计总数
            count_sql = text(f"SELECT COUNT(*) FROM operation_history WHERE {where_clause}")
            total = self.db_session.execute(count_sql, params).scalar()

            # 计算分页
            total_pages = (total + page_size - 1) // page_size
            offset = (page - 1) * page_size

            # 查询数据
            order_direction = "DESC" if order_desc else "ASC"
            data_sql = text(f"""
                SELECT id, system, module, action, target_type, target_id, target_name,
                       operator_id, operator_name, operator_role, ip_address,
                       old_value, new_value, description, extra_data, created_at
                FROM operation_history
                WHERE {where_clause}
                ORDER BY {order_by} {order_direction}
                LIMIT :limit OFFSET :offset
            """)

            params["limit"] = page_size
            params["offset"] = offset

            result = self.db_session.execute(data_sql, params)
            rows = result.fetchall()

            # 格式化数据
            data = []
            for row in rows:
                record = {
                    "id": row[0],
                    "system": row[1],
                    "module": row[2],
                    "action": row[3],
                    "action_label": get_action_label(row[3]),
                    "target_type": row[4],
                    "target_id": row[5],
                    "target_name": row[6],
                    "operator_id": row[7],
                    "operator_name": row[8],
                    "operator_role": row[9],
                    "ip_address": row[10],
                    "old_value": json.loads(row[11]) if row[11] else None,
                    "new_value": json.loads(row[12]) if row[12] else None,
                    "description": row[13],
                    "extra_data": json.loads(row[14]) if row[14] else None,
                    "created_at": row[15].isoformat() if row[15] else None
                }
                data.append(record)

            return {
                "data": data,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }

        except Exception as e:
            logger.error(f"查询操作历史失败: {str(e)}")
            return {"data": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    def get_target_history(
        self,
        target_type: str,
        target_id: str,
        system: str = None
    ) -> List[Dict[str, Any]]:
        """
        获取特定目标的完整历史记录

        Args:
            target_type: 目标类型
            target_id: 目标ID
            system: 系统标识（可选）

        Returns:
            历史记录列表
        """
        result = self.query(
            system=system,
            target_type=target_type,
            target_id=str(target_id),
            page_size=1000  # 获取所有记录
        )
        return result.get("data", [])


# 装饰器：自动记录操作历史
def log_operation(
    system: str,
    module: str,
    action: str,
    target_type: str = None,
    get_target_id=None,
    get_target_name=None,
    get_description=None
):
    """
    装饰器：自动记录操作历史

    用法:
        @log_operation(
            system="caigou",
            module="pr",
            action="approve",
            target_type="PR",
            get_target_id=lambda args, kwargs, result: kwargs.get('pr_id'),
            get_target_name=lambda args, kwargs, result: result.get('pr_number')
        )
        def approve_pr(pr_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # 提取信息
            target_id = get_target_id(args, kwargs, result) if get_target_id else None
            target_name = get_target_name(args, kwargs, result) if get_target_name else None
            description = get_description(args, kwargs, result) if get_description else None

            # 记录操作
            logger.info(
                f"[Operation] {system}.{module}.{action}: "
                f"target={target_type}#{target_id}, name={target_name}"
            )

            return result
        return wrapper
    return decorator


# 创建数据库表的SQL（供各系统使用）
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS operation_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    system VARCHAR(50) NOT NULL COMMENT '系统标识',
    module VARCHAR(100) NOT NULL COMMENT '模块名称',
    action VARCHAR(100) NOT NULL COMMENT '操作类型',
    target_type VARCHAR(100) COMMENT '目标类型',
    target_id VARCHAR(100) COMMENT '目标ID',
    target_name VARCHAR(255) COMMENT '目标名称',
    operator_id INT COMMENT '操作人ID',
    operator_name VARCHAR(100) COMMENT '操作人姓名',
    operator_role VARCHAR(50) COMMENT '操作人角色',
    ip_address VARCHAR(50) COMMENT 'IP地址',
    old_value TEXT COMMENT '旧值（JSON）',
    new_value TEXT COMMENT '新值（JSON）',
    description TEXT COMMENT '操作描述',
    extra_data TEXT COMMENT '附加数据（JSON）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_system (system),
    INDEX idx_module (module),
    INDEX idx_action (action),
    INDEX idx_target (target_type, target_id),
    INDEX idx_operator (operator_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作历史记录';
"""
