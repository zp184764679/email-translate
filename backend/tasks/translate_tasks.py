"""
翻译相关 Celery 任务

包含：
- translate_email_task: 翻译单封邮件
- batch_translate_task: 批量翻译邮件
- poll_batch_status: 轮询 Claude Batch API 状态
"""
import asyncio
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime
from typing import Optional

from celery_app import celery_app


def get_db_session():
    """获取同步数据库会话（Celery worker 使用）"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os

    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def notify_completion(account_id: int, event_type: str, data: dict):
    """发送任务完成通知"""
    try:
        from services.notification_service import notification_manager
        # 使用 asyncio.run() 替代 get_event_loop() 以兼容 Python 3.10+
        asyncio.run(
            notification_manager.broadcast(account_id, event_type, data)
        )
    except Exception as e:
        print(f"[Notify] Failed to send notification: {e}")


@celery_app.task(bind=True, max_retries=3, soft_time_limit=180, time_limit=240)
def translate_email_task(self, email_id: int, account_id: int, force: bool = False):
    """
    异步翻译单封邮件

    Args:
        email_id: 邮件ID
        account_id: 账户ID（用于通知）
        force: 是否强制重新翻译

    Returns:
        dict: 翻译结果 {success, email_id, provider}
    """
    from database.models import Email, SharedEmailTranslation, EmailAccount
    from services.translate_service import TranslateService
    from config import get_settings

    settings = get_settings()
    db = get_db_session()

    try:
        # 获取邮件
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            return {"success": False, "error": "Email not found", "email_id": email_id}

        # 检查是否已翻译
        if email.is_translated and not force:
            return {"success": True, "email_id": email_id, "cached": True}

        # 获取账户信息（用于术语表）
        account = db.query(EmailAccount).filter(EmailAccount.id == email.account_id).first()

        # 创建翻译服务（使用 Ollama）
        service = TranslateService(
            provider=settings.translate_provider,
            api_key=settings.claude_api_key,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            claude_model=settings.claude_model,
        )

        # 执行翻译
        provider_used = settings.translate_provider
        if settings.smart_routing_enabled and email.body_original:
            # 智能路由翻译
            result = service.translate_with_smart_routing(
                text=email.body_original,
                target_lang="zh",
                source_lang=email.language_detected,
                glossary=None,  # TODO: 加载术语表
                subject=email.subject_original
            )
            body_translated = result.get("translated_text", "")
            provider_used = result.get("provider_used", provider_used)
        else:
            # 普通翻译
            body_translated = service.translate_text(
                text=email.body_original,
                target_lang="zh",
                source_lang=email.language_detected
            )

        # 翻译主题
        subject_translated = None
        if email.subject_original:
            subject_translated = service.translate_text(
                text=email.subject_original,
                target_lang="zh",
                source_lang=email.language_detected
            )

        # 更新邮件
        email.subject_translated = subject_translated
        email.body_translated = body_translated
        email.is_translated = True
        email.translation_status = "completed"

        # 保存到共享翻译表
        if email.message_id:
            shared = db.query(SharedEmailTranslation).filter(
                SharedEmailTranslation.message_id == email.message_id
            ).first()
            if not shared:
                shared = SharedEmailTranslation(
                    message_id=email.message_id,
                    subject_translated=subject_translated,
                    body_translated=body_translated,
                    translated_by=account.id if account else None,
                    translated_at=datetime.utcnow()
                )
                db.add(shared)
            else:
                shared.subject_translated = subject_translated
                shared.body_translated = body_translated
                shared.translated_at = datetime.utcnow()

        db.commit()

        # 发送完成通知
        notify_completion(account_id, "translation_complete", {
            "email_id": email_id,
            "provider": provider_used,
            "success": True
        })

        # 翻译完成后，异步触发任务信息提取（供Portal项目管理导入）
        try:
            from tasks.task_extract_tasks import extract_task_info_for_email
            extract_task_info_for_email.delay(email_id, account_id)
            print(f"[TranslateTask] Triggered task extraction for email {email_id}")
        except Exception as e:
            # 提取失败不影响翻译结果
            print(f"[TranslateTask] Failed to trigger task extraction: {e}")

        return {
            "success": True,
            "email_id": email_id,
            "provider": provider_used
        }

    except SoftTimeLimitExceeded:
        # 软超时，尝试重试（使用指数退避：10s, 20s, 40s）
        raise self.retry(countdown=10 * (2 ** self.request.retries))
    except Exception as e:
        db.rollback()
        print(f"[TranslateTask] Error translating email {email_id}: {e}")

        # 发送失败通知
        notify_completion(account_id, "translation_failed", {
            "email_id": email_id,
            "error": str(e)
        })

        # 重试
        raise self.retry(exc=e, countdown=5)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, soft_time_limit=600, time_limit=660)
def batch_translate_task(self, email_ids: list, account_id: int, batch_size: int = 20):
    """
    批量翻译邮件（分批处理，避免队列爆炸）

    Args:
        email_ids: 邮件ID列表
        account_id: 账户ID
        batch_size: 每批处理的邮件数量（默认20，防止内存溢出）

    Returns:
        dict: 批量翻译结果
    """
    from celery import group
    import time

    total = len(email_ids)
    completed = 0
    failed = 0

    print(f"[BatchTranslate] Starting batch translation: {total} emails, batch_size={batch_size}")

    # 分批处理
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_ids = email_ids[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"[BatchTranslate] Processing batch {batch_num}/{total_batches} ({len(batch_ids)} emails)")

        # 创建当前批次的子任务组
        tasks = group(
            translate_email_task.s(email_id, account_id)
            for email_id in batch_ids
        )

        # 执行当前批次
        result = tasks.apply_async()

        try:
            # 等待当前批次完成（每批最长等待3分钟）
            batch_results = result.get(timeout=180)

            for r in batch_results:
                if r.get("success"):
                    completed += 1
                else:
                    failed += 1

        except Exception as e:
            print(f"[BatchTranslate] Batch {batch_num} error: {e}")
            # 当前批次失败，记录失败数量
            failed += len(batch_ids) - (completed - (batch_start - failed))

        # 批次间短暂休息，避免过度占用资源
        if batch_end < total:
            time.sleep(1)

        # 发送进度通知（每批完成后）
        notify_completion(account_id, "batch_translation_progress", {
            "total": total,
            "processed": batch_end,
            "completed": completed,
            "failed": failed,
            "progress": int(batch_end / total * 100)
        })

    # 发送最终完成通知
    notify_completion(account_id, "batch_translation_complete", {
        "total": total,
        "completed": completed,
        "failed": failed
    })

    print(f"[BatchTranslate] Completed: {completed}/{total} success, {failed} failed")

    return {
        "success": True,
        "total": total,
        "completed": completed,
        "failed": failed
    }


@celery_app.task(bind=True)
def poll_batch_status(self):
    """
    轮询 Claude Batch API 状态

    定时任务，检查所有进行中的批次并处理完成的结果
    使用 batch_service 的 poll_and_process_batches 方法处理
    """
    from services.batch_service import get_batch_service

    try:
        # 使用 asyncio.run() 调用异步方法
        service = get_batch_service()
        result = asyncio.run(service.poll_and_process_batches())

        checked = result.get("checked", 0)
        completed = result.get("completed", 0)

        if completed > 0:
            print(f"[BatchPoll] Checked {checked} batches, completed {completed}")

        return {
            "checked": checked,
            "completed": completed,
            "results": result.get("results", [])
        }

    except Exception as e:
        print(f"[BatchPoll] Error: {e}")
        return {"error": str(e)}
