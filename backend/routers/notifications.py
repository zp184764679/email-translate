"""
通知中心 API

提供通知的增删改查功能
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, and_, desc
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import Notification
from routers.users import get_current_account

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ============ Schemas ============
class NotificationOut(BaseModel):
    """通知输出"""
    id: int
    type: str
    title: str
    message: Optional[str]
    related_id: Optional[int]
    related_type: Optional[str]
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime]

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """通知列表响应"""
    items: List[NotificationOut]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """未读数量响应"""
    count: int


class CreateNotificationRequest(BaseModel):
    """创建通知请求"""
    type: str
    title: str
    message: Optional[str] = None
    related_id: Optional[int] = None
    related_type: Optional[str] = None


# ============ API Endpoints ============

@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    type_filter: Optional[str] = Query(None, alias="type"),
    is_read: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """获取通知列表"""
    # 构建查询
    query = select(Notification).where(
        Notification.account_id == account.id
    )

    # 类型过滤
    if type_filter:
        query = query.where(Notification.type == type_filter)

    # 已读/未读过滤
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)

    # 按创建时间倒序
    query = query.order_by(desc(Notification.created_at))

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # 获取未读数量
    unread_query = select(func.count()).where(
        and_(
            Notification.account_id == account.id,
            Notification.is_read == False
        )
    )
    unread_count = await db.scalar(unread_query)

    # 分页
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    return NotificationListResponse(
        items=[NotificationOut.model_validate(n) for n in notifications],
        total=total or 0,
        unread_count=unread_count or 0
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """获取未读通知数量"""
    query = select(func.count()).where(
        and_(
            Notification.account_id == account.id,
            Notification.is_read == False
        )
    )
    count = await db.scalar(query)
    return UnreadCountResponse(count=count or 0)


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """标记单个通知为已读"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.account_id == account.id
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")

    notification.is_read = True
    notification.read_at = datetime.utcnow()
    await db.commit()

    return {"message": "已标记为已读"}


@router.post("/read-all")
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """标记所有通知为已读"""
    now = datetime.utcnow()
    await db.execute(
        update(Notification)
        .where(
            and_(
                Notification.account_id == account.id,
                Notification.is_read == False
            )
        )
        .values(is_read=True, read_at=now)
    )
    await db.commit()

    return {"message": "已全部标记为已读"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """删除单个通知"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.account_id == account.id
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")

    await db.delete(notification)
    await db.commit()

    return {"message": "通知已删除"}


@router.delete("")
async def clear_all_notifications(
    db: AsyncSession = Depends(get_db),
    account = Depends(get_current_account)
):
    """清空所有通知"""
    await db.execute(
        delete(Notification).where(
            Notification.account_id == account.id
        )
    )
    await db.commit()

    return {"message": "已清空所有通知"}


# ============ Helper function for creating notifications ============

async def create_notification(
    db: AsyncSession,
    account_id: int,
    type: str,
    title: str,
    message: Optional[str] = None,
    related_id: Optional[int] = None,
    related_type: Optional[str] = None
) -> Notification:
    """创建通知的辅助函数（供其他模块调用）"""
    notification = Notification(
        account_id=account_id,
        type=type,
        title=title,
        message=message,
        related_id=related_id,
        related_type=related_type
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification
