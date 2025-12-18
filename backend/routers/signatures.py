from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, case
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import EmailSignature, EmailAccount
from routers.users import get_current_account

router = APIRouter(prefix="/api/signatures", tags=["signatures"])

# 预定义的签名模板类别
SIGNATURE_CATEGORIES = {
    "default": "默认签名",
    "formal": "正式场合",
    "informal": "非正式场合",
    "holiday": "节假日问候",
    "auto_reply": "自动回复",
    "follow_up": "跟进提醒",
}


# ============ Schemas ============
class SignatureCreate(BaseModel):
    name: str
    category: str = "default"
    content_chinese: str
    content_translated: Optional[str] = None
    target_language: str = "en"
    is_default: bool = False


class SignatureUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    content_chinese: Optional[str] = None
    content_translated: Optional[str] = None
    target_language: Optional[str] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None


class SignatureResponse(BaseModel):
    id: int
    name: str
    category: str = "default"
    content_chinese: Optional[str]
    content_translated: Optional[str]
    target_language: str
    is_default: bool
    sort_order: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SignatureReorderRequest(BaseModel):
    """签名重排序请求"""
    signature_ids: List[int]


class SignatureCategoryInfo(BaseModel):
    """签名类别信息"""
    key: str
    name: str
    count: int = 0


# ============ Routes ============
@router.get("", response_model=List[SignatureResponse])
async def get_signatures(
    category: Optional[str] = None,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的所有签名（可按类别过滤）"""
    query = select(EmailSignature).where(EmailSignature.account_id == account.id)

    if category:
        query = query.where(EmailSignature.category == category)

    query = query.order_by(
        EmailSignature.is_default.desc(),
        EmailSignature.sort_order,
        EmailSignature.created_at.desc()
    )

    result = await db.execute(query)
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
    # 验证类别
    if data.category and data.category not in SIGNATURE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的类别。可用类别: {', '.join(SIGNATURE_CATEGORIES.keys())}"
        )

    # 如果设置为默认，先取消其他默认签名
    if data.is_default:
        await db.execute(
            update(EmailSignature)
            .where(EmailSignature.account_id == account.id)
            .values(is_default=False)
        )

    # 获取当前最大 sort_order
    max_order_result = await db.execute(
        select(func.max(EmailSignature.sort_order)).where(
            EmailSignature.account_id == account.id
        )
    )
    max_order = max_order_result.scalar() or 0

    signature = EmailSignature(
        account_id=account.id,
        name=data.name,
        category=data.category,
        content_chinese=data.content_chinese,
        content_translated=data.content_translated,
        target_language=data.target_language,
        is_default=data.is_default,
        sort_order=max_order + 1
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

    # 验证类别
    if data.category and data.category not in SIGNATURE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的类别。可用类别: {', '.join(SIGNATURE_CATEGORIES.keys())}"
        )

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
    if data.category is not None:
        signature.category = data.category
    if data.content_chinese is not None:
        signature.content_chinese = data.content_chinese
    if data.content_translated is not None:
        signature.content_translated = data.content_translated
    if data.target_language is not None:
        signature.target_language = data.target_language
    if data.is_default is not None:
        signature.is_default = data.is_default
    if data.sort_order is not None:
        signature.sort_order = data.sort_order

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


# ============ 签名类别和排序 API ============
@router.get("/categories", response_model=List[SignatureCategoryInfo])
async def get_signature_categories(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取所有签名类别及其签名数量"""
    # 统计每个类别的签名数量
    result = await db.execute(
        select(EmailSignature.category, func.count(EmailSignature.id))
        .where(EmailSignature.account_id == account.id)
        .group_by(EmailSignature.category)
    )
    category_counts = {row[0]: row[1] for row in result.fetchall()}

    # 构建响应，包含所有预定义类别
    categories = []
    for key, name in SIGNATURE_CATEGORIES.items():
        categories.append(SignatureCategoryInfo(
            key=key,
            name=name,
            count=category_counts.get(key, 0)
        ))

    return categories


@router.post("/reorder")
async def reorder_signatures(
    data: SignatureReorderRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    批量重排序签名（拖拽排序）

    传入按新顺序排列的签名 ID 列表，自动更新 sort_order
    """
    if not data.signature_ids:
        return {"message": "无签名需要排序"}

    # 验证所有签名都属于当前用户
    result = await db.execute(
        select(EmailSignature.id).where(
            EmailSignature.account_id == account.id,
            EmailSignature.id.in_(data.signature_ids)
        )
    )
    valid_ids = set(row[0] for row in result.fetchall())

    # 过滤掉不属于当前用户的签名
    filtered_ids = [sid for sid in data.signature_ids if sid in valid_ids]

    if not filtered_ids:
        raise HTTPException(status_code=400, detail="未找到有效的签名")

    # 使用 CASE WHEN 原子性更新所有排序
    case_conditions = []
    for index, signature_id in enumerate(filtered_ids):
        case_conditions.append((EmailSignature.id == signature_id, index))

    await db.execute(
        update(EmailSignature)
        .where(EmailSignature.id.in_(filtered_ids))
        .values(sort_order=case(*case_conditions, else_=EmailSignature.sort_order))
    )
    await db.commit()

    return {
        "message": f"已更新 {len(filtered_ids)} 个签名的排序",
        "updated_count": len(filtered_ids)
    }
