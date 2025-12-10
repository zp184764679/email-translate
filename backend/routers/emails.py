from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import os

from database.database import get_db
from database import crud
from database.models import Email, EmailAccount, Attachment, EmailLabel
from services.email_service import EmailService
from routers.users import get_current_account
from config import get_settings
from utils.crypto import decrypt_password, mask_email
from shared.cache_config import cache_get, cache_set
import re

router = APIRouter(prefix="/api/emails", tags=["emails"])


def html_to_text_with_format(html: str) -> str:
    """从 HTML 提取文本，保留段落格式"""
    if not html:
        return ""
    text = html
    # 先保留原始换行符
    text = text.replace('\r\n', '\n')
    # <br> -> 换行
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    # </p>, </div>, </li>, </tr>, </h1-6> -> 换行
    text = re.sub(r'</(?:p|div|li|tr|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    # 移除其他 HTML 标签（不影响换行）
    text = re.sub(r'<[^>]+>', '', text)
    # 处理 HTML 实体
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'&[a-z]+;', '', text, flags=re.IGNORECASE)
    # 清理但保留换行：只压缩水平空白（空格、制表符等）
    text = re.sub(r'[ \t]+', ' ', text)
    # 每行首尾空格清理
    lines = [line.strip() for line in text.split('\n')]
    # 合并连续空行为1个
    result = []
    last_was_empty = False
    for line in lines:
        if line == '':
            if not last_was_empty:
                result.append(line)
                last_was_empty = True
        else:
            result.append(line)
            last_was_empty = False
    return '\n'.join(result).strip()


settings = get_settings()


# ============ Schemas ============
class LabelBriefResponse(BaseModel):
    """标签简要信息（用于邮件列表）"""
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


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

    # 标签
    labels: List[LabelBriefResponse] = []

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
    """邮件详情响应（包含附件和标签）"""
    attachments: List[AttachmentResponse] = []
    labels: List[LabelBriefResponse] = []


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

    # 构建数据查询（包含标签和文件夹）
    query = select(Email).where(*base_conditions).options(
        selectinload(Email.labels),
        selectinload(Email.folders)
    )

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


@router.get("/contacts")
async def get_contacts(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取历史联系人列表（从邮件中提取，按使用频率排序）"""
    # 查询所有邮件的发件人和收件人
    result = await db.execute(
        select(Email.from_email, Email.from_name, Email.to_email, Email.cc_email)
        .where(Email.account_id == account.id)
        .order_by(Email.received_at.desc())
        .limit(500)  # 限制查询范围
    )
    emails = result.all()

    # 提取联系人并统计频率
    contacts_dict = {}

    def add_contact(email_addr, name=None):
        if not email_addr:
            return
        email_lower = email_addr.lower().strip()
        if not email_lower:
            return

        if email_lower in contacts_dict:
            # 增加频率计数
            contacts_dict[email_lower]["frequency"] += 1
            # 如果有更好的名字（非空），更新名字
            if name and not contacts_dict[email_lower]["name"]:
                contacts_dict[email_lower]["name"] = name.strip()
        else:
            contacts_dict[email_lower] = {
                "email": email_addr.strip(),
                "name": name.strip() if name else None,
                "frequency": 1
            }

    def extract_email(addr):
        """从地址字符串中提取邮箱"""
        if not addr:
            return None, None
        match = re.match(r'^(.+?)\s*<([^>]+)>$', addr.strip())
        if match:
            return match.group(2).strip(), match.group(1).strip()
        return addr.strip(), None

    for email in emails:
        # 发件人
        add_contact(email.from_email, email.from_name)

        # 收件人
        if email.to_email:
            for addr in email.to_email.split(','):
                email_addr, name = extract_email(addr.strip())
                add_contact(email_addr, name)

        # 抄送
        if email.cc_email:
            for addr in email.cc_email.split(','):
                email_addr, name = extract_email(addr.strip())
                add_contact(email_addr, name)

    # 排除自己的邮箱
    contacts_dict.pop(account.email.lower(), None)

    # 按频率降序排序，取前100个常用联系人
    sorted_contacts = sorted(
        contacts_dict.values(),
        key=lambda c: c.get("frequency", 0),
        reverse=True
    )[:100]

    return {"contacts": sorted_contacts}


@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单封邮件详情（包含附件、标签和文件夹）"""
    result = await db.execute(
        select(Email)
        .options(
            selectinload(Email.attachments),
            selectinload(Email.labels),
            selectinload(Email.folders)
        )
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
    """后台任务：拉取邮件并自动翻译（增量拉取优化）"""
    import asyncio
    import traceback
    import hashlib
    from database.database import async_session
    from database.models import TranslationCache, SharedEmailTranslation
    from services.translate_service import TranslateService
    from config import get_settings

    settings = get_settings()

    print(f"[Background] Starting email fetch for {mask_email(account.email)}")

    # 增量拉取优化：查询数据库中最新邮件的时间
    async with async_session() as db:
        latest_result = await db.execute(
            select(Email.received_at)
            .where(Email.account_id == account.id)
            .order_by(Email.received_at.desc())
            .limit(1)
        )
        last_sync_time = latest_result.scalar()

    if last_sync_time:
        # 有历史邮件：从最新邮件时间开始拉取（往前推1天避免边界问题）
        since_date = last_sync_time - timedelta(days=1)
        print(f"[Background] Incremental fetch since {since_date} (last email: {last_sync_time})")
    else:
        # 首次同步：使用 since_days 参数
        since_date = datetime.utcnow() - timedelta(days=since_days)
        print(f"[Background] First sync, fetching emails from last {since_days} days")

    try:
        service = EmailService(
            imap_server=account.imap_server,
            smtp_server=account.smtp_server,
            email_address=account.email,
            password=decrypt_password(account.password),
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

        # 创建翻译服务（支持智能路由）
        # 智能路由会根据邮件复杂度自动选择引擎：简单→Ollama，复杂→DeepL/Claude
        translate_service = TranslateService(
            api_key=settings.deepl_api_key or settings.claude_api_key,
            provider=settings.translate_provider,
            is_free_api=settings.deepl_free_api,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            claude_model=getattr(settings, 'claude_model', None),
            tencent_secret_id=settings.tencent_secret_id,
            tencent_secret_key=settings.tencent_secret_key
        )

        # 是否启用智能路由（可通过配置控制）
        use_smart_routing = getattr(settings, 'smart_routing_enabled', True)

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

                try:
                    new_email = await crud.create_email(db, email_data)
                    saved_count += 1
                except IntegrityError:
                    # 处理并发请求导致的重复插入
                    await db.rollback()
                    print(f"[EmailSync] Skipped duplicate: {email_data.get('message_id', 'unknown')[:50]}")
                    continue

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
                            # 翻译主题（主题通常很短，直接用普通翻译）
                            subject_translated = ""
                            if email_data.get("subject_original"):
                                subject_translated = await translate_with_cache_async(
                                    db, translate_service,
                                    email_data["subject_original"], lang, "zh"
                                )

                            # 智能翻译正文（检测引用 + 智能路由）
                            body_translated = ""
                            provider_used = "ollama"
                            complexity_info = None

                            if email_data.get("body_original"):
                                in_reply_to = email_data.get("in_reply_to")
                                if use_smart_routing:
                                    # 智能路由翻译
                                    result = translate_service.translate_with_smart_routing(
                                        text=email_data["body_original"],
                                        subject=email_data.get("subject_original", ""),
                                        target_lang="zh",
                                        source_lang=lang
                                    )
                                    body_translated = result["translated_text"]
                                    provider_used = result["provider_used"]
                                    complexity_info = result["complexity"]
                                    print(f"[SmartRouting] Email {email_data['message_id'][:20]}... "
                                          f"→ {provider_used} (complexity: {complexity_info['level']}, "
                                          f"score: {complexity_info['score']})")
                                else:
                                    # 智能翻译（检测引用，只翻译新内容）
                                    body_translated = await smart_translate_email_body(
                                        db, translate_service,
                                        email_data["body_original"], lang, "zh",
                                        in_reply_to=in_reply_to
                                    )

                            new_email.subject_translated = subject_translated
                            new_email.body_translated = body_translated
                            # 只有当翻译结果非空时才标记为已翻译
                            new_email.is_translated = bool(subject_translated or body_translated)

                            # 保存到共享翻译表（只有翻译成功才保存）
                            if subject_translated or body_translated:
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
                                print(f"[AutoTranslate] Translated ({provider_used}) and saved: {email_data['message_id'][:30]}")
                            else:
                                print(f"[AutoTranslate] Skip saving (empty translation): {email_data['message_id'][:30]}")

                        translated_count += 1
                    except Exception as te:
                        print(f"[AutoTranslate] Failed for {email_data['message_id'][:30]}: {te}")

            await db.commit()

        # 在线程池中断开连接
        await loop.run_in_executor(None, service.disconnect_imap)
        print(f"[Background] Saved {saved_count} emails, auto-translated {translated_count} for {mask_email(account.email)}")

    except Exception as e:
        print(f"[Background] Error fetching emails for {mask_email(account.email)}: {e}")
        traceback.print_exc()


def extract_new_content_from_reply(body: str) -> tuple[str, str, int]:
    """
    从回复邮件中提取新内容，分离引用部分

    返回: (new_content, quoted_content, quote_start_line)
    """
    import re

    if not body:
        return "", "", -1

    lines = body.split('\n')
    quote_patterns = [
        # 英文引用标记
        r'^On .+ wrote:$',
        r'^From: .+$',
        r'^Sent: .+$',
        r'^-----Original Message-----',
        r'^----- Original Message -----',
        r'^> ',
        r'^_{3,}',  # _____ 分隔线
        r'^-{3,}',  # ----- 分隔线
        # 中文引用标记
        r'^发件人[:：].+$',
        r'^发送时间[:：].+$',
        r'^原始邮件',
        # 日文引用
        r'^差出人[:：].+$',
        # 常见邮件客户端格式
        r'^\[mailto:.+\]',
        r'^Date: .+$',
        r'^To: .+$',
        r'^Subject: .+$',
        r'^Cc: .+$',
    ]

    quote_start = -1
    consecutive_quotes = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 检查是否是引用开始标记
        is_quote_marker = False
        for pattern in quote_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                is_quote_marker = True
                break

        if is_quote_marker:
            consecutive_quotes += 1
            if consecutive_quotes >= 1 and quote_start == -1:
                # 找到引用开始位置，往前查找可能的空行
                quote_start = i
                # 往前跳过空行
                while quote_start > 0 and not lines[quote_start - 1].strip():
                    quote_start -= 1
                break
        else:
            consecutive_quotes = 0

    if quote_start == -1:
        # 没有找到引用，返回全部内容
        return body, "", -1

    new_content = '\n'.join(lines[:quote_start]).strip()
    quoted_content = '\n'.join(lines[quote_start:]).strip()

    return new_content, quoted_content, quote_start


async def translate_with_cache_async(db, translate_service, text: str, source_lang: str, target_lang: str) -> str:
    """带缓存的翻译（异步版本，L1 Redis → L2 MySQL）"""
    import hashlib
    from database.models import TranslationCache

    if not text:
        return ""

    # 计算缓存键
    cache_key = hashlib.sha256(f"{text}|{source_lang or 'auto'}|{target_lang}".encode()).hexdigest()
    redis_key = f"trans:{cache_key}"

    # L1: 先查 Redis（毫秒级）
    redis_result = cache_get(redis_key)
    if redis_result:
        print(f"[Redis HIT] text={text[:30]}...")
        return redis_result

    # L2: Redis 未命中，查 MySQL
    cache_result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    cached = cache_result.scalar_one_or_none()

    if cached:
        cached.hit_count += 1
        # 写回 Redis（预热 L1 缓存）
        cache_set(redis_key, cached.translated_text, ttl=3600)
        print(f"[MySQL HIT] hit_count={cached.hit_count}")
        return cached.translated_text

    # 调用翻译 API
    translated = translate_service.translate_text(text=text, target_lang=target_lang)

    # L1: 写入 Redis
    cache_set(redis_key, translated, ttl=3600)

    # L2: 保存到 MySQL（持久化）
    new_cache = TranslationCache(
        text_hash=cache_key,
        source_text=text,
        translated_text=translated,
        source_lang=source_lang,
        target_lang=target_lang
    )
    db.add(new_cache)
    print(f"[Cache SAVE] Redis + MySQL, text={text[:30]}...")

    return translated


async def smart_translate_email_body(
    db, translate_service, body: str, source_lang: str, target_lang: str,
    in_reply_to: str = None
) -> str:
    """
    智能翻译邮件正文：
    1. 检测并分离新内容和引用内容
    2. 只翻译新内容
    3. 尝试复用引用内容的已有翻译
    4. 合并结果
    """
    from database.models import SharedEmailTranslation

    if not body:
        return ""

    # 分离新内容和引用
    new_content, quoted_content, quote_start = extract_new_content_from_reply(body)

    if quote_start == -1:
        # 没有引用，全文翻译
        return await translate_with_cache_async(db, translate_service, body, source_lang, target_lang)

    print(f"[SmartTranslate] Found quote at line {quote_start}, new content: {len(new_content)} chars, quoted: {len(quoted_content)} chars")

    # 翻译新内容
    new_translated = ""
    if new_content:
        new_translated = await translate_with_cache_async(db, translate_service, new_content, source_lang, target_lang)

    # 尝试查找引用内容的已有翻译
    quoted_translated = ""
    if quoted_content and in_reply_to:
        # 通过 in_reply_to 查找原邮件的翻译
        shared_result = await db.execute(
            select(SharedEmailTranslation).where(
                SharedEmailTranslation.message_id == in_reply_to
            )
        )
        shared = shared_result.scalar_one_or_none()
        if shared and shared.body_translated:
            # 使用已有翻译，加上引用标记
            quoted_translated = f"\n\n--- 以下为引用内容（已翻译）---\n{shared.body_translated}"
            print(f"[SmartTranslate] Reused translation from {in_reply_to[:30]}")
        else:
            # 没有找到已有翻译，标记为引用（不翻译）
            quoted_translated = f"\n\n--- 以下为引用内容（原文）---\n{quoted_content[:500]}{'...' if len(quoted_content) > 500 else ''}"
    elif quoted_content:
        # 没有 in_reply_to，只标记引用
        quoted_translated = f"\n\n--- 以下为引用内容（原文）---\n{quoted_content[:500]}{'...' if len(quoted_content) > 500 else ''}"

    return new_translated + quoted_translated


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

    # 未读邮件数
    unread_result = await db.execute(
        select(func.count(Email.id)).where(
            Email.account_id == account.id,
            Email.is_read == False,
            Email.direction == "inbound"
        )
    )
    unread = unread_result.scalar()

    return {
        "total": total,
        "inbound": inbound,
        "outbound": total - inbound,
        "untranslated": untranslated,
        "unread": unread
    }


# ============ 附件下载 API ============
@router.get("/{email_id}/attachment/{attachment_id}")
async def download_attachment(
    email_id: int,
    attachment_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """下载单个附件"""
    # 验证邮件属于当前用户
    email_result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email = email_result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 获取附件
    att_result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.email_id == email_id
        )
    )
    attachment = att_result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")

    # 检查文件是否存在
    if not attachment.file_path or not os.path.exists(attachment.file_path):
        raise HTTPException(status_code=404, detail="附件文件不存在")

    # 返回文件
    return FileResponse(
        path=attachment.file_path,
        filename=attachment.filename,
        media_type=attachment.mime_type or "application/octet-stream"
    )


# ============ 邮件导出 API ============
@router.get("/{email_id}/export")
async def export_email_as_eml(
    email_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """导出邮件为 EML 格式"""
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.utils import formatdate, make_msgid
    import io

    # 获取邮件
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.account_id == account.id)
    )
    email_obj = result.scalar_one_or_none()
    if not email_obj:
        raise HTTPException(status_code=404, detail="邮件不存在")

    # 构建 EML 内容
    msg = MIMEMultipart('alternative')
    msg['Message-ID'] = email_obj.message_id or make_msgid()
    msg['Subject'] = email_obj.subject_original or ''
    msg['From'] = f"{email_obj.from_name} <{email_obj.from_email}>" if email_obj.from_name else email_obj.from_email
    msg['To'] = email_obj.to_email or ''
    if email_obj.cc_email:
        msg['Cc'] = email_obj.cc_email
    msg['Date'] = formatdate(localtime=True)
    if email_obj.in_reply_to:
        msg['In-Reply-To'] = email_obj.in_reply_to

    # 添加纯文本正文
    if email_obj.body_original:
        text_part = MIMEText(email_obj.body_original, 'plain', 'utf-8')
        msg.attach(text_part)

    # 添加 HTML 正文
    if email_obj.body_html:
        html_part = MIMEText(email_obj.body_html, 'html', 'utf-8')
        msg.attach(html_part)

    # 生成 EML 内容
    eml_content = msg.as_string()

    # 生成文件名
    subject_safe = (email_obj.subject_original or 'email')[:50].replace('/', '_').replace('\\', '_').replace(':', '_')
    filename = f"{subject_safe}.eml"

    return Response(
        content=eml_content,
        media_type="message/rfc822",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


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

    # 重新查询以加载关系字段（避免 MissingGreenlet 错误）
    result = await db.execute(
        select(Email)
        .options(selectinload(Email.labels), selectinload(Email.folders))
        .where(Email.id == email_id)
    )
    return result.scalar_one()


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

    # 重新查询以加载关系字段（避免 MissingGreenlet 错误）
    result = await db.execute(
        select(Email)
        .options(selectinload(Email.labels), selectinload(Email.folders))
        .where(Email.id == email_id)
    )
    return result.scalar_one()


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

    # 重新查询以加载关系字段（避免 MissingGreenlet 错误）
    result = await db.execute(
        select(Email)
        .options(selectinload(Email.labels), selectinload(Email.folders))
        .where(Email.id == email_id)
    )
    return result.scalar_one()


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

    # 重新查询以加载关系字段（避免 MissingGreenlet 错误）
    result = await db.execute(
        select(Email)
        .options(selectinload(Email.labels), selectinload(Email.folders))
        .where(Email.id == email_id)
    )
    return result.scalar_one()


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


# ============ 批量操作 API ============
class BatchEmailRequest(BaseModel):
    email_ids: List[int]


@router.post("/batch/read")
async def batch_mark_as_read(
    request: BatchEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量标记邮件为已读"""
    from sqlalchemy import update

    result = await db.execute(
        update(Email)
        .where(Email.id.in_(request.email_ids), Email.account_id == account.id)
        .values(is_read=True)
    )
    await db.commit()
    return {"message": f"已将 {result.rowcount} 封邮件标记为已读"}


@router.post("/batch/unread")
async def batch_mark_as_unread(
    request: BatchEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量标记邮件为未读"""
    from sqlalchemy import update

    result = await db.execute(
        update(Email)
        .where(Email.id.in_(request.email_ids), Email.account_id == account.id)
        .values(is_read=False)
    )
    await db.commit()
    return {"message": f"已将 {result.rowcount} 封邮件标记为未读"}


@router.post("/batch/delete")
async def batch_delete_emails(
    request: BatchEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量删除邮件"""
    from sqlalchemy import delete as sql_delete

    result = await db.execute(
        sql_delete(Email)
        .where(Email.id.in_(request.email_ids), Email.account_id == account.id)
    )
    await db.commit()
    return {"message": f"已删除 {result.rowcount} 封邮件"}


@router.post("/batch/flag")
async def batch_flag_emails(
    request: BatchEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量添加星标"""
    from sqlalchemy import update

    result = await db.execute(
        update(Email)
        .where(Email.id.in_(request.email_ids), Email.account_id == account.id)
        .values(is_flagged=True)
    )
    await db.commit()
    return {"message": f"已为 {result.rowcount} 封邮件添加星标"}


@router.post("/batch/unflag")
async def batch_unflag_emails(
    request: BatchEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """批量取消星标"""
    from sqlalchemy import update

    result = await db.execute(
        update(Email)
        .where(Email.id.in_(request.email_ids), Email.account_id == account.id)
        .values(is_flagged=False)
    )
    await db.commit()
    return {"message": f"已为 {result.rowcount} 封邮件取消星标"}


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

    # 只有当已翻译且翻译内容确实存在时才跳过
    if email.is_translated and email.body_translated:
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

    # 2. 翻译辅助函数（带缓存，L1 Redis → L2 MySQL）
    async def translate_with_cache(text: str, source_lang: str, target_lang: str) -> str:
        if not text:
            return ""

        # 计算缓存键
        cache_key = hashlib.sha256(f"{text}|{source_lang or 'auto'}|{target_lang}".encode()).hexdigest()
        redis_key = f"trans:{cache_key}"

        # L1: 先查 Redis（毫秒级）
        redis_result = cache_get(redis_key)
        if redis_result:
            print(f"[Redis HIT] text={text[:30]}...")
            return redis_result

        # L2: Redis 未命中，查 MySQL
        cache_result = await db.execute(
            select(TranslationCache).where(TranslationCache.text_hash == cache_key)
        )
        cached = cache_result.scalar_one_or_none()
        if cached:
            cached.hit_count += 1
            # 写回 Redis（预热 L1 缓存）
            cache_set(redis_key, cached.translated_text, ttl=3600)
            print(f"[MySQL HIT] hit_count={cached.hit_count}")
            return cached.translated_text

        # 调用翻译 API
        service = TranslateService(
            api_key=settings.deepl_api_key or settings.claude_api_key,
            provider=settings.translate_provider,
            is_free_api=settings.deepl_free_api,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            claude_model=getattr(settings, 'claude_model', None),
            tencent_secret_id=settings.tencent_secret_id,
            tencent_secret_key=settings.tencent_secret_key
        )

        translated = service.translate_text(text=text, target_lang=target_lang)

        # L1: 写入 Redis
        cache_set(redis_key, translated, ttl=3600)

        # L2: 保存到 MySQL（持久化）
        new_cache = TranslationCache(
            text_hash=cache_key,
            source_text=text,
            translated_text=translated,
            source_lang=source_lang,
            target_lang=target_lang
        )
        db.add(new_cache)
        print(f"[Cache SAVE] Redis + MySQL, text={text[:30]}...")

        return translated

    # 3. 执行翻译
    source_lang = email.language_detected or "auto"

    subject_translated = await translate_with_cache(
        email.subject_original, source_lang, "zh"
    ) if email.subject_original else ""

    # 获取要翻译的正文内容：优先纯文本，其次从 HTML 提取
    body_to_translate = email.body_original
    if not body_to_translate and email.body_html:
        # 从 HTML 提取文本用于翻译，保留段落格式
        body_to_translate = html_to_text_with_format(email.body_html)
        print(f"[Translate] Extracted {len(body_to_translate)} chars from HTML for email {email.id}")

    # 智能翻译正文（检测引用，只翻译新内容）
    body_translated = ""
    if body_to_translate:
        # 创建翻译服务用于智能翻译
        service = TranslateService(
            api_key=settings.deepl_api_key or settings.claude_api_key,
            provider=settings.translate_provider,
            is_free_api=settings.deepl_free_api,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            claude_model=getattr(settings, 'claude_model', None),
            tencent_secret_id=settings.tencent_secret_id,
            tencent_secret_key=settings.tencent_secret_key
        )
        body_translated = await smart_translate_email_body(
            db, service, body_to_translate, source_lang, "zh",
            in_reply_to=email.in_reply_to
        )

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


# ============ 发送邮件 API ============
class SendEmailRequest(BaseModel):
    to: str
    cc: Optional[str] = None
    subject: str
    body: str


@router.post("/send")
async def send_email(
    request: SendEmailRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """直接发送邮件（非回复）"""
    try:
        service = EmailService(
            imap_server=account.imap_server,
            smtp_server=account.smtp_server,
            email_address=account.email,
            password=decrypt_password(account.password),
            smtp_port=account.smtp_port
        )

        success = service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc
        )

        if success:
            return {"status": "sent", "message": "邮件发送成功"}
        else:
            raise HTTPException(status_code=500, detail="邮件发送失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")
