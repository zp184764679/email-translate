from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import EmailFolder, Email, EmailAccount, email_folder_mappings
from routers.users import get_current_account

router = APIRouter(prefix="/api/folders", tags=["folders"])


# ============ Schemas ============
class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    color: str = "#409EFF"
    icon: str = "folder"


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class FolderResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    color: str
    icon: str
    sort_order: int
    is_system: bool
    email_count: Optional[int] = 0
    created_at: datetime
    children: List["FolderResponse"] = []

    class Config:
        from_attributes = True


# 解决递归类型引用
FolderResponse.model_rebuild()


class EmailFolderAction(BaseModel):
    email_ids: List[int]


# ============ Routes ============
@router.get("", response_model=List[FolderResponse])
async def get_folders(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的文件夹树"""
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
        .order_by(EmailFolder.sort_order, EmailFolder.created_at)
    )
    folders = result.scalars().all()

    # 构建文件夹树
    folder_dict = {}
    for folder in folders:
        folder_dict[folder.id] = {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "color": folder.color,
            "icon": folder.icon,
            "sort_order": folder.sort_order,
            "is_system": folder.is_system,
            "email_count": len(folder.emails) if folder.emails else 0,
            "created_at": folder.created_at,
            "children": []
        }

    # 构建树结构
    root_folders = []
    for folder_id, folder_data in folder_dict.items():
        if folder_data["parent_id"] is None:
            root_folders.append(folder_data)
        else:
            parent = folder_dict.get(folder_data["parent_id"])
            if parent:
                parent["children"].append(folder_data)

    return root_folders


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个文件夹"""
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.id == folder_id, EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "color": folder.color,
        "icon": folder.icon,
        "sort_order": folder.sort_order,
        "is_system": folder.is_system,
        "email_count": len(folder.emails) if folder.emails else 0,
        "created_at": folder.created_at,
        "children": []
    }


async def check_folder_depth(db: AsyncSession, parent_id: int, max_depth: int = 10) -> int:
    """
    检查文件夹嵌套深度
    返回当前深度，如果超过限制则抛出异常
    """
    depth = 0
    current_id = parent_id

    while current_id and depth < max_depth + 1:
        result = await db.execute(
            select(EmailFolder.parent_id).where(EmailFolder.id == current_id)
        )
        row = result.first()
        if not row:
            break
        current_id = row[0]
        depth += 1

    if depth >= max_depth:
        raise HTTPException(status_code=400, detail=f"文件夹嵌套深度不能超过{max_depth}级")

    return depth


@router.post("", response_model=FolderResponse)
async def create_folder(
    data: FolderCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建文件夹"""
    # 检查同级是否有重名
    parent_check = EmailFolder.parent_id == data.parent_id if data.parent_id else EmailFolder.parent_id.is_(None)
    result = await db.execute(
        select(EmailFolder).where(
            EmailFolder.account_id == account.id,
            parent_check,
            EmailFolder.name == data.name
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="同级文件夹中已存在该名称")

    # 验证父文件夹存在且属于当前用户
    if data.parent_id:
        parent_result = await db.execute(
            select(EmailFolder).where(
                EmailFolder.id == data.parent_id,
                EmailFolder.account_id == account.id
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="父文件夹不存在")

        # 检查嵌套深度限制
        await check_folder_depth(db, data.parent_id)

    folder = EmailFolder(
        account_id=account.id,
        name=data.name,
        parent_id=data.parent_id,
        color=data.color,
        icon=data.icon
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "color": folder.color,
        "icon": folder.icon,
        "sort_order": folder.sort_order,
        "is_system": folder.is_system,
        "email_count": 0,
        "created_at": folder.created_at,
        "children": []
    }


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: int,
    data: FolderUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新文件夹"""
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.id == folder_id, EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if folder.is_system:
        raise HTTPException(status_code=400, detail="系统文件夹不可修改")

    # 检查新名称是否与同级其他文件夹重复
    if data.name and data.name != folder.name:
        parent_id = data.parent_id if data.parent_id is not None else folder.parent_id
        parent_check = EmailFolder.parent_id == parent_id if parent_id else EmailFolder.parent_id.is_(None)
        check = await db.execute(
            select(EmailFolder).where(
                EmailFolder.account_id == account.id,
                parent_check,
                EmailFolder.name == data.name,
                EmailFolder.id != folder_id
            )
        )
        if check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="同级文件夹中已存在该名称")

    if data.name is not None:
        folder.name = data.name
    if data.parent_id is not None:
        # 检查循环引用：不能将自己设为父文件夹
        if data.parent_id == folder_id:
            raise HTTPException(status_code=400, detail="不能将文件夹设为自己的子文件夹")

        # 检查是否会导致循环引用（新父文件夹不能是自己的子文件夹）
        if data.parent_id:
            current_id = data.parent_id
            while current_id:
                if current_id == folder_id:
                    raise HTTPException(status_code=400, detail="不能形成循环引用")
                result = await db.execute(
                    select(EmailFolder.parent_id).where(EmailFolder.id == current_id)
                )
                row = result.first()
                if not row:
                    break
                current_id = row[0]

            # 检查深度限制
            await check_folder_depth(db, data.parent_id)

        folder.parent_id = data.parent_id
    if data.color is not None:
        folder.color = data.color
    if data.icon is not None:
        folder.icon = data.icon
    if data.sort_order is not None:
        folder.sort_order = data.sort_order

    await db.commit()
    await db.refresh(folder)

    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "color": folder.color,
        "icon": folder.icon,
        "sort_order": folder.sort_order,
        "is_system": folder.is_system,
        "email_count": len(folder.emails) if folder.emails else 0,
        "created_at": folder.created_at,
        "children": []
    }


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除文件夹"""
    result = await db.execute(
        select(EmailFolder).where(
            EmailFolder.id == folder_id,
            EmailFolder.account_id == account.id
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if folder.is_system:
        raise HTTPException(status_code=400, detail="系统文件夹不可删除")

    await db.delete(folder)
    await db.commit()
    return {"message": "文件夹已删除"}


# ============ 邮件-文件夹关联 API ============
@router.post("/{folder_id}/emails")
async def add_emails_to_folder(
    folder_id: int,
    data: EmailFolderAction,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """将邮件添加到文件夹"""
    # 验证文件夹
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.id == folder_id, EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 获取要添加的邮件
    email_result = await db.execute(
        select(Email).where(
            Email.id.in_(data.email_ids),
            Email.account_id == account.id
        )
    )
    emails = email_result.scalars().all()

    # 添加邮件到文件夹
    added = 0
    for email in emails:
        if email not in folder.emails:
            folder.emails.append(email)
            added += 1

    await db.commit()
    return {"message": f"已添加 {added} 封邮件到文件夹"}


@router.delete("/{folder_id}/emails/{email_id}")
async def remove_email_from_folder(
    folder_id: int,
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从文件夹移除邮件"""
    # 验证文件夹
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.id == folder_id, EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 找到并移除邮件
    email_to_remove = None
    for email in folder.emails:
        if email.id == email_id:
            email_to_remove = email
            break

    if email_to_remove:
        folder.emails.remove(email_to_remove)
        await db.commit()
        return {"message": "邮件已从文件夹移除"}
    else:
        return {"message": "邮件不在此文件夹中"}


@router.get("/{folder_id}/emails")
async def get_folder_emails(
    folder_id: int,
    limit: int = 50,
    offset: int = 0,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取文件夹中的邮件"""
    # 验证文件夹
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.id == folder_id, EmailFolder.account_id == account.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 查询文件夹中的邮件
    email_result = await db.execute(
        select(Email)
        .join(email_folder_mappings, Email.id == email_folder_mappings.c.email_id)
        .where(email_folder_mappings.c.folder_id == folder_id)
        .order_by(Email.received_at.desc())
        .limit(limit)
        .offset(offset)
    )
    emails = email_result.scalars().all()

    # 获取总数
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Email.id))
        .join(email_folder_mappings, Email.id == email_folder_mappings.c.email_id)
        .where(email_folder_mappings.c.folder_id == folder_id)
    )
    total = count_result.scalar()

    return {
        "emails": emails,
        "total": total
    }


# ============ 初始化系统文件夹 ============
async def create_default_folders(account_id: int, db: AsyncSession):
    """为用户创建默认系统文件夹"""
    default_folders = [
        {"name": "存档", "icon": "folder", "is_system": True, "sort_order": 1},
    ]

    for folder_data in default_folders:
        # 检查是否已存在
        result = await db.execute(
            select(EmailFolder).where(
                EmailFolder.account_id == account_id,
                EmailFolder.name == folder_data["name"],
                EmailFolder.is_system == True
            )
        )
        if not result.scalar_one_or_none():
            folder = EmailFolder(
                account_id=account_id,
                **folder_data
            )
            db.add(folder)

    await db.commit()
