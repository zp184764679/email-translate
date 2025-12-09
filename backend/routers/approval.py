from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database.database import get_db
from database.models import Draft, Email, EmailAccount
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
    to_address: Optional[str] = None
    cc_address: Optional[str] = None
    subject: Optional[str] = None
    body_chinese: str
    body_translated: Optional[str]
    target_language: str
    status: str
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


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
    """更新草稿"""
    result = await db.execute(
        select(Draft)
        .join(Email, Draft.reply_to_email_id == Email.id)
        .where(Draft.id == draft_id, Email.account_id == account.id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

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
async def send_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """发送草稿"""
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

    # 获取原始邮件
    email_result = await db.execute(select(Email).where(Email.id == draft.reply_to_email_id))
    original = email_result.scalar_one_or_none()

    if not original:
        raise HTTPException(status_code=404, detail="原邮件不存在")

    # 发送邮件
    try:
        service = EmailService(
            imap_server=account.imap_server,
            smtp_server=account.smtp_server,
            email_address=account.email,
            password=decrypt_password(account.password),
            smtp_port=account.smtp_port
        )

        # 使用草稿中的收件人和主题，如果没有则使用原邮件信息
        to_addr = draft.to_address or original.from_email
        subject = draft.subject
        if not subject:
            subject = original.subject_original
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

        success = service.send_email(
            to=to_addr,
            cc=draft.cc_address,  # 添加抄送
            subject=subject,
            body=draft.body_translated or draft.body_chinese
        )

        if success:
            draft.status = "sent"
            draft.sent_at = datetime.utcnow()
            await db.commit()
            return {"status": "sent", "message": "邮件发送成功"}
        else:
            raise HTTPException(status_code=500, detail="邮件发送失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")


@router.delete("/{draft_id}")
async def delete_draft(
    draft_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除草稿"""
    result = await db.execute(
        select(Draft)
        .join(Email, Draft.reply_to_email_id == Email.id)
        .where(Draft.id == draft_id, Email.account_id == account.id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="已发送的邮件无法删除")

    await db.execute(delete(Draft).where(Draft.id == draft_id))
    await db.commit()

    return {"message": "草稿已删除"}
