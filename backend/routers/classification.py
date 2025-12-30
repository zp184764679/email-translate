"""
邮件分类路由

功能：
- 单封邮件分类
- 批量分类
- 获取分类统计
- 获取分类定义
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from database.models import Email, EmailAccount
from routers.users import get_current_account
from services.email_classifier_service import classifier_service, EMAIL_CATEGORIES


router = APIRouter(prefix="/api/classification", tags=["classification"])


# ========== Pydantic Schemas ==========

class ClassificationResult(BaseModel):
    id: int
    category: Optional[str]
    confidence: Optional[float]
    reason: Optional[str] = None
    categorized_at: Optional[str]


class BatchClassifyRequest(BaseModel):
    email_ids: List[int]
    force: bool = False


class CategoryDefinition(BaseModel):
    code: str
    name: str
    description: str


# ========== API 端点 ==========

@router.get("/categories", response_model=List[CategoryDefinition])
async def get_categories():
    """获取所有分类定义"""
    return [
        {
            "code": code,
            "name": desc.split(" - ")[0],
            "description": desc.split(" - ")[1] if " - " in desc else desc
        }
        for code, desc in EMAIL_CATEGORIES.items()
    ]


@router.post("/emails/{email_id}", response_model=ClassificationResult)
async def classify_email(
    email_id: int,
    force: bool = Query(False, description="强制重新分类"),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """分类单封邮件"""
    # 验证邮件归属
    result = await db.execute(
        select(Email).where(
            Email.id == email_id,
            Email.account_id == current_account.id
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 执行分类
    classification = await classifier_service.classify_and_save(db, email_id, force)
    if not classification:
        raise HTTPException(status_code=500, detail="分类失败")

    return ClassificationResult(
        id=classification["id"],
        category=classification.get("category"),
        confidence=classification.get("confidence"),
        reason=classification.get("reason"),
        categorized_at=classification.get("categorized_at").isoformat() if classification.get("categorized_at") else None
    )


@router.post("/batch")
async def batch_classify_emails(
    data: BatchClassifyRequest,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """批量分类邮件"""
    # 验证邮件归属
    result = await db.execute(
        select(Email.id).where(
            Email.id.in_(data.email_ids),
            Email.account_id == current_account.id
        )
    )
    valid_ids = [row[0] for row in result.fetchall()]

    if not valid_ids:
        raise HTTPException(status_code=404, detail="没有找到有效的邮件")

    # 执行批量分类
    stats = await classifier_service.batch_classify(db, valid_ids, data.force)

    return stats


@router.get("/stats")
async def get_classification_stats(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取分类统计"""
    # 总邮件数
    total_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id
        )
    )
    total_emails = total_result.scalar()

    # 已分类数
    classified_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.ai_category.isnot(None)
        )
    )
    classified_count = classified_result.scalar()

    # 各分类数量
    category_result = await db.execute(
        select(Email.ai_category, func.count(Email.id))
        .where(
            Email.account_id == current_account.id,
            Email.ai_category.isnot(None)
        )
        .group_by(Email.ai_category)
    )
    category_stats = {row[0]: row[1] for row in category_result.fetchall()}

    # 平均置信度
    confidence_result = await db.execute(
        select(func.avg(Email.ai_category_confidence)).where(
            Email.account_id == current_account.id,
            Email.ai_category_confidence.isnot(None)
        )
    )
    avg_confidence = confidence_result.scalar() or 0

    return {
        "total_emails": total_emails,
        "classified_count": classified_count,
        "unclassified_count": total_emails - classified_count,
        "classification_rate": round(classified_count / total_emails * 100, 1) if total_emails > 0 else 0,
        "average_confidence": round(avg_confidence, 2),
        "by_category": category_stats
    }


@router.post("/auto-classify")
async def auto_classify_unclassified(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """自动分类所有未分类邮件"""
    # 获取未分类的邮件ID
    result = await db.execute(
        select(Email.id).where(
            Email.account_id == current_account.id,
            Email.ai_category.is_(None)
        )
        .order_by(Email.received_at.desc())
        .limit(limit)
    )
    email_ids = [row[0] for row in result.fetchall()]

    if not email_ids:
        return {"message": "没有需要分类的邮件", "classified": 0}

    # 执行批量分类
    stats = await classifier_service.batch_classify(db, email_ids, force=False)

    return stats


@router.get("/emails/{email_id}")
async def get_email_classification(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取邮件的分类结果"""
    result = await db.execute(
        select(Email).where(
            Email.id == email_id,
            Email.account_id == current_account.id
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    if not email.ai_category:
        return {"id": email_id, "classified": False}

    return {
        "id": email_id,
        "classified": True,
        "category": email.ai_category,
        "category_name": EMAIL_CATEGORIES.get(email.ai_category, "未知").split(" - ")[0],
        "confidence": email.ai_category_confidence,
        "categorized_at": email.ai_categorized_at.isoformat() if email.ai_categorized_at else None
    }
