"""审批人组管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import ApproverGroup, ApproverGroupMember, EmailAccount
from routers.users import get_current_account

router = APIRouter(prefix="/api/approval-groups", tags=["approval-groups"])


# ============ Schemas ============
class GroupMemberInfo(BaseModel):
    id: int
    email: str


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    member_ids: List[int] = []  # 初始成员ID列表


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    owner_id: int
    created_at: datetime
    members: List[GroupMemberInfo] = []

    class Config:
        from_attributes = True


class AddMemberRequest(BaseModel):
    member_id: int


# ============ Routes ============
@router.get("", response_model=List[GroupResponse])
async def get_my_groups(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户创建的审批人组列表"""
    result = await db.execute(
        select(ApproverGroup)
        .options(selectinload(ApproverGroup.members).selectinload(ApproverGroupMember.member))
        .where(ApproverGroup.owner_id == account.id)
        .order_by(ApproverGroup.created_at.desc())
    )
    groups = result.scalars().all()

    # 构建响应
    response = []
    for group in groups:
        members = [
            GroupMemberInfo(id=m.member.id, email=m.member.email)
            for m in group.members if m.member
        ]
        response.append(GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            owner_id=group.owner_id,
            created_at=group.created_at,
            members=members
        ))

    return response


@router.get("/available", response_model=List[GroupResponse])
async def get_available_groups(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取可用于提交审批的组（我创建的 + 我所在的组）"""
    # 查询我创建的组
    my_groups_result = await db.execute(
        select(ApproverGroup)
        .options(selectinload(ApproverGroup.members).selectinload(ApproverGroupMember.member))
        .where(ApproverGroup.owner_id == account.id)
    )
    my_groups = my_groups_result.scalars().all()

    # 查询我所在的组（作为成员）
    member_groups_result = await db.execute(
        select(ApproverGroup)
        .options(selectinload(ApproverGroup.members).selectinload(ApproverGroupMember.member))
        .join(ApproverGroupMember, ApproverGroup.id == ApproverGroupMember.group_id)
        .where(ApproverGroupMember.member_id == account.id)
    )
    member_groups = member_groups_result.scalars().all()

    # 合并去重
    all_groups = {g.id: g for g in my_groups}
    for g in member_groups:
        all_groups[g.id] = g

    # 构建响应
    response = []
    for group in all_groups.values():
        members = [
            GroupMemberInfo(id=m.member.id, email=m.member.email)
            for m in group.members if m.member
        ]
        response.append(GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            owner_id=group.owner_id,
            created_at=group.created_at,
            members=members
        ))

    return sorted(response, key=lambda x: x.created_at, reverse=True)


@router.post("", response_model=GroupResponse)
async def create_group(
    group: GroupCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建审批人组"""
    # 验证组名不为空
    if not group.name or not group.name.strip():
        raise HTTPException(status_code=400, detail="组名不能为空")

    # 创建组
    new_group = ApproverGroup(
        name=group.name.strip(),
        description=group.description,
        owner_id=account.id
    )
    db.add(new_group)
    await db.flush()

    # 添加初始成员
    members_info = []
    if group.member_ids:
        for member_id in group.member_ids:
            # 验证成员存在
            member_result = await db.execute(
                select(EmailAccount).where(EmailAccount.id == member_id)
            )
            member = member_result.scalar_one_or_none()
            if member:
                new_member = ApproverGroupMember(
                    group_id=new_group.id,
                    member_id=member_id
                )
                db.add(new_member)
                members_info.append(GroupMemberInfo(id=member.id, email=member.email))

    await db.commit()

    return GroupResponse(
        id=new_group.id,
        name=new_group.name,
        description=new_group.description,
        owner_id=new_group.owner_id,
        created_at=new_group.created_at,
        members=members_info
    )


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    group_update: GroupUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新审批人组信息"""
    result = await db.execute(
        select(ApproverGroup)
        .options(selectinload(ApproverGroup.members).selectinload(ApproverGroupMember.member))
        .where(ApproverGroup.id == group_id, ApproverGroup.owner_id == account.id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="审批人组不存在或无权限")

    # 更新字段
    if group_update.name is not None:
        if not group_update.name.strip():
            raise HTTPException(status_code=400, detail="组名不能为空")
        group.name = group_update.name.strip()

    if group_update.description is not None:
        group.description = group_update.description

    await db.commit()

    # 构建响应
    members = [
        GroupMemberInfo(id=m.member.id, email=m.member.email)
        for m in group.members if m.member
    ]

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_id=group.owner_id,
        created_at=group.created_at,
        members=members
    )


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除审批人组"""
    result = await db.execute(
        select(ApproverGroup).where(
            ApproverGroup.id == group_id,
            ApproverGroup.owner_id == account.id
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="审批人组不存在或无权限")

    await db.delete(group)
    await db.commit()

    return {"message": "审批人组已删除"}


@router.post("/{group_id}/members")
async def add_member(
    group_id: int,
    request: AddMemberRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """添加组成员"""
    # 验证组存在且当前用户是所有者
    group_result = await db.execute(
        select(ApproverGroup).where(
            ApproverGroup.id == group_id,
            ApproverGroup.owner_id == account.id
        )
    )
    group = group_result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="审批人组不存在或无权限")

    # 验证成员存在
    member_result = await db.execute(
        select(EmailAccount).where(EmailAccount.id == request.member_id)
    )
    member = member_result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="成员账户不存在")

    # 检查是否已经是成员
    existing = await db.execute(
        select(ApproverGroupMember).where(
            ApproverGroupMember.group_id == group_id,
            ApproverGroupMember.member_id == request.member_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该用户已是组成员")

    # 添加成员
    new_member = ApproverGroupMember(
        group_id=group_id,
        member_id=request.member_id
    )
    db.add(new_member)
    await db.commit()

    return {"message": "成员已添加", "member": {"id": member.id, "email": member.email}}


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(
    group_id: int,
    member_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """移除组成员"""
    # 验证组存在且当前用户是所有者
    group_result = await db.execute(
        select(ApproverGroup).where(
            ApproverGroup.id == group_id,
            ApproverGroup.owner_id == account.id
        )
    )
    group = group_result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="审批人组不存在或无权限")

    # 删除成员
    result = await db.execute(
        delete(ApproverGroupMember).where(
            ApproverGroupMember.group_id == group_id,
            ApproverGroupMember.member_id == member_id
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="成员不存在")

    await db.commit()

    return {"message": "成员已移除"}
