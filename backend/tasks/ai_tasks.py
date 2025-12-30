"""
AI 相关 Celery 任务

包含：
- extract_email_info_task: AI 提取邮件信息
"""
import asyncio
import os
from datetime import datetime
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from typing import Optional

from celery_app import celery_app


def get_db_session():
    """获取同步数据库会话"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def notify_completion(account_id: int, event_type: str, data: dict):
    """发送任务完成通知"""
    try:
        from services.notification_service import notification_manager
        asyncio.get_event_loop().run_until_complete(
            notification_manager.broadcast(account_id, event_type, data)
        )
    except Exception as e:
        print(f"[Notify] Failed to send notification: {e}")


@celery_app.task(bind=True, max_retries=2, soft_time_limit=60, time_limit=90)
def extract_email_info_task(self, email_id: int, account_id: int, force: bool = False):
    """
    异步提取邮件信息（使用 vLLM AI）

    Args:
        email_id: 邮件ID
        account_id: 账户ID
        force: 是否强制重新提取

    Returns:
        dict: 提取结果
    """
    from database.models import Email, EmailExtraction
    from services.ai_extract_service import extract_email_info
    import json

    db = get_db_session()

    try:
        # 获取邮件
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            return {"success": False, "error": "Email not found", "email_id": email_id}

        # 检查是否已提取
        existing = db.query(EmailExtraction).filter(
            EmailExtraction.email_id == email_id
        ).first()

        if existing and not force:
            return {
                "success": True,
                "email_id": email_id,
                "cached": True,
                "data": {
                    "summary": existing.summary,
                    "dates": json.loads(existing.dates) if existing.dates else [],
                    "amounts": json.loads(existing.amounts) if existing.amounts else [],
                    "contacts": json.loads(existing.contacts) if existing.contacts else [],
                    "action_items": json.loads(existing.action_items) if existing.action_items else []
                }
            }

        # 发送开始通知
        notify_completion(account_id, "extraction_started", {
            "email_id": email_id
        })

        # 准备邮件内容
        subject = email.subject_original or ""
        body = email.body_original or ""
        body_translated = email.body_translated  # 优先使用翻译后的内容

        # 执行提取（使用异步函数）
        extraction_data = asyncio.run(extract_email_info(
            subject=subject,
            body=body,
            body_translated=body_translated
        ))

        if not extraction_data:
            raise Exception("AI extraction returned no data")

        # 保存或更新提取结果
        if existing:
            existing.summary = extraction_data.get("summary", "")
            existing.dates = json.dumps(extraction_data.get("dates", []), ensure_ascii=False)
            existing.amounts = json.dumps(extraction_data.get("amounts", []), ensure_ascii=False)
            existing.contacts = json.dumps(extraction_data.get("contacts", []), ensure_ascii=False)
            existing.action_items = json.dumps(extraction_data.get("action_items", []), ensure_ascii=False)
            existing.key_points = json.dumps(extraction_data.get("key_points", []), ensure_ascii=False)
            existing.extracted_at = datetime.utcnow()
        else:
            new_extraction = EmailExtraction(
                email_id=email_id,
                summary=extraction_data.get("summary", ""),
                dates=json.dumps(extraction_data.get("dates", []), ensure_ascii=False),
                amounts=json.dumps(extraction_data.get("amounts", []), ensure_ascii=False),
                contacts=json.dumps(extraction_data.get("contacts", []), ensure_ascii=False),
                action_items=json.dumps(extraction_data.get("action_items", []), ensure_ascii=False),
                key_points=json.dumps(extraction_data.get("key_points", []), ensure_ascii=False),
                extracted_at=datetime.utcnow()
            )
            db.add(new_extraction)

        db.commit()

        # 发送完成通知
        notify_completion(account_id, "extraction_complete", {
            "email_id": email_id,
            "success": True,
            "data": extraction_data
        })

        return {
            "success": True,
            "email_id": email_id,
            "data": extraction_data
        }

    except SoftTimeLimitExceeded:
        notify_completion(account_id, "extraction_timeout", {
            "email_id": email_id,
            "error": "Extraction operation timed out"
        })
        raise self.retry(countdown=15)
    except Exception as e:
        db.rollback()
        print(f"[ExtractTask] Error extracting email {email_id}: {e}")

        notify_completion(account_id, "extraction_failed", {
            "email_id": email_id,
            "error": str(e)
        })

        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, soft_time_limit=300, time_limit=360)
def batch_extract_task(self, email_ids: list, account_id: int):
    """
    批量提取邮件信息

    Args:
        email_ids: 邮件ID列表
        account_id: 账户ID

    Returns:
        dict: 批量提取结果
    """
    from celery import group

    total = len(email_ids)
    completed = 0
    failed = 0

    # 创建子任务组
    tasks = group(
        extract_email_info_task.s(email_id, account_id)
        for email_id in email_ids
    )

    # 执行并等待
    result = tasks.apply_async()

    try:
        results = result.get(timeout=300)

        for r in results:
            if r.get("success"):
                completed += 1
            else:
                failed += 1

    except Exception as e:
        print(f"[BatchExtract] Error: {e}")
        failed = total - completed

    # 发送批量完成通知
    notify_completion(account_id, "batch_extraction_complete", {
        "total": total,
        "completed": completed,
        "failed": failed
    })

    return {
        "success": True,
        "total": total,
        "completed": completed,
        "failed": failed
    }


@celery_app.task(bind=True, max_retries=2, soft_time_limit=120, time_limit=150)
def classify_email_task(self, email_id: int, account_id: int, force: bool = False):
    """
    异步分类单封邮件

    Args:
        email_id: 邮件ID
        account_id: 账户ID
        force: 是否强制重新分类

    Returns:
        dict: 分类结果
    """
    from database.models import Email
    from services.email_classifier_service import classifier_service
    from database.database import async_session
    import asyncio

    async def do_classify():
        async with async_session() as db:
            result = await classifier_service.classify_and_save(db, email_id, force)
            return result

    try:
        result = asyncio.run(do_classify())

        if result:
            notify_completion(account_id, "classification_complete", {
                "email_id": email_id,
                "category": result.get("category"),
                "confidence": result.get("confidence")
            })

        return {
            "success": True,
            "email_id": email_id,
            "data": result
        }

    except Exception as e:
        print(f"[ClassifyTask] Error classifying email {email_id}: {e}")

        notify_completion(account_id, "classification_failed", {
            "email_id": email_id,
            "error": str(e)
        })

        raise self.retry(exc=e, countdown=10)


@celery_app.task(bind=True, max_retries=1, soft_time_limit=600, time_limit=660)
def auto_classify_pending_emails(self, account_id: int = None, limit: int = 100):
    """
    自动分类未分类的邮件（定时任务）

    Args:
        account_id: 账户ID（可选，不传则处理所有账户）
        limit: 每次处理的邮件数量

    Returns:
        dict: 分类统计
    """
    from database.models import Email
    from services.email_classifier_service import classifier_service
    from database.database import async_session
    from sqlalchemy import select
    import asyncio

    async def do_batch_classify():
        async with async_session() as db:
            # 构建查询
            query = select(Email.id, Email.account_id).where(
                Email.ai_category.is_(None),
                Email.is_translated == True  # 只分类已翻译的邮件
            )
            if account_id:
                query = query.where(Email.account_id == account_id)

            query = query.order_by(Email.received_at.desc()).limit(limit)

            result = await db.execute(query)
            emails = result.fetchall()

            if not emails:
                return {"total": 0, "success": 0, "failed": 0}

            email_ids = [e[0] for e in emails]
            stats = await classifier_service.batch_classify(db, email_ids, force=False)
            return stats

    try:
        stats = asyncio.run(do_batch_classify())
        print(f"[AutoClassify] Completed: {stats}")
        return stats

    except Exception as e:
        print(f"[AutoClassify] Error: {e}")
        return {"error": str(e)}
