from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import Draft, Email, EmailAccount, ApproverGroup, ApproverGroupMember, SentEmailMapping
from services.email_service import EmailService
from routers.users import get_current_account
from utils.crypto import decrypt_password

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


# ============ Schemas ============
class DraftCreate(BaseModel):
    reply_to_email_id: int
    to: Optional[str] = None         # 收件人（可自定义）
    cc: Optional[str] = None         # 抄送（可选）
    subject: Optional[str] = None    # 主题（可自定义）
    body_chinese: str
    body_translated: Optional[str] = None
    target_language: str = "en"


class DraftUpdate(BaseModel):
    to: Optional[str] = None
    cc: Optional[str] = None
    subject: Optional[str] = None
    body_chinese: Optional[str] = None
    body_translated: Optional[str] = None


class DraftResponse(BaseModel):
    id: int
    reply_to_email_id: int
    author_id: Optional[int] = None
    to_address: Optional[str] = None
    cc_address: Optional[str] = None
    subject: Optional[str] = None
    body_chinese: str
    body_translated: Optional[str]
    target_language: str
    status: str
    sent_at: Optional[datetime]
    created_at: datetime
    # 审批相关
    approver_id: Optional[int] = None
    approver_group_id: Optional[int] = None
    submitted_at: Optional[datetime] = None
    reject_reason: Optional[str] = None

    class Config:
        from_attributes = True


class SubmitForApprovalRequest(BaseModel):
    approver_id: Optional[int] = None        # 单人审批
    approver_group_id: Optional[int] = None  # 组审批（二选一）
    save_as_default: bool = False


class RejectRequest(BaseModel):
    reason: str


# ============ Routes ============
@router.get("", response_model=List[DraftResponse])
async def get_my_drafts(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前账户的草稿列表"""
    result = await db.execute(
        select(Draft)
        .join(Email, Draft.reply_to_email_id == Email.id)
        .where(Email.account_id == account.id)
        .order_by(Draft.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=DraftResponse)
async def create_draft(
    draft: DraftCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """创建回复草稿"""
    # 验证邮件属于当前账户
    result = await db.execute(
        select(Email).where(Email.id == draft.reply_to_email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 如果没有提供收件人/主题，使用原邮件的信息
    to_addr = draft.to or email.from_email
    subject_text = draft.subject
    if not subject_text:
        orig_subject = email.subject_original or ""
        subject_text = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

    new_draft = Draft(
        reply_to_email_id=draft.reply_to_email_id,
        author_id=account.id,  # 使用账户ID作为作者
        to_address=to_addr,
        cc_address=draft.cc,
        subject=subject_text,
        body_chinese=draft.body_chinese,
        body_translated=draft.body_translated,
        target_language=draft.target_language,
        status="draft"
    )
    db.add(new_draft)
    await db.commit()
    await db.refresh(new_draft)

    return new_draft


@router.put("/{draft_id}", response_model=DraftResponse)
async def update_draft(
    draft_id: int,
    draft_update: DraftUpdate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """更新草稿（作者或审批人都可以修改）"""
    # 先查找草稿
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 检查权限：作者或审批人可以修改
    email_result = await db.execute(
        select(Email).where(Email.id == draft.reply_to_email_id)
    )
    email = email_result.scalar_one_or_none()

    is_author = email and email.account_id == account.id

    # 检查是否是审批人（单人或组成员）
    is_approver = False
    if draft.status == "pending":
        if draft.approver_id == account.id:
            is_approver = True
        elif draft.approver_group_id:
            # 检查是否是组成员
            member_check = await db.execute(
                select(ApproverGroupMember).where(
                    ApproverGroupMember.group_id == draft.approver_group_id,
                    ApproverGroupMember.member_id == account.id
                )
            )
            is_approver = member_check.scalar_one_or_none() is not None

    if not is_author and not is_approver:
        raise HTTPException(status_code=403, detail="没有权限修改此草稿")

    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="已发送的邮件无法编辑")

    # 更新收件人、抄送、主题字段
    if draft_update.to is not None:
        draft.to_address = draft_update.to
    if draft_update.cc is not None:
        draft.cc_address = draft_update.cc
    if draft_update.subject is not None:
        draft.subject = draft_update.subject

    # 更新正文字段
    if draft_update.body_chinese is not None:
        draft.body_chinese = draft_update.body_chinese
    if draft_update.body_translated is not None:
        draft.body_translated = draft_update.body_translated

    await db.commit()
    return draft


@router.post("/{draft_id}/send")
async def submit_for_approval(
    draft_id: int,
    request: SubmitForApprovalRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """提交草稿给审批人审批（支持单人或组）"""
    # 验证必须选择一个审批方式
    if not request.approver_id and not request.approver_group_id:
        raise HTTPException(status_code=400, detail="请选择审批人或审批人组")

    if request.approver_id and request.approver_group_id:
        raise HTTPException(status_code=400, detail="只能选择一种审批方式")

    result = await db.execute(
        select(Draft)
        .join(Email, Draft.reply_to_email_id == Email.id)
        .where(Draft.id == draft_id, Email.account_id == account.id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="邮件已发送")

    if draft.status == "pending":
        raise HTTPException(status_code=400, detail="邮件已提交审批，请等待审批")

    approver_info = None

    if request.approver_id:
        # 单人审批模式
        approver_result = await db.execute(
            select(EmailAccount).where(EmailAccount.id == request.approver_id)
        )
        approver = approver_result.scalar_one_or_none()
        if not approver:
            raise HTTPException(status_code=404, detail="审批人不存在")

        draft.approver_id = request.approver_id
        draft.approver_group_id = None
        approver_info = approver.email

        # 保存为默认审批人
        if request.save_as_default:
            account.default_approver_id = request.approver_id

    else:
        # 组审批模式
        group_result = await db.execute(
            select(ApproverGroup)
            .options(selectinload(ApproverGroup.members))
            .where(ApproverGroup.id == request.approver_group_id)
        )
        group = group_result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="审批人组不存在")

        if not group.members:
            raise HTTPException(status_code=400, detail="审批人组没有成员")

        draft.approver_id = None
        draft.approver_group_id = request.approver_group_id
        approver_info = f"组: {group.name}"

    # 提交审批
    draft.status = "pending"
    draft.submitted_at = datetime.utcnow()
    draft.reject_reason = None

    await db.commit()

    return {
        "status": "pending",
        "message": "邮件已提交审批",
        "approver": approver_info
    }


@router.delete("/{draft_id}")
async def delete_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除草稿

    权限检查：
    - 草稿作者可以删除自己的草稿
    - 审批人可以删除待自己审批的草稿（相当于驳回）
    - 已发送的邮件无法删除
    """
    # 先获取草稿，不加权限条件
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="已发送的邮件无法删除")

    # 检查权限：作者 or 审批人
    is_author = draft.author_id == account.id
    is_approver = draft.approver_id == account.id if draft.approver_id else False

    if not is_author and not is_approver:
        raise HTTPException(status_code=403, detail="没有权限删除此草稿")

    await db.execute(delete(Draft).where(Draft.id == draft_id))
    await db.commit()

    return {"message": "草稿已删除"}


# ============ 审批相关 API ============

class PendingDraftResponse(BaseModel):
    """待审批草稿响应（包含作者信息）"""
    id: int
    reply_to_email_id: int
    author_id: int
    author_email: str  # 提交人邮箱
    to_address: Optional[str] = None
    cc_address: Optional[str] = None
    subject: Optional[str] = None
    body_chinese: str
    body_translated: Optional[str]
    target_language: str
    status: str
    submitted_at: Optional[datetime] = None
    created_at: datetime
    # 审批方式
    approver_id: Optional[int] = None
    approver_group_id: Optional[int] = None
    approver_group_name: Optional[str] = None  # 组名

    class Config:
        from_attributes = True


@router.get("/pending", response_model=List[PendingDraftResponse])
async def get_pending_drafts(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取需要当前用户审批的草稿列表（支持单人和组）"""
    # 先获取用户所在的组ID列表
    member_groups_result = await db.execute(
        select(ApproverGroupMember.group_id).where(
            ApproverGroupMember.member_id == account.id
        )
    )
    my_group_ids = [row[0] for row in member_groups_result.all()]

    # 查询待审批草稿：指定给我 或 指定给我所在的组
    conditions = [Draft.status == "pending"]

    if my_group_ids:
        conditions.append(or_(
            Draft.approver_id == account.id,
            Draft.approver_group_id.in_(my_group_ids)
        ))
    else:
        conditions.append(Draft.approver_id == account.id)

    result = await db.execute(
        select(Draft, EmailAccount.email.label("author_email"), ApproverGroup.name.label("group_name"))
        .join(EmailAccount, Draft.author_id == EmailAccount.id)
        .outerjoin(ApproverGroup, Draft.approver_group_id == ApproverGroup.id)
        .where(*conditions)
        .order_by(Draft.submitted_at.desc())
    )

    drafts = []
    for row in result.all():
        draft = row[0]
        author_email = row[1]
        group_name = row[2]
        drafts.append(PendingDraftResponse(
            id=draft.id,
            reply_to_email_id=draft.reply_to_email_id,
            author_id=draft.author_id,
            author_email=author_email,
            to_address=draft.to_address,
            cc_address=draft.cc_address,
            subject=draft.subject,
            body_chinese=draft.body_chinese,
            body_translated=draft.body_translated,
            target_language=draft.target_language,
            status=draft.status,
            submitted_at=draft.submitted_at,
            created_at=draft.created_at,
            approver_id=draft.approver_id,
            approver_group_id=draft.approver_group_id,
            approver_group_name=group_name
        ))

    return drafts


async def check_approver_permission(draft: Draft, account: EmailAccount, db: AsyncSession) -> bool:
    """检查用户是否有审批权限（支持单人和组）"""
    # 单人审批
    if draft.approver_id:
        return draft.approver_id == account.id

    # 组审批：检查用户是否是组成员
    if draft.approver_group_id:
        result = await db.execute(
            select(ApproverGroupMember).where(
                ApproverGroupMember.group_id == draft.approver_group_id,
                ApproverGroupMember.member_id == account.id
            )
        )
        return result.scalar_one_or_none() is not None

    return False


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """通过审批并发送邮件"""
    # 获取草稿
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 验证当前用户有审批权限
    has_permission = await check_approver_permission(draft, account, db)
    if not has_permission:
        raise HTTPException(status_code=403, detail="您没有审批此邮件的权限")

    if draft.status != "pending":
        raise HTTPException(status_code=400, detail="此草稿不在待审批状态")

    # 获取草稿作者账户（用于发送邮件）
    author_result = await db.execute(
        select(EmailAccount).where(EmailAccount.id == draft.author_id)
    )
    author = author_result.scalar_one_or_none()
    if not author:
        raise HTTPException(status_code=404, detail="草稿作者不存在")

    # 获取原始邮件
    email_result = await db.execute(
        select(Email).where(Email.id == draft.reply_to_email_id)
    )
    original = email_result.scalar_one_or_none()

    # 准备发送参数
    to_addr = draft.to_address
    if not to_addr and original:
        to_addr = original.from_email

    subject = draft.subject
    if not subject and original:
        subject = original.subject_original
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

    body_to_send = draft.body_translated or draft.body_chinese

    # 判断是否经过翻译
    was_translated = bool(
        draft.body_chinese and draft.body_translated
        and draft.body_chinese.strip() != draft.body_translated.strip()
    )

    # 先标记为"发送中"状态，防止重复发送
    draft.status = "sending"
    await db.commit()

    # 发送邮件（使用作者的账户发送）
    sent_message_id = None
    send_error = None

    try:
        service = EmailService(
            imap_server=author.imap_server,
            smtp_server=author.smtp_server,
            email_address=author.email,
            password=decrypt_password(author.password),
            smtp_port=author.smtp_port
        )

        success, sent_message_id = service.send_email(
            to=to_addr,
            cc=draft.cc_address,
            subject=subject or "",
            body=body_to_send
        )

        if not success:
            send_error = "SMTP 发送失败"

    except Exception as e:
        send_error = str(e)
        print(f"[Approval] Email send error for draft {draft_id}: {e}")

    # 无论数据库操作是否成功，邮件发送结果已确定
    # 更新数据库状态
    try:
        if send_error:
            # 发送失败，回退状态
            draft.status = "pending"
            await db.commit()
            raise HTTPException(status_code=500, detail=f"邮件发送失败: {send_error}")

        # 发送成功，保存映射和更新状态
        if sent_message_id:
            mapping = SentEmailMapping(
                message_id=sent_message_id,
                draft_id=draft.id,
                account_id=author.id,
                subject_original=draft.subject,
                subject_sent=subject or "",
                body_original=draft.body_chinese or draft.body_translated,
                body_sent=body_to_send,
                was_translated=was_translated,
                to_email=to_addr
            )
            db.add(mapping)
            draft.sent_message_id = sent_message_id

        draft.status = "sent"
        draft.sent_at = datetime.utcnow()
        await db.commit()

        return {"status": "sent", "message": "审批通过，邮件已发送"}

    except HTTPException:
        raise
    except Exception as db_error:
        # 关键：邮件已发送但数据库更新失败
        # 记录日志以便手动修复
        print(f"[CRITICAL] Email sent but DB update failed! draft_id={draft_id}, message_id={sent_message_id}, error={db_error}")
        # 尝试至少更新状态
        try:
            draft.status = "sent"
            draft.sent_at = datetime.utcnow()
            await db.commit()
        except Exception:
            pass
        # 返回成功（因为邮件确实已发送）
        return {"status": "sent", "message": "邮件已发送（注意：发送记录可能未完整保存）"}


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: int,
    request: RejectRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """驳回审批"""
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 验证当前用户有审批权限
    has_permission = await check_approver_permission(draft, account, db)
    if not has_permission:
        raise HTTPException(status_code=403, detail="您没有审批此邮件的权限")

    if draft.status != "pending":
        raise HTTPException(status_code=400, detail="此草稿不在待审批状态")

    # 驳回
    draft.status = "rejected"
    draft.reject_reason = request.reason

    await db.commit()

    return {"status": "rejected", "message": "已驳回"}
