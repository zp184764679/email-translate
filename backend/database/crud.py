from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import Optional, List
from passlib.context import CryptContext

from .models import (
    EmailAccount, Supplier, Email, Attachment,
    Draft, ApprovalRule, Approval, Glossary, EmailReadStatus,
    TranslationBatch
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============ Email Account CRUD ============
async def create_email_account(db: AsyncSession, email: str, password: str, imap_server: str,
                                smtp_server: str, imap_port: int = 993, smtp_port: int = 465):
    account = EmailAccount(
        email=email,
        password=password,  # Should be encrypted before storing
        imap_server=imap_server,
        imap_port=imap_port,
        smtp_server=smtp_server,
        smtp_port=smtp_port
    )
    db.add(account)
    await db.flush()
    return account


async def get_active_email_accounts(db: AsyncSession) -> List[EmailAccount]:
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.is_active == True)
    )
    return result.scalars().all()


async def get_email_account_by_email(db: AsyncSession, email: str) -> Optional[EmailAccount]:
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.email == email)
    )
    return result.scalar_one_or_none()


async def get_email_account_by_id(db: AsyncSession, account_id: int) -> Optional[EmailAccount]:
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.id == account_id)
    )
    return result.scalar_one_or_none()


# ============ Email CRUD ============
async def create_email(db: AsyncSession, email_data: dict) -> Email:
    email = Email(**email_data)
    db.add(email)
    await db.flush()
    return email


async def get_email_by_message_id(db: AsyncSession, message_id: str) -> Optional[Email]:
    result = await db.execute(
        select(Email).where(Email.message_id == message_id)
    )
    return result.scalar_one_or_none()


async def get_emails(db: AsyncSession, supplier_id: int = None, user_id: int = None,
                     direction: str = None, limit: int = 50, offset: int = 0) -> List[Email]:
    query = select(Email).options(
        selectinload(Email.attachments),
        selectinload(Email.supplier)
    )

    if supplier_id:
        query = query.where(Email.supplier_id == supplier_id)
    if direction:
        query = query.where(Email.direction == direction)

    query = query.order_by(Email.received_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


async def get_untranslated_emails(db: AsyncSession, limit: int = 100) -> List[Email]:
    result = await db.execute(
        select(Email)
        .where(and_(
            Email.is_translated == False,
            Email.direction == "inbound",
            Email.language_detected != "zh"
        ))
        .limit(limit)
    )
    return result.scalars().all()


async def update_email_translation(db: AsyncSession, email_id: int,
                                    subject_translated: str, body_translated: str):
    await db.execute(
        update(Email)
        .where(Email.id == email_id)
        .values(
            subject_translated=subject_translated,
            body_translated=body_translated,
            is_translated=True
        )
    )


# ============ Draft CRUD ============
async def create_draft(db: AsyncSession, reply_to_email_id: int, author_id: int,
                       body_chinese: str, target_language: str) -> Draft:
    draft = Draft(
        reply_to_email_id=reply_to_email_id,
        author_id=author_id,
        body_chinese=body_chinese,
        target_language=target_language
    )
    db.add(draft)
    await db.flush()
    return draft


async def get_pending_drafts(db: AsyncSession) -> List[Draft]:
    result = await db.execute(
        select(Draft)
        .options(selectinload(Draft.reply_to_email))
        .where(Draft.status == "draft")
        .order_by(Draft.created_at.desc())
    )
    return result.scalars().all()


async def get_drafts_by_author(db: AsyncSession, author_id: int) -> List[Draft]:
    result = await db.execute(
        select(Draft)
        .options(selectinload(Draft.reply_to_email))
        .where(Draft.author_id == author_id)
        .order_by(Draft.created_at.desc())
    )
    return result.scalars().all()


async def update_draft_status(db: AsyncSession, draft_id: int, status: str):
    values = {"status": status, "updated_at": datetime.utcnow()}
    if status == "sent":
        values["sent_at"] = datetime.utcnow()

    await db.execute(
        update(Draft).where(Draft.id == draft_id).values(**values)
    )


# ============ Supplier CRUD ============
async def get_or_create_supplier_by_email(db: AsyncSession, email: str) -> Supplier:
    domain = "@" + email.split("@")[-1] if "@" in email else None

    if domain:
        result = await db.execute(
            select(Supplier).where(Supplier.email_domain == domain)
        )
        supplier = result.scalar_one_or_none()
        if supplier:
            return supplier

    # Create new supplier
    supplier = Supplier(
        name=domain.replace("@", "") if domain else email,
        email_domain=domain,
        contact_email=email
    )
    db.add(supplier)
    await db.flush()
    return supplier


# ============ Glossary CRUD ============
async def get_glossary_by_supplier(db: AsyncSession, supplier_id: int) -> List[Glossary]:
    result = await db.execute(
        select(Glossary).where(Glossary.supplier_id == supplier_id)
    )
    return result.scalars().all()


async def add_glossary_term(db: AsyncSession, supplier_id: int, term_source: str,
                            term_target: str, source_lang: str, target_lang: str) -> Glossary:
    term = Glossary(
        supplier_id=supplier_id,
        term_source=term_source,
        term_target=term_target,
        source_lang=source_lang,
        target_lang=target_lang
    )
    db.add(term)
    await db.flush()
    return term


# ============ Translation Batch CRUD ============
async def create_translation_batch(db: AsyncSession, batch_id: str, total_requests: int) -> TranslationBatch:
    batch = TranslationBatch(
        batch_id=batch_id,
        total_requests=total_requests
    )
    db.add(batch)
    await db.flush()
    return batch


async def update_batch_status(db: AsyncSession, batch_id: str, status: str, completed_requests: int = None):
    values = {"status": status}
    if status == "completed":
        values["completed_at"] = datetime.utcnow()
    if completed_requests is not None:
        values["completed_requests"] = completed_requests

    await db.execute(
        update(TranslationBatch)
        .where(TranslationBatch.batch_id == batch_id)
        .values(**values)
    )
