"""
日历事件提醒任务

定时检查需要提醒的事件，通过 WebSocket 推送到前端
"""
from celery import shared_task
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import asyncio


@shared_task(name="tasks.reminder_tasks.check_event_reminders")
def check_event_reminders():
    """
    检查需要提醒的日历事件

    每分钟运行一次，查找：
    - 未提醒的事件
    - 当前时间 >= start_time - reminder_minutes
    - 事件还未开始
    """
    # 使用 asyncio.run() 替代 get_event_loop() 以兼容 Python 3.10+
    return asyncio.run(_check_reminders_async())


async def _check_reminders_async():
    """异步检查提醒"""
    from config import get_settings
    from database.models import CalendarEvent
    from websocket import manager

    settings = get_settings()

    # 创建数据库连接
    db_url = f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}?charset=utf8mb4"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime.utcnow()
    reminders_sent = 0

    async with async_session() as db:
        try:
            # 查找需要提醒的事件
            # 条件：未提醒 + 当前时间在提醒窗口内 + 事件未开始
            result = await db.execute(
                select(CalendarEvent).where(
                    and_(
                        CalendarEvent.reminded_at.is_(None),  # 未提醒
                        CalendarEvent.start_time > now,  # 事件还未开始
                    )
                )
            )
            events = result.scalars().all()

            for event in events:
                # 计算提醒时间
                reminder_time = event.start_time - timedelta(minutes=event.reminder_minutes or 15)

                # 如果当前时间已到达提醒时间
                if now >= reminder_time:
                    # 发送提醒
                    await send_reminder(event, manager)

                    # 标记为已提醒
                    event.reminded_at = now
                    reminders_sent += 1

            if reminders_sent > 0:
                await db.commit()
                print(f"[ReminderTask] Sent {reminders_sent} reminders")

        except Exception as e:
            print(f"[ReminderTask] Error checking reminders: {e}")
            await db.rollback()
        finally:
            await engine.dispose()

    return {"reminders_sent": reminders_sent}


async def send_reminder(event, manager):
    """
    发送事件提醒到前端

    Args:
        event: CalendarEvent 对象
        manager: WebSocket 连接管理器
    """
    # 计算距离开始的时间
    now = datetime.utcnow()
    minutes_until = int((event.start_time - now).total_seconds() / 60)

    reminder_data = {
        "event_id": event.id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "all_day": event.all_day,
        "color": event.color,
        "email_id": event.email_id,
        "minutes_until": minutes_until,
    }

    # 通过 WebSocket 推送到对应账户
    await manager.broadcast(
        account_id=event.account_id,
        event_type="calendar_reminder",
        data=reminder_data
    )

    print(f"[ReminderTask] Sent reminder for event {event.id} ({event.title}) to account {event.account_id}")


@shared_task(name="tasks.reminder_tasks.send_test_reminder")
def send_test_reminder(account_id: int, event_id: int = None):
    """
    发送测试提醒（用于调试）

    Args:
        account_id: 账户ID
        event_id: 可选的事件ID
    """
    # 使用 asyncio.run() 替代 get_event_loop() 以兼容 Python 3.10+
    return asyncio.run(_send_test_reminder_async(account_id, event_id))


async def _send_test_reminder_async(account_id: int, event_id: int = None):
    """异步发送测试提醒"""
    from websocket import manager

    test_data = {
        "event_id": event_id or 0,
        "title": "测试提醒",
        "description": "这是一条测试提醒消息",
        "location": "",
        "start_time": (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(minutes=75)).isoformat(),
        "all_day": False,
        "color": "#409EFF",
        "email_id": None,
        "minutes_until": 15,
    }

    await manager.broadcast(
        account_id=account_id,
        event_type="calendar_reminder",
        data=test_data
    )

    return {"success": True, "account_id": account_id}
