from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, insert
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import (
    EmailAccount, Customer, CustomerDomain, CustomerContact, CustomerTag, customer_tag_mappings
)
from routers.users import get_current_account

router = APIRouter(prefix="/api/customers", tags=["customers"])


# ============ Schemas ============
class TagBrief(BaseModel):
    """标签简要信息"""
    id: int
    name: str
    color: str


class CustomerResponse(BaseModel):
    id: int
    name: str
    email_domain: Optional[str]
    contact_email: Optional[str]
    country: Optional[str]
    notes: Optional[str]
    # AI 分类字段
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    category_reason: Optional[str] = None
    category_manual: bool = False
    category_analyzed_at: Optional[datetime] = None
    # 关联统计
    domain_count: int = 0
    contact_count: int = 0
    tags: List[TagBrief] = []
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerCreate(BaseModel):
    name: str
    email_domain: Optional[str] = None
    contact_email: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email_domain: Optional[str] = None
    contact_email: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


class CustomerTagCreate(BaseModel):
    name: str
    color: str = "#409EFF"
    description: Optional[str] = None


class CustomerTagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class CustomerTagResponse(BaseModel):
    id: int
    name: str
    color: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerDomainCreate(BaseModel):
    email_domain: str
    is_primary: bool = False
    description: Optional[str] = None


class CustomerDomainResponse(BaseModel):
    id: int
    customer_id: int
    email_domain: str
    is_primary: bool
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerContactCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None


class CustomerContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_primary: Optional[bool] = None
    notes: Optional[str] = None


class CustomerContactResponse(BaseModel):
    id: int
    customer_id: int
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


class CustomerCategoryRequest(BaseModel):
    category: str


# ============ 客户列表 ============
@router.get("", response_model=List[CustomerResponse])
async def get_customers(
    search: Optional[str] = None,
    category: Optional[str] = None,
    tag_id: Optional[int] = None,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有客户（支持搜索、分类筛选、标签筛选）"""
    query = select(Customer)

    # 搜索过滤
    if search:
        query = query.where(
            Customer.name.ilike(f"%{search}%") |
            Customer.email_domain.ilike(f"%{search}%") |
            Customer.contact_email.ilike(f"%{search}%")
        )

    # 分类过滤
    if category:
        query = query.where(Customer.category == category)

    # 标签过滤
    if tag_id:
        query = query.join(
            customer_tag_mappings,
            Customer.id == customer_tag_mappings.c.customer_id
        ).where(customer_tag_mappings.c.tag_id == tag_id)

    query = query.order_by(Customer.name)
    result = await db.execute(query)
    customers_raw = result.scalars().all()

    customers = []
    for customer in customers_raw:
        # 获取域名数量
        domain_count_result = await db.execute(
            select(func.count(CustomerDomain.id))
            .where(CustomerDomain.customer_id == customer.id)
        )
        domain_count = domain_count_result.scalar() or 0

        # 获取联系人数量
        contact_count_result = await db.execute(
            select(func.count(CustomerContact.id))
            .where(CustomerContact.customer_id == customer.id)
        )
        contact_count = contact_count_result.scalar() or 0

        # 获取标签
        tags_result = await db.execute(
            select(CustomerTag)
            .join(customer_tag_mappings, CustomerTag.id == customer_tag_mappings.c.tag_id)
            .where(customer_tag_mappings.c.customer_id == customer.id)
        )
        tags = [
            TagBrief(id=t.id, name=t.name, color=t.color)
            for t in tags_result.scalars().all()
        ]

        customers.append(CustomerResponse(
            id=customer.id,
            name=customer.name,
            email_domain=customer.email_domain,
            contact_email=customer.contact_email,
            country=customer.country,
            notes=customer.notes,
            category=customer.category,
            category_confidence=customer.category_confidence,
            category_reason=customer.category_reason,
            category_manual=customer.category_manual or False,
            category_analyzed_at=customer.category_analyzed_at,
            domain_count=domain_count,
            contact_count=contact_count,
            tags=tags,
            created_at=customer.created_at
        ))

    return customers


# ============ 标签管理 API（静态路由，必须在动态路由之前）============

@router.get("/tags", response_model=List[CustomerTagResponse])
async def get_customer_tags(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有客户标签"""
    result = await db.execute(
        select(CustomerTag)
        .where(CustomerTag.account_id == account.id)
        .order_by(CustomerTag.name)
    )
    return result.scalars().all()


@router.post("/tags", response_model=CustomerTagResponse)
async def create_customer_tag(
    tag_data: CustomerTagCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建客户标签"""
    tag = CustomerTag(
        account_id=account.id,
        name=tag_data.name,
        color=tag_data.color,
        description=tag_data.description
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.put("/tags/{tag_id}", response_model=CustomerTagResponse)
async def update_customer_tag(
    tag_id: int,
    tag_data: CustomerTagUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新客户标签"""
    result = await db.execute(
        select(CustomerTag).where(
            CustomerTag.id == tag_id,
            CustomerTag.account_id == account.id
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
async def delete_customer_tag(
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除客户标签"""
    result = await db.execute(
        select(CustomerTag).where(
            CustomerTag.id == tag_id,
            CustomerTag.account_id == account.id
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    await db.delete(tag)
    await db.commit()
    return {"message": "标签已删除"}


@router.get("/category-stats")
async def get_category_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取客户分类统计"""
    result = await db.execute(
        select(
            Customer.category,
            func.count(Customer.id).label("count")
        )
        .group_by(Customer.category)
    )

    stats = {}
    for row in result.all():
        category = row[0] or "未分类"
        stats[category] = row[1]

    return stats


# ============ 动态路由（/{customer_id} 开头）============

@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个客户详情"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 获取域名数量
    domain_count_result = await db.execute(
        select(func.count(CustomerDomain.id))
        .where(CustomerDomain.customer_id == customer.id)
    )
    domain_count = domain_count_result.scalar() or 0

    # 获取联系人数量
    contact_count_result = await db.execute(
        select(func.count(CustomerContact.id))
        .where(CustomerContact.customer_id == customer.id)
    )
    contact_count = contact_count_result.scalar() or 0

    # 获取标签
    tags_result = await db.execute(
        select(CustomerTag)
        .join(customer_tag_mappings, CustomerTag.id == customer_tag_mappings.c.tag_id)
        .where(customer_tag_mappings.c.customer_id == customer.id)
    )
    tags = [
        TagBrief(id=t.id, name=t.name, color=t.color)
        for t in tags_result.scalars().all()
    ]

    return CustomerResponse(
        id=customer.id,
        name=customer.name,
        email_domain=customer.email_domain,
        contact_email=customer.contact_email,
        country=customer.country,
        notes=customer.notes,
        category=customer.category,
        category_confidence=customer.category_confidence,
        category_reason=customer.category_reason,
        category_manual=customer.category_manual or False,
        category_analyzed_at=customer.category_analyzed_at,
        domain_count=domain_count,
        contact_count=contact_count,
        tags=tags,
        created_at=customer.created_at
    )


@router.post("", response_model=CustomerResponse)
async def create_customer(
    customer_data: CustomerCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建客户"""
    customer = Customer(
        name=customer_data.name,
        email_domain=customer_data.email_domain,
        contact_email=customer_data.contact_email,
        country=customer_data.country,
        notes=customer_data.notes
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    return CustomerResponse(
        id=customer.id,
        name=customer.name,
        email_domain=customer.email_domain,
        contact_email=customer.contact_email,
        country=customer.country,
        notes=customer.notes,
        category=None,
        category_confidence=None,
        category_reason=None,
        category_manual=False,
        category_analyzed_at=None,
        domain_count=0,
        contact_count=0,
        tags=[],
        created_at=customer.created_at
    )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新客户"""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    if customer_update.name is not None:
        customer.name = customer_update.name
    if customer_update.email_domain is not None:
        customer.email_domain = customer_update.email_domain
    if customer_update.contact_email is not None:
        customer.contact_email = customer_update.contact_email
    if customer_update.country is not None:
        customer.country = customer_update.country
    if customer_update.notes is not None:
        customer.notes = customer_update.notes

    await db.commit()

    # 获取统计数据
    domain_count_result = await db.execute(
        select(func.count(CustomerDomain.id))
        .where(CustomerDomain.customer_id == customer.id)
    )
    domain_count = domain_count_result.scalar() or 0

    contact_count_result = await db.execute(
        select(func.count(CustomerContact.id))
        .where(CustomerContact.customer_id == customer.id)
    )
    contact_count = contact_count_result.scalar() or 0

    tags_result = await db.execute(
        select(CustomerTag)
        .join(customer_tag_mappings, CustomerTag.id == customer_tag_mappings.c.tag_id)
        .where(customer_tag_mappings.c.customer_id == customer.id)
    )
    tags = [
        TagBrief(id=t.id, name=t.name, color=t.color)
        for t in tags_result.scalars().all()
    ]

    return CustomerResponse(
        id=customer.id,
        name=customer.name,
        email_domain=customer.email_domain,
        contact_email=customer.contact_email,
        country=customer.country,
        notes=customer.notes,
        category=customer.category,
        category_confidence=customer.category_confidence,
        category_reason=customer.category_reason,
        category_manual=customer.category_manual or False,
        category_analyzed_at=customer.category_analyzed_at,
        domain_count=domain_count,
        contact_count=contact_count,
        tags=tags,
        created_at=customer.created_at
    )


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除客户"""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    await db.execute(delete(Customer).where(Customer.id == customer_id))
    await db.commit()

    return {"message": "客户已删除"}


@router.put("/{customer_id}/category")
async def set_customer_category(
    customer_id: int,
    request: CustomerCategoryRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """手动设置客户分类"""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    customer.category = request.category
    customer.category_manual = True
    customer.category_analyzed_at = datetime.utcnow()
    customer.category_confidence = 1.0

    await db.commit()

    return {"message": "分类已更新", "category": request.category}


# ============ 多域名管理 API ============

@router.get("/{customer_id}/domains", response_model=List[CustomerDomainResponse])
async def get_customer_domains(
    customer_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取客户的所有域名"""
    result = await db.execute(
        select(CustomerDomain)
        .where(CustomerDomain.customer_id == customer_id)
        .order_by(CustomerDomain.is_primary.desc(), CustomerDomain.created_at)
    )
    return result.scalars().all()


@router.post("/{customer_id}/domains", response_model=CustomerDomainResponse)
async def add_customer_domain(
    customer_id: int,
    domain_data: CustomerDomainCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """添加客户域名"""
    # 检查客户是否存在
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="客户不存在")

    # 检查域名是否已存在
    existing = await db.execute(
        select(CustomerDomain).where(CustomerDomain.email_domain == domain_data.email_domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该域名已被其他客户使用")

    # 如果是主域名，取消其他主域名
    if domain_data.is_primary:
        await db.execute(
            CustomerDomain.__table__.update()
            .where(CustomerDomain.customer_id == customer_id)
            .values(is_primary=False)
        )

    domain = CustomerDomain(
        customer_id=customer_id,
        email_domain=domain_data.email_domain,
        is_primary=domain_data.is_primary,
        description=domain_data.description
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@router.delete("/{customer_id}/domains/{domain_id}")
async def delete_customer_domain(
    customer_id: int,
    domain_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除客户域名"""
    result = await db.execute(
        select(CustomerDomain).where(
            CustomerDomain.id == domain_id,
            CustomerDomain.customer_id == customer_id
        )
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="域名不存在")

    await db.delete(domain)
    await db.commit()
    return {"message": "域名已删除"}


# ============ 联系人管理 API ============

@router.get("/{customer_id}/contacts", response_model=List[CustomerContactResponse])
async def get_customer_contacts(
    customer_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取客户的所有联系人"""
    result = await db.execute(
        select(CustomerContact)
        .where(CustomerContact.customer_id == customer_id)
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.name)
    )
    return result.scalars().all()


@router.post("/{customer_id}/contacts", response_model=CustomerContactResponse)
async def add_customer_contact(
    customer_id: int,
    contact_data: CustomerContactCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """添加客户联系人"""
    # 检查客户是否存在
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="客户不存在")

    # 如果是主要联系人，取消其他主要联系人
    if contact_data.is_primary:
        await db.execute(
            CustomerContact.__table__.update()
            .where(CustomerContact.customer_id == customer_id)
            .values(is_primary=False)
        )

    contact = CustomerContact(
        customer_id=customer_id,
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


@router.put("/{customer_id}/contacts/{contact_id}", response_model=CustomerContactResponse)
async def update_customer_contact(
    customer_id: int,
    contact_id: int,
    contact_data: CustomerContactUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新客户联系人"""
    result = await db.execute(
        select(CustomerContact).where(
            CustomerContact.id == contact_id,
            CustomerContact.customer_id == customer_id
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    # 如果设置为主要联系人，取消其他主要联系人
    if contact_data.is_primary:
        await db.execute(
            CustomerContact.__table__.update()
            .where(CustomerContact.customer_id == customer_id, CustomerContact.id != contact_id)
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


@router.delete("/{customer_id}/contacts/{contact_id}")
async def delete_customer_contact(
    customer_id: int,
    contact_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除客户联系人"""
    result = await db.execute(
        select(CustomerContact).where(
            CustomerContact.id == contact_id,
            CustomerContact.customer_id == customer_id
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")

    await db.delete(contact)
    await db.commit()
    return {"message": "联系人已删除"}


# ============ 客户标签分配 API ============

@router.get("/{customer_id}/tags", response_model=List[CustomerTagResponse])
async def get_customer_assigned_tags(
    customer_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取客户已分配的标签"""
    result = await db.execute(
        select(CustomerTag)
        .join(customer_tag_mappings, CustomerTag.id == customer_tag_mappings.c.tag_id)
        .where(customer_tag_mappings.c.customer_id == customer_id)
    )
    return result.scalars().all()


@router.post("/{customer_id}/tags/{tag_id}")
async def add_tag_to_customer(
    customer_id: int,
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """为客户添加标签"""
    # 检查客户是否存在
    customer_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    if not customer_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="客户不存在")

    # 检查标签是否存在
    tag_result = await db.execute(
        select(CustomerTag).where(CustomerTag.id == tag_id, CustomerTag.account_id == account.id)
    )
    if not tag_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="标签不存在")

    # 检查是否已经关联
    existing = await db.execute(
        select(customer_tag_mappings).where(
            customer_tag_mappings.c.customer_id == customer_id,
            customer_tag_mappings.c.tag_id == tag_id
        )
    )
    if existing.first():
        return {"message": "标签已存在"}

    # 添加关联
    await db.execute(
        insert(customer_tag_mappings).values(
            customer_id=customer_id,
            tag_id=tag_id
        )
    )
    await db.commit()
    return {"message": "标签已添加"}


@router.delete("/{customer_id}/tags/{tag_id}")
async def remove_tag_from_customer(
    customer_id: int,
    tag_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从客户移除标签"""
    await db.execute(
        delete(customer_tag_mappings).where(
            customer_tag_mappings.c.customer_id == customer_id,
            customer_tag_mappings.c.tag_id == tag_id
        )
    )
    await db.commit()
    return {"message": "标签已移除"}
