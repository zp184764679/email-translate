from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import EmailSignature, EmailAccount
from routers.users import get_current_account

router = APIRouter(prefix="/api/signatures", tags=["signatures"])


# ============ Schemas ============
class SignatureCreate(BaseModel):
    name: str
    content_chinese: str
    content_translated: Optional[str] = None
    target_language: str = "en"
    is_default: bool = False


class SignatureUpdate(BaseModel):
    name: Optional[str] = None
    content_chinese: Optional[str] = None
    content_translated: Optional[str] = None
    target_language: Optional[str] = None
    is_default: Optional[bool] = None


class SignatureResponse(BaseModel):
    id: int
    name: str
    content_chinese: Optional[str]
    content_translated: Optional[str]
    target_language: str
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Routes ============
@router.get("", response_model=List[SignatureResponse])
async def get_signatures(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的所有签名"""
    result = await db.execute(
        select(EmailSignature)
        .where(EmailSignature.account_id == account.id)
        .order_by(EmailSignature.is_default.desc(), EmailSignature.created_at.desc())
    )
    return result.scalars().all()


@router.get("/default", response_model=Optional[SignatureResponse])
async def get_default_signature(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取默认签名"""
    result = await db.execute(
        select(EmailSignature).where(
            EmailSignature.account_id == account.id,
            EmailSignature.is_default == True
        )
    )
    signature = result.scalar_one_or_none()
    return signature


@router.get("/{signature_id}", response_model=SignatureResponse)
async def get_signature(
    signature_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个签名"""
    result = await db.execute(
        select(EmailSignature).where(
            EmailSignature.id == signature_id,
            EmailSignature.account_id == account.id
        )
    )
    signature = result.scalar_one_or_none()
    if not signature:
        raise HTTPException(status_code=404, detail="签名不存在")
    return signature


@router.post("", response_model=SignatureResponse)
async def create_signature(
    data: SignatureCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建签名"""
    # 如果设置为默认，先取消其他默认签名
    if data.is_default:
        await db.execute(
            update(EmailSignature)
            .where(EmailSignature.account_id == account.id)
            .values(is_default=False)
        )

    signature = EmailSignature(
        account_id=account.id,
        name=data.name,
        content_chinese=data.content_chinese,
        content_translated=data.content_translated,
        target_language=data.target_language,
        is_default=data.is_default
    )
    db.add(signature)
    await db.commit()
    await db.refresh(signature)
    return signature


@router.put("/{signature_id}", response_model=SignatureResponse)
async def update_signature(
    signature_id: int,
    data: SignatureUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新签名"""
    result = await db.execute(
        select(EmailSignature).where(
            EmailSignature.id == signature_id,
            EmailSignature.account_id == account.id
        )
    )
    signature = result.scalar_one_or_none()
    if not signature:
        raise HTTPException(status_code=404, detail="签名不存在")

    # 如果设置为默认，先取消其他默认签名
    if data.is_default:
        await db.execute(
            update(EmailSignature)
            .where(EmailSignature.account_id == account.id, EmailSignature.id != signature_id)
            .values(is_default=False)
        )

    # 更新字段
    if data.name is not None:
        signature.name = data.name
    if data.content_chinese is not None:
        signature.content_chinese = data.content_chinese
    if data.content_translated is not None:
        signature.content_translated = data.content_translated
    if data.target_language is not None:
        signature.target_language = data.target_language
    if data.is_default is not None:
        signature.is_default = data.is_default

    await db.commit()
    await db.refresh(signature)
    return signature


@router.delete("/{signature_id}")
async def delete_signature(
    signature_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除签名"""
    result = await db.execute(
        select(EmailSignature).where(
            EmailSignature.id == signature_id,
            EmailSignature.account_id == account.id
        )
    )
    signature = result.scalar_one_or_none()
    if not signature:
        raise HTTPException(status_code=404, detail="签名不存在")

    await db.delete(signature)
    await db.commit()
    return {"message": "签名已删除"}


@router.post("/{signature_id}/set-default")
async def set_default_signature(
    signature_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """设置默认签名"""
    # 验证签名存在
    result = await db.execute(
        select(EmailSignature).where(
            EmailSignature.id == signature_id,
            EmailSignature.account_id == account.id
        )
    )
    signature = result.scalar_one_or_none()
    if not signature:
        raise HTTPException(status_code=404, detail="签名不存在")

    # 取消所有默认
    await db.execute(
        update(EmailSignature)
        .where(EmailSignature.account_id == account.id)
        .values(is_default=False)
    )

    # 设置新默认
    signature.is_default = True
    await db.commit()

    return {"message": "已设置为默认签名"}
