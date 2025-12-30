"""
邮件统计报表路由

功能：
- 邮件量趋势（日/周/月）
- 供应商邮件量排行
- 翻译引擎使用分布
- 分类统计
- 响应时间分析
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from database.models import (
    Email, EmailAccount, Supplier, TranslationUsage,
    Draft, TranslationCache, SharedEmailTranslation
)
from routers.users import get_current_account


router = APIRouter(prefix="/api/statistics", tags=["statistics"])


# ========== Pydantic Schemas ==========

class TrendData(BaseModel):
    date: str
    count: int


class SupplierRanking(BaseModel):
    supplier_id: int
    supplier_name: str
    email_count: int
    percentage: float


class TranslationEngineStats(BaseModel):
    provider: str
    total_requests: int
    total_chars: int
    percentage: float


class CategoryStats(BaseModel):
    category: str
    count: int
    percentage: float


class OverviewStats(BaseModel):
    total_emails: int
    unread_emails: int
    translated_emails: int
    flagged_emails: int
    total_suppliers: int
    total_drafts: int
    emails_today: int
    emails_this_week: int
    emails_this_month: int


# ========== API 端点 ==========

@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取概览统计"""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    # 总邮件数
    total_result = await db.execute(
        select(func.count(Email.id)).where(Email.account_id == current_account.id)
    )
    total_emails = total_result.scalar() or 0

    # 未读邮件
    unread_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.is_read == False
        )
    )
    unread_emails = unread_result.scalar() or 0

    # 已翻译邮件
    translated_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.is_translated == True
        )
    )
    translated_emails = translated_result.scalar() or 0

    # 星标邮件
    flagged_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.is_flagged == True
        )
    )
    flagged_emails = flagged_result.scalar() or 0

    # 供应商数
    suppliers_result = await db.execute(
        select(func.count(func.distinct(Email.supplier_id))).where(
            Email.account_id == current_account.id,
            Email.supplier_id.isnot(None)
        )
    )
    total_suppliers = suppliers_result.scalar() or 0

    # 草稿数
    drafts_result = await db.execute(
        select(func.count(Draft.id)).where(
            Draft.author_id == current_account.id,
            Draft.status == "draft"
        )
    )
    total_drafts = drafts_result.scalar() or 0

    # 今日邮件
    today_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.received_at >= today_start
        )
    )
    emails_today = today_result.scalar() or 0

    # 本周邮件
    week_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.received_at >= week_start
        )
    )
    emails_this_week = week_result.scalar() or 0

    # 本月邮件
    month_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.received_at >= month_start
        )
    )
    emails_this_month = month_result.scalar() or 0

    return OverviewStats(
        total_emails=total_emails,
        unread_emails=unread_emails,
        translated_emails=translated_emails,
        flagged_emails=flagged_emails,
        total_suppliers=total_suppliers,
        total_drafts=total_drafts,
        emails_today=emails_today,
        emails_this_week=emails_this_week,
        emails_this_month=emails_this_month
    )


@router.get("/email-trend", response_model=List[TrendData])
async def get_email_trend(
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取邮件量趋势"""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    if period == "daily":
        date_format = "%Y-%m-%d"
        group_expr = func.date(Email.received_at)
    elif period == "weekly":
        date_format = "%Y-W%W"
        group_expr = func.concat(
            func.year(Email.received_at),
            '-W',
            func.lpad(func.week(Email.received_at), 2, '0')
        )
    else:  # monthly
        date_format = "%Y-%m"
        group_expr = func.date_format(Email.received_at, '%Y-%m')

    result = await db.execute(
        select(group_expr.label('date'), func.count(Email.id).label('count'))
        .where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date
        )
        .group_by(group_expr)
        .order_by(group_expr)
    )

    return [TrendData(date=str(row[0]), count=row[1]) for row in result.fetchall()]


@router.get("/supplier-ranking", response_model=List[SupplierRanking])
async def get_supplier_ranking(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取供应商邮件量排行"""
    start_date = datetime.utcnow() - timedelta(days=days)

    # 获取总邮件数（用于计算百分比）
    total_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date,
            Email.supplier_id.isnot(None)
        )
    )
    total_count = total_result.scalar() or 1

    # 获取排行
    result = await db.execute(
        select(
            Email.supplier_id,
            Supplier.name,
            func.count(Email.id).label('email_count')
        )
        .join(Supplier, Email.supplier_id == Supplier.id)
        .where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date,
            Email.supplier_id.isnot(None)
        )
        .group_by(Email.supplier_id, Supplier.name)
        .order_by(func.count(Email.id).desc())
        .limit(limit)
    )

    rankings = []
    for row in result.fetchall():
        rankings.append(SupplierRanking(
            supplier_id=row[0],
            supplier_name=row[1] or "未知供应商",
            email_count=row[2],
            percentage=round(row[2] / total_count * 100, 1)
        ))

    return rankings


@router.get("/translation-engine-stats", response_model=List[TranslationEngineStats])
async def get_translation_engine_stats(
    months: int = Query(1, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取翻译引擎使用分布"""
    # 计算月份范围
    now = datetime.utcnow()
    start_month = (now.replace(day=1) - timedelta(days=30 * (months - 1))).strftime("%Y-%m")

    result = await db.execute(
        select(
            TranslationUsage.provider,
            func.sum(TranslationUsage.total_requests).label('total_requests'),
            func.sum(TranslationUsage.total_chars).label('total_chars')
        )
        .where(TranslationUsage.year_month >= start_month)
        .group_by(TranslationUsage.provider)
    )

    stats = result.fetchall()

    # 计算总请求数
    total_requests = sum(s[1] or 0 for s in stats) or 1

    return [
        TranslationEngineStats(
            provider=row[0],
            total_requests=row[1] or 0,
            total_chars=row[2] or 0,
            percentage=round((row[1] or 0) / total_requests * 100, 1)
        )
        for row in stats
    ]


@router.get("/category-distribution", response_model=List[CategoryStats])
async def get_category_distribution(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取邮件分类分布"""
    start_date = datetime.utcnow() - timedelta(days=days)

    # 获取总分类邮件数
    total_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date,
            Email.ai_category.isnot(None)
        )
    )
    total_count = total_result.scalar() or 1

    # 获取分类统计
    result = await db.execute(
        select(Email.ai_category, func.count(Email.id).label('count'))
        .where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date,
            Email.ai_category.isnot(None)
        )
        .group_by(Email.ai_category)
        .order_by(func.count(Email.id).desc())
    )

    return [
        CategoryStats(
            category=row[0],
            count=row[1],
            percentage=round(row[1] / total_count * 100, 1)
        )
        for row in result.fetchall()
    ]


@router.get("/response-time")
async def get_response_time_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取平均响应时间分析（基于草稿发送时间与原邮件接收时间差）"""
    start_date = datetime.utcnow() - timedelta(days=days)

    # 查询已发送的草稿及其原邮件
    result = await db.execute(
        select(
            Draft.sent_at,
            Email.received_at,
            Supplier.name.label('supplier_name')
        )
        .join(Email, Draft.reply_to_email_id == Email.id)
        .outerjoin(Supplier, Email.supplier_id == Supplier.id)
        .where(
            Draft.author_id == current_account.id,
            Draft.status == "sent",
            Draft.sent_at.isnot(None),
            Draft.sent_at >= start_date
        )
    )

    response_times = []
    supplier_times = {}

    for row in result.fetchall():
        if row[0] and row[1]:
            diff = (row[0] - row[1]).total_seconds() / 3600  # 转换为小时
            if diff > 0:  # 排除异常数据
                response_times.append(diff)
                supplier = row[2] or "未知供应商"
                if supplier not in supplier_times:
                    supplier_times[supplier] = []
                supplier_times[supplier].append(diff)

    if not response_times:
        return {
            "average_hours": 0,
            "min_hours": 0,
            "max_hours": 0,
            "total_responses": 0,
            "by_supplier": []
        }

    # 按供应商平均响应时间排序
    supplier_avg = [
        {
            "supplier": s,
            "average_hours": round(sum(times) / len(times), 1),
            "response_count": len(times)
        }
        for s, times in supplier_times.items()
    ]
    supplier_avg.sort(key=lambda x: x["average_hours"])

    return {
        "average_hours": round(sum(response_times) / len(response_times), 1),
        "min_hours": round(min(response_times), 1),
        "max_hours": round(max(response_times), 1),
        "total_responses": len(response_times),
        "by_supplier": supplier_avg[:10]  # Top 10
    }


@router.get("/cache-stats")
async def get_cache_stats(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取翻译缓存统计"""
    # 缓存条目数
    cache_count_result = await db.execute(
        select(func.count(TranslationCache.id))
    )
    cache_count = cache_count_result.scalar() or 0

    # 总命中次数
    hit_count_result = await db.execute(
        select(func.sum(TranslationCache.hit_count))
    )
    total_hits = hit_count_result.scalar() or 0

    # 共享翻译数
    shared_count_result = await db.execute(
        select(func.count(SharedEmailTranslation.id))
    )
    shared_count = shared_count_result.scalar() or 0

    # 热门缓存（按命中数）
    top_cache_result = await db.execute(
        select(
            TranslationCache.source_text,
            TranslationCache.hit_count
        )
        .order_by(TranslationCache.hit_count.desc())
        .limit(5)
    )
    top_cache = [
        {"text": row[0][:50] + "..." if len(row[0]) > 50 else row[0], "hits": row[1]}
        for row in top_cache_result.fetchall()
    ]

    return {
        "cache_entries": cache_count,
        "total_cache_hits": total_hits,
        "shared_translations": shared_count,
        "estimated_savings": f"约 {total_hits} 次 API 调用",
        "top_cached": top_cache
    }


@router.get("/daily-activity")
async def get_daily_activity(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """获取每日活动热力图数据（按小时统计）"""
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            func.dayofweek(Email.received_at).label('weekday'),
            func.hour(Email.received_at).label('hour'),
            func.count(Email.id).label('count')
        )
        .where(
            Email.account_id == current_account.id,
            Email.received_at >= start_date
        )
        .group_by(
            func.dayofweek(Email.received_at),
            func.hour(Email.received_at)
        )
    )

    # 构建热力图数据
    heatmap = {}
    for row in result.fetchall():
        weekday = row[0]  # 1=Sunday, 2=Monday, ...
        hour = row[1]
        count = row[2]
        key = f"{weekday}-{hour}"
        heatmap[key] = count

    return {
        "days": days,
        "heatmap": heatmap
    }
