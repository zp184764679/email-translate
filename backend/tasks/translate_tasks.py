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
        asyncio.get_event_loop().run_until_complete(
            notification_manager.broadcast(account_id, event_type, data)
        )
    except Exception as e:
        print(f"[Notify] Failed to send notification: {e}")


@celery_app.task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
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

        # 创建翻译服务
        service = TranslateService(
            provider=settings.translate_provider,
            api_key=settings.claude_api_key or settings.deepl_api_key,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            claude_model=settings.claude_model,
            is_free_api=settings.deepl_free_api,
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
            body_translated = service.translate(
                text=email.body_original,
                target_lang="zh",
                source_lang=email.language_detected
            )

        # 翻译主题
        subject_translated = None
        if email.subject_original:
            subject_translated = service.translate(
                text=email.subject_original,
                target_lang="zh",
                source_lang=email.language_detected
            )

        # 更新邮件
        email.subject_translated = subject_translated
        email.body_translated = body_translated
        email.is_translated = True
        email.translated_at = datetime.utcnow()

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
                    translated_by=account.email if account else "system",
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

        return {
            "success": True,
            "email_id": email_id,
            "provider": provider_used
        }

    except SoftTimeLimitExceeded:
        # 软超时，尝试重试
        self.retry(countdown=10, max_retries=2)
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


@celery_app.task(bind=True, max_retries=2, soft_time_limit=300, time_limit=360)
def batch_translate_task(self, email_ids: list, account_id: int):
    """
    批量翻译邮件

    Args:
        email_ids: 邮件ID列表
        account_id: 账户ID

    Returns:
        dict: 批量翻译结果
    """
    from celery import group

    total = len(email_ids)
    completed = 0
    failed = 0

    # 创建子任务组
    tasks = group(
        translate_email_task.s(email_id, account_id)
        for email_id in email_ids
    )

    # 执行并等待所有任务完成
    result = tasks.apply_async()

    try:
        # 等待所有任务完成（最长等待5分钟）
        results = result.get(timeout=300)

        for r in results:
            if r.get("success"):
                completed += 1
            else:
                failed += 1

    except Exception as e:
        print(f"[BatchTranslate] Error: {e}")
        failed = total - completed

    # 发送批量完成通知
    notify_completion(account_id, "batch_translation_complete", {
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


@celery_app.task(bind=True)
def poll_batch_status(self):
    """
    轮询 Claude Batch API 状态

    定时任务，检查所有进行中的批次并处理完成的结果
    """
    from database.models import TranslationBatch, Email
    from services.batch_service import check_batch_status, get_batch_results

    db = get_db_session()

    try:
        # 查询所有进行中的批次
        batches = db.query(TranslationBatch).filter(
            TranslationBatch.status.in_(["submitted", "in_progress"])
        ).all()

        if not batches:
            return {"checked": 0, "completed": 0}

        completed_count = 0

        for batch in batches:
            try:
                # 检查批次状态
                status = check_batch_status(batch.batch_id)

                if status == "completed":
                    # 获取并处理结果
                    results = get_batch_results(batch.batch_id)

                    for result in results:
                        email_id = result.get("email_id")
                        if email_id:
                            email = db.query(Email).filter(Email.id == email_id).first()
                            if email:
                                email.body_translated = result.get("body_translated")
                                email.subject_translated = result.get("subject_translated")
                                email.is_translated = True
                                email.translated_at = datetime.utcnow()

                    batch.status = "completed"
                    batch.completed_at = datetime.utcnow()
                    completed_count += 1

                    # 通知用户
                    notify_completion(batch.account_id, "batch_complete", {
                        "batch_id": batch.id,
                        "email_count": len(results)
                    })

                elif status == "failed":
                    batch.status = "failed"
                    batch.completed_at = datetime.utcnow()

            except Exception as e:
                print(f"[BatchPoll] Error checking batch {batch.batch_id}: {e}")

        db.commit()

        return {
            "checked": len(batches),
            "completed": completed_count
        }

    except Exception as e:
        db.rollback()
        print(f"[BatchPoll] Error: {e}")
        return {"error": str(e)}
    finally:
        db.close()
