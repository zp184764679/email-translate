from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, and_, insert
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from database.database import get_db
from database.models import (
    EmailAccount, Supplier, Glossary, Email,
    SupplierDomain, SupplierContact, SupplierTag, supplier_tag_mappings
)
from routers.users import get_current_account

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


# ============ Schemas ============
class TagBrief(BaseModel):
    """标签简要信息（用于供应商列表）"""
    id: int
    name: str
    color: str


class SupplierResponse(BaseModel):
    id: int
    name: str
    email_domain: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    glossary_count: int = 0
    # AI 分类字段
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    category_reason: Optional[str] = None
    category_manual: bool = False
    category_analyzed_at: Optional[datetime] = None
    # 关联统计
    domain_count: int = 1
    contact_count: int = 0
    tags: List[TagBrief] = []
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
    """获取所有供应商（包含分类、标签、域名/联系人统计）"""
    # 获取供应商及术语表统计
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

        # 获取域名数量
        domain_count_result = await db.execute(
            select(func.count(SupplierDomain.id))
            .where(SupplierDomain.supplier_id == supplier.id)
        )
        domain_count = domain_count_result.scalar() or 0
        # 至少显示1（主域名）
        domain_count = max(domain_count, 1) if supplier.email_domain else domain_count

        # 获取联系人数量
        contact_count_result = await db.execute(
            select(func.count(SupplierContact.id))
            .where(SupplierContact.supplier_id == supplier.id)
        )
        contact_count = contact_count_result.scalar() or 0

        # 获取标签
        tags_result = await db.execute(
            select(SupplierTag)
            .join(supplier_tag_mappings, SupplierTag.id == supplier_tag_mappings.c.tag_id)
            .where(supplier_tag_mappings.c.supplier_id == supplier.id)
        )
        tags = [
            TagBrief(id=t.id, name=t.name, color=t.color)
            for t in tags_result.scalars().all()
        ]

        suppliers.append(SupplierResponse(
            id=supplier.id,
            name=supplier.name,
            email_domain=supplier.email_domain,
            contact_email=supplier.contact_email,
            notes=supplier.notes,
            glossary_count=glossary_count,
            category=supplier.category,
            category_confidence=supplier.category_confidence,
            category_reason=supplier.category_reason,
            category_manual=supplier.category_manual or False,
            category_analyzed_at=supplier.category_analyzed_at,
            domain_count=domain_count,
            contact_count=contact_count,
            tags=tags,
            created_at=supplier.created_at
        ))

    return suppliers


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个供应商（包含完整信息）"""
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

    # 获取域名数量
    domain_count_result = await db.execute(
        select(func.count(SupplierDomain.id))
        .where(SupplierDomain.supplier_id == supplier.id)
    )
    domain_count = domain_count_result.scalar() or 0
    domain_count = max(domain_count, 1) if supplier.email_domain else domain_count

    # 获取联系人数量
    contact_count_result = await db.execute(
        select(func.count(SupplierContact.id))
        .where(SupplierContact.supplier_id == supplier.id)
    )
    contact_count = contact_count_result.scalar() or 0

    # 获取标签
    tags_result = await db.execute(
        select(SupplierTag)
        .join(supplier_tag_mappings, SupplierTag.id == supplier_tag_mappings.c.tag_id)
        .where(supplier_tag_mappings.c.supplier_id == supplier.id)
    )
    tags = [
        TagBrief(id=t.id, name=t.name, color=t.color)
        for t in tags_result.scalars().all()
    ]

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        email_domain=supplier.email_domain,
        contact_email=supplier.contact_email,
        notes=supplier.notes,
        glossary_count=glossary_count,
        category=supplier.category,
        category_confidence=supplier.category_confidence,
        category_reason=supplier.category_reason,
        category_manual=supplier.category_manual or False,
        category_analyzed_at=supplier.category_analyzed_at,
        domain_count=domain_count,
        contact_count=contact_count,
        tags=tags,
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
        category=None,
        category_confidence=None,
        category_reason=None,
        category_manual=False,
        category_analyzed_at=None,
        domain_count=1 if supplier.email_domain else 0,
        contact_count=0,
        tags=[],
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

    # 获取统计数据
    glossary_count_result = await db.execute(
        select(func.count(Glossary.id)).where(Glossary.supplier_id == supplier_id)
    )
    glossary_count = glossary_count_result.scalar() or 0

    domain_count_result = await db.execute(
        select(func.count(SupplierDomain.id))
        .where(SupplierDomain.supplier_id == supplier.id)
    )
    domain_count = domain_count_result.scalar() or 0
    domain_count = max(domain_count, 1) if supplier.email_domain else domain_count

    contact_count_result = await db.execute(
        select(func.count(SupplierContact.id))
        .where(SupplierContact.supplier_id == supplier.id)
    )
    contact_count = contact_count_result.scalar() or 0

    tags_result = await db.execute(
        select(SupplierTag)
        .join(supplier_tag_mappings, SupplierTag.id == supplier_tag_mappings.c.tag_id)
        .where(supplier_tag_mappings.c.supplier_id == supplier.id)
    )
    tags = [
        TagBrief(id=t.id, name=t.name, color=t.color)
        for t in tags_result.scalars().all()
    ]

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        email_domain=supplier.email_domain,
        contact_email=supplier.contact_email,
        notes=supplier.notes,
        glossary_count=glossary_count,
        category=supplier.category,
        category_confidence=supplier.category_confidence,
        category_reason=supplier.category_reason,
        category_manual=supplier.category_manual or False,
        category_analyzed_at=supplier.category_analyzed_at,
        domain_count=domain_count,
        contact_count=contact_count,
        tags=tags,
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


# ============ 新增 Schemas ============

class SupplierDomainCreate(BaseModel):
    email_domain: str
    is_primary: bool = False
    description: Optional[str] = None


class SupplierDomainResponse(BaseModel):
    id: int
    supplier_id: int
    email_domain: str
    is_primary: bool
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierContactCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None


class SupplierContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None


class SupplierContactResponse(BaseModel):
    id: int
    supplier_id: int
    name: str
    email: str
    phone: Optional[str]
    role: Optional[str]
    department: Optional[str]
    is_primary: bool
    notes: Optional[str]
    last_contact_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierTagCreate(BaseModel):
    name: str
    color: str = "#409EFF"
    description: Optional[str] = None


class SupplierTagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class SupplierTagResponse(BaseModel):
    id: int
    name: str
    color: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierCategoryRequest(BaseModel):
    category: str


# ============ AI 分类 API ============

@router.post("/{supplier_id}/analyze-category")
async def analyze_supplier_category(
    supplier_id: int,
    force: bool = False,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """AI 分析单个供应商分类"""
    from services.supplier_analysis_service import get_supplier_analysis_service
    service = get_supplier_analysis_service()
    result = await service.analyze_supplier(db, supplier_id, force=force)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/batch-analyze")
async def batch_analyze_suppliers(
    supplier_ids: Optional[List[int]] = None,
    force: bool = False,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量分析供应商分类"""
    from services.supplier_analysis_service import get_supplier_analysis_service
    service = get_supplier_analysis_service()
    return await service.batch_analyze(db, supplier_ids, force=force)


@router.get("/category-stats")
async def get_category_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商分类统计"""
    from services.supplier_analysis_service import get_supplier_analysis_service
    service = get_supplier_analysis_service()
    return await service.get_category_stats(db)


@router.put("/{supplier_id}/category")
async def set_supplier_category(
    supplier_id: int,
    request: SupplierCategoryRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """手动设置供应商分类"""
    from services.supplier_analysis_service import get_supplier_analysis_service
    service = get_supplier_analysis_service()
    result = await service.set_manual_category(db, supplier_id, request.category)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ============ 多域名管理 API ============

@router.get("/{supplier_id}/domains", response_model=List[SupplierDomainResponse])
async def get_supplier_domains(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商的所有域名"""
    result = await db.execute(
        select(SupplierDomain)
        .where(SupplierDomain.supplier_id == supplier_id)
        .order_by(SupplierDomain.is_primary.desc(), SupplierDomain.created_at)
    )
    return result.scalars().all()


@router.post("/{supplier_id}/domains", response_model=SupplierDomainResponse)
async def add_supplier_domain(
    supplier_id: int,
    domain_data: SupplierDomainCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """添加供应商域名"""
    # 检查供应商是否存在
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 检查域名是否已存在
    existing = await db.execute(
        select(SupplierDomain).where(SupplierDomain.email_domain == domain_data.email_domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该域名已被其他供应商使用")

    # 如果是主域名，取消其他主域名
    if domain_data.is_primary:
        await db.execute(
            select(SupplierDomain)
            .where(SupplierDomain.supplier_id == supplier_id, SupplierDomain.is_primary == True)
        )
        # 更新现有主域名
        await db.execute(
            SupplierDomain.__table__.update()
            .where(SupplierDomain.supplier_id == supplier_id)
            .values(is_primary=False)
        )

    domain = SupplierDomain(
        supplier_id=supplier_id,
        email_domain=domain_data.email_domain,
        is_primary=domain_data.is_primary,
        description=domain_data.description
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@router.delete("/{supplier_id}/domains/{domain_id}")
async def delete_supplier_domain(
    supplier_id: int,
    domain_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商域名"""
    result = await db.execute(
        select(SupplierDomain).where(
            SupplierDomain.id == domain_id,
            SupplierDomain.supplier_id == supplier_id
        )
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="域名不存在")

    await db.delete(domain)
    await db.commit()
    return {"message": "域名已删除"}


# ============ 联系人管理 API ============

@router.get("/{supplier_id}/contacts", response_model=List[SupplierContactResponse])
async def get_supplier_contacts(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商的所有联系人"""
    result = await db.execute(
        select(SupplierContact)
        .where(SupplierContact.supplier_id == supplier_id)
        .order_by(SupplierContact.is_primary.desc(), SupplierContact.name)
    )
    return result.scalars().all()


@router.post("/{supplier_id}/contacts", response_model=SupplierContactResponse)
async def add_supplier_contact(
    supplier_id: int,
    contact_data: SupplierContactCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """添加供应商联系人"""
    # 检查供应商是否存在
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 如果是主要联系人，取消其他主要联系人
    if contact_data.is_primary:
        await db.execute(
            SupplierContact.__table__.update()
            .where(SupplierContact.supplier_id == supplier_id)
            .values(is_primary=False)
        )

    contact = SupplierContact(
        supplier_id=supplier_id,
        name=contact_data.name,
        email=contact_data.email,
        phone=contact_data.phone,
        role=contact_data.role,
        department=contact_data.department,
        is_primary=contact_data.is_primary,
        notes=contact_data.notes
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.put("/{supplier_id}/contacts/{contact_id}", response_model=SupplierContactResponse)
async def update_supplier_contact(
    supplier_id: int,
    contact_id: int,
    contact_data: SupplierContactUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新供应商联系人"""
    result = await db.execute(
        select(SupplierContact).where(
            SupplierContact.id == contact_id,
            SupplierContact.supplier_id == supplier_id
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    # 如果设置为主要联系人，取消其他主要联系人
    if contact_data.is_primary:
        await db.execute(
            SupplierContact.__table__.update()
            .where(SupplierContact.supplier_id == supplier_id, SupplierContact.id != contact_id)
            .values(is_primary=False)
        )

    if contact_data.name is not None:
        contact.name = contact_data.name
    if contact_data.email is not None:
        contact.email = contact_data.email
    if contact_data.phone is not None:
        contact.phone = contact_data.phone
    if contact_data.role is not None:
        contact.role = contact_data.role
    if contact_data.department is not None:
        contact.department = contact_data.department
    if contact_data.is_primary is not None:
        contact.is_primary = contact_data.is_primary
    if contact_data.notes is not None:
        contact.notes = contact_data.notes

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{supplier_id}/contacts/{contact_id}")
async def delete_supplier_contact(
    supplier_id: int,
    contact_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商联系人"""
    result = await db.execute(
        select(SupplierContact).where(
            SupplierContact.id == contact_id,
            SupplierContact.supplier_id == supplier_id
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    await db.delete(contact)
    await db.commit()
    return {"message": "联系人已删除"}


# ============ 标签管理 API ============

@router.get("/tags", response_model=List[SupplierTagResponse])
async def get_supplier_tags(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有供应商标签"""
    result = await db.execute(
        select(SupplierTag)
        .where(SupplierTag.account_id == account.id)
        .order_by(SupplierTag.name)
    )
    return result.scalars().all()


@router.post("/tags", response_model=SupplierTagResponse)
async def create_supplier_tag(
    tag_data: SupplierTagCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建供应商标签"""
    tag = SupplierTag(
        account_id=account.id,
        name=tag_data.name,
        color=tag_data.color,
        description=tag_data.description
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.put("/tags/{tag_id}", response_model=SupplierTagResponse)
async def update_supplier_tag(
    tag_id: int,
    tag_data: SupplierTagUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新供应商标签"""
    result = await db.execute(
        select(SupplierTag).where(
            SupplierTag.id == tag_id,
            SupplierTag.account_id == account.id
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    if tag_data.name is not None:
        tag.name = tag_data.name
    if tag_data.color is not None:
        tag.color = tag_data.color
    if tag_data.description is not None:
        tag.description = tag_data.description

    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}")
async def delete_supplier_tag(
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商标签"""
    result = await db.execute(
        select(SupplierTag).where(
            SupplierTag.id == tag_id,
            SupplierTag.account_id == account.id
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    await db.delete(tag)
    await db.commit()
    return {"message": "标签已删除"}


@router.get("/{supplier_id}/tags", response_model=List[SupplierTagResponse])
async def get_supplier_assigned_tags(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商已分配的标签"""
    result = await db.execute(
        select(SupplierTag)
        .join(supplier_tag_mappings, SupplierTag.id == supplier_tag_mappings.c.tag_id)
        .where(supplier_tag_mappings.c.supplier_id == supplier_id)
    )
    return result.scalars().all()


@router.post("/{supplier_id}/tags/{tag_id}")
async def add_tag_to_supplier(
    supplier_id: int,
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """为供应商添加标签"""
    # 检查供应商是否存在
    supplier_result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    if not supplier_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 检查标签是否存在
    tag_result = await db.execute(
        select(SupplierTag).where(SupplierTag.id == tag_id, SupplierTag.account_id == account.id)
    )
    if not tag_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="标签不存在")

    # 检查是否已经关联
    existing = await db.execute(
        select(supplier_tag_mappings).where(
            supplier_tag_mappings.c.supplier_id == supplier_id,
            supplier_tag_mappings.c.tag_id == tag_id
        )
    )
    if existing.first():
        return {"message": "标签已存在"}

    # 添加关联
    await db.execute(
        insert(supplier_tag_mappings).values(
            supplier_id=supplier_id,
            tag_id=tag_id
        )
    )
    await db.commit()
    return {"message": "标签已添加"}


@router.delete("/{supplier_id}/tags/{tag_id}")
async def remove_tag_from_supplier(
    supplier_id: int,
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从供应商移除标签"""
    await db.execute(
        delete(supplier_tag_mappings).where(
            supplier_tag_mappings.c.supplier_id == supplier_id,
            supplier_tag_mappings.c.tag_id == tag_id
        )
    )
    await db.commit()
    return {"message": "标签已移除"}


# ============ 导入导出 ============
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import csv
import io


class ImportResult(BaseModel):
    """导入结果"""
    total: int
    imported: int
    skipped: int
    errors: List[str]


@router.get("/export/csv")
async def export_suppliers_csv(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """导出供应商为CSV文件"""
    # 获取所有供应商及关联数据
    result = await db.execute(
        select(Supplier)
        .options(
            selectinload(Supplier.domains),
            selectinload(Supplier.contacts)
        )
        .order_by(Supplier.name)
    )
    suppliers = result.scalars().all()

    # 创建CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow([
        '供应商名称', '主域名', '联系邮箱', '备注',
        '分类', '分类置信度', '其他域名', '联系人列表'
    ])

    # 写入数据
    for s in suppliers:
        # 其他域名（排除主域名）
        other_domains = [d.email_domain for d in s.domains if not d.is_primary]

        # 联系人格式: "姓名<邮箱>(角色)"
        contacts = [
            f"{c.name}<{c.email}>({c.role or ''})"
            for c in s.contacts
        ]

        writer.writerow([
            s.name,
            s.email_domain or '',
            s.contact_email or '',
            s.notes or '',
            s.category or '',
            round(s.category_confidence * 100, 1) if s.category_confidence else '',
            ';'.join(other_domains),
            ';'.join(contacts)
        ])

    output.seek(0)

    # 添加 BOM 以支持 Excel 中文显示
    bom = '\ufeff'
    content = bom + output.getvalue()

    return StreamingResponse(
        iter([content.encode('utf-8')]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=suppliers_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        }
    )


@router.post("/import/csv", response_model=ImportResult)
async def import_suppliers_csv(
    file: UploadFile = File(...),
    skip_existing: bool = True,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从CSV文件导入供应商

    CSV格式要求:
    - 第一行为表头
    - 必须包含"供应商名称"列
    - 可选列: 主域名, 联系邮箱, 备注
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="请上传CSV文件")

    content = await file.read()

    # 尝试不同编码
    for encoding in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(status_code=400, detail="无法识别文件编码，请使用UTF-8或GBK编码")

    # 解析CSV
    reader = csv.DictReader(io.StringIO(text))

    # 验证必须列
    if '供应商名称' not in reader.fieldnames and 'name' not in reader.fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV必须包含'供应商名称'或'name'列"
        )

    total = 0
    imported = 0
    skipped = 0
    errors = []

    for row in reader:
        total += 1

        # 获取供应商名称
        name = row.get('供应商名称') or row.get('name', '').strip()
        if not name:
            errors.append(f"第{total}行: 供应商名称为空")
            continue

        # 检查是否已存在
        existing = await db.execute(
            select(Supplier).where(func.lower(Supplier.name) == name.lower())
        )
        if existing.scalar_one_or_none():
            if skip_existing:
                skipped += 1
                continue
            else:
                errors.append(f"第{total}行: 供应商'{name}'已存在")
                continue

        # 创建供应商
        supplier = Supplier(
            name=name,
            email_domain=row.get('主域名') or row.get('email_domain', '').strip() or None,
            contact_email=row.get('联系邮箱') or row.get('contact_email', '').strip() or None,
            notes=row.get('备注') or row.get('notes', '').strip() or None
        )

        db.add(supplier)
        imported += 1

    await db.commit()

    return ImportResult(
        total=total,
        imported=imported,
        skipped=skipped,
        errors=errors[:20]  # 最多返回20条错误
    )


@router.get("/export/template")
async def get_import_template():
    """获取导入模板CSV文件"""
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow(['供应商名称', '主域名', '联系邮箱', '备注'])

    # 写入示例数据
    writer.writerow(['示例供应商A', 'example-a.com', 'sales@example-a.com', '这是示例供应商'])
    writer.writerow(['示例供应商B', 'example-b.com', 'info@example-b.com', ''])

    output.seek(0)

    # 添加 BOM
    bom = '\ufeff'
    content = bom + output.getvalue()

    return StreamingResponse(
        iter([content.encode('utf-8')]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=supplier_import_template.csv"
        }
    )
