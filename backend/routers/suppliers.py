from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import EmailAccount, Supplier, Glossary
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
