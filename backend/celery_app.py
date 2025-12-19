"""
Celery 配置和实例

使用 Redis 作为消息代理和结果后端
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import os
from dotenv import load_dotenv

load_dotenv()

# 从环境变量获取配置
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# 创建 Celery 实例
celery_app = Celery(
    "email_translate",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "tasks.translate_tasks",
        "tasks.email_tasks",
        "tasks.ai_tasks",
        "tasks.maintenance_tasks",
        "tasks.reminder_tasks",
        "tasks.task_extract_tasks",
    ]
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 任务配置
    task_default_queue="email_translate",
    task_queues=(
        Queue("email_translate", routing_key="email_translate"),
        Queue("translate", routing_key="translate"),
        Queue("maintenance", routing_key="maintenance"),
    ),

    # 任务路由
    task_routes={
        "tasks.translate_tasks.*": {"queue": "translate"},
        "tasks.email_tasks.*": {"queue": "email_translate"},
        "tasks.ai_tasks.*": {"queue": "email_translate"},
        "tasks.maintenance_tasks.*": {"queue": "maintenance"},
        "tasks.reminder_tasks.*": {"queue": "email_translate"},
        "tasks.task_extract_tasks.*": {"queue": "email_translate"},
    },

    # 重试配置
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # worker 丢失时拒绝任务

    # 结果配置
    result_expires=3600,  # 结果保留1小时

    # 并发配置
    worker_concurrency=4,  # 4个并发worker
    worker_prefetch_multiplier=2,  # 预取2个任务

    # 任务超时
    task_time_limit=300,  # 5分钟硬超时
    task_soft_time_limit=270,  # 4.5分钟软超时

    # Beat 定时任务配置
    beat_schedule={
        # 缓存预热 - 每小时
        "warm-translation-cache": {
            "task": "tasks.maintenance_tasks.warm_translation_cache",
            "schedule": 3600.0,
        },
        # 清理过期翻译缓存 - 每天凌晨2点
        "cleanup-old-translations": {
            "task": "tasks.maintenance_tasks.cleanup_old_translations",
            "schedule": crontab(hour=2, minute=0),
        },
        # 清理临时文件 - 每天凌晨3点
        "cleanup-temp-files": {
            "task": "tasks.maintenance_tasks.cleanup_temp_files",
            "schedule": crontab(hour=3, minute=0),
        },
        # 重建联系人索引 - 每天凌晨4点
        "rebuild-contacts-index": {
            "task": "tasks.maintenance_tasks.rebuild_contacts_index",
            "schedule": crontab(hour=4, minute=0),
        },
        # Batch API 轮询 - 每30秒
        "poll-batch-status": {
            "task": "tasks.translate_tasks.poll_batch_status",
            "schedule": 30.0,
        },
        # 日历事件提醒检查 - 每分钟
        "check-event-reminders": {
            "task": "tasks.reminder_tasks.check_event_reminders",
            "schedule": 60.0,
        },
        # 清理卡死的翻译状态 - 每5分钟
        "cleanup-stuck-translations": {
            "task": "tasks.maintenance_tasks.cleanup_stuck_translations",
            "schedule": 300.0,  # 5分钟
        },
        # 月度配额重置 - 每月1日凌晨0点
                # 收集未翻译邮件并提交批次 - 每5分钟
        "collect-and-submit-batch": {
            "task": "tasks.translate_tasks.collect_and_submit_batch",
            "schedule": 300.0,  # 5分钟
            "kwargs": {"limit": 50},
        },
    },
)


# 可选：设置默认任务基类
class BaseTask(celery_app.Task):
    """自定义任务基类，添加通用错误处理"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败时的回调"""
        print(f"[Celery] Task {self.name}[{task_id}] failed: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功时的回调"""
        print(f"[Celery] Task {self.name}[{task_id}] completed")
        super().on_success(retval, task_id, args, kwargs)


celery_app.Task = BaseTask
