"""
任务提取 API 路由

供 Portal 项目管理系统导入任务使用
提供预提取结果查询和手动重试接口

包含两套接口：
1. 用户级接口（/emails/{id}）- 需要邮件系统登录
2. Portal集成接口（/portal/...）- 使用服务令牌认证
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from database.database import get_db
from database.models import TaskExtraction, Email
from routers.users import get_current_account
from services.portal_integration import portal_integration_service

router = APIRouter(prefix="/api/task-extractions", tags=["task-extractions"])


# ==================== Pydantic 模型 ====================

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    project_id: Optional[int] = None
    create_project: bool = False
    project_name: Optional[str] = None
    # 任务信息（用户可修改）
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: str = "general"
    priority: str = "normal"
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    assigned_to_id: Optional[int] = None
    action_items: Optional[List[str]] = None
    # 项目信息（创建新项目时使用）
    customer_name: Optional[str] = None
    order_no: Optional[str] = None
    part_number: Optional[str] = None

# Portal 服务令牌（用于服务间通信）
PORTAL_SERVICE_TOKEN = os.getenv('PORTAL_SERVICE_TOKEN', 'jzc-portal-integration-token-2025')


async def verify_portal_token(x_portal_token: Optional[str] = Header(None)):
    """验证 Portal 服务令牌"""
    if not x_portal_token or x_portal_token != PORTAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="无效的 Portal 服务令牌"
        )
    return True


@router.get("/emails/{email_id}")
async def get_task_extraction(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    获取邮件的预提取任务信息

    Args:
        email_id: 邮件ID

    Returns:
        提取结果，包含状态和数据
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 获取提取记录
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if not extraction:
        return {
            "email_id": email_id,
            "status": "none",
            "message": "尚未提取任务信息",
            "data": None
        }

    return {
        "email_id": email_id,
        "status": extraction.status,
        "data": extraction.to_dict() if extraction.status == "completed" else None,
        "error_message": extraction.error_message if extraction.status == "failed" else None
    }


@router.post("/emails/{email_id}/extract")
async def trigger_extraction(
    email_id: int,
    force: bool = Query(False, description="是否强制重新提取"),
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    手动触发任务提取

    用于：
    - 未提取的邮件
    - 提取失败需要重试
    - 强制重新提取

    Args:
        email_id: 邮件ID
        force: 是否强制重新提取（即使已完成）

    Returns:
        触发结果
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 检查现有提取状态
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if extraction and extraction.status == "completed" and not force:
        return {
            "success": True,
            "message": "任务信息已提取完成",
            "status": "completed",
            "data": extraction.to_dict()
        }

    if extraction and extraction.status == "processing":
        return {
            "success": False,
            "message": "任务提取正在进行中，请稍后查询",
            "status": "processing"
        }

    # 触发 Celery 任务
    from tasks.task_extract_tasks import extract_task_info_for_email

    try:
        task = extract_task_info_for_email.delay(email_id, current_account.id)

        return {
            "success": True,
            "message": "已触发任务提取",
            "status": "triggered",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发提取失败: {str(e)}")


@router.get("")
async def list_extractions(
    status: Optional[str] = Query(None, description="筛选状态: pending/processing/completed/failed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    获取当前账户的所有任务提取记录

    Args:
        status: 可选状态筛选
        page: 页码
        page_size: 每页数量

    Returns:
        分页的提取记录列表
    """
    # 构建查询：只返回当前账户的邮件对应的提取记录
    query = select(TaskExtraction, Email).join(
        Email, TaskExtraction.email_id == Email.id
    ).where(
        Email.account_id == current_account.id
    )

    if status:
        query = query.where(TaskExtraction.status == status)

    # 按创建时间倒序
    query = query.order_by(TaskExtraction.created_at.desc())

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for extraction, email in rows:
        item = extraction.to_dict()
        item["email_subject"] = email.subject_translated or email.subject_original
        item["email_from"] = email.from_name or email.from_email
        item["email_received_at"] = email.received_at.isoformat() if email.received_at else None
        items.append(item)

    # 获取总数
    from sqlalchemy import func
    count_query = select(func.count()).select_from(TaskExtraction).join(
        Email, TaskExtraction.email_id == Email.id
    ).where(
        Email.account_id == current_account.id
    )
    if status:
        count_query = count_query.where(TaskExtraction.status == status)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.post("/batch-extract")
async def batch_extract(
    email_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    批量触发任务提取

    Args:
        email_ids: 邮件ID列表

    Returns:
        批量触发结果
    """
    if not email_ids:
        raise HTTPException(status_code=400, detail="邮件ID列表不能为空")

    if len(email_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多提取50封邮件")

    # 验证所有邮件属于当前账户
    result = await db.execute(
        select(Email.id).where(
            and_(
                Email.id.in_(email_ids),
                Email.account_id == current_account.id
            )
        )
    )
    valid_ids = [row[0] for row in result.all()]

    if not valid_ids:
        raise HTTPException(status_code=404, detail="未找到有效的邮件")

    # 触发批量提取
    from tasks.task_extract_tasks import batch_extract_tasks

    try:
        task = batch_extract_tasks.delay(valid_ids, current_account.id)

        return {
            "success": True,
            "message": f"已触发 {len(valid_ids)} 封邮件的任务提取",
            "valid_count": len(valid_ids),
            "invalid_count": len(email_ids) - len(valid_ids),
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发批量提取失败: {str(e)}")


# ==================== Portal 集成接口 ====================
# 使用服务令牌认证，供 Portal 项目管理系统调用

@router.get("/portal/emails")
async def portal_list_emails(
    keyword: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    translation_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_portal_token)
):
    """
    Portal 集成：获取邮件列表
    使用服务令牌认证，返回所有账户的已翻译邮件
    """
    query = select(Email).where(Email.translation_status == "completed")

    if keyword:
        query = query.where(
            (Email.subject_translated.ilike(f"%{keyword}%")) |
            (Email.subject_original.ilike(f"%{keyword}%")) |
            (Email.from_name.ilike(f"%{keyword}%")) |
            (Email.from_email.ilike(f"%{keyword}%"))
        )

    # 日期筛选
    if start_date:
        from datetime import datetime
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.where(Email.received_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        from datetime import datetime, timedelta
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(Email.received_at < end_dt)
        except ValueError:
            pass

    # 分页
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    query = query.order_by(Email.received_at.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    emails = result.scalars().all()

    items = []
    for email in emails:
        # 查询是否有预提取结果
        ext_result = await db.execute(
            select(TaskExtraction.status).where(TaskExtraction.email_id == email.id)
        )
        ext_status = ext_result.scalar_one_or_none()

        items.append({
            "id": email.id,
            "subject_original": email.subject_original,
            "subject_translated": email.subject_translated,
            "from_name": email.from_name,
            "from_email": email.from_email,
            "received_at": email.received_at.isoformat() if email.received_at else None,
            "translation_status": email.translation_status,
            "task_extraction_status": ext_status or "none"
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/portal/emails/{email_id}")
async def portal_get_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_portal_token)
):
    """
    Portal 集成：获取邮件详情
    """
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    return {
        "id": email.id,
        "subject_original": email.subject_original,
        "subject_translated": email.subject_translated,
        "body_original": email.body_original,
        "body_translated": email.body_translated,
        "from_name": email.from_name,
        "from_email": email.from_email,
        "to_email": email.to_email,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "translation_status": email.translation_status,
        "language_detected": email.language_detected
    }


@router.get("/portal/emails/{email_id}/extraction")
async def portal_get_extraction(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_portal_token)
):
    """
    Portal 集成：获取邮件的预提取任务信息
    """
    # 验证邮件存在
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 获取提取记录
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if not extraction:
        return {
            "email_id": email_id,
            "status": "none",
            "message": "尚未提取任务信息",
            "data": None
        }

    return {
        "email_id": email_id,
        "status": extraction.status,
        "data": extraction.to_dict() if extraction.status == "completed" else None,
        "error_message": extraction.error_message if extraction.status == "failed" else None
    }


@router.post("/portal/sync")
async def portal_sync_emails(
    since_days: int = Query(7, description="同步最近多少天的邮件"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_portal_token)
):
    """
    Portal 集成：触发邮件同步

    从 IMAP 服务器拉取最新邮件到本地数据库

    Args:
        since_days: 同步最近多少天的邮件（默认7天）

    Returns:
        同步触发结果
    """
    from database.models import EmailAccount

    # 获取所有活跃的邮箱账户
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.is_active == True)
    )
    accounts = result.scalars().all()

    if not accounts:
        return {
            "success": False,
            "message": "没有配置活跃的邮箱账户",
            "synced_accounts": 0
        }

    # 为每个账户触发后台同步任务
    synced_count = 0
    for account in accounts:
        try:
            # 调用邮件同步的后台任务
            from routers.emails import fetch_emails_background
            import asyncio
            asyncio.create_task(fetch_emails_background(account, since_days))
            synced_count += 1
        except Exception as e:
            print(f"[Portal Sync] Failed to sync account {account.email}: {e}")

    return {
        "success": True,
        "message": f"已触发 {synced_count} 个邮箱账户的同步",
        "synced_accounts": synced_count,
        "since_days": since_days
    }


@router.post("/portal/emails/{email_id}/extract")
async def portal_trigger_extraction(
    email_id: int,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_portal_token)
):
    """
    Portal 集成：触发任务提取
    """
    # 验证邮件存在
    result = await db.execute(select(Email).where(Email.id == email_id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 检查现有提取状态
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if extraction and extraction.status == "completed" and not force:
        return {
            "success": True,
            "message": "任务信息已提取完成",
            "status": "completed",
            "data": extraction.to_dict()
        }

    if extraction and extraction.status == "processing":
        return {
            "success": False,
            "message": "任务提取正在进行中，请稍后查询",
            "status": "processing"
        }

    # 触发 Celery 任务
    from tasks.task_extract_tasks import extract_task_info_for_email

    try:
        task = extract_task_info_for_email.delay(email_id, email.account_id)

        return {
            "success": True,
            "message": "已触发任务提取",
            "status": "triggered",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发提取失败: {str(e)}")


# ==================== 项目匹配接口 ====================

@router.get("/emails/{email_id}/match-projects")
async def match_projects_for_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    根据邮件提取信息匹配 Portal 项目

    Returns:
        {
            'matches': [...],
            'best_match': {...} or None,
            'should_create_project': bool,
            'suggested_project_name': str
        }
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 获取提取记录
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if not extraction or extraction.status != "completed":
        return {
            "success": False,
            "message": "邮件尚未完成任务提取",
            "matches": [],
            "best_match": None,
            "should_create_project": True,
            "suggested_project_name": None
        }

    # 调用 Portal 服务匹配项目
    match_result = portal_integration_service.match_projects(
        order_no=extraction.order_no,
        customer_name=extraction.customer_name,
        part_number=extraction.part_number
    )

    # 更新提取记录中的匹配信息
    if match_result.get('best_match'):
        best = match_result['best_match']
        extraction.matched_project_id = best.get('id')
        extraction.matched_project_name = best.get('name')
        extraction.should_create_project = False
    else:
        extraction.should_create_project = True
        # 生成建议的项目名称
        if extraction.project_name:
            extraction.suggested_project_name = extraction.project_name
        elif extraction.customer_name and extraction.order_no:
            extraction.suggested_project_name = f"{extraction.customer_name} - {extraction.order_no}"
        elif extraction.customer_name:
            extraction.suggested_project_name = f"{extraction.customer_name} 项目"
        else:
            extraction.suggested_project_name = f"邮件项目 - {email.subject_translated or email.subject_original}"[:100]

    await db.commit()
    await db.refresh(extraction)

    return {
        "success": True,
        "matches": match_result.get('matches', []),
        "best_match": match_result.get('best_match'),
        "should_create_project": extraction.should_create_project,
        "suggested_project_name": extraction.suggested_project_name,
        "extraction": extraction.to_dict()
    }


@router.post("/emails/{email_id}/create-task")
async def create_task_from_email(
    email_id: int,
    request: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    从邮件创建 Portal 任务

    支持：
    1. 关联到已有项目
    2. 创建新项目并关联

    Args:
        email_id: 邮件ID
        request: 创建任务请求（包含项目ID或新项目信息）

    Returns:
        {
            'success': True,
            'project': {...},
            'task': {...},
            'created_project': bool
        }
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 获取提取记录
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if not extraction or extraction.status != "completed":
        raise HTTPException(status_code=400, detail="邮件尚未完成任务提取，请先提取")

    # 检查是否已导入
    if extraction.imported_to_portal:
        return {
            "success": False,
            "message": "该邮件已导入到 Portal",
            "portal_task_id": extraction.portal_task_id,
            "portal_project_id": extraction.portal_project_id,
            "imported_at": extraction.imported_at.isoformat() if extraction.imported_at else None
        }

    # 验证必要参数
    if not request.project_id and not request.create_project:
        raise HTTPException(
            status_code=400,
            detail="必须指定项目ID或选择创建新项目"
        )

    if request.create_project and not request.project_name:
        # 使用建议的项目名称
        request.project_name = extraction.suggested_project_name

    # 构建提取数据（合并AI提取和用户修改）
    extraction_data = {
        "title": request.title or extraction.title,
        "description": request.description or extraction.description,
        "task_type": request.task_type or extraction.task_type or "general",
        "priority": request.priority or extraction.priority or "normal",
        "due_date": request.due_date or (extraction.due_date.isoformat() if extraction.due_date else None),
        "start_date": request.start_date or (extraction.start_date.isoformat() if extraction.start_date else None),
        "assigned_to_id": request.assigned_to_id,
        "action_items": request.action_items or extraction.action_items,
        "customer_name": request.customer_name or extraction.customer_name,
        "order_no": request.order_no or extraction.order_no,
        "part_number": request.part_number or extraction.part_number,
        "suggested_project_name": request.project_name,
    }

    # 调用 Portal 服务创建任务
    create_result = portal_integration_service.create_task_from_email(
        email_id=email_id,
        email_subject=email.subject_translated or email.subject_original,
        extraction_data=extraction_data,
        project_id=request.project_id,
        create_project=request.create_project,
        project_name=request.project_name
    )

    if not create_result.get('success'):
        raise HTTPException(
            status_code=500,
            detail=create_result.get('error', '创建任务失败')
        )

    # 更新提取记录
    extraction.imported_to_portal = True
    extraction.portal_task_id = create_result.get('task', {}).get('id')
    extraction.portal_project_id = create_result.get('project_id')
    extraction.imported_at = datetime.utcnow()

    await db.commit()
    await db.refresh(extraction)

    return {
        "success": True,
        "message": "任务创建成功",
        "project": create_result.get('project'),
        "task": create_result.get('task'),
        "project_id": create_result.get('project_id'),
        "created_project": create_result.get('created_project', False),
        "extraction": extraction.to_dict()
    }


@router.get("/emails/{email_id}/employees")
async def get_employees_for_assignment(
    email_id: int,
    search: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    获取可分配的员工列表（用于任务分配）
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 调用 Portal 服务获取员工列表
    emp_result = portal_integration_service.get_employees(
        search=search,
        page=page,
        page_size=page_size
    )

    return emp_result


@router.get("/emails/{email_id}/import-status")
async def get_import_status(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_account = Depends(get_current_account)
):
    """
    获取邮件的 Portal 导入状态
    """
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id == email_id,
                Email.account_id == current_account.id
            )
        )
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在或无权限访问")

    # 获取提取记录
    result = await db.execute(
        select(TaskExtraction).where(TaskExtraction.email_id == email_id)
    )
    extraction = result.scalar_one_or_none()

    if not extraction:
        return {
            "extracted": False,
            "imported": False,
            "message": "尚未提取任务信息"
        }

    return {
        "extracted": extraction.status == "completed",
        "extraction_status": extraction.status,
        "imported": extraction.imported_to_portal,
        "portal_task_id": extraction.portal_task_id,
        "portal_project_id": extraction.portal_project_id,
        "imported_at": extraction.imported_at.isoformat() if extraction.imported_at else None,
        "matched_project_id": extraction.matched_project_id,
        "matched_project_name": extraction.matched_project_name,
        "should_create_project": extraction.should_create_project,
        "suggested_project_name": extraction.suggested_project_name
    }
