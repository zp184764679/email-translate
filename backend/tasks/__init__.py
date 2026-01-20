"""
Celery 任务模块

包含所有异步任务定义：
- translate_tasks: 翻译相关任务
- email_tasks: 邮件相关任务（拉取、发送）
- ai_tasks: AI 提取任务
- maintenance_tasks: 定时维护任务
"""
from tasks.translate_tasks import (
    translate_email_task,
    batch_translate_task,
    collect_and_translate_pending,
)
from tasks.email_tasks import (
    fetch_emails_task,
    send_email_task,
    export_emails_task,
)
from tasks.ai_tasks import (
    extract_email_info_task,
)
from tasks.maintenance_tasks import (
    warm_translation_cache,
    cleanup_old_translations,
    cleanup_temp_files,
    rebuild_contacts_index,
    reset_monthly_quota,
)

__all__ = [
    # 翻译任务
    "translate_email_task",
    "batch_translate_task",
    "collect_and_translate_pending",
    # 邮件任务
    "fetch_emails_task",
    "send_email_task",
    "export_emails_task",
    # AI 任务
    "extract_email_info_task",
    # 维护任务
    "warm_translation_cache",
    "cleanup_old_translations",
    "cleanup_temp_files",
    "rebuild_contacts_index",
    "reset_monthly_quota",
]
