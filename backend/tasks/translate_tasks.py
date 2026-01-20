"""
翻译相关 Celery 任务

包含：
- translate_email_task: 翻译单封邮件（支持超长邮件分段翻译）
- batch_translate_task: 批量翻译邮件
- collect_and_translate_pending: 收集并翻译待处理邮件

所有翻译任务使用本地 vLLM 大模型，零 API 成本。
"""
import asyncio
import re
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime
from typing import Optional, List, Tuple

from celery_app import celery_app

# 超长邮件阈值（字节）
LONG_EMAIL_THRESHOLD = 25000  # 25KB
# 每段最大长度（字符）
CHUNK_MAX_SIZE = 8000


def get_db_session():
    """获取同步数据库会话（Celery worker 使用）"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os

    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def split_email_into_chunks(text: str, max_chunk_size: int = CHUNK_MAX_SIZE) -> List[str]:
    """
    将长邮件文本分割成多个片段，在段落或句子边界处分割

    Args:
        text: 原始文本
        max_chunk_size: 每个片段的最大长度

    Returns:
        List[str]: 分割后的文本片段列表
    """
    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    current_pos = 0

    while current_pos < len(text):
        # 如果剩余内容不超过限制，直接添加
        if current_pos + max_chunk_size >= len(text):
            chunks.append(text[current_pos:])
            break

        # 找到合适的分割点（优先级：段落 > 换行 > 句号 > 空格）
        end_pos = current_pos + max_chunk_size
        chunk_text = text[current_pos:end_pos]

        # 从后向前查找最佳分割点
        split_patterns = [
            r'\n\n',  # 段落分隔
            r'\n',    # 换行
            r'[.。！!?？](?=\s|$)',  # 句末标点
            r'[,，;；](?=\s)',  # 子句分隔
            r'\s',    # 空格
        ]

        best_split = len(chunk_text)

        for pattern in split_patterns:
            # 在后半部分查找分割点
            search_start = max(0, len(chunk_text) // 2)
            matches = list(re.finditer(pattern, chunk_text[search_start:]))
            if matches:
                # 取最后一个匹配
                last_match = matches[-1]
                split_pos = search_start + last_match.end()
                if split_pos > search_start:
                    best_split = split_pos
                    break

        # 添加片段
        chunks.append(text[current_pos:current_pos + best_split])
        current_pos += best_split

    return chunks


def translate_long_email(service, text: str, target_lang: str, source_lang: str, glossary=None) -> str:
    """
    翻译超长邮件，自动分段处理

    Args:
        service: TranslateService 实例
        text: 原始文本
        target_lang: 目标语言
        source_lang: 源语言
        glossary: 术语表

    Returns:
        str: 完整翻译结果
    """
    chunks = split_email_into_chunks(text)
    print(f"[TranslateTask] Long email split into {len(chunks)} chunks")

    translated_chunks = []
    for i, chunk in enumerate(chunks):
        print(f"[TranslateTask] Translating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
        translated = service.translate_text(
            text=chunk,
            target_lang=target_lang,
            source_lang=source_lang,
            glossary=glossary
        )
        translated_chunks.append(translated)

    return "\n".join(translated_chunks)


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


@celery_app.task(bind=True, max_retries=3, soft_time_limit=600, time_limit=900)
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
    from sqlalchemy import and_

    settings = get_settings()
    db = get_db_session()

    try:
        # 获取邮件
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            return {"success": False, "error": "Email not found", "email_id": email_id}

        # 中文邮件无需翻译，直接标记为已完成
        if email.language_detected == 'zh':
            email.is_translated = True
            email.translation_status = 'completed'
            db.commit()
            print(f"[TranslateTask] Email {email_id} is Chinese, skipping translation")
            # 发送完成通知
            notify_completion(account_id, "translation_complete", {
                "email_id": email_id,
                "provider": "native_chinese",
                "success": True,
                "is_translated": True,
                "translation_status": "completed"
            })
            return {"success": True, "email_id": email_id, "reason": "chinese_email"}

        # 检查是否已翻译
        if email.is_translated and not force:
            return {"success": True, "email_id": email_id, "cached": True}

        # 翻译锁：使用数据库原子更新防止并发翻译
        # 只有状态为 none/pending/failed/NULL 的邮件才能开始翻译
        from sqlalchemy import update, or_
        from datetime import datetime
        result = db.execute(
            update(Email)
            .where(and_(
                Email.id == email_id,
                or_(
                    Email.translation_status.in_(["none", "pending", "failed"]),
                    Email.translation_status.is_(None)
                )
            ))
            .values(
                translation_status="translating",
                translate_started_at=datetime.utcnow(),
                translate_retry_count=Email.translate_retry_count + 1
            )
        )
        db.commit()

        if result.rowcount == 0:
            # 邮件正在被其他 worker 翻译，跳过
            print(f"[TranslateTask] Email {email_id} is already being translated, skipping")
            return {"success": True, "email_id": email_id, "skipped": True, "reason": "already_translating"}

        # 刷新邮件对象以获取最新状态
        db.refresh(email)

        # 获取账户信息（用于术语表）
        account = db.query(EmailAccount).filter(EmailAccount.id == email.account_id).first()

        # 创建翻译服务（使用 vLLM）
        service = TranslateService(
            vllm_base_url=settings.vllm_base_url,
            vllm_model=settings.vllm_model,
            vllm_api_key=settings.vllm_api_key,
        )

        # 执行翻译（统一使用 vLLM）
        provider_used = "vllm"
        body_original = email.body_original or ""
        body_len = len(body_original)
        is_long_email = body_len > LONG_EMAIL_THRESHOLD

        # 分离最新内容和引用内容
        latest_content, quoted_content = service.extract_latest_email(body_original)
        print(f"[TranslateTask] Email {email_id}: latest={len(latest_content)} chars, quoted={len(quoted_content)} chars")

        if is_long_email:
            # 超长邮件：使用分段翻译（仅翻译最新内容）
            print(f"[TranslateTask] Long email detected ({body_len} bytes), using chunked translation")
            body_translated = translate_long_email(
                service=service,
                text=latest_content,
                target_lang="zh",
                source_lang=email.language_detected,
                glossary=None
            )
            provider_used = "vllm+chunked"
        elif latest_content:
            # 智能路由翻译最新内容
            result = service.translate_with_smart_routing(
                text=latest_content,
                target_lang="zh",
                source_lang=email.language_detected,
                glossary=None,  # TODO: 加载术语表
                subject=email.subject_original
            )
            body_translated = result.get("translated_text", "")
            provider_used = result.get("provider_used", "vllm")
        else:
            # 空正文
            body_translated = ""

        # 处理引用内容
        if quoted_content and body_translated:
            quoted_translated = None

            # 优先查找历史翻译（通过 in_reply_to）
            if email.in_reply_to:
                # 查找被引用邮件的翻译
                original_email = db.query(Email).filter(
                    Email.message_id == email.in_reply_to,
                    Email.is_translated == True
                ).first()
                if original_email and original_email.body_translated:
                    quoted_translated = original_email.body_translated
                    print(f"[TranslateTask] Found historical translation for quoted content")
                else:
                    # 查找共享翻译
                    shared_translation = db.query(SharedEmailTranslation).filter(
                        SharedEmailTranslation.message_id == email.in_reply_to
                    ).first()
                    if shared_translation and shared_translation.body_translated:
                        quoted_translated = shared_translation.body_translated
                        print(f"[TranslateTask] Found shared translation for quoted content")

            # 如果没有找到历史翻译，单独翻译引用内容
            if not quoted_translated:
                print(f"[TranslateTask] No historical translation found, translating quoted content")
                quoted_translated = service.translate_quoted_content(
                    quoted_content,
                    target_lang="zh",
                    source_lang=email.language_detected
                )

            # 合并翻译结果
            if quoted_translated:
                body_translated = f"{body_translated}\n\n--- 以下为引用内容（已翻译）---\n{quoted_translated}"

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

        # 发送完成通知（包含完整翻译数据，前端无需再请求 API）
        notify_completion(account_id, "translation_complete", {
            "email_id": email_id,
            "provider": provider_used,
            "success": True,
            "subject_translated": subject_translated,
            "body_translated": body_translated,
            "is_translated": True,
            "translation_status": "completed"
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
        # 软超时，重置状态为 failed 以便重试
        try:
            db.rollback()
            email = db.query(Email).filter(Email.id == email_id).first()
            if email:
                email.translation_status = "failed"
                db.commit()
        except Exception as cleanup_err:
            print(f"[TranslateTask] Cleanup failed during retry: {cleanup_err}")
        # 尝试重试（使用指数退避：10s, 20s, 40s）
        raise self.retry(countdown=10 * (2 ** self.request.retries))
    except Exception as e:
        # 翻译失败，更新状态为 failed
        try:
            db.rollback()
            email = db.query(Email).filter(Email.id == email_id).first()
            if email:
                email.translation_status = "failed"
                db.commit()
        except Exception as cleanup_err:
            print(f"[TranslateTask] Cleanup failed: {cleanup_err}")
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
        batch_size: 每批处理的邮件数量（默认500，防止内存溢出）

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
def collect_and_translate_pending(self, limit: int = 500):
    """
    收集未翻译邮件并使用 vLLM 翻译

    定时任务，自动收集 is_translated=0 的邮件，
    调用 translate_email_task 进行翻译（使用配置的翻译引擎，默认 vLLM）。

    Args:
        limit: 每次最多处理的邮件数量（默认500，避免队列积压）

    Returns:
        dict: 处理结果
    """
    from database.models import Email
    from celery import group

    db = get_db_session()

    try:
        # 查找未翻译的邮件（包括 none、NULL、pending 状态）
        # 'pending' 状态是由 cleanup_stuck_translations 重置的邮件
        # 排除中文邮件（language_detected = 'zh'），因为中文无需翻译
        from sqlalchemy import or_
        pending_emails = db.query(Email).filter(
            Email.is_translated == False,
            or_(
                Email.translation_status.in_(['none', 'pending']),
                Email.translation_status.is_(None)
            ),
            Email.language_detected != 'zh',  # 排除中文邮件
            Email.language_detected.isnot(None)  # 排除未检测语言的邮件
        ).order_by(Email.received_at.desc()).limit(limit).all()

        if not pending_emails:
            return {"message": "No pending emails", "count": 0}

        email_ids = [(e.id, e.account_id) for e in pending_emails]
        print(f"[CollectTranslate] Found {len(email_ids)} pending emails")

        # 不在这里标记状态，让 translate_email_task 自己处理锁定
        # 这样可以避免状态冲突

        # 创建翻译任务组
        tasks = group(
            translate_email_task.s(email_id, account_id)
            for email_id, account_id in email_ids
        )

        # 异步执行（不等待结果）
        tasks.apply_async()

        return {
            "message": f"Queued {len(email_ids)} emails for translation",
            "count": len(email_ids),
            "email_ids": [e[0] for e in email_ids]
        }

    except Exception as e:
        db.rollback()
        print(f"[CollectTranslate] Error: {e}")
        return {"error": str(e)}
    finally:
        db.close()
