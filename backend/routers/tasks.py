"""
任务状态查询路由

提供 Celery 任务状态查询 API
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from celery.result import AsyncResult
from datetime import datetime

from celery_app import celery_app
from routers.users import get_current_account

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str  # PENDING, STARTED, RETRY, FAILURE, SUCCESS
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: Optional[int] = None


class TaskSubmitResponse(BaseModel):
    """任务提交响应"""
    task_id: str
    status: str
    message: str


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str, account=Depends(get_current_account)):
    """
    获取任务状态

    Args:
        task_id: Celery 任务ID

    Returns:
        任务状态信息
    """
    result = AsyncResult(task_id, app=celery_app)

    response = TaskStatusResponse(
        task_id=task_id,
        status=result.status,
        result=None,
        error=None,
        progress=None
    )

    if result.ready():
        if result.successful():
            response.result = result.result
        else:
            response.error = str(result.result) if result.result else "Unknown error"
    elif result.status == "PROGRESS":
        # 如果任务支持进度报告
        if result.info and isinstance(result.info, dict):
            response.progress = result.info.get("progress", 0)

    return response


@router.delete("/{task_id}")
async def cancel_task(task_id: str, account=Depends(get_current_account)):
    """
    取消任务

    Args:
        task_id: Celery 任务ID

    Returns:
        取消结果
    """
    result = AsyncResult(task_id, app=celery_app)

    if result.ready():
        raise HTTPException(status_code=400, detail="Task already completed")

    # 尝试撤销任务
    celery_app.control.revoke(task_id, terminate=True)

    return {"task_id": task_id, "status": "cancelled"}


@router.post("/translate/email/{email_id}", response_model=TaskSubmitResponse)
async def submit_translate_task(
    email_id: int,
    force: bool = False,
    account=Depends(get_current_account)
):
    """
    提交翻译任务

    Args:
        email_id: 邮件ID
        force: 是否强制重新翻译

    Returns:
        任务提交信息
    """
    from tasks.translate_tasks import translate_email_task

    task = translate_email_task.delay(email_id, account.id, force)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Translation task for email {email_id} submitted"
    )


@router.post("/translate/batch", response_model=TaskSubmitResponse)
async def submit_batch_translate_task(
    email_ids: List[int],
    account=Depends(get_current_account)
):
    """
    提交批量翻译任务

    Args:
        email_ids: 邮件ID列表

    Returns:
        任务提交信息
    """
    from tasks.translate_tasks import batch_translate_task

    task = batch_translate_task.delay(email_ids, account.id)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Batch translation task for {len(email_ids)} emails submitted"
    )


@router.post("/fetch", response_model=TaskSubmitResponse)
async def submit_fetch_task(
    since_days: int = 30,
    account=Depends(get_current_account)
):
    """
    提交邮件拉取任务

    Args:
        since_days: 拉取最近多少天的邮件

    Returns:
        任务提交信息
    """
    from tasks.email_tasks import fetch_emails_task

    task = fetch_emails_task.delay(account.id, since_days)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Fetch task submitted for last {since_days} days"
    )


@router.post("/send/{draft_id}", response_model=TaskSubmitResponse)
async def submit_send_task(draft_id: int, account=Depends(get_current_account)):
    """
    提交邮件发送任务

    Args:
        draft_id: 草稿ID

    Returns:
        任务提交信息
    """
    from tasks.email_tasks import send_email_task

    task = send_email_task.delay(draft_id, account.id)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Send task for draft {draft_id} submitted"
    )


@router.post("/extract/{email_id}", response_model=TaskSubmitResponse)
async def submit_extract_task(
    email_id: int,
    force: bool = False,
    account=Depends(get_current_account)
):
    """
    提交 AI 提取任务

    Args:
        email_id: 邮件ID
        force: 是否强制重新提取

    Returns:
        任务提交信息
    """
    from tasks.ai_tasks import extract_email_info_task

    task = extract_email_info_task.delay(email_id, account.id, force)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Extraction task for email {email_id} submitted"
    )


@router.post("/export", response_model=TaskSubmitResponse)
async def submit_export_task(
    email_ids: List[int],
    export_format: str = "eml",
    account=Depends(get_current_account)
):
    """
    提交邮件导出任务

    Args:
        email_ids: 要导出的邮件ID列表
        export_format: 导出格式

    Returns:
        任务提交信息
    """
    from tasks.email_tasks import export_emails_task

    task = export_emails_task.delay(email_ids, account.id, export_format)

    return TaskSubmitResponse(
        task_id=task.id,
        status="submitted",
        message=f"Export task for {len(email_ids)} emails submitted"
    )
