from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from database.database import get_db
from database.models import EmailAccount, Supplier, Glossary, Email
from routers.users import get_current_account

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


# ============ Schemas ============
class SupplierResponse(BaseModel):
    id: int
    name: str
    email_domain: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    glossary_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierCreate(BaseModel):
    name: str
    email_domain: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    email_domain: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class SupplierStatsResponse(BaseModel):
    """供应商统计响应"""
    supplier_id: int
    supplier_name: str
    email_domain: Optional[str]
    total_emails: int
    received_emails: int
    sent_emails: int
    unread_emails: int
    translated_emails: int
    last_email_date: Optional[datetime]
    emails_last_7_days: int
    emails_last_30_days: int
    glossary_count: int


class AllSuppliersStatsResponse(BaseModel):
    """所有供应商统计汇总"""
    total_suppliers: int
    total_emails_from_suppliers: int
    suppliers_with_stats: List[SupplierStatsResponse]
    most_active_supplier: Optional[dict] = None
    suppliers_without_emails: List[dict] = []


# ============ Routes ============
@router.get("", response_model=List[SupplierResponse])
async def get_suppliers(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有供应商"""
    result = await db.execute(
        select(
            Supplier,
            func.count(Glossary.id).label("glossary_count")
        )
        .outerjoin(Glossary, Supplier.id == Glossary.supplier_id)
        .group_by(Supplier.id)
        .order_by(Supplier.name)
    )

    suppliers = []
    for row in result.all():
        supplier = row[0]
        glossary_count = row[1]
        suppliers.append(SupplierResponse(
            id=supplier.id,
            name=supplier.name,
            email_domain=supplier.email_domain,
            contact_email=supplier.contact_email,
            notes=supplier.notes,
            glossary_count=glossary_count,
            created_at=supplier.created_at
        ))

    return suppliers


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个供应商"""
    result = await db.execute(
        select(
            Supplier,
            func.count(Glossary.id).label("glossary_count")
        )
        .outerjoin(Glossary, Supplier.id == Glossary.supplier_id)
        .where(Supplier.id == supplier_id)
        .group_by(Supplier.id)
    )
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="供应商不存在")

    supplier = row[0]
    glossary_count = row[1]

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        email_domain=supplier.email_domain,
        contact_email=supplier.contact_email,
        notes=supplier.notes,
        glossary_count=glossary_count,
        created_at=supplier.created_at
    )


@router.post("", response_model=SupplierResponse)
async def create_supplier(
    supplier_data: SupplierCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建供应商"""
    supplier = Supplier(
        name=supplier_data.name,
        email_domain=supplier_data.email_domain,
        contact_email=supplier_data.contact_email,
        notes=supplier_data.notes
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        email_domain=supplier.email_domain,
        contact_email=supplier.contact_email,
        notes=supplier.notes,
        glossary_count=0,
        created_at=supplier.created_at
    )


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: int,
    supplier_update: SupplierUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新供应商"""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")

    if supplier_update.name is not None:
        supplier.name = supplier_update.name
    if supplier_update.email_domain is not None:
        supplier.email_domain = supplier_update.email_domain
    if supplier_update.contact_email is not None:
        supplier.contact_email = supplier_update.contact_email
    if supplier_update.notes is not None:
        supplier.notes = supplier_update.notes

    await db.commit()

    count_result = await db.execute(
        select(func.count(Glossary.id)).where(Glossary.supplier_id == supplier_id)
    )
    glossary_count = count_result.scalar() or 0

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        email_domain=supplier.email_domain,
        contact_email=supplier.contact_email,
        notes=supplier.notes,
        glossary_count=glossary_count,
        created_at=supplier.created_at
    )


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商"""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")

    await db.execute(delete(Supplier).where(Supplier.id == supplier_id))
    await db.commit()

    return {"message": "供应商已删除"}


# ============ 供应商统计 API ============
@router.get("/stats/all", response_model=AllSuppliersStatsResponse)
async def get_all_suppliers_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有供应商的邮件统计汇总"""
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # 获取所有供应商
    supplier_result = await db.execute(
        select(Supplier).order_by(Supplier.name)
    )
    suppliers = supplier_result.scalars().all()

    suppliers_with_stats = []
    total_emails_from_suppliers = 0
    most_active_supplier = None
    max_emails = 0
    suppliers_without_emails = []

    for supplier in suppliers:
        if not supplier.email_domain:
            suppliers_without_emails.append({
                "id": supplier.id,
                "name": supplier.name,
                "reason": "未设置邮箱域名"
            })
            continue

        domain = supplier.email_domain.lower()

        # 统计该供应商的邮件
        # 收到的邮件（发件人域名匹配）
        received_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%")
            )
        )
        received_count = received_result.scalar() or 0

        # 发送的邮件（收件人域名匹配）
        sent_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.recipients).like(f"%@{domain}%")
            )
        )
        sent_count = sent_result.scalar() or 0

        total_emails = received_count + sent_count

        if total_emails == 0:
            suppliers_without_emails.append({
                "id": supplier.id,
                "name": supplier.name,
                "email_domain": supplier.email_domain,
                "reason": "无邮件往来记录"
            })
            continue

        # 未读邮件
        unread_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%"),
                Email.is_read == False
            )
        )
        unread_count = unread_result.scalar() or 0

        # 已翻译邮件
        translated_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%"),
                Email.body_translated.isnot(None)
            )
        )
        translated_count = translated_result.scalar() or 0

        # 最近邮件日期
        last_email_result = await db.execute(
            select(func.max(Email.received_at)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%")
            )
        )
        last_email_date = last_email_result.scalar()

        # 最近7天邮件
        recent_7_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%"),
                Email.received_at >= seven_days_ago
            )
        )
        recent_7_count = recent_7_result.scalar() or 0

        # 最近30天邮件
        recent_30_result = await db.execute(
            select(func.count(Email.id)).where(
                Email.account_id == account.id,
                func.lower(Email.sender).like(f"%@{domain}%"),
                Email.received_at >= thirty_days_ago
            )
        )
        recent_30_count = recent_30_result.scalar() or 0

        # 术语表数量
        glossary_result = await db.execute(
            select(func.count(Glossary.id)).where(Glossary.supplier_id == supplier.id)
        )
        glossary_count = glossary_result.scalar() or 0

        stats = SupplierStatsResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            email_domain=supplier.email_domain,
            total_emails=total_emails,
            received_emails=received_count,
            sent_emails=sent_count,
            unread_emails=unread_count,
            translated_emails=translated_count,
            last_email_date=last_email_date,
            emails_last_7_days=recent_7_count,
            emails_last_30_days=recent_30_count,
            glossary_count=glossary_count
        )
        suppliers_with_stats.append(stats)
        total_emails_from_suppliers += total_emails

        if total_emails > max_emails:
            max_emails = total_emails
            most_active_supplier = {
                "id": supplier.id,
                "name": supplier.name,
                "total_emails": total_emails
            }

    return AllSuppliersStatsResponse(
        total_suppliers=len(suppliers),
        total_emails_from_suppliers=total_emails_from_suppliers,
        suppliers_with_stats=suppliers_with_stats,
        most_active_supplier=most_active_supplier,
        suppliers_without_emails=suppliers_without_emails
    )


@router.get("/{supplier_id}/stats", response_model=SupplierStatsResponse)
async def get_supplier_stats(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个供应商的邮件统计"""
    # 获取供应商
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")

    if not supplier.email_domain:
        raise HTTPException(status_code=400, detail="该供应商未设置邮箱域名，无法统计邮件")

    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    domain = supplier.email_domain.lower()

    # 收到的邮件
    received_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%")
        )
    )
    received_count = received_result.scalar() or 0

    # 发送的邮件
    sent_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.recipients).like(f"%@{domain}%")
        )
    )
    sent_count = sent_result.scalar() or 0

    # 未读邮件
    unread_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%"),
            Email.is_read == False
        )
    )
    unread_count = unread_result.scalar() or 0

    # 已翻译邮件
    translated_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%"),
            Email.body_translated.isnot(None)
        )
    )
    translated_count = translated_result.scalar() or 0

    # 最近邮件日期
    last_email_result = await db.execute(
        select(func.max(Email.received_at)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%")
        )
    )
    last_email_date = last_email_result.scalar()

    # 最近7天邮件
    recent_7_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%"),
            Email.received_at >= seven_days_ago
        )
    )
    recent_7_count = recent_7_result.scalar() or 0

    # 最近30天邮件
    recent_30_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            func.lower(Email.sender).like(f"%@{domain}%"),
            Email.received_at >= thirty_days_ago
        )
    )
    recent_30_count = recent_30_result.scalar() or 0

    # 术语表数量
    glossary_result = await db.execute(
        select(func.count(Glossary.id)).where(Glossary.supplier_id == supplier.id)
    )
    glossary_count = glossary_result.scalar() or 0

    return SupplierStatsResponse(
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        email_domain=supplier.email_domain,
        total_emails=received_count + sent_count,
        received_emails=received_count,
        sent_emails=sent_count,
        unread_emails=unread_count,
        translated_emails=translated_count,
        last_email_date=last_email_date,
        emails_last_7_days=recent_7_count,
        emails_last_30_days=recent_30_count,
        glossary_count=glossary_count
    )
