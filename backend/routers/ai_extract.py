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


class ExtractionResponse(BaseModel):
    id: int
    email_id: int
    summary: Optional[str]
    dates: List[dict]
    amounts: List[dict]
    contacts: List[dict]
    action_items: List[dict]
    key_points: List[str]
    extracted_at: datetime

    class Config:
        from_attributes = True


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

    # 检查是否已有提取结果
    if not force:
        existing_result = await db.execute(
            select(EmailExtraction).where(
                EmailExtraction.email_id == email_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

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

    return extraction


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
    if not email_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 获取提取结果
    result = await db.execute(
        select(EmailExtraction).where(
            EmailExtraction.email_id == email_id
        )
    )
    extraction = result.scalar_one_or_none()

    return extraction


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
