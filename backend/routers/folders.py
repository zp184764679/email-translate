from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update, case
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
import re

from database.database import get_db
from database.models import EmailFolder, Email, EmailAccount, email_folder_mappings
from routers.users import get_current_account

router = APIRouter(prefix="/api/folders", tags=["folders"])


# ============ Schemas ============
class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="文件夹名称")
    parent_id: Optional[int] = Field(None, ge=1, description="父文件夹ID")
    color: str = Field("#409EFF", max_length=20, description="颜色代码")
    icon: str = Field("folder", max_length=50, description="图标名称")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("文件夹名称不能为空")
        # 禁止特殊字符
        if re.search(r'[<>:"/\\|?*]', v):
            raise ValueError("文件夹名称不能包含特殊字符: < > : \" / \\ | ? *")
        return v

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v and not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError("颜色格式无效，应为 #RRGGBB")
        return v


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = Field(None, ge=1)
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = Field(None, ge=0)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("文件夹名称不能为空")
            if re.search(r'[<>:"/\\|?*]', v):
                raise ValueError("文件夹名称不能包含特殊字符")
        return v

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError("颜色格式无效，应为 #RRGGBB")
        return v


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


class FolderReorderRequest(BaseModel):
    """文件夹重排序请求"""
    folder_ids: List[int]  # 按新顺序排列的文件夹 ID 列表
    parent_id: Optional[int] = None  # 可选：只重排指定父文件夹下的子文件夹


class FolderStatsResponse(BaseModel):
    """文件夹统计响应"""
    total_folders: int
    total_emails_in_folders: int
    folders_with_counts: List[dict]
    most_used_folder: Optional[dict] = None
    empty_folders: List[dict] = []
    max_depth: int = 0


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
    force: bool = False,  # 是否强制删除（即使有关联邮件）
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除文件夹

    Args:
        folder_id: 文件夹ID
        force: 如果为 True，即使有关联邮件也会删除（邮件不会被删除，只解除关联）
    """
    result = await db.execute(
        select(EmailFolder)
        .where(
            EmailFolder.id == folder_id,
            EmailFolder.account_id == account.id
        )
        .options(selectinload(EmailFolder.emails))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if folder.is_system:
        raise HTTPException(status_code=400, detail="系统文件夹不可删除")

    # 检查是否有子文件夹
    child_result = await db.execute(
        select(func.count(EmailFolder.id)).where(EmailFolder.parent_id == folder_id)
    )
    child_count = child_result.scalar() or 0
    if child_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该文件夹包含 {child_count} 个子文件夹，请先删除子文件夹"
        )

    # 检查是否有关联邮件
    email_count = len(folder.emails) if folder.emails else 0
    if email_count > 0 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"该文件夹包含 {email_count} 封邮件，请使用 force=true 强制删除（邮件不会被删除）"
        )

    await db.delete(folder)
    await db.commit()
    return {"message": f"文件夹已删除" + (f"（已解除 {email_count} 封邮件的关联）" if email_count > 0 else "")}


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


# ============ 文件夹排序和统计 API ============
@router.post("/reorder")
async def reorder_folders(
    data: FolderReorderRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    批量重排序文件夹（拖拽排序）

    传入按新顺序排列的文件夹 ID 列表，自动更新 sort_order
    可选指定 parent_id 只重排某个父文件夹下的子文件夹
    """
    if not data.folder_ids:
        return {"message": "无文件夹需要排序"}

    # 验证所有文件夹都属于当前用户
    query = select(EmailFolder.id).where(
        EmailFolder.account_id == account.id,
        EmailFolder.id.in_(data.folder_ids),
        EmailFolder.is_system == False  # 系统文件夹不可重排
    )

    # 如果指定了父文件夹，只重排该父文件夹下的
    if data.parent_id is not None:
        if data.parent_id == 0:  # 0 表示根级别
            query = query.where(EmailFolder.parent_id.is_(None))
        else:
            query = query.where(EmailFolder.parent_id == data.parent_id)

    result = await db.execute(query)
    valid_ids = set(row[0] for row in result.fetchall())

    # 过滤掉不属于当前用户或不在指定父文件夹下的
    filtered_ids = [fid for fid in data.folder_ids if fid in valid_ids]

    if not filtered_ids:
        raise HTTPException(status_code=400, detail="未找到有效的文件夹")

    # 使用 CASE WHEN 原子性更新所有排序
    case_conditions = []
    for index, folder_id in enumerate(filtered_ids):
        case_conditions.append((EmailFolder.id == folder_id, index))

    await db.execute(
        update(EmailFolder)
        .where(EmailFolder.id.in_(filtered_ids))
        .values(sort_order=case(*case_conditions, else_=EmailFolder.sort_order))
    )
    await db.commit()

    return {
        "message": f"已更新 {len(filtered_ids)} 个文件夹的排序",
        "updated_count": len(filtered_ids)
    }


@router.get("/stats", response_model=FolderStatsResponse)
async def get_folder_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取文件夹使用统计"""
    # 获取所有文件夹及其邮件数量
    result = await db.execute(
        select(EmailFolder)
        .where(EmailFolder.account_id == account.id)
        .options(selectinload(EmailFolder.emails))
        .order_by(EmailFolder.sort_order)
    )
    folders = result.scalars().all()

    folders_with_counts = []
    total_emails_in_folders = 0
    most_used_folder = None
    max_count = 0
    empty_folders = []
    max_depth = 0

    # 计算每个文件夹的深度
    folder_depths = {}
    for folder in folders:
        depth = 0
        parent_id = folder.parent_id
        while parent_id:
            depth += 1
            parent_folder = next((f for f in folders if f.id == parent_id), None)
            parent_id = parent_folder.parent_id if parent_folder else None
        folder_depths[folder.id] = depth
        max_depth = max(max_depth, depth)

    for folder in folders:
        email_count = len(folder.emails) if folder.emails else 0
        folder_info = {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "color": folder.color,
            "is_system": folder.is_system,
            "depth": folder_depths.get(folder.id, 0),
            "email_count": email_count
        }
        folders_with_counts.append(folder_info)
        total_emails_in_folders += email_count

        if email_count > max_count:
            max_count = email_count
            most_used_folder = folder_info

        if email_count == 0 and not folder.is_system:
            empty_folders.append(folder_info)

    return {
        "total_folders": len(folders),
        "total_emails_in_folders": total_emails_in_folders,
        "folders_with_counts": folders_with_counts,
        "most_used_folder": most_used_folder,
        "empty_folders": empty_folders,
        "max_depth": max_depth
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
