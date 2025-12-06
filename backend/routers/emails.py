from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from database.database import get_db
from database import crud
from database.models import Email, EmailAccount, Attachment
from services.email_service import EmailService
from routers.users import get_current_account
from config import get_settings

router = APIRouter(prefix="/api/emails", tags=["emails"])
settings = get_settings()


# ============ Schemas ============
class EmailResponse(BaseModel):
    """邮件响应模型 (符合 RFC 5322 标准)"""
    id: int
    message_id: str

    # 发件人信息
    from_email: str
    from_name: Optional[str]

    # 收件人信息 (完整列表)
    to_email: Optional[str]           # 收件人列表
    cc_email: Optional[str]           # 抄送列表
    bcc_email: Optional[str] = None   # 密送列表
    reply_to: Optional[str] = None    # 回复地址

    # 邮件内容
    subject_original: str
    subject_translated: Optional[str]
    body_original: Optional[str]
    body_translated: Optional[str]
    body_html: Optional[str]          # HTML正文

    # 元数据
    language_detected: Optional[str]
    direction: str                    # inbound/outbound
    is_translated: bool
    is_read: bool = False
    is_flagged: bool = False
    received_at: datetime
    supplier_id: Optional[int]

    # 邮件线程信息
    thread_id: Optional[str]
    in_reply_to: Optional[str]

    class Config:
        from_attributes = True


class AttachmentResponse(BaseModel):
    id: int
    filename: str
    file_size: Optional[int]
    mime_type: Optional[str]

    class Config:
        from_attributes = True


class EmailListResponse(BaseModel):
    emails: List[EmailResponse]
    total: int


class EmailDetailResponse(EmailResponse):
    """邮件详情响应（包含附件）"""
    attachments: List[AttachmentResponse] = []


class FetchEmailsRequest(BaseModel):
    since_days: int = 30  # 默认拉取30天的邮件


# ============ Routes ============
@router.get("", response_model=EmailListResponse)
async def get_emails(
    supplier_id: Optional[int] = None,
    direction: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "date_desc",  # date_desc, date_asc, from, subject
    limit: int = 100,
    offset: int = 0,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取当前账户的邮件列表"""
    from sqlalchemy import or_

    # 构建基础查询条件
    base_conditions = [Email.account_id == account.id]

    if supplier_id:
        base_conditions.append(Email.supplier_id == supplier_id)
    if direction:
        base_conditions.append(Email.direction == direction)

    # 搜索功能：搜索主题、正文、发件人
    if search:
        search_pattern = f"%{search}%"
        base_conditions.append(or_(
            Email.subject_original.ilike(search_pattern),
            Email.body_original.ilike(search_pattern),
            Email.from_email.ilike(search_pattern),
            Email.from_name.ilike(search_pattern)
        ))

    # 先计算总数
    count_query = select(func.count(Email.id)).where(*base_conditions)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 构建数据查询
    query = select(Email).where(*base_conditions)

    # 排序
    if sort_by == "date_asc":
        query = query.order_by(Email.received_at.asc())
    elif sort_by == "from":
        query = query.order_by(Email.from_name.asc(), Email.received_at.desc())
    elif sort_by == "subject":
        query = query.order_by(Email.subject_original.asc(), Email.received_at.desc())
    else:  # date_desc 默认
        query = query.order_by(Email.received_at.desc())

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    emails = result.scalars().all()

    return EmailListResponse(emails=emails, total=total)


@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单封邮件详情（包含附件）"""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Email)
        .options(selectinload(Email.attachments))
        .where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    return email


@router.get("/{email_id}/attachments")
async def get_email_attachments(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取邮件附件列表"""
    # 验证邮件属于当前用户
    email_result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = email_result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    result = await db.execute(
        select(Attachment).where(Attachment.email_id == email_id)
    )
    attachments = result.scalars().all()
    return {"attachments": attachments}


@router.get("/thread/{thread_id}")
async def get_email_thread(
    thread_id: str,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取邮件线程"""
    result = await db.execute(
        select(Email)
        .where(Email.thread_id == thread_id, Email.account_id == account.id)
        .order_by(Email.received_at.asc())
    )
    emails = result.scalars().all()
    return {"emails": emails, "count": len(emails)}


@router.post("/fetch")
async def fetch_emails(
    request: FetchEmailsRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """手动拉取当前账户的邮件"""
    import asyncio
    # 使用 asyncio.create_task 来正确运行异步后台任务
    asyncio.create_task(fetch_emails_background(account, request.since_days))
    return {"message": f"开始拉取 {account.email} 的邮件"}


async def fetch_emails_background(account: EmailAccount, since_days: int):
    """后台任务：拉取邮件并自动翻译"""
    import asyncio
    import traceback
    import hashlib
    from database.database import async_session
    from database.models import TranslationCache, SharedEmailTranslation
    from services.translate_service import TranslateService
    from config import get_settings

    settings = get_settings()
    since_date = datetime.utcnow() - timedelta(days=since_days)

    print(f"[Background] Starting email fetch for {account.email}")

    try:
        service = EmailService(
            imap_server=account.imap_server,
            smtp_server=account.smtp_server,
            email_address=account.email,
            password=account.password,
            imap_port=account.imap_port,
            smtp_port=account.smtp_port
        )

        # 在线程池中运行同步的IMAP操作，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        emails = await loop.run_in_executor(
            None,
            lambda: service.fetch_emails(since_date=since_date)
        )

        print(f"[Background] Fetched {len(emails)} emails from IMAP")

        # 创建翻译服务
        if settings.translate_provider == "deepl":
            translate_service = TranslateService(
                api_key=settings.deepl_api_key,
                provider="deepl",
                is_free_api=settings.deepl_free_api
            )
        else:
            translate_service = TranslateService(
                provider="ollama",
                ollama_base_url=settings.ollama_base_url,
                ollama_model=settings.ollama_model
            )

        saved_count = 0
        translated_count = 0

        async with async_session() as db:
            for email_data in emails:
                # 检查是否已存在
                existing = await crud.get_email_by_message_id(db, email_data["message_id"])
                if existing:
                    continue

                # 获取或创建供应商
                supplier = await crud.get_or_create_supplier_by_email(db, email_data["from_email"])

                # 创建邮件记录
                email_data["account_id"] = account.id
                email_data["supplier_id"] = supplier.id
                attachments = email_data.pop("attachments", [])

                new_email = await crud.create_email(db, email_data)
                saved_count += 1

                # 自动翻译非中文邮件
                lang = email_data.get("language_detected", "")
                if lang and lang != "zh" and settings.translate_enabled:
                    try:
                        # 先检查共享翻译表
                        shared_result = await db.execute(
                            select(SharedEmailTranslation).where(
                                SharedEmailTranslation.message_id == email_data["message_id"]
                            )
                        )
                        shared = shared_result.scalar_one_or_none()

                        if shared:
                            # 使用共享翻译
                            new_email.subject_translated = shared.subject_translated
                            new_email.body_translated = shared.body_translated
                            new_email.is_translated = True
                            print(f"[AutoTranslate] Used shared translation for {email_data['message_id'][:30]}")
                        else:
                            # 翻译主题
                            subject_translated = ""
                            if email_data.get("subject_original"):
                                subject_translated = await translate_with_cache_async(
                                    db, translate_service,
                                    email_data["subject_original"], lang, "zh"
                                )

                            # 翻译正文
                            body_translated = ""
                            if email_data.get("body_original"):
                                body_translated = await translate_with_cache_async(
                                    db, translate_service,
                                    email_data["body_original"], lang, "zh"
                                )

                            new_email.subject_translated = subject_translated
                            new_email.body_translated = body_translated
                            new_email.is_translated = True

                            # 保存到共享翻译表
                            shared_entry = SharedEmailTranslation(
                                message_id=email_data["message_id"],
                                subject_original=email_data.get("subject_original"),
                                subject_translated=subject_translated,
                                body_original=email_data.get("body_original"),
                                body_translated=body_translated,
                                source_lang=lang,
                                target_lang="zh",
                                translated_by=account.id
                            )
                            db.add(shared_entry)
                            print(f"[AutoTranslate] Translated and saved: {email_data['message_id'][:30]}")

                        translated_count += 1
                    except Exception as te:
                        print(f"[AutoTranslate] Failed for {email_data['message_id'][:30]}: {te}")

            await db.commit()

        # 在线程池中断开连接
        await loop.run_in_executor(None, service.disconnect_imap)
        print(f"[Background] Saved {saved_count} emails, auto-translated {translated_count} for {account.email}")

    except Exception as e:
        print(f"[Background] Error fetching emails for {account.email}: {e}")
        traceback.print_exc()


async def translate_with_cache_async(db, translate_service, text: str, source_lang: str, target_lang: str) -> str:
    """带缓存的翻译（异步版本）"""
    import hashlib
    from database.models import TranslationCache

    if not text:
        return ""

    # 查缓存
    cache_key = hashlib.sha256(f"{text}|{source_lang or 'auto'}|{target_lang}".encode()).hexdigest()
    cache_result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    cached = cache_result.scalar_one_or_none()

    if cached:
        cached.hit_count += 1
        print(f"[Cache HIT] hit_count={cached.hit_count}")
        return cached.translated_text

    # 调用翻译 API
    translated = translate_service.translate_text(text=text, target_lang=target_lang)

    # 保存到缓存
    new_cache = TranslationCache(
        text_hash=cache_key,
        source_text=text,
        translated_text=translated,
        source_lang=source_lang,
        target_lang=target_lang
    )
    db.add(new_cache)
    print(f"[Cache SAVE] text={text[:30]}...")

    return translated


@router.get("/stats/unread")
async def get_unread_count(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取未翻译邮件数量"""
    result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            Email.is_translated == False,
            Email.direction == "inbound"
        )
    )
    count = result.scalar()
    return {"untranslated_count": count}


@router.get("/stats/summary")
async def get_email_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取邮件统计"""
    # 总数
    total_result = await db.execute(
        select(func.count(Email.id)).where(Email.account_id == account.id)
    )
    total = total_result.scalar()

    # 收件
    inbound_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            Email.direction == "inbound"
        )
    )
    inbound = inbound_result.scalar()

    # 未翻译
    untranslated_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            Email.is_translated == False,
            Email.direction == "inbound"
        )
    )
    untranslated = untranslated_result.scalar()

    return {
        "total": total,
        "inbound": inbound,
        "outbound": total - inbound,
        "untranslated": untranslated
    }


# ============ 邮件操作API ============
@router.patch("/{email_id}/read", response_model=EmailResponse)
async def mark_email_as_read(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """标记邮件为已读"""
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    email.is_read = True
    await db.commit()
    await db.refresh(email)
    return email


@router.patch("/{email_id}/unread", response_model=EmailResponse)
async def mark_email_as_unread(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """标记邮件为未读"""
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    email.is_read = False
    await db.commit()
    await db.refresh(email)
    return email


@router.patch("/{email_id}/flag", response_model=EmailResponse)
async def flag_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """标记邮件为星标"""
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    email.is_flagged = True
    await db.commit()
    await db.refresh(email)
    return email


@router.patch("/{email_id}/unflag", response_model=EmailResponse)
async def unflag_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """取消邮件星标"""
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    email.is_flagged = False
    await db.commit()
    await db.refresh(email)
    return email


@router.delete("/{email_id}")
async def delete_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """删除邮件"""
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    await db.delete(email)
    await db.commit()
    return {"message": "邮件已删除"}


@router.post("/{email_id}/translate", response_model=EmailResponse)
async def translate_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """翻译单个邮件（带缓存和共享）"""
    from database.models import SharedEmailTranslation, TranslationCache
    from services.translate_service import TranslateService
    from config import get_settings
    import hashlib

    settings = get_settings()

    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    if email.is_translated:
        return email

    # 1. 先检查共享翻译表（其他用户是否已翻译过这封邮件）
    if email.message_id:
        shared_result = await db.execute(
            select(SharedEmailTranslation).where(
                SharedEmailTranslation.message_id == email.message_id
            )
        )
        shared = shared_result.scalar_one_or_none()
        if shared:
            print(f"[SharedTranslation HIT] message_id={email.message_id}")
            email.subject_translated = shared.subject_translated
            email.body_translated = shared.body_translated
            email.is_translated = True
            await db.commit()
            await db.refresh(email)
            return email

    # 2. 翻译辅助函数（带缓存）
    async def translate_with_cache(text: str, source_lang: str, target_lang: str) -> str:
        if not text:
            return ""

        # 查缓存
        cache_key = hashlib.sha256(f"{text}|{source_lang or 'auto'}|{target_lang}".encode()).hexdigest()
        cache_result = await db.execute(
            select(TranslationCache).where(TranslationCache.text_hash == cache_key)
        )
        cached = cache_result.scalar_one_or_none()
        if cached:
            cached.hit_count += 1
            print(f"[Cache HIT] hit_count={cached.hit_count}")
            return cached.translated_text

        # 调用翻译 API
        if settings.translate_provider == "deepl":
            service = TranslateService(
                api_key=settings.deepl_api_key,
                provider="deepl",
                is_free_api=settings.deepl_free_api
            )
        else:
            service = TranslateService(
                provider="ollama",
                ollama_base_url=settings.ollama_base_url,
                ollama_model=settings.ollama_model
            )

        translated = service.translate_text(text=text, target_lang=target_lang)

        # 保存到缓存
        new_cache = TranslationCache(
            text_hash=cache_key,
            source_text=text,
            translated_text=translated,
            source_lang=source_lang,
            target_lang=target_lang
        )
        db.add(new_cache)
        print(f"[Cache SAVE] text={text[:30]}...")

        return translated

    # 3. 执行翻译
    source_lang = email.language_detected or "auto"

    subject_translated = await translate_with_cache(
        email.subject_original, source_lang, "zh"
    ) if email.subject_original else ""

    body_translated = await translate_with_cache(
        email.body_original, source_lang, "zh"
    ) if email.body_original else ""

    # 4. 更新邮件记录
    email.subject_translated = subject_translated
    email.body_translated = body_translated
    email.is_translated = True

    # 5. 保存到共享翻译表（供其他用户复用）
    if email.message_id:
        shared_entry = SharedEmailTranslation(
            message_id=email.message_id,
            subject_original=email.subject_original,
            subject_translated=subject_translated,
            body_original=email.body_original,
            body_translated=body_translated,
            source_lang=source_lang,
            target_lang="zh",
            translated_by=account.id
        )
        db.add(shared_entry)
        print(f"[SharedTranslation SAVE] message_id={email.message_id}")

    await db.commit()
    await db.refresh(email)
    return email
