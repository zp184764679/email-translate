"""
邮件归档路由

功能：
- 归档文件夹 CRUD
- 邮件归档/取消归档
- 批量归档操作
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.database import get_db
from database.models import Email, ArchiveFolder, EmailAccount
from routers.users import get_current_account


router = APIRouter(prefix="/api/archive", tags=["archive"])


# ========== Pydantic Schemas ==========

class ArchiveFolderCreate(BaseModel):
    name: str
    folder_type: str = "custom"  # year/project/supplier/custom
    parent_id: Optional[int] = None
    description: Optional[str] = None
    color: str = "#409EFF"


class ArchiveFolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class ArchiveFolderResponse(BaseModel):
    id: int
    name: str
    folder_type: str
    parent_id: Optional[int]
    description: Optional[str]
    color: str
    email_count: int
    created_at: datetime
    children: List["ArchiveFolderResponse"] = []

    class Config:
        from_attributes = True


class ArchiveEmailRequest(BaseModel):
    folder_id: int


class BatchArchiveRequest(BaseModel):
    email_ids: List[int]
    folder_id: int


class ArchivedEmailResponse(BaseModel):
    id: int
    message_id: Optional[str]
    subject_original: Optional[str]
    subject_translated: Optional[str]
    from_email: Optional[str]
    from_name: Optional[str]
    received_at: Optional[datetime]
    archived_at: Optional[datetime]
    archive_folder_id: Optional[int]
    is_read: bool
    is_flagged: bool

    class Config:
        from_attributes = True


# ========== 归档文件夹 API ==========

@router.get("/folders", response_model=List[ArchiveFolderResponse])
async def get_archive_folders(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取归档文件夹树"""
    result = await db.execute(
        select(ArchiveFolder)
        .where(ArchiveFolder.account_id == current_account.id)
        .order_by(ArchiveFolder.folder_type, ArchiveFolder.name)
    )
    folders = result.scalars().all()

    # 构建树形结构
    folder_dict = {f.id: {
        "id": f.id,
        "name": f.name,
        "folder_type": f.folder_type,
        "parent_id": f.parent_id,
        "description": f.description,
        "color": f.color,
        "email_count": f.email_count,
        "created_at": f.created_at,
        "children": []
    } for f in folders}

    root_folders = []
    for f in folders:
        if f.parent_id and f.parent_id in folder_dict:
            folder_dict[f.parent_id]["children"].append(folder_dict[f.id])
        else:
            root_folders.append(folder_dict[f.id])

    return root_folders


@router.post("/folders", response_model=ArchiveFolderResponse)
async def create_archive_folder(
    data: ArchiveFolderCreate,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """创建归档文件夹"""
    # 验证父文件夹
    if data.parent_id:
        result = await db.execute(
            select(ArchiveFolder).where(
                ArchiveFolder.id == data.parent_id,
                ArchiveFolder.account_id == current_account.id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="父文件夹不存在")

    folder = ArchiveFolder(
        account_id=current_account.id,
        name=data.name,
        folder_type=data.folder_type,
        parent_id=data.parent_id,
        description=data.description,
        color=data.color
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return folder


@router.put("/folders/{folder_id}", response_model=ArchiveFolderResponse)
async def update_archive_folder(
    folder_id: int,
    data: ArchiveFolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """更新归档文件夹"""
    result = await db.execute(
        select(ArchiveFolder).where(
            ArchiveFolder.id == folder_id,
            ArchiveFolder.account_id == current_account.id
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if data.name is not None:
        folder.name = data.name
    if data.description is not None:
        folder.description = data.description
    if data.color is not None:
        folder.color = data.color

    folder.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(folder)

    return folder


@router.delete("/folders/{folder_id}")
async def delete_archive_folder(
    folder_id: int,
    force: bool = Query(False, description="强制删除（连同归档邮件一起取消归档）"),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """删除归档文件夹"""
    result = await db.execute(
        select(ArchiveFolder).where(
            ArchiveFolder.id == folder_id,
            ArchiveFolder.account_id == current_account.id
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 检查子文件夹
    child_result = await db.execute(
        select(func.count(ArchiveFolder.id)).where(ArchiveFolder.parent_id == folder_id)
    )
    child_count = child_result.scalar()
    if child_count > 0:
        raise HTTPException(status_code=400, detail="请先删除子文件夹")

    # 检查归档邮件
    if folder.email_count > 0 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"文件夹中有 {folder.email_count} 封归档邮件，请使用 force=true 强制删除"
        )

    # 取消归档该文件夹下的所有邮件
    await db.execute(
        update(Email)
        .where(Email.archive_folder_id == folder_id)
        .values(archive_folder_id=None, archived_at=None)
    )

    await db.delete(folder)
    await db.commit()

    return {"success": True, "message": "文件夹已删除"}


# ========== 邮件归档 API ==========

@router.post("/emails/{email_id}")
async def archive_email(
    email_id: int,
    data: ArchiveEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """归档单封邮件"""
    # 验证邮件
    result = await db.execute(
        select(Email).where(
            Email.id == email_id,
            Email.account_id == current_account.id
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 验证归档文件夹
    folder_result = await db.execute(
        select(ArchiveFolder).where(
            ArchiveFolder.id == data.folder_id,
            ArchiveFolder.account_id == current_account.id
        )
    )
    folder = folder_result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="归档文件夹不存在")

    # 如果已在其他文件夹，先减少原文件夹计数
    if email.archive_folder_id and email.archive_folder_id != data.folder_id:
        await db.execute(
            update(ArchiveFolder)
            .where(ArchiveFolder.id == email.archive_folder_id)
            .values(email_count=ArchiveFolder.email_count - 1)
        )

    # 更新邮件归档状态
    email.archived_at = datetime.utcnow()
    email.archive_folder_id = data.folder_id

    # 增加目标文件夹计数
    folder.email_count += 1

    await db.commit()

    return {"success": True, "archived_at": email.archived_at}


@router.post("/emails/{email_id}/unarchive")
async def unarchive_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """取消归档邮件"""
    result = await db.execute(
        select(Email).where(
            Email.id == email_id,
            Email.account_id == current_account.id
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    if not email.archived_at:
        raise HTTPException(status_code=400, detail="邮件未归档")

    # 减少文件夹计数
    if email.archive_folder_id:
        await db.execute(
            update(ArchiveFolder)
            .where(ArchiveFolder.id == email.archive_folder_id)
            .values(email_count=ArchiveFolder.email_count - 1)
        )

    email.archived_at = None
    email.archive_folder_id = None

    await db.commit()

    return {"success": True}


@router.post("/batch")
async def batch_archive_emails(
    data: BatchArchiveRequest,
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """批量归档邮件"""
    # 验证归档文件夹
    folder_result = await db.execute(
        select(ArchiveFolder).where(
            ArchiveFolder.id == data.folder_id,
            ArchiveFolder.account_id == current_account.id
        )
    )
    folder = folder_result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="归档文件夹不存在")

    # 获取要归档的邮件
    result = await db.execute(
        select(Email).where(
            Email.id.in_(data.email_ids),
            Email.account_id == current_account.id
        )
    )
    emails = result.scalars().all()

    archived_count = 0
    for email in emails:
        # 如果已在其他文件夹，先减少原文件夹计数
        if email.archive_folder_id and email.archive_folder_id != data.folder_id:
            await db.execute(
                update(ArchiveFolder)
                .where(ArchiveFolder.id == email.archive_folder_id)
                .values(email_count=ArchiveFolder.email_count - 1)
            )
            archived_count += 1
        elif not email.archived_at:
            archived_count += 1

        email.archived_at = datetime.utcnow()
        email.archive_folder_id = data.folder_id

    # 更新目标文件夹计数
    folder.email_count += archived_count

    await db.commit()

    return {"success": True, "archived_count": len(emails)}


@router.post("/batch/unarchive")
async def batch_unarchive_emails(
    email_ids: List[int],
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """批量取消归档"""
    result = await db.execute(
        select(Email).where(
            Email.id.in_(email_ids),
            Email.account_id == current_account.id,
            Email.archived_at.isnot(None)
        )
    )
    emails = result.scalars().all()

    # 按文件夹分组减少计数
    folder_counts = {}
    for email in emails:
        if email.archive_folder_id:
            folder_counts[email.archive_folder_id] = folder_counts.get(email.archive_folder_id, 0) + 1

        email.archived_at = None
        email.archive_folder_id = None

    # 更新文件夹计数
    for folder_id, count in folder_counts.items():
        await db.execute(
            update(ArchiveFolder)
            .where(ArchiveFolder.id == folder_id)
            .values(email_count=ArchiveFolder.email_count - count)
        )

    await db.commit()

    return {"success": True, "unarchived_count": len(emails)}


@router.get("/emails", response_model=List[ArchivedEmailResponse])
async def get_archived_emails(
    folder_id: Optional[int] = Query(None, description="文件夹ID，不传则获取所有归档邮件"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取归档邮件列表"""
    query = select(Email).where(
        Email.account_id == current_account.id,
        Email.archived_at.isnot(None)
    )

    if folder_id:
        query = query.where(Email.archive_folder_id == folder_id)

    query = query.order_by(Email.archived_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    emails = result.scalars().all()

    return emails


@router.get("/stats")
async def get_archive_stats(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取归档统计"""
    # 总归档邮件数
    total_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.archived_at.isnot(None)
        )
    )
    total_archived = total_result.scalar()

    # 文件夹数
    folder_result = await db.execute(
        select(func.count(ArchiveFolder.id)).where(
            ArchiveFolder.account_id == current_account.id
        )
    )
    folder_count = folder_result.scalar()

    # 按类型统计
    type_result = await db.execute(
        select(ArchiveFolder.folder_type, func.sum(ArchiveFolder.email_count))
        .where(ArchiveFolder.account_id == current_account.id)
        .group_by(ArchiveFolder.folder_type)
    )
    type_stats = {row[0]: row[1] or 0 for row in type_result.fetchall()}

    return {
        "total_archived": total_archived,
        "folder_count": folder_count,
        "by_type": type_stats
    }


# 自动创建年份文件夹
@router.post("/folders/auto-create-year")
async def auto_create_year_folder(
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """自动创建年份归档文件夹"""
    # 检查是否已存在
    result = await db.execute(
        select(ArchiveFolder).where(
            ArchiveFolder.account_id == current_account.id,
            ArchiveFolder.folder_type == "year",
            ArchiveFolder.name == str(year)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    folder = ArchiveFolder(
        account_id=current_account.id,
        name=str(year),
        folder_type="year",
        description=f"{year}年归档邮件",
        color="#67C23A"  # 绿色
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return folder
