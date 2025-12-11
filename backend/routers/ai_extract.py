"""
AI 邮件信息提取 API 路由
使用 Ollama 提取邮件中的关键信息（日期、金额、联系人、待办事项等）
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel

from database.database import get_db
from database.models import Email, EmailExtraction, EmailAccount
from routers.users import get_current_account
from services.ai_extract_service import extract_email_info

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ============ Pydantic Schemas ============

class DateInfo(BaseModel):
    date: str
    context: Optional[str] = None


class AmountInfo(BaseModel):
    amount: float
    currency: str
    context: Optional[str] = None


class ContactInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None


class ActionItem(BaseModel):
    task: str
    priority: Optional[str] = "medium"
    deadline: Optional[str] = None


class InternalAttendee(BaseModel):
    """公司内部参会人员（从 to/cc 提取的 @jingzhicheng.com.cn 邮箱）"""
    name: Optional[str] = None
    email: str


class ExtractionResponse(BaseModel):
    id: int
    email_id: int
    summary: Optional[str]
    dates: List[dict]
    amounts: List[dict]
    contacts: List[dict]
    action_items: List[dict]
    key_points: List[str]
    internal_attendees: List[InternalAttendee] = []  # 公司内部参会人员
    extracted_at: datetime

    class Config:
        from_attributes = True


# ============ Helper Functions ============

def extract_internal_attendees(to_email: str, cc_email: str) -> List[dict]:
    """
    从 to/cc 中提取 @jingzhicheng.com.cn 的公司内部人员

    邮件地址格式可能是：
    - "张三 <zhangsan@jingzhicheng.com.cn>"
    - "zhangsan@jingzhicheng.com.cn"
    - "张三 <zhangsan@jingzhicheng.com.cn>, 李四 <lisi@jingzhicheng.com.cn>"
    """
    import re
    attendees = []
    seen_emails = set()

    # 合并 to 和 cc
    all_addresses = f"{to_email or ''}, {cc_email or ''}"

    # 匹配邮箱地址的正则
    # 格式1: "Name <email@domain.com>"
    pattern1 = r'"?([^"<>]*)"?\s*<([^<>]+@jingzhicheng\.com\.cn)>'
    # 格式2: 纯邮箱 email@jingzhicheng.com.cn
    pattern2 = r'\b([a-zA-Z0-9._%+-]+@jingzhicheng\.com\.cn)\b'

    # 先匹配带名字的格式
    for match in re.finditer(pattern1, all_addresses, re.IGNORECASE):
        name = match.group(1).strip() if match.group(1) else None
        email = match.group(2).lower()
        if email not in seen_emails:
            seen_emails.add(email)
            attendees.append({"name": name, "email": email})

    # 再匹配纯邮箱格式（排除已经匹配的）
    for match in re.finditer(pattern2, all_addresses, re.IGNORECASE):
        email = match.group(1).lower()
        if email not in seen_emails:
            seen_emails.add(email)
            # 尝试从邮箱前缀提取名字
            name = email.split('@')[0]
            attendees.append({"name": name, "email": email})

    return attendees


# ============ API Endpoints ============

@router.post("/extract/{email_id}", response_model=ExtractionResponse)
async def extract_email(
    email_id: int,
    force: bool = False,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    提取邮件中的关键信息

    Args:
        email_id: 邮件 ID
        force: 是否强制重新提取（即使已有结果）
    """
    # 验证邮件存在且属于当前用户
    email_result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == account.id
            )
        )
    )
    email = email_result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 提取公司内部参会人员（从 to/cc 提取 @jingzhicheng.com.cn）
    internal_attendees = extract_internal_attendees(email.to_email, email.cc_email)

    # 检查是否已有提取结果
    if not force:
        existing_result = await db.execute(
            select(EmailExtraction).where(
                EmailExtraction.email_id == email_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            # 返回时添加 internal_attendees
            return ExtractionResponse(
                id=existing.id,
                email_id=existing.email_id,
                summary=existing.summary,
                dates=existing.dates or [],
                amounts=existing.amounts or [],
                contacts=existing.contacts or [],
                action_items=existing.action_items or [],
                key_points=existing.key_points or [],
                internal_attendees=internal_attendees,
                extracted_at=existing.extracted_at
            )

    # 调用 AI 提取服务
    extraction_data = await extract_email_info(
        subject=email.subject_translated or email.subject_original or "",
        body=email.body_original or "",
        body_translated=email.body_translated
    )

    # 查找或创建提取记录
    existing_result = await db.execute(
        select(EmailExtraction).where(
            EmailExtraction.email_id == email_id
        )
    )
    extraction = existing_result.scalar_one_or_none()

    if extraction:
        # 更新现有记录
        extraction.summary = extraction_data.get("summary")
        extraction.dates = extraction_data.get("dates", [])
        extraction.amounts = extraction_data.get("amounts", [])
        extraction.contacts = extraction_data.get("contacts", [])
        extraction.action_items = extraction_data.get("action_items", [])
        extraction.key_points = extraction_data.get("key_points", [])
        extraction.extracted_at = datetime.utcnow()
    else:
        # 创建新记录
        extraction = EmailExtraction(
            email_id=email_id,
            summary=extraction_data.get("summary"),
            dates=extraction_data.get("dates", []),
            amounts=extraction_data.get("amounts", []),
            contacts=extraction_data.get("contacts", []),
            action_items=extraction_data.get("action_items", []),
            key_points=extraction_data.get("key_points", [])
        )
        db.add(extraction)

    await db.commit()
    await db.refresh(extraction)

    # 返回时添加 internal_attendees
    return ExtractionResponse(
        id=extraction.id,
        email_id=extraction.email_id,
        summary=extraction.summary,
        dates=extraction.dates or [],
        amounts=extraction.amounts or [],
        contacts=extraction.contacts or [],
        action_items=extraction.action_items or [],
        key_points=extraction.key_points or [],
        internal_attendees=internal_attendees,
        extracted_at=extraction.extracted_at
    )


@router.get("/extract/{email_id}", response_model=Optional[ExtractionResponse])
async def get_extraction(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取邮件的 AI 提取结果（如果存在）"""
    # 验证邮件属于当前用户
    email_result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == account.id
            )
        )
    )
    email = email_result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 获取提取结果
    result = await db.execute(
        select(EmailExtraction).where(
            EmailExtraction.email_id == email_id
        )
    )
    extraction = result.scalar_one_or_none()

    if not extraction:
        return None

    # 提取公司内部参会人员
    internal_attendees = extract_internal_attendees(email.to_email, email.cc_email)

    return ExtractionResponse(
        id=extraction.id,
        email_id=extraction.email_id,
        summary=extraction.summary,
        dates=extraction.dates or [],
        amounts=extraction.amounts or [],
        contacts=extraction.contacts or [],
        action_items=extraction.action_items or [],
        key_points=extraction.key_points or [],
        internal_attendees=internal_attendees,
        extracted_at=extraction.extracted_at
    )


@router.delete("/extract/{email_id}")
async def delete_extraction(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除邮件的 AI 提取结果"""
    # 验证邮件属于当前用户
    email_result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == account.id
            )
        )
    )
    if not email_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 删除提取结果
    result = await db.execute(
        select(EmailExtraction).where(
            EmailExtraction.email_id == email_id
        )
    )
    extraction = result.scalar_one_or_none()

    if extraction:
        await db.delete(extraction)
        await db.commit()

    return {"message": "提取结果已删除"}
