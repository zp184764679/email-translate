"""
日历事件 API 路由
支持创建、编辑、删除日历事件，以及从邮件创建事件
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from database.database import get_db
from database.models import CalendarEvent, Email, EmailAccount
from routers.users import get_current_account

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# ============ Pydantic Schemas ============

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    color: str = "#409EFF"
    reminder_minutes: int = 15
    email_id: Optional[int] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: Optional[bool] = None
    color: Optional[str] = None
    reminder_minutes: Optional[int] = None


class EventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    location: Optional[str]
    start_time: datetime
    end_time: datetime
    all_day: bool
    color: str
    reminder_minutes: int
    email_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventFromEmailCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    all_day: bool = False
    description: Optional[str] = None


# ============ API Endpoints ============

@router.get("/events", response_model=List[EventResponse])
async def get_events(
    start: Optional[datetime] = Query(None, description="开始时间过滤"),
    end: Optional[datetime] = Query(None, description="结束时间过滤"),
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取日历事件列表，支持按时间范围过滤"""
    query = select(CalendarEvent).where(
        CalendarEvent.account_id == account.id
    )

    if start:
        query = query.where(CalendarEvent.end_time >= start)
    if end:
        query = query.where(CalendarEvent.start_time <= end)

    query = query.order_by(CalendarEvent.start_time)

    result = await db.execute(query)
    events = result.scalars().all()

    return events


@router.post("/events", response_model=EventResponse)
async def create_event(
    event_data: EventCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建新的日历事件"""
    # 验证时间
    if event_data.end_time < event_data.start_time:
        raise HTTPException(status_code=400, detail="结束时间不能早于开始时间")

    # 如果关联邮件，验证邮件存在
    if event_data.email_id:
        email_result = await db.execute(
            select(Email).where(
                and_(
                    Email.id == event_data.email_id,
                    Email.account_id == account.id
                )
            )
        )
        if not email_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="关联的邮件不存在")

    event = CalendarEvent(
        account_id=account.id,
        **event_data.model_dump()
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return event


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个事件详情"""
    result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.id == event_id,
                CalendarEvent.account_id == account.id
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    return event


@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    event_data: EventUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新日历事件"""
    result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.id == event_id,
                CalendarEvent.account_id == account.id
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 更新字段
    update_data = event_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    # 验证时间
    if event.end_time < event.start_time:
        raise HTTPException(status_code=400, detail="结束时间不能早于开始时间")

    await db.commit()
    await db.refresh(event)

    return event


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除日历事件"""
    result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.id == event_id,
                CalendarEvent.account_id == account.id
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    await db.delete(event)
    await db.commit()

    return {"message": "事件已删除"}


@router.post("/events/from-email/{email_id}", response_model=EventResponse)
async def create_event_from_email(
    email_id: int,
    event_data: EventFromEmailCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """从邮件创建日历事件"""
    # 验证邮件存在
    email_result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == account.id
            )
        )
    )
    email = email_result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 设置结束时间（默认1小时）
    end_time = event_data.end_time
    if not end_time:
        end_time = event_data.start_time + timedelta(hours=1)

    # 设置描述（默认使用邮件主题）
    description = event_data.description
    if not description:
        description = f"来自邮件: {email.subject_translated or email.subject_original}"

    event = CalendarEvent(
        account_id=account.id,
        email_id=email_id,
        title=event_data.title,
        description=description,
        start_time=event_data.start_time,
        end_time=end_time,
        all_day=event_data.all_day
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return event


@router.get("/events/by-email/{email_id}", response_model=List[EventResponse])
async def get_events_by_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取与指定邮件关联的所有事件"""
    result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.email_id == email_id,
                CalendarEvent.account_id == account.id
            )
        ).order_by(CalendarEvent.start_time)
    )
    events = result.scalars().all()

    return events
