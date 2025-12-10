from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import EmailLabel, Email, EmailAccount, email_label_mappings
from routers.users import get_current_account

router = APIRouter(prefix="/api/labels", tags=["labels"])


# ============ Schemas ============
class LabelCreate(BaseModel):
    name: str
    color: str = "#409EFF"
    description: Optional[str] = None


class LabelUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


class LabelResponse(BaseModel):
    id: int
    name: str
    color: str
    description: Optional[str]
    email_count: Optional[int] = 0
    created_at: datetime

    class Config:
        from_attributes = True


class EmailLabelAction(BaseModel):
    label_ids: List[int]


# ============ Routes ============
@router.get("", response_model=List[LabelResponse])
async def get_labels(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的所有标签"""
    result = await db.execute(
        select(EmailLabel)
        .where(EmailLabel.account_id == account.id)
        .options(selectinload(EmailLabel.emails))
        .order_by(EmailLabel.created_at.desc())
    )
    labels = result.scalars().all()

    # 添加邮件计数
    response = []
    for label in labels:
        label_dict = {
            "id": label.id,
            "name": label.name,
            "color": label.color,
            "description": label.description,
            "email_count": len(label.emails) if label.emails else 0,
            "created_at": label.created_at
        }
        response.append(label_dict)

    return response


@router.get("/{label_id}", response_model=LabelResponse)
async def get_label(
    label_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个标签"""
    result = await db.execute(
        select(EmailLabel)
        .where(EmailLabel.id == label_id, EmailLabel.account_id == account.id)
        .options(selectinload(EmailLabel.emails))
    )
    label = result.scalar_one_or_none()
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")

    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "description": label.description,
        "email_count": len(label.emails) if label.emails else 0,
        "created_at": label.created_at
    }


@router.post("", response_model=LabelResponse)
async def create_label(
    data: LabelCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建标签"""
    # 检查名称是否重复
    result = await db.execute(
        select(EmailLabel).where(
            EmailLabel.account_id == account.id,
            EmailLabel.name == data.name
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="标签名称已存在")

    label = EmailLabel(
        account_id=account.id,
        name=data.name,
        color=data.color,
        description=data.description
    )
    db.add(label)
    await db.commit()
    await db.refresh(label)

    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "description": label.description,
        "email_count": 0,
        "created_at": label.created_at
    }


@router.put("/{label_id}", response_model=LabelResponse)
async def update_label(
    label_id: int,
    data: LabelUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新标签"""
    result = await db.execute(
        select(EmailLabel)
        .where(EmailLabel.id == label_id, EmailLabel.account_id == account.id)
        .options(selectinload(EmailLabel.emails))
    )
    label = result.scalar_one_or_none()
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")

    # 检查新名称是否与其他标签重复
    if data.name and data.name != label.name:
        check = await db.execute(
            select(EmailLabel).where(
                EmailLabel.account_id == account.id,
                EmailLabel.name == data.name,
                EmailLabel.id != label_id
            )
        )
        if check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="标签名称已存在")

    if data.name is not None:
        label.name = data.name
    if data.color is not None:
        label.color = data.color
    if data.description is not None:
        label.description = data.description

    await db.commit()
    await db.refresh(label)

    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "description": label.description,
        "email_count": len(label.emails) if label.emails else 0,
        "created_at": label.created_at
    }


@router.delete("/{label_id}")
async def delete_label(
    label_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除标签"""
    result = await db.execute(
        select(EmailLabel).where(
            EmailLabel.id == label_id,
            EmailLabel.account_id == account.id
        )
    )
    label = result.scalar_one_or_none()
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")

    await db.delete(label)
    await db.commit()
    return {"message": "标签已删除"}


# ============ 邮件-标签关联 API ============
@router.post("/emails/{email_id}")
async def add_labels_to_email(
    email_id: int,
    data: EmailLabelAction,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """为邮件添加标签"""
    # 验证邮件存在且属于当前用户
    result = await db.execute(
        select(Email)
        .where(Email.id == email_id, Email.account_id == account.id)
        .options(selectinload(Email.labels))
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 获取要添加的标签
    label_result = await db.execute(
        select(EmailLabel).where(
            EmailLabel.id.in_(data.label_ids),
            EmailLabel.account_id == account.id
        )
    )
    labels = label_result.scalars().all()

    # 添加标签
    for label in labels:
        if label not in email.labels:
            email.labels.append(label)

    await db.commit()

    return {"message": f"已添加 {len(labels)} 个标签"}


@router.delete("/emails/{email_id}/{label_id}")
async def remove_label_from_email(
    email_id: int,
    label_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从邮件移除标签"""
    # 验证邮件存在且属于当前用户
    result = await db.execute(
        select(Email)
        .where(Email.id == email_id, Email.account_id == account.id)
        .options(selectinload(Email.labels))
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 找到并移除标签
    label_to_remove = None
    for label in email.labels:
        if label.id == label_id:
            label_to_remove = label
            break

    if label_to_remove:
        email.labels.remove(label_to_remove)
        await db.commit()
        return {"message": "标签已移除"}
    else:
        return {"message": "邮件未包含此标签"}


@router.get("/emails/{email_id}", response_model=List[LabelResponse])
async def get_email_labels(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取邮件的所有标签"""
    result = await db.execute(
        select(Email)
        .where(Email.id == email_id, Email.account_id == account.id)
        .options(selectinload(Email.labels))
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    return [
        {
            "id": label.id,
            "name": label.name,
            "color": label.color,
            "description": label.description,
            "email_count": 0,
            "created_at": label.created_at
        }
        for label in email.labels
    ]
