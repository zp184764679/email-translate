"""
邮件规则管理 API
"""

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

    if "conditions" in update_data and update_data["conditions"]:
        update_data["conditions"] = update_data["conditions"]

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
    """调整规则优先级顺序"""
    for index, rule_id in enumerate(request.rule_ids):
        await db.execute(
            update(EmailRule)
            .where(EmailRule.id == rule_id, EmailRule.account_id == account.id)
            .values(priority=index)
        )

    await db.commit()

    return {"message": "优先级已更新"}


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
