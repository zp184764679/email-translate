"""
日历事件 API 路由
支持创建、编辑、删除日历事件，以及从邮件创建事件
支持重复事件（RRULE 格式）
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from dateutil.rrule import rrulestr
from dateutil.relativedelta import relativedelta

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
    # 重复事件字段
    recurrence_rule: Optional[str] = None  # RRULE 格式
    recurrence_end: Optional[datetime] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: Optional[bool] = None
    color: Optional[str] = None
    reminder_minutes: Optional[int] = None
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None


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
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    parent_event_id: Optional[int] = None
    is_recurring: bool = False  # 前端用于区分普通事件和重复事件
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


# ============ Helper Functions ============

def expand_recurring_event(event: CalendarEvent, start: datetime, end: datetime) -> List[dict]:
    """
    展开重复事件到指定时间范围内的所有实例

    Args:
        event: 带有 recurrence_rule 的事件
        start: 范围开始
        end: 范围结束

    Returns:
        展开后的事件列表（字典）
    """
    if not event.recurrence_rule:
        return []

    try:
        # 解析 RRULE
        rule = rrulestr(
            f"RRULE:{event.recurrence_rule}",
            dtstart=event.start_time
        )

        # 计算事件持续时间
        duration = event.end_time - event.start_time

        # 生成在范围内的所有实例
        instances = []
        recurrence_end = event.recurrence_end or end

        # 获取范围内的所有日期
        for dt in rule.between(start, min(end, recurrence_end), inc=True):
            # 跳过原始事件（已作为普通事件返回）
            if dt == event.start_time:
                continue

            instance = {
                "id": event.id,  # 虚拟实例使用相同ID但带不同时间
                "title": event.title,
                "description": event.description,
                "location": event.location,
                "start_time": dt,
                "end_time": dt + duration,
                "all_day": event.all_day,
                "color": event.color,
                "reminder_minutes": event.reminder_minutes,
                "email_id": event.email_id,
                "recurrence_rule": event.recurrence_rule,
                "recurrence_end": event.recurrence_end,
                "parent_event_id": event.id,  # 指向原始事件
                "is_recurring": True,
                "created_at": event.created_at,
                "updated_at": event.updated_at,
            }
            instances.append(instance)

        return instances

    except Exception as e:
        print(f"[Calendar] Failed to expand recurring event {event.id}: {e}")
        return []


def event_to_dict(event: CalendarEvent) -> dict:
    """将事件对象转为字典，包含 is_recurring 字段"""
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "all_day": event.all_day,
        "color": event.color,
        "reminder_minutes": event.reminder_minutes,
        "email_id": event.email_id,
        "recurrence_rule": event.recurrence_rule,
        "recurrence_end": event.recurrence_end,
        "parent_event_id": event.parent_event_id,
        "is_recurring": bool(event.recurrence_rule),
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


# ============ API Endpoints ============

@router.get("/events")
async def get_events(
    start: Optional[datetime] = Query(None, description="开始时间过滤"),
    end: Optional[datetime] = Query(None, description="结束时间过滤"),
    search: Optional[str] = Query(None, description="搜索关键词（标题、描述、地点）"),
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取日历事件列表，支持按时间范围过滤和关键词搜索
    重复事件会自动展开到指定时间范围内
    """
    query = select(CalendarEvent).where(
        CalendarEvent.account_id == account.id
    )

    # 关键词搜索
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                CalendarEvent.title.ilike(search_term),
                CalendarEvent.description.ilike(search_term),
                CalendarEvent.location.ilike(search_term)
            )
        )

    # 对于普通事件，按时间范围过滤
    # 对于重复事件，需要包含在范围内可能有实例的事件
    if start and end:
        query = query.where(
            or_(
                # 普通事件：在范围内
                and_(
                    CalendarEvent.recurrence_rule.is_(None),
                    CalendarEvent.end_time >= start,
                    CalendarEvent.start_time <= end
                ),
                # 重复事件：开始时间在范围结束前，且（无结束日期或结束日期在范围开始后）
                and_(
                    CalendarEvent.recurrence_rule.isnot(None),
                    CalendarEvent.start_time <= end,
                    or_(
                        CalendarEvent.recurrence_end.is_(None),
                        CalendarEvent.recurrence_end >= start
                    )
                )
            )
        )
    elif start:
        query = query.where(
            or_(
                CalendarEvent.end_time >= start,
                and_(
                    CalendarEvent.recurrence_rule.isnot(None),
                    or_(
                        CalendarEvent.recurrence_end.is_(None),
                        CalendarEvent.recurrence_end >= start
                    )
                )
            )
        )
    elif end:
        query = query.where(CalendarEvent.start_time <= end)

    query = query.order_by(CalendarEvent.start_time)

    result = await db.execute(query)
    events = result.scalars().all()

    # 构建返回结果，展开重复事件
    all_events = []

    for event in events:
        # 添加原始事件
        event_dict = event_to_dict(event)

        # 检查原始事件是否在范围内
        in_range = True
        if start and event.end_time < start:
            in_range = False
        if end and event.start_time > end:
            in_range = False

        if in_range:
            all_events.append(event_dict)

        # 如果是重复事件且指定了时间范围，展开实例
        if event.recurrence_rule and start and end:
            instances = expand_recurring_event(event, start, end)
            all_events.extend(instances)

    # 按开始时间排序
    all_events.sort(key=lambda x: x["start_time"])

    return all_events


@router.post("/events", response_model=EventResponse)
async def create_event(
    event_data: EventCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建新的日历事件，支持重复规则"""
    # 验证时间
    if event_data.end_time < event_data.start_time:
        raise HTTPException(status_code=400, detail="结束时间不能早于开始时间")

    # 验证重复规则格式
    if event_data.recurrence_rule:
        try:
            rrulestr(f"RRULE:{event_data.recurrence_rule}", dtstart=event_data.start_time)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"重复规则格式错误: {str(e)}")

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


# ============ Conflict Detection ============

class ConflictCheckRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    exclude_event_id: Optional[int] = None  # 编辑时排除自己


class ConflictResponse(BaseModel):
    has_conflict: bool
    conflicts: List[EventResponse]


@router.post("/events/check-conflicts", response_model=ConflictResponse)
async def check_event_conflicts(
    request: ConflictCheckRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    检测时间冲突

    检查指定时间范围内是否有其他事件存在重叠
    用于创建/编辑事件时提前警告用户
    """
    # 查询与指定时间范围重叠的事件
    # 重叠条件：existing.start < new.end AND existing.end > new.start
    query = select(CalendarEvent).where(
        and_(
            CalendarEvent.account_id == account.id,
            CalendarEvent.start_time < request.end_time,
            CalendarEvent.end_time > request.start_time
        )
    )

    # 排除指定事件（编辑时排除自己）
    if request.exclude_event_id:
        query = query.where(CalendarEvent.id != request.exclude_event_id)

    result = await db.execute(query.order_by(CalendarEvent.start_time))
    conflicts = result.scalars().all()

    return ConflictResponse(
        has_conflict=len(conflicts) > 0,
        conflicts=[event_to_dict(e) for e in conflicts]
    )
