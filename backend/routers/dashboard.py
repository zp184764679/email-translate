"""
仪表盘 API

提供邮件统计、翻译进度、邮件趋势等概览数据
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from database.database import get_db
from database.models import Email, Draft, CalendarEvent
from routers.users import get_current_account

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ============ Schemas ============
class StatCardData(BaseModel):
    """统计卡片数据"""
    today_count: int
    unread_count: int
    pending_translation: int
    pending_approval: int


class TranslationStats(BaseModel):
    """翻译统计"""
    translated: int
    untranslated: int
    translating: int
    failed: int


class DailyTrend(BaseModel):
    """每日趋势"""
    date: str
    count: int


class RecentEmail(BaseModel):
    """最近邮件"""
    id: int
    subject: str
    from_email: str
    received_at: datetime
    is_read: bool
    is_translated: bool


class TodayEvent(BaseModel):
    """今日事件"""
    id: int
    title: str
    start_time: datetime
    end_time: Optional[datetime]
    location: Optional[str]
    is_all_day: bool


class DashboardResponse(BaseModel):
    """仪表盘响应"""
    stats: StatCardData
    translation_stats: TranslationStats
    weekly_trend: List[DailyTrend]
    recent_emails: List[RecentEmail]
    today_events: List[TodayEvent]


# ============ API ============
@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """获取仪表盘统计数据"""
    account_id = current_account.id
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=6)

    # 1. 统计卡片数据
    # 今日新邮件
    today_count_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.account_id == account_id,
                Email.received_at >= today
            )
        )
    )
    today_count = today_count_result.scalar() or 0

    # 未读邮件
    unread_count_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.account_id == account_id,
                Email.is_read == False
            )
        )
    )
    unread_count = unread_count_result.scalar() or 0

    # 待翻译邮件（非中文且未翻译）
    pending_translation_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.account_id == account_id,
                Email.is_translated == False,
                Email.language_detected != 'zh',
                Email.language_detected.isnot(None)
            )
        )
    )
    pending_translation = pending_translation_result.scalar() or 0

    # 待审批草稿
    pending_approval_result = await db.execute(
        select(func.count(Draft.id)).where(
            and_(
                Draft.approver_id == account_id,
                Draft.status == 'pending_approval'
            )
        )
    )
    pending_approval = pending_approval_result.scalar() or 0

    stats = StatCardData(
        today_count=today_count,
        unread_count=unread_count,
        pending_translation=pending_translation,
        pending_approval=pending_approval
    )

    # 2. 翻译统计
    translation_stats_result = await db.execute(
        select(
            func.sum(case((Email.is_translated == True, 1), else_=0)).label('translated'),
            func.sum(case(
                (and_(
                    Email.is_translated == False,
                    Email.translation_status.notin_(['translating', 'failed'])
                ), 1),
                else_=0
            )).label('untranslated'),
            func.sum(case((Email.translation_status == 'translating', 1), else_=0)).label('translating'),
            func.sum(case((Email.translation_status == 'failed', 1), else_=0)).label('failed')
        ).where(
            and_(
                Email.account_id == account_id,
                Email.language_detected != 'zh',
                Email.language_detected.isnot(None)
            )
        )
    )
    row = translation_stats_result.first()
    translation_stats = TranslationStats(
        translated=row.translated or 0,
        untranslated=row.untranslated or 0,
        translating=row.translating or 0,
        failed=row.failed or 0
    )

    # 3. 近7天邮件趋势
    weekly_trend = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        next_day = day + timedelta(days=1)
        count_result = await db.execute(
            select(func.count(Email.id)).where(
                and_(
                    Email.account_id == account_id,
                    Email.received_at >= day,
                    Email.received_at < next_day
                )
            )
        )
        count = count_result.scalar() or 0
        weekly_trend.append(DailyTrend(
            date=day.strftime('%m-%d'),
            count=count
        ))

    # 4. 最近5封邮件
    recent_emails_result = await db.execute(
        select(Email).where(
            Email.account_id == account_id
        ).order_by(Email.received_at.desc()).limit(5)
    )
    recent_emails = [
        RecentEmail(
            id=e.id,
            subject=e.subject_translated or e.subject_original or '(无主题)',
            from_email=e.from_email,
            received_at=e.received_at,
            is_read=e.is_read,
            is_translated=e.is_translated
        )
        for e in recent_emails_result.scalars().all()
    ]

    # 5. 今日日程
    today_end = today + timedelta(days=1)
    today_events_result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.account_id == account_id,
                CalendarEvent.start_time >= today,
                CalendarEvent.start_time < today_end
            )
        ).order_by(CalendarEvent.start_time)
    )
    today_events = [
        TodayEvent(
            id=e.id,
            title=e.title,
            start_time=e.start_time,
            end_time=e.end_time,
            location=e.location,
            is_all_day=e.is_all_day
        )
        for e in today_events_result.scalars().all()
    ]

    return DashboardResponse(
        stats=stats,
        translation_stats=translation_stats,
        weekly_trend=weekly_trend,
        recent_emails=recent_emails,
        today_events=today_events
    )
