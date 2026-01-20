"""
附件管理路由

功能：
- 跨邮件附件搜索
- 存储统计（总量、类型分布）
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from database.models import Attachment, Email, EmailAccount, Supplier
from routers.users import get_current_account


router = APIRouter(prefix="/api/attachments", tags=["attachments"])


# ========== Pydantic Schemas ==========

class AttachmentSearchResult(BaseModel):
    id: int
    email_id: int
    filename: str
    file_size: int
    mime_type: Optional[str]
    created_at: datetime
    # 关联信息
    email_subject: Optional[str]
    sender: Optional[str]
    supplier_name: Optional[str]

    class Config:
        from_attributes = True


class AttachmentSearchResponse(BaseModel):
    items: List[AttachmentSearchResult]
    total: int
    page: int
    page_size: int


class TypeDistribution(BaseModel):
    type: str
    count: int
    size: int
    percentage: float


class StorageStats(BaseModel):
    total_count: int
    total_size: int
    total_size_formatted: str
    type_distribution: List[TypeDistribution]
    largest_files: List[AttachmentSearchResult]
    duplicate_count: int
    duplicate_size_saved: int


# ========== 工具函数 ==========

def format_file_size(bytes_size: int) -> str:
    """格式化文件大小"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


def get_file_type_category(filename: str, mime_type: str = None) -> str:
    """获取文件类型分类"""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    image_exts = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'}
    doc_exts = {'doc', 'docx', 'pdf', 'txt', 'rtf', 'odt'}
    sheet_exts = {'xls', 'xlsx', 'csv', 'ods'}
    archive_exts = {'zip', 'rar', '7z', 'tar', 'gz'}
    code_exts = {'py', 'js', 'ts', 'java', 'c', 'cpp', 'h', 'html', 'css', 'json', 'xml'}

    if ext in image_exts:
        return '图片'
    elif ext in doc_exts:
        return '文档'
    elif ext in sheet_exts:
        return '表格'
    elif ext in archive_exts:
        return '压缩包'
    elif ext in code_exts:
        return '代码'
    else:
        return '其他'


# ========== API 端点 ==========

@router.get("/search", response_model=AttachmentSearchResponse)
async def search_attachments(
    q: Optional[str] = Query(None, description="文件名关键词"),
    file_type: Optional[str] = Query(None, description="文件类型: image/document/spreadsheet/archive/other"),
    min_size: Optional[int] = Query(None, description="最小文件大小(字节)"),
    max_size: Optional[int] = Query(None, description="最大文件大小(字节)"),
    from_date: Optional[datetime] = Query(None, description="开始日期"),
    to_date: Optional[datetime] = Query(None, description="结束日期"),
    supplier_id: Optional[int] = Query(None, description="供应商ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    跨邮件搜索附件

    搜索维度：
    - 文件名关键词
    - 文件类型（图片/文档/表格/压缩包/其他）
    - 文件大小范围
    - 时间范围
    - 供应商
    """
    # 构建查询
    query = (
        select(
            Attachment.id,
            Attachment.email_id,
            Attachment.filename,
            Attachment.file_size,
            Attachment.mime_type,
            Attachment.created_at,
            Email.subject_original.label('email_subject'),
            Email.from_email.label('sender'),
            Supplier.name.label('supplier_name')
        )
        .join(Email, Attachment.email_id == Email.id)
        .outerjoin(Supplier, Email.supplier_id == Supplier.id)
        .where(Email.account_id == current_account.id)
    )

    # 文件名搜索
    if q:
        q = q[:200]  # 限制搜索长度
        query = query.where(Attachment.filename.ilike(f"%{q}%"))

    # 文件类型过滤
    if file_type:
        type_map = {
            'image': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'],
            'document': ['doc', 'docx', 'pdf', 'txt', 'rtf', 'odt'],
            'spreadsheet': ['xls', 'xlsx', 'csv', 'ods'],
            'archive': ['zip', 'rar', '7z', 'tar', 'gz'],
        }
        if file_type in type_map:
            ext_conditions = [Attachment.filename.ilike(f"%.{ext}") for ext in type_map[file_type]]
            query = query.where(or_(*ext_conditions))

    # 文件大小过滤
    if min_size is not None:
        query = query.where(Attachment.file_size >= min_size)
    if max_size is not None:
        query = query.where(Attachment.file_size <= max_size)

    # 时间范围过滤
    if from_date:
        query = query.where(Attachment.created_at >= from_date)
    if to_date:
        query = query.where(Attachment.created_at <= to_date)

    # 供应商过滤
    if supplier_id:
        query = query.where(Email.supplier_id == supplier_id)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页和排序
    query = query.order_by(Attachment.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = [
        AttachmentSearchResult(
            id=row.id,
            email_id=row.email_id,
            filename=row.filename,
            file_size=row.file_size or 0,
            mime_type=row.mime_type,
            created_at=row.created_at,
            email_subject=row.email_subject,
            sender=row.sender,
            supplier_name=row.supplier_name
        )
        for row in rows
    ]

    return AttachmentSearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/stats", response_model=StorageStats)
async def get_storage_stats(
    db: AsyncSession = Depends(get_db),
    current_account: EmailAccount = Depends(get_current_account)
):
    """
    获取附件存储统计

    返回：
    - 总附件数和总大小
    - 按类型分布（图片/文档/表格等）
    - 最大的10个文件
    - 重复文件统计（通过 content_hash 识别）
    """
    # 基础查询：当前账户的所有附件
    base_query = (
        select(Attachment)
        .join(Email, Attachment.email_id == Email.id)
        .where(Email.account_id == current_account.id)
    )

    # 1. 总数和总大小
    stats_query = (
        select(
            func.count(Attachment.id).label('total_count'),
            func.coalesce(func.sum(Attachment.file_size), 0).label('total_size')
        )
        .join(Email, Attachment.email_id == Email.id)
        .where(Email.account_id == current_account.id)
    )
    stats_result = await db.execute(stats_query)
    stats = stats_result.one()
    total_count = stats.total_count or 0
    total_size = stats.total_size or 0

    # 2. 按类型分布
    all_attachments_query = (
        select(Attachment.filename, Attachment.file_size, Attachment.mime_type)
        .join(Email, Attachment.email_id == Email.id)
        .where(Email.account_id == current_account.id)
    )
    all_result = await db.execute(all_attachments_query)
    all_attachments = all_result.all()

    type_stats = {}
    for att in all_attachments:
        category = get_file_type_category(att.filename or '', att.mime_type)
        if category not in type_stats:
            type_stats[category] = {'count': 0, 'size': 0}
        type_stats[category]['count'] += 1
        type_stats[category]['size'] += att.file_size or 0

    type_distribution = [
        TypeDistribution(
            type=t,
            count=data['count'],
            size=data['size'],
            percentage=round(data['count'] / total_count * 100, 1) if total_count > 0 else 0
        )
        for t, data in sorted(type_stats.items(), key=lambda x: x[1]['size'], reverse=True)
    ]

    # 3. 最大的10个文件
    largest_query = (
        select(
            Attachment.id,
            Attachment.email_id,
            Attachment.filename,
            Attachment.file_size,
            Attachment.mime_type,
            Attachment.created_at,
            Email.subject_original.label('email_subject'),
            Email.from_email.label('sender'),
            Supplier.name.label('supplier_name')
        )
        .join(Email, Attachment.email_id == Email.id)
        .outerjoin(Supplier, Email.supplier_id == Supplier.id)
        .where(Email.account_id == current_account.id)
        .order_by(Attachment.file_size.desc())
        .limit(10)
    )
    largest_result = await db.execute(largest_query)
    largest_rows = largest_result.all()

    largest_files = [
        AttachmentSearchResult(
            id=row.id,
            email_id=row.email_id,
            filename=row.filename,
            file_size=row.file_size or 0,
            mime_type=row.mime_type,
            created_at=row.created_at,
            email_subject=row.email_subject,
            sender=row.sender,
            supplier_name=row.supplier_name
        )
        for row in largest_rows
    ]

    # 4. 重复文件统计（相同 content_hash）
    duplicate_query = (
        select(
            Attachment.content_hash,
            func.count(Attachment.id).label('count'),
            func.min(Attachment.file_size).label('file_size')
        )
        .join(Email, Attachment.email_id == Email.id)
        .where(
            and_(
                Email.account_id == current_account.id,
                Attachment.content_hash.isnot(None),
                Attachment.content_hash != ''
            )
        )
        .group_by(Attachment.content_hash)
        .having(func.count(Attachment.id) > 1)
    )
    dup_result = await db.execute(duplicate_query)
    duplicates = dup_result.all()

    duplicate_count = sum(d.count - 1 for d in duplicates)  # 重复的数量（不含原始）
    duplicate_size_saved = sum((d.count - 1) * (d.file_size or 0) for d in duplicates)

    return StorageStats(
        total_count=total_count,
        total_size=total_size,
        total_size_formatted=format_file_size(total_size),
        type_distribution=type_distribution,
        largest_files=largest_files,
        duplicate_count=duplicate_count,
        duplicate_size_saved=duplicate_size_saved
    )
