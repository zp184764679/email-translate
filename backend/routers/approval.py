import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, func, case
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import Draft, Email, EmailAccount, ApproverGroup, ApproverGroupMember, SentEmailMapping, Approval
from services.email_service import EmailService
from routers.users import get_current_account
from utils.crypto import decrypt_password

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


# ============ 邮箱验证 ============
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_email_address(email: str) -> tuple[bool, str]:
    """
    验证邮箱地址格式

    Returns:
        (is_valid, error_message)
    """
    if not email:
        return False, "邮箱地址不能为空"

    email = email.strip()

    if len(email) > 254:
        return False, "邮箱地址过长"

    if not EMAIL_REGEX.match(email):
        return False, f"邮箱格式无效: {email}"

    return True, ""


def validate_email_list(email_str: str) -> tuple[bool, str, List[str]]:
    """
    验证邮箱列表（逗号或分号分隔）

    Returns:
        (is_valid, error_message, cleaned_emails)
    """
    if not email_str:
        return True, "", []

    # 支持逗号和分号分隔
    emails = [e.strip() for e in re.split(r'[,;]', email_str) if e.strip()]

    if not emails:
        return True, "", []

    cleaned = []
    for email in emails:
        is_valid, error = validate_email_address(email)
        if not is_valid:
            return False, error, []
        cleaned.append(email)

    return True, "", cleaned


# ============ 状态常量 ============
DRAFT_STATUS_DRAFT = "draft"
DRAFT_STATUS_PENDING = "pending"
DRAFT_STATUS_SENDING = "sending"
DRAFT_STATUS_SENT = "sent"
DRAFT_STATUS_REJECTED = "rejected"

# 合法的状态转换
VALID_STATUS_TRANSITIONS = {
    DRAFT_STATUS_DRAFT: [DRAFT_STATUS_PENDING],          # 草稿 -> 待审批
    DRAFT_STATUS_PENDING: [DRAFT_STATUS_SENDING, DRAFT_STATUS_REJECTED],  # 待审批 -> 发送中/驳回
    DRAFT_STATUS_SENDING: [DRAFT_STATUS_SENT, DRAFT_STATUS_PENDING],      # 发送中 -> 已发送/回退到待审批
    DRAFT_STATUS_REJECTED: [DRAFT_STATUS_DRAFT],         # 驳回 -> 草稿（需要显式操作）
    DRAFT_STATUS_SENT: [],                               # 已发送 -> 终态
}


def can_transition_to(current_status: str, target_status: str) -> bool:
    """检查状态转换是否合法"""
    allowed = VALID_STATUS_TRANSITIONS.get(current_status, [])
    return target_status in allowed


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
    # 定时发送相关
    scheduled_at: Optional[datetime] = None
    scheduled_status: Optional[str] = None

    class Config:
        from_attributes = True


class ScheduleDraftRequest(BaseModel):
    """定时发送请求"""
    scheduled_at: datetime  # 预定发送时间 (UTC)


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

    # 状态检查（使用状态机）
    if draft.status == DRAFT_STATUS_SENT:
        raise HTTPException(status_code=400, detail="邮件已发送")

    if draft.status == DRAFT_STATUS_PENDING:
        raise HTTPException(status_code=400, detail="邮件已提交审批，请等待审批")

    if draft.status == DRAFT_STATUS_REJECTED:
        raise HTTPException(
            status_code=400,
            detail="驳回的草稿需要先修改后重新保存，请使用「撤回到草稿」功能"
        )

    if not can_transition_to(draft.status, DRAFT_STATUS_PENDING):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 '{draft.status}' 不能提交审批"
        )

    # 验证收件人格式
    if draft.to_address:
        is_valid, error, _ = validate_email_list(draft.to_address)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"收件人格式错误: {error}")

    # 验证抄送格式
    if draft.cc_address:
        is_valid, error, _ = validate_email_list(draft.cc_address)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"抄送格式错误: {error}")

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
    - 审批组成员可以删除待组审批的草稿
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

    # 检查权限：作者 or 审批人（支持单人和组）
    is_author = draft.author_id == account.id
    is_approver = False

    if draft.status == "pending":
        # 单人审批模式
        if draft.approver_id == account.id:
            is_approver = True
        # 组审批模式：检查是否是组成员
        elif draft.approver_group_id:
            member_check = await db.execute(
                select(ApproverGroupMember).where(
                    ApproverGroupMember.group_id == draft.approver_group_id,
                    ApproverGroupMember.member_id == account.id
                )
            )
            is_approver = member_check.scalar_one_or_none() is not None

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
    # 获取草稿（使用 FOR UPDATE 锁定，防止并发审批）
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id).with_for_update()
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 幂等性检查：如果已经发送过，直接返回成功
    if draft.status == "sent":
        return {"status": "sent", "message": "邮件已发送（重复请求）"}

    # 幂等性检查：如果正在发送中，拒绝重复请求
    if draft.status == "sending":
        raise HTTPException(status_code=409, detail="邮件正在发送中，请勿重复操作")

    # 幂等性检查：如果已有 sent_message_id，说明邮件已发送
    if draft.sent_message_id:
        # 修复状态不一致的情况
        draft.status = "sent"
        await db.commit()
        return {"status": "sent", "message": "邮件已发送（状态已修复）"}

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

    # 验证收件人（发送前最终检查）
    if not to_addr:
        raise HTTPException(status_code=400, detail="收件人地址为空，无法发送")

    is_valid, error, cleaned_to = validate_email_list(to_addr)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"收件人格式错误: {error}")

    if not cleaned_to:
        raise HTTPException(status_code=400, detail="收件人地址为空，无法发送")

    # 验证抄送（可选）
    if draft.cc_address:
        is_valid, error, _ = validate_email_list(draft.cc_address)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"抄送格式错误: {error}")

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

    # 处理发送结果
    if send_error:
        # 发送失败，回退状态
        draft.status = "pending"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"邮件发送失败: {send_error}")

    # 邮件发送成功 - 关键：优先保存 sent_message_id 防止重复发送
    if sent_message_id:
        try:
            # 第一步：立即保存 message_id（幂等性关键）
            draft.sent_message_id = sent_message_id
            draft.status = "sent"
            draft.sent_at = datetime.utcnow()
            await db.commit()
        except Exception as e:
            print(f"[CRITICAL] Failed to save sent_message_id! draft_id={draft_id}, message_id={sent_message_id}, error={e}")
            # 重试一次
            try:
                await db.rollback()
                draft.sent_message_id = sent_message_id
                draft.status = "sent"
                draft.sent_at = datetime.utcnow()
                await db.commit()
            except Exception:
                # 至少记录到日志，便于手动修复
                print(f"[CRITICAL] Retry also failed! Manual fix required: UPDATE drafts SET sent_message_id='{sent_message_id}', status='sent' WHERE id={draft_id}")

        # 第二步：尝试保存发送映射（非关键，失败不影响）
        try:
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
            await db.commit()
        except Exception as e:
            print(f"[Warning] Failed to save SentEmailMapping for draft {draft_id}: {e}")
            # 映射保存失败不影响主流程

        # 第三步：记录审批历史
        try:
            approval_record = Approval(
                draft_id=draft.id,
                operator_id=account.id,
                action="approved",
                comment="审批通过并发送"
            )
            db.add(approval_record)
            await db.commit()
        except Exception as e:
            print(f"[Warning] Failed to save Approval record for draft {draft_id}: {e}")

    else:
        # 没有 message_id（罕见情况），仍标记为已发送
        draft.status = "sent"
        draft.sent_at = datetime.utcnow()

        # 记录审批历史
        approval_record = Approval(
            draft_id=draft.id,
            operator_id=account.id,
            action="approved",
            comment="审批通过并发送（无 message_id）"
        )
        db.add(approval_record)

        await db.commit()

    return {"status": "sent", "message": "审批通过，邮件已发送"}


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

    # 记录审批历史
    approval_record = Approval(
        draft_id=draft.id,
        operator_id=account.id,
        action="rejected",
        comment=request.reason
    )
    db.add(approval_record)

    await db.commit()

    return {"status": "rejected", "message": "已驳回"}


# ============ 新增功能 ============

@router.post("/{draft_id}/revert")
async def revert_to_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """将驳回的草稿撤回到草稿状态，以便修改后重新提交

    只有草稿作者可以执行此操作。
    """
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 只有作者可以撤回
    if draft.author_id != account.id:
        raise HTTPException(status_code=403, detail="只有草稿作者可以撤回到草稿状态")

    # 检查状态转换是否合法
    if draft.status != DRAFT_STATUS_REJECTED:
        raise HTTPException(
            status_code=400,
            detail=f"只有驳回状态的草稿可以撤回，当前状态: {draft.status}"
        )

    # 撤回到草稿状态
    draft.status = DRAFT_STATUS_DRAFT
    draft.approver_id = None
    draft.approver_group_id = None
    draft.submitted_at = None
    # 保留 reject_reason 以便用户查看驳回原因

    await db.commit()

    return {"status": "draft", "message": "已撤回到草稿状态，您可以修改后重新提交"}


# ============ 批量审批 ============

class BatchApproveRequest(BaseModel):
    draft_ids: List[int]


class BatchRejectRequest(BaseModel):
    draft_ids: List[int]
    reason: str


@router.post("/batch/approve")
async def batch_approve(
    request: BatchApproveRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量通过审批

    注意：批量审批不会发送邮件，只是标记为"已批准待发送"状态。
    邮件发送需要单独操作。
    """
    if not request.draft_ids:
        raise HTTPException(status_code=400, detail="请选择要审批的草稿")

    if len(request.draft_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多批量审批 50 个草稿")

    results = {
        "success": [],
        "failed": []
    }

    for draft_id in request.draft_ids:
        try:
            result = await db.execute(
                select(Draft).where(Draft.id == draft_id)
            )
            draft = result.scalar_one_or_none()

            if not draft:
                results["failed"].append({"id": draft_id, "error": "草稿不存在"})
                continue

            # 检查权限
            has_permission = await check_approver_permission(draft, account, db)
            if not has_permission:
                results["failed"].append({"id": draft_id, "error": "没有审批权限"})
                continue

            if draft.status != "pending":
                results["failed"].append({"id": draft_id, "error": f"状态不正确: {draft.status}"})
                continue

            # 记录审批历史
            approval_record = Approval(
                draft_id=draft.id,
                operator_id=account.id,
                action="approved",
                comment="批量审批通过"
            )
            db.add(approval_record)

            results["success"].append(draft_id)

        except Exception as e:
            results["failed"].append({"id": draft_id, "error": str(e)})

    await db.commit()

    return {
        "message": f"批量审批完成，成功 {len(results['success'])} 个，失败 {len(results['failed'])} 个",
        "results": results
    }


@router.post("/batch/reject")
async def batch_reject(
    request: BatchRejectRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量驳回审批"""
    if not request.draft_ids:
        raise HTTPException(status_code=400, detail="请选择要驳回的草稿")

    if len(request.draft_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多批量驳回 50 个草稿")

    if not request.reason:
        raise HTTPException(status_code=400, detail="请填写驳回原因")

    results = {
        "success": [],
        "failed": []
    }

    for draft_id in request.draft_ids:
        try:
            result = await db.execute(
                select(Draft).where(Draft.id == draft_id)
            )
            draft = result.scalar_one_or_none()

            if not draft:
                results["failed"].append({"id": draft_id, "error": "草稿不存在"})
                continue

            # 检查权限
            has_permission = await check_approver_permission(draft, account, db)
            if not has_permission:
                results["failed"].append({"id": draft_id, "error": "没有审批权限"})
                continue

            if draft.status != "pending":
                results["failed"].append({"id": draft_id, "error": f"状态不正确: {draft.status}"})
                continue

            # 驳回
            draft.status = "rejected"
            draft.reject_reason = request.reason

            # 记录审批历史
            approval_record = Approval(
                draft_id=draft.id,
                operator_id=account.id,
                action="rejected",
                comment=request.reason
            )
            db.add(approval_record)

            results["success"].append(draft_id)

        except Exception as e:
            results["failed"].append({"id": draft_id, "error": str(e)})

    await db.commit()

    return {
        "message": f"批量驳回完成，成功 {len(results['success'])} 个，失败 {len(results['failed'])} 个",
        "results": results
    }


# ============ 审批历史 ============

class ApprovalHistoryResponse(BaseModel):
    id: int
    draft_id: int
    operator_id: int
    operator_email: Optional[str] = None
    action: str
    comment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/{draft_id}/history", response_model=List[ApprovalHistoryResponse])
async def get_approval_history(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取草稿的审批历史"""
    # 先验证草稿存在且用户有权限查看
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 作者或审批人可以查看
    is_author = draft.author_id == account.id
    is_approver = await check_approver_permission(draft, account, db)

    if not is_author and not is_approver:
        raise HTTPException(status_code=403, detail="没有权限查看此草稿的审批历史")

    # 查询审批历史
    result = await db.execute(
        select(Approval, EmailAccount.email.label("operator_email"))
        .outerjoin(EmailAccount, Approval.operator_id == EmailAccount.id)
        .where(Approval.draft_id == draft_id)
        .order_by(Approval.created_at.desc())
    )

    history = []
    for row in result.all():
        approval = row[0]
        operator_email = row[1]
        history.append(ApprovalHistoryResponse(
            id=approval.id,
            draft_id=approval.draft_id,
            operator_id=approval.operator_id,
            operator_email=operator_email,
            action=approval.action,
            comment=approval.comment,
            created_at=approval.created_at
        ))

    return history


# ============ 审批统计 ============

class ApprovalStats(BaseModel):
    total_drafts: int
    pending_count: int
    approved_count: int
    rejected_count: int
    sent_count: int
    # 我作为审批人的统计
    my_pending: int
    my_approved: int
    my_rejected: int


# ============ 定时发送 ============

class ScheduledDraftResponse(BaseModel):
    """定时发送草稿响应"""
    id: int
    to_address: Optional[str] = None
    subject: Optional[str] = None
    scheduled_at: datetime
    scheduled_status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/scheduled", response_model=List[ScheduledDraftResponse])
async def get_scheduled_drafts(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的定时发送列表"""
    result = await db.execute(
        select(Draft)
        .where(
            Draft.author_id == account.id,
            Draft.scheduled_status == "pending"
        )
        .order_by(Draft.scheduled_at.asc())
    )
    return result.scalars().all()


@router.post("/{draft_id}/schedule")
async def schedule_draft(
    draft_id: int,
    request: ScheduleDraftRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """设置草稿定时发送

    注意：定时发送不需要审批流程，由作者直接设置
    """
    # 验证时间不能是过去
    if request.scheduled_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="预定发送时间必须在当前时间之后")

    # 获取草稿
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 只有作者可以设置定时发送
    if draft.author_id != account.id:
        raise HTTPException(status_code=403, detail="只有草稿作者可以设置定时发送")

    # 已发送的邮件不能再设置
    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="邮件已发送，无法设置定时发送")

    # 待审批的邮件不能设置定时发送
    if draft.status == "pending":
        raise HTTPException(status_code=400, detail="邮件正在审批中，请先撤回审批再设置定时发送")

    # 验证收件人
    if not draft.to_address:
        raise HTTPException(status_code=400, detail="收件人地址为空，无法设置定时发送")

    is_valid, error, _ = validate_email_list(draft.to_address)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"收件人格式错误: {error}")

    # 验证翻译内容
    if not draft.body_translated and not draft.body_chinese:
        raise HTTPException(status_code=400, detail="邮件正文为空，无法发送")

    # 设置定时发送
    draft.scheduled_at = request.scheduled_at
    draft.scheduled_status = "pending"
    draft.status = "scheduled"  # 新状态：已安排定时发送

    await db.commit()

    return {
        "status": "scheduled",
        "message": "已设置定时发送",
        "scheduled_at": request.scheduled_at.isoformat()
    }


@router.post("/{draft_id}/cancel-schedule")
async def cancel_scheduled_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """取消定时发送"""
    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 只有作者可以取消
    if draft.author_id != account.id:
        raise HTTPException(status_code=403, detail="只有草稿作者可以取消定时发送")

    # 检查是否是定时发送状态
    if draft.scheduled_status != "pending":
        raise HTTPException(status_code=400, detail="此草稿没有待发送的定时任务")

    # 取消定时发送
    draft.scheduled_at = None
    draft.scheduled_status = "cancelled"
    draft.status = "draft"  # 恢复为草稿状态

    await db.commit()

    return {"status": "cancelled", "message": "已取消定时发送"}


@router.put("/{draft_id}/reschedule")
async def reschedule_draft(
    draft_id: int,
    request: ScheduleDraftRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """修改定时发送时间"""
    # 验证时间不能是过去
    if request.scheduled_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="预定发送时间必须在当前时间之后")

    result = await db.execute(
        select(Draft).where(Draft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 只有作者可以修改
    if draft.author_id != account.id:
        raise HTTPException(status_code=403, detail="只有草稿作者可以修改定时发送")

    # 检查是否是定时发送状态
    if draft.scheduled_status != "pending":
        raise HTTPException(status_code=400, detail="此草稿没有待发送的定时任务")

    # 更新时间
    draft.scheduled_at = request.scheduled_at

    await db.commit()

    return {
        "status": "rescheduled",
        "message": "已更新发送时间",
        "scheduled_at": request.scheduled_at.isoformat()
    }


@router.get("/stats/summary", response_model=ApprovalStats)
async def get_approval_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取审批统计摘要"""
    # 我作为作者的草稿统计
    result = await db.execute(
        select(
            func.count(Draft.id).label("total"),
            func.sum(case((Draft.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((Draft.status == "sent", 1), else_=0)).label("sent"),
            func.sum(case((Draft.status == "rejected", 1), else_=0)).label("rejected")
        )
        .where(Draft.author_id == account.id)
    )
    my_stats = result.one()

    # 我作为审批人的统计
    # 先获取我所在的组
    member_groups_result = await db.execute(
        select(ApproverGroupMember.group_id).where(
            ApproverGroupMember.member_id == account.id
        )
    )
    my_group_ids = [row[0] for row in member_groups_result.all()]

    # 我需要审批的（pending 状态，指定给我或我的组）
    conditions = [Draft.status == "pending"]
    if my_group_ids:
        conditions.append(or_(
            Draft.approver_id == account.id,
            Draft.approver_group_id.in_(my_group_ids)
        ))
    else:
        conditions.append(Draft.approver_id == account.id)

    pending_result = await db.execute(
        select(func.count(Draft.id)).where(*conditions)
    )
    my_pending = pending_result.scalar() or 0

    # 我审批过的记录
    approved_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.operator_id == account.id,
            Approval.action == "approved"
        )
    )
    my_approved = approved_result.scalar() or 0

    rejected_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.operator_id == account.id,
            Approval.action == "rejected"
        )
    )
    my_rejected = rejected_result.scalar() or 0

    return ApprovalStats(
        total_drafts=my_stats.total or 0,
        pending_count=my_stats.pending or 0,
        approved_count=my_approved,  # 使用审批记录
        rejected_count=my_stats.rejected or 0,
        sent_count=my_stats.sent or 0,
        my_pending=my_pending,
        my_approved=my_approved,
        my_rejected=my_rejected
    )
