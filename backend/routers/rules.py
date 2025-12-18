"""
邮件规则管理 API
"""

import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from database.database import get_db
from database.models import EmailRule, Email, EmailAccount
from routers.users import get_current_account
from services.rule_engine import RuleEngine

router = APIRouter(prefix="/api/rules", tags=["rules"])


# ============== 正则表达式安全验证 ==============

# 已知的危险正则模式（可能导致 ReDoS 攻击）
DANGEROUS_REGEX_PATTERNS = [
    r'\(.*\+\)\+',      # (a+)+ 类型
    r'\(.*\*\)\+',      # (a*)+  类型
    r'\(.*\+\)\*',      # (a+)* 类型
    r'\(.*\*\)\*',      # (a*)* 类型
    r'\(.*\?\)\+',      # (a?)+ 类型
    r'\(.*\{.*\}\)\+',  # (a{n,m})+ 类型
    r'\.{3,}\*',        # ... followed by *
]

# 正则表达式最大长度
MAX_REGEX_LENGTH = 500


def validate_regex_pattern(pattern: str) -> tuple[bool, str]:
    """
    验证正则表达式的安全性

    Returns:
        (is_valid, error_message)
    """
    if not pattern:
        return False, "正则表达式不能为空"

    # 检查长度
    if len(pattern) > MAX_REGEX_LENGTH:
        return False, f"正则表达式长度不能超过 {MAX_REGEX_LENGTH} 字符"

    # 检查是否是有效的正则表达式
    try:
        re.compile(pattern)
    except re.error as e:
        return False, f"无效的正则表达式: {str(e)}"

    # 检查危险模式
    for dangerous in DANGEROUS_REGEX_PATTERNS:
        if re.search(dangerous, pattern):
            return False, f"正则表达式可能导致性能问题，请简化模式（检测到危险模式）"

    # 检查过多的嵌套分组
    group_count = pattern.count('(')
    if group_count > 10:
        return False, f"正则表达式分组过多（最多 10 个），当前 {group_count} 个"

    # 检查过多的量词组合
    quantifiers = re.findall(r'[*+?]\??', pattern)
    if len(quantifiers) > 15:
        return False, f"正则表达式量词过多，请简化模式"

    return True, ""


def validate_rule_conditions(conditions: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证规则条件中的正则表达式

    Returns:
        (is_valid, error_message)
    """
    rules = conditions.get("rules", [])

    for rule in rules:
        operator = rule.get("operator", "")
        value = rule.get("value", "")

        if operator == "regex":
            is_valid, error = validate_regex_pattern(value)
            if not is_valid:
                field = rule.get("field", "unknown")
                return False, f"字段 '{field}' 的{error}"

    return True, ""


# ============== Pydantic Models ==============

class RuleCondition(BaseModel):
    field: str  # from_email, from_name, subject, body, has_attachment, language
    operator: str  # contains, equals, starts_with, ends_with, regex
    value: str


class RuleConditions(BaseModel):
    logic: str = "AND"  # AND 或 OR
    rules: List[RuleCondition]


class RuleAction(BaseModel):
    type: str  # move_to_folder, add_label, mark_read, mark_flagged, skip_translate
    folder_id: Optional[int] = None
    label_id: Optional[int] = None


class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    conditions: RuleConditions
    actions: List[RuleAction]
    priority: int = 0
    stop_processing: bool = False
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[RuleConditions] = None
    actions: Optional[List[RuleAction]] = None
    priority: Optional[int] = None
    stop_processing: Optional[bool] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    priority: int
    stop_processing: bool
    conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    match_count: int
    last_match_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class RuleTestRequest(BaseModel):
    """测试规则的请求"""
    email_data: Dict[str, Any]  # 模拟的邮件数据


class RuleTestResult(BaseModel):
    rule_id: int
    rule_name: str
    matched: bool
    actions: List[Dict[str, Any]]
    priority: int


class ReorderRequest(BaseModel):
    """调整优先级请求"""
    rule_ids: List[int]  # 按新的优先级顺序排列的规则ID列表


# ============== API Endpoints ==============

@router.get("", response_model=List[RuleResponse])
async def get_rules(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前账户的所有规则"""
    result = await db.execute(
        select(EmailRule)
        .where(EmailRule.account_id == account.id)
        .order_by(EmailRule.priority.asc())
    )
    rules = result.scalars().all()
    return rules


@router.post("", response_model=RuleResponse)
async def create_rule(
    rule: RuleCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建新规则"""
    # 验证条件和动作
    if not rule.conditions.rules:
        raise HTTPException(status_code=400, detail="至少需要一个条件")
    if not rule.actions:
        raise HTTPException(status_code=400, detail="至少需要一个动作")

    # 验证正则表达式安全性
    is_valid, error = validate_rule_conditions(rule.conditions.model_dump())
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    new_rule = EmailRule(
        account_id=account.id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        priority=rule.priority,
        stop_processing=rule.stop_processing,
        conditions=rule.conditions.model_dump(),
        actions=[a.model_dump() for a in rule.actions]
    )

    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)

    return new_rule


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个规则详情"""
    result = await db.execute(
        select(EmailRule).where(
            EmailRule.id == rule_id,
            EmailRule.account_id == account.id
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    return rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    rule_update: RuleUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新规则"""
    result = await db.execute(
        select(EmailRule).where(
            EmailRule.id == rule_id,
            EmailRule.account_id == account.id
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # 更新字段
    update_data = rule_update.model_dump(exclude_unset=True)

    # 如果更新了条件，验证正则表达式安全性
    if "conditions" in update_data and update_data["conditions"]:
        is_valid, error = validate_rule_conditions(update_data["conditions"])
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)

    if "actions" in update_data and update_data["actions"]:
        update_data["actions"] = update_data["actions"]

    for key, value in update_data.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)

    return rule


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除规则"""
    result = await db.execute(
        select(EmailRule).where(
            EmailRule.id == rule_id,
            EmailRule.account_id == account.id
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    await db.delete(rule)
    await db.commit()

    return {"message": "规则已删除"}


@router.post("/{rule_id}/toggle", response_model=RuleResponse)
async def toggle_rule(
    rule_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """切换规则启用/禁用状态"""
    result = await db.execute(
        select(EmailRule).where(
            EmailRule.id == rule_id,
            EmailRule.account_id == account.id
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)

    return rule


@router.post("/reorder")
async def reorder_rules(
    request: ReorderRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    调整规则优先级顺序（幂等性保证）

    使用单个批量更新语句，确保原子性
    """
    if not request.rule_ids:
        return {"message": "没有需要更新的规则"}

    # 验证所有规则都属于当前用户
    result = await db.execute(
        select(EmailRule.id).where(
            EmailRule.id.in_(request.rule_ids),
            EmailRule.account_id == account.id
        )
    )
    valid_rule_ids = set(row[0] for row in result.fetchall())

    # 过滤掉不属于当前用户的规则
    filtered_rule_ids = [rid for rid in request.rule_ids if rid in valid_rule_ids]

    if not filtered_rule_ids:
        raise HTTPException(status_code=400, detail="没有有效的规则ID")

    # 使用 CASE WHEN 实现批量更新，保证原子性
    # 构建 SQL：UPDATE email_rules SET priority = CASE id WHEN 1 THEN 0 WHEN 2 THEN 1 ... END
    from sqlalchemy import case, literal

    case_conditions = []
    for index, rule_id in enumerate(filtered_rule_ids):
        case_conditions.append((EmailRule.id == rule_id, index))

    await db.execute(
        update(EmailRule)
        .where(EmailRule.id.in_(filtered_rule_ids))
        .values(priority=case(*case_conditions, else_=EmailRule.priority))
    )

    await db.commit()

    return {
        "message": "优先级已更新",
        "updated_count": len(filtered_rule_ids)
    }


@router.post("/test", response_model=List[RuleTestResult])
async def test_rules(
    request: RuleTestRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """测试规则匹配（不实际执行动作）"""
    engine = RuleEngine(db, account.id)
    await engine.load_rules()

    results = await engine.test_rules(request.email_data)
    return results


@router.post("/apply")
async def apply_rules_to_existing(
    email_ids: List[int],
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """对已有邮件应用规则"""
    engine = RuleEngine(db, account.id)
    await engine.load_rules()

    if not engine.rules:
        return {"message": "没有启用的规则", "processed": 0}

    processed = 0
    applied_count = 0

    for email_id in email_ids:
        # 获取邮件数据
        result = await db.execute(
            select(Email).where(
                Email.id == email_id,
                Email.account_id == account.id
            )
        )
        email = result.scalar_one_or_none()

        if not email:
            continue

        # 构建邮件数据字典
        email_data = {
            "from_email": email.from_email,
            "from_name": email.from_name,
            "to_email": email.to_email,
            "subject_original": email.subject_original,
            "body_original": email.body_original,
            "language_detected": email.language_detected,
            "attachments": []  # TODO: 从附件表获取
        }

        # 处理邮件
        result = await engine.process_email(email_data, email_id)

        processed += 1
        if result["applied_rules"]:
            applied_count += 1

    await db.commit()

    return {
        "message": f"已处理 {processed} 封邮件",
        "processed": processed,
        "rules_applied": applied_count
    }


# ============== 辅助端点 ==============

@router.get("/fields/options")
async def get_field_options():
    """获取可用的条件字段和操作符"""
    return {
        "fields": [
            {"value": "from_email", "label": "发件人邮箱", "operators": ["contains", "equals", "starts_with", "ends_with", "regex"]},
            {"value": "from_name", "label": "发件人名称", "operators": ["contains", "equals", "starts_with", "ends_with"]},
            {"value": "to_email", "label": "收件人", "operators": ["contains", "equals"]},
            {"value": "subject", "label": "主题", "operators": ["contains", "equals", "starts_with", "ends_with", "regex"]},
            {"value": "body", "label": "正文", "operators": ["contains", "regex"]},
            {"value": "has_attachment", "label": "是否有附件", "operators": ["equals"]},
            {"value": "language", "label": "语言", "operators": ["equals"]}
        ],
        "operators": [
            {"value": "contains", "label": "包含"},
            {"value": "equals", "label": "等于"},
            {"value": "starts_with", "label": "开头匹配"},
            {"value": "ends_with", "label": "结尾匹配"},
            {"value": "regex", "label": "正则表达式"},
            {"value": "not_contains", "label": "不包含"},
            {"value": "not_equals", "label": "不等于"}
        ],
        "actions": [
            {"value": "move_to_folder", "label": "移动到文件夹", "params": ["folder_id"]},
            {"value": "add_label", "label": "添加标签", "params": ["label_id"]},
            {"value": "remove_label", "label": "移除标签", "params": ["label_id"]},
            {"value": "mark_read", "label": "标记为已读", "params": []},
            {"value": "mark_unread", "label": "标记为未读", "params": []},
            {"value": "mark_flagged", "label": "添加星标", "params": []},
            {"value": "mark_unflagged", "label": "移除星标", "params": []},
            {"value": "skip_translate", "label": "跳过翻译", "params": []}
        ],
        "languages": [
            {"value": "zh", "label": "中文"},
            {"value": "en", "label": "英文"},
            {"value": "ja", "label": "日文"},
            {"value": "ko", "label": "韩文"},
            {"value": "de", "label": "德文"},
            {"value": "fr", "label": "法文"},
            {"value": "es", "label": "西班牙文"}
        ]
    }


# ============== 执行日志端点 ==============

class ExecutionLogResponse(BaseModel):
    id: int
    rule_id: int
    rule_name: Optional[str] = None
    email_id: int
    matched: bool
    actions_applied: Optional[List[str]]
    actions_success: bool
    error_message: Optional[str]
    executed_at: datetime

    class Config:
        from_attributes = True


class ExecutionStatsResponse(BaseModel):
    total_executions: int
    successful_executions: int
    failed_executions: int
    rules_triggered: int
    top_rules: List[Dict[str, Any]]


@router.get("/executions", response_model=List[ExecutionLogResponse])
async def get_execution_logs(
    rule_id: Optional[int] = None,
    email_id: Optional[int] = None,
    success_only: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取规则执行日志

    Args:
        rule_id: 按规则ID过滤
        email_id: 按邮件ID过滤
        success_only: True=只看成功，False=只看失败，None=全部
        limit: 返回数量限制
        offset: 分页偏移
    """
    from database.models import RuleExecution

    query = select(RuleExecution).where(RuleExecution.account_id == account.id)

    if rule_id:
        query = query.where(RuleExecution.rule_id == rule_id)
    if email_id:
        query = query.where(RuleExecution.email_id == email_id)
    if success_only is not None:
        query = query.where(RuleExecution.actions_success == success_only)

    query = query.order_by(RuleExecution.executed_at.desc()).offset(offset).limit(min(limit, 500))

    result = await db.execute(query)
    executions = result.scalars().all()

    # 获取规则名称
    rule_ids = list(set(e.rule_id for e in executions))
    if rule_ids:
        rules_result = await db.execute(
            select(EmailRule.id, EmailRule.name).where(EmailRule.id.in_(rule_ids))
        )
        rule_names = {r[0]: r[1] for r in rules_result.fetchall()}
    else:
        rule_names = {}

    # 构建响应
    response = []
    for e in executions:
        response.append(ExecutionLogResponse(
            id=e.id,
            rule_id=e.rule_id,
            rule_name=rule_names.get(e.rule_id),
            email_id=e.email_id,
            matched=e.matched,
            actions_applied=e.actions_applied,
            actions_success=e.actions_success,
            error_message=e.error_message,
            executed_at=e.executed_at
        ))

    return response


@router.get("/executions/stats", response_model=ExecutionStatsResponse)
async def get_execution_stats(
    days: int = 7,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取规则执行统计

    Args:
        days: 统计最近多少天的数据
    """
    from database.models import RuleExecution
    from sqlalchemy import func, case
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(days=days)

    # 基础统计
    stats_result = await db.execute(
        select(
            func.count(RuleExecution.id).label("total"),
            func.sum(case((RuleExecution.actions_success == True, 1), else_=0)).label("success"),
            func.sum(case((RuleExecution.actions_success == False, 1), else_=0)).label("failed"),
            func.count(func.distinct(RuleExecution.rule_id)).label("rules_count")
        ).where(
            RuleExecution.account_id == account.id,
            RuleExecution.executed_at >= since
        )
    )
    stats = stats_result.fetchone()

    # Top 规则
    top_rules_result = await db.execute(
        select(
            RuleExecution.rule_id,
            EmailRule.name,
            func.count(RuleExecution.id).label("count")
        ).join(EmailRule, RuleExecution.rule_id == EmailRule.id)
        .where(
            RuleExecution.account_id == account.id,
            RuleExecution.executed_at >= since,
            RuleExecution.matched == True
        )
        .group_by(RuleExecution.rule_id, EmailRule.name)
        .order_by(func.count(RuleExecution.id).desc())
        .limit(10)
    )
    top_rules = [
        {"rule_id": r[0], "rule_name": r[1], "match_count": r[2]}
        for r in top_rules_result.fetchall()
    ]

    return ExecutionStatsResponse(
        total_executions=stats[0] or 0,
        successful_executions=stats[1] or 0,
        failed_executions=stats[2] or 0,
        rules_triggered=stats[3] or 0,
        top_rules=top_rules
    )


@router.delete("/executions")
async def clear_execution_logs(
    days_old: int = 30,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    清理旧的执行日志

    Args:
        days_old: 清理多少天前的日志
    """
    from database.models import RuleExecution
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days_old)

    result = await db.execute(
        delete(RuleExecution).where(
            RuleExecution.account_id == account.id,
            RuleExecution.executed_at < cutoff
        )
    )
    await db.commit()

    return {"message": f"已清理 {days_old} 天前的执行日志", "deleted_count": result.rowcount}


# ============== 导入导出端点 ==============

class RuleExportData(BaseModel):
    """规则导出数据格式"""
    name: str
    description: Optional[str]
    conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    priority: int
    stop_processing: bool
    is_active: bool


class RuleImportRequest(BaseModel):
    """规则导入请求"""
    rules: List[RuleExportData]
    overwrite: bool = False  # 是否覆盖同名规则


@router.get("/export")
async def export_rules(
    rule_ids: Optional[str] = None,  # 逗号分隔的规则ID，不传则导出全部
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    导出规则

    Args:
        rule_ids: 逗号分隔的规则ID（如 "1,2,3"），不传则导出全部
    """
    query = select(EmailRule).where(EmailRule.account_id == account.id)

    if rule_ids:
        try:
            ids = [int(x.strip()) for x in rule_ids.split(",")]
            query = query.where(EmailRule.id.in_(ids))
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的规则ID格式")

    query = query.order_by(EmailRule.priority.asc())
    result = await db.execute(query)
    rules = result.scalars().all()

    export_data = {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "rules_count": len(rules),
        "rules": [
            {
                "name": r.name,
                "description": r.description,
                "conditions": r.conditions,
                "actions": r.actions,
                "priority": r.priority,
                "stop_processing": r.stop_processing,
                "is_active": r.is_active
            }
            for r in rules
        ]
    }

    return export_data


@router.post("/import")
async def import_rules(
    request: RuleImportRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    导入规则

    Args:
        request.rules: 规则数据列表
        request.overwrite: 是否覆盖同名规则
    """
    if not request.rules:
        raise HTTPException(status_code=400, detail="没有要导入的规则")

    # 获取现有规则名称
    existing_result = await db.execute(
        select(EmailRule.id, EmailRule.name).where(EmailRule.account_id == account.id)
    )
    existing_rules = {r[1]: r[0] for r in existing_result.fetchall()}

    imported = 0
    updated = 0
    skipped = 0
    errors = []

    for rule_data in request.rules:
        try:
            # 验证条件中的正则表达式
            is_valid, error = validate_rule_conditions(rule_data.conditions)
            if not is_valid:
                errors.append(f"规则 '{rule_data.name}': {error}")
                skipped += 1
                continue

            if rule_data.name in existing_rules:
                if request.overwrite:
                    # 更新现有规则
                    await db.execute(
                        update(EmailRule)
                        .where(EmailRule.id == existing_rules[rule_data.name])
                        .values(
                            description=rule_data.description,
                            conditions=rule_data.conditions,
                            actions=rule_data.actions,
                            priority=rule_data.priority,
                            stop_processing=rule_data.stop_processing,
                            is_active=rule_data.is_active
                        )
                    )
                    updated += 1
                else:
                    skipped += 1
            else:
                # 创建新规则
                new_rule = EmailRule(
                    account_id=account.id,
                    name=rule_data.name,
                    description=rule_data.description,
                    conditions=rule_data.conditions,
                    actions=rule_data.actions,
                    priority=rule_data.priority,
                    stop_processing=rule_data.stop_processing,
                    is_active=rule_data.is_active
                )
                db.add(new_rule)
                imported += 1

        except Exception as e:
            errors.append(f"规则 '{rule_data.name}': {str(e)}")
            skipped += 1

    await db.commit()

    return {
        "message": "导入完成",
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors if errors else None
    }
