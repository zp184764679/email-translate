from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import hashlib

from database.database import get_db
from database import crud
from database.models import EmailAccount, Glossary, TranslationCache
from services.translate_service import TranslateService
from routers.users import get_current_account
from config import get_settings
from shared.cache_config import cache_get, cache_set
from utils.rate_limit import translate_limiter, batch_limiter

router = APIRouter(prefix="/api/translate", tags=["translate"])
settings = get_settings()


# ============ 缓存工具函数 ============
def compute_glossary_hash(glossary: List[dict]) -> str:
    """计算术语表 hash

    基于术语表内容生成唯一标识，当术语表更新时 hash 会变化
    """
    if not glossary:
        return ""
    # 对术语排序确保顺序一致性
    sorted_terms = sorted(glossary, key=lambda x: x.get("source", ""))
    content = "|".join(f"{t.get('source', '')}:{t.get('target', '')}" for t in sorted_terms)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]  # 取前16位即可


def compute_cache_key(text: str, source_lang: str, target_lang: str,
                      glossary_hash: str = None) -> str:
    """计算缓存键（SHA256）

    Args:
        text: 源文本
        source_lang: 源语言
        target_lang: 目标语言
        glossary_hash: 术语表 hash（可选，用于区分不同术语表的翻译结果）

    术语表 hash 的作用：
    - 当术语表更新后，生成新的 hash，导致缓存键变化
    - 旧缓存自然失效，新翻译会使用更新后的术语
    """
    content = f"{text}|{source_lang or 'auto'}|{target_lang}"
    if glossary_hash:
        content += f"|g:{glossary_hash}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


async def get_cached_translation(db: AsyncSession, text: str, source_lang: str, target_lang: str,
                                  glossary_hash: str = None) -> Optional[str]:
    """从缓存获取翻译结果（L1 Redis → L2 MySQL）"""
    cache_key = compute_cache_key(text, source_lang, target_lang, glossary_hash)
    redis_key = f"trans:{cache_key}"

    # L1: 先查 Redis（毫秒级）
    redis_result = cache_get(redis_key)
    if redis_result:
        print(f"[Redis HIT] text={text[:30]}...")
        return redis_result

    # L2: Redis 未命中，查 MySQL
    result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    cached = result.scalar_one_or_none()

    if cached:
        # 更新命中次数
        cached.hit_count += 1
        await db.commit()
        # 写回 Redis（预热 L1 缓存）
        cache_set(redis_key, cached.translated_text, ttl=3600)
        print(f"[MySQL HIT] hit_count={cached.hit_count}, text={text[:30]}...")
        return cached.translated_text

    return None


async def save_to_cache(db: AsyncSession, text: str, translated: str, source_lang: str, target_lang: str,
                        glossary_hash: str = None):
    """保存翻译结果到缓存（L1 Redis + L2 MySQL）"""
    cache_key = compute_cache_key(text, source_lang, target_lang, glossary_hash)
    redis_key = f"trans:{cache_key}"

    # L1: 写入 Redis（热点缓存，1小时过期）
    cache_set(redis_key, translated, ttl=3600)

    # L2: 写入 MySQL（持久化）
    # 检查是否已存在（避免重复插入）
    result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    if result.scalar_one_or_none():
        print(f"[Cache SAVE] Redis only (MySQL exists), text={text[:30]}...")
        return

    cache_entry = TranslationCache(
        text_hash=cache_key,
        source_text=text,
        translated_text=translated,
        source_lang=source_lang,
        target_lang=target_lang
    )
    db.add(cache_entry)
    await db.commit()
    print(f"[Cache SAVE] Redis + MySQL, text={text[:30]}...")


def get_translate_service() -> TranslateService:
    """Get configured translation service instance

    使用本地 vLLM 大模型进行翻译（免费，数据本地化）
    """
    return TranslateService(
        vllm_base_url=settings.vllm_base_url,
        vllm_model=settings.vllm_model,
        vllm_api_key=settings.vllm_api_key,
    )


# ============ Schemas ============
class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "zh"
    supplier_id: Optional[int] = None
    context: Optional[str] = None


class TranslateResponse(BaseModel):
    translated_text: str
    source_lang: Optional[str] = None


class BatchTranslateRequest(BaseModel):
    email_ids: List[int]


class GlossaryCreate(BaseModel):
    supplier_id: int
    term_source: str
    term_target: str
    source_lang: str = "en"
    target_lang: str = "zh"


class GlossaryResponse(BaseModel):
    id: int
    supplier_id: int
    term_source: str
    term_target: str
    source_lang: str
    target_lang: str

    class Config:
        from_attributes = True


# ============ Routes ============
@router.post("", response_model=TranslateResponse)
async def translate_text(
    request: TranslateRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Translate text using vLLM (with cache)

    使用本地 vLLM 大模型进行翻译
    """
    # 速率限制：每用户每分钟 30 次
    translate_limiter.check(f"user:{account.id}")

    if not settings.translate_enabled:
        return TranslateResponse(translated_text=request.text, source_lang="disabled")

    # 先查缓存
    cached = await get_cached_translation(db, request.text, None, request.target_lang)
    if cached:
        return TranslateResponse(translated_text=cached, source_lang="cache")

    glossary = []
    if request.supplier_id:
        terms = await crud.get_glossary_by_supplier(db, request.supplier_id)
        glossary = [{"source": t.term_source, "target": t.term_target} for t in terms]

    try:
        service = get_translate_service()

        # 使用 vLLM 本地模型翻译
        result = service.translate_with_smart_routing(
            text=request.text,
            target_lang=request.target_lang,
            glossary=glossary
        )
        translated = result["translated_text"]
        source_lang = result.get("provider_used", "vllm")

        # 保存到缓存
        await save_to_cache(db, request.text, translated, None, request.target_lang)

        return TranslateResponse(translated_text=translated, source_lang=source_lang)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")


@router.post("/reverse", response_model=TranslateResponse)
async def translate_reply(
    request: TranslateRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Translate Chinese reply to target language using vLLM (with cache)

    使用本地 vLLM 大模型进行翻译
    """
    if not settings.translate_enabled:
        return TranslateResponse(translated_text=request.text, source_lang="disabled")

    # 先查缓存 (中文 → 目标语言)
    cached = await get_cached_translation(db, request.text, "zh", request.target_lang)
    if cached:
        return TranslateResponse(translated_text=cached, source_lang="cache")

    glossary = []
    if request.supplier_id:
        terms = await crud.get_glossary_by_supplier(db, request.supplier_id)
        glossary = [{"source": t.term_target, "target": t.term_source} for t in terms]

    try:
        service = get_translate_service()

        # 使用 vLLM 本地模型翻译
        result = service.translate_with_smart_routing(
            text=request.text,
            target_lang=request.target_lang,
            glossary=glossary,
            source_lang="zh"
        )
        translated = result["translated_text"]
        source_lang = result.get("provider_used", "vllm")

        # 保存到缓存
        await save_to_cache(db, request.text, translated, "zh", request.target_lang)

        return TranslateResponse(translated_text=translated, source_lang=source_lang)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")


@router.post("/batch")
async def create_batch_translation(
    request: BatchTranslateRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Translate multiple emails"""
    # 速率限制：每用户每分钟 20 次批量操作
    batch_limiter.check(f"user:{account.id}")

    if not settings.translate_enabled:
        return {"message": "翻译已禁用", "results": []}

    from sqlalchemy import select
    from database.models import Email

    result = await db.execute(
        select(Email).where(Email.id.in_(request.email_ids))
    )
    emails = result.scalars().all()

    if not emails:
        raise HTTPException(status_code=404, detail="未找到邮件")

    batch_data = []
    for email in emails:
        if email.language_detected != "zh" and not email.is_translated:
            batch_data.append({
                "id": email.id,
                "subject": email.subject_original,
                "body": email.body_original,
                "target_lang": "zh",
                "source_lang": email.language_detected
            })

    if not batch_data:
        return {"message": "没有需要翻译的邮件"}

    try:
        service = get_translate_service()
        results = []
        success_count = 0

        for item in batch_data:
            try:
                # 翻译主题
                subject_translated = item.get("subject", "")
                if subject_translated:
                    result = service.translate_with_smart_routing(
                        text=subject_translated,
                        target_lang=item.get("target_lang", "zh"),
                        source_lang=item.get("source_lang")
                    )
                    subject_translated = result.get("translated_text", subject_translated)

                # 翻译正文
                body_translated = item.get("body", "")
                if body_translated:
                    result = service.translate_with_smart_routing(
                        text=body_translated,
                        target_lang=item.get("target_lang", "zh"),
                        source_lang=item.get("source_lang")
                    )
                    body_translated = result.get("translated_text", body_translated)

                # 更新数据库
                await crud.update_email_translation(
                    db,
                    item["id"],
                    subject_translated,
                    body_translated
                )

                results.append({"email_id": item["id"], "success": True})
                success_count += 1

            except Exception as e:
                print(f"[Batch] Failed to translate email {item['id']}: {e}")
                results.append({"email_id": item["id"], "success": False, "error": str(e)})

        await db.commit()

        return {
            "message": f"已翻译 {success_count}/{len(batch_data)} 封邮件",
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量翻译失败: {str(e)}")


@router.post("/batch-all")
async def batch_translate_all(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """翻译所有未翻译的邮件"""
    if not settings.translate_enabled:
        return {"message": "翻译已禁用", "translated": 0, "total": 0}

    from database.models import Email

    # 查询所有未翻译的非中文邮件
    result = await db.execute(
        select(Email).where(
            Email.is_translated == False,
            Email.language_detected != "zh",
            Email.language_detected.isnot(None)
        )
    )
    emails = result.scalars().all()

    if not emails:
        return {"message": "没有需要翻译的邮件", "translated": 0, "total": 0}

    total = len(emails)
    translated_count = 0
    service = get_translate_service()

    for email in emails:
        try:
            # 翻译主题
            subject_translated = email.subject_original
            if email.subject_original:
                subject_translated = service.translate(
                    email.subject_original,
                    target_lang="zh",
                    source_lang=email.language_detected
                )

            # 翻译正文
            body_translated = email.body_original
            if email.body_original:
                body_translated = service.translate(
                    email.body_original,
                    target_lang="zh",
                    source_lang=email.language_detected
                )

            # 更新邮件
            email.subject_translated = subject_translated
            email.body_translated = body_translated
            email.is_translated = True
            translated_count += 1

        except Exception as e:
            print(f"[Batch] Failed to translate email {email.id}: {e}")
            continue

    await db.commit()

    return {
        "message": f"已翻译 {translated_count}/{total} 封邮件",
        "translated": translated_count,
        "total": total
    }


# ============ 翻译用量统计 ============
@router.get("/usage-stats")
async def get_usage_stats(
    provider: Optional[str] = None,
    account: EmailAccount = Depends(get_current_account)
):
    """
    获取翻译 API 用量统计

    参数:
    - provider: 可选，指定翻译引擎 (vllm)
                不指定则返回所有引擎的用量

    返回:
    - current_month: 当前统计月份
    - providers: 各引擎用量列表
        - provider: 引擎名称
        - total_chars: 本月累计字符数
        - total_requests: 请求次数
        - free_quota: 免费额度
        - remaining: 剩余额度
        - usage_percent: 使用百分比
        - is_disabled: 是否已禁用
    """
    from services.usage_service import get_translation_usage_stats

    try:
        stats = await get_translation_usage_stats(provider)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用量统计失败: {str(e)}")


@router.get("/usage-stats/{provider}")
async def get_provider_usage_stats(
    provider: str,
    account: EmailAccount = Depends(get_current_account)
):
    """
    获取指定翻译引擎的用量统计

    路径参数:
    - provider: 翻译引擎名称 (vllm)
    """
    from services.usage_service import check_translation_quota

    try:
        quota = await check_translation_quota(provider)
        return {
            "provider": provider,
            **quota
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用量统计失败: {str(e)}")


@router.post("/usage-stats/{provider}/reset")
async def reset_provider_disabled(
    provider: str,
    account: EmailAccount = Depends(get_current_account)
):
    """
    手动重新启用被禁用的翻译引擎

    注意: 这只会重置禁用状态，不会重置用量统计。
          用量统计会在每月1日自动重置。
    """
    from services.usage_service import get_usage_service

    try:
        service = get_usage_service()
        success = await service.reset_disabled(provider)
        if success:
            return {"message": f"{provider} 翻译已重新启用"}
        else:
            raise HTTPException(status_code=500, detail="重置失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")


# ============ Glossary Routes ============
@router.get("/glossary/{supplier_id}", response_model=List[GlossaryResponse])
async def get_glossary(
    supplier_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Get glossary terms for a supplier"""
    terms = await crud.get_glossary_by_supplier(db, supplier_id)
    return terms


@router.post("/glossary", response_model=GlossaryResponse)
async def add_glossary_term(
    term: GlossaryCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Add new glossary term and record history"""
    from database.models import GlossaryHistory

    new_term = await crud.add_glossary_term(
        db,
        supplier_id=term.supplier_id,
        term_source=term.term_source,
        term_target=term.term_target,
        source_lang=term.source_lang,
        target_lang=term.target_lang
    )
    await db.flush()  # 确保获取到 new_term.id

    # 记录创建历史
    history = GlossaryHistory(
        glossary_id=new_term.id,
        supplier_id=term.supplier_id,
        term_source=term.term_source,
        term_target=term.term_target,
        source_lang=term.source_lang,
        target_lang=term.target_lang,
        action="create",
        changed_by=account.id
    )
    db.add(history)

    await db.commit()
    return new_term


@router.delete("/glossary/{term_id}")
async def delete_glossary_term(
    term_id: int,
    reason: Optional[str] = None,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Delete glossary term and record history"""
    from sqlalchemy import delete
    from database.models import GlossaryHistory

    # 先获取术语信息用于记录历史
    result = await db.execute(select(Glossary).where(Glossary.id == term_id))
    term = result.scalar_one_or_none()

    if term:
        # 记录删除历史
        history = GlossaryHistory(
            glossary_id=term.id,
            supplier_id=term.supplier_id,
            term_source=term.term_source,
            term_target=term.term_target,
            source_lang=term.source_lang,
            target_lang=term.target_lang,
            context=term.context,
            action="delete",
            changed_by=account.id,
            change_reason=reason
        )
        db.add(history)

        await db.execute(delete(Glossary).where(Glossary.id == term_id))
        await db.commit()

    return {"message": "术语已删除"}


@router.put("/glossary/{term_id}", response_model=GlossaryResponse)
async def update_glossary_term(
    term_id: int,
    term_source: str,
    term_target: str,
    reason: Optional[str] = None,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Update glossary term and record history"""
    from database.models import GlossaryHistory

    result = await db.execute(select(Glossary).where(Glossary.id == term_id))
    term = result.scalar_one_or_none()

    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")

    # 记录更新历史
    history = GlossaryHistory(
        glossary_id=term.id,
        supplier_id=term.supplier_id,
        term_source=term_source,
        term_target=term_target,
        term_source_old=term.term_source,
        term_target_old=term.term_target,
        source_lang=term.source_lang,
        target_lang=term.target_lang,
        context=term.context,
        action="update",
        changed_by=account.id,
        change_reason=reason
    )
    db.add(history)

    # 更新术语
    term.term_source = term_source
    term.term_target = term_target

    await db.commit()
    await db.refresh(term)
    return term


# ============ Glossary History Routes ============
class GlossaryHistoryResponse(BaseModel):
    id: int
    glossary_id: int
    supplier_id: Optional[int]
    term_source: str
    term_target: str
    term_source_old: Optional[str]
    term_target_old: Optional[str]
    action: str
    changed_by: Optional[int]
    changed_at: datetime
    change_reason: Optional[str]
    changer_email: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/glossary/{supplier_id}/history", response_model=List[GlossaryHistoryResponse])
async def get_glossary_history(
    supplier_id: int,
    limit: int = 50,
    offset: int = 0,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商术语表的修改历史"""
    from database.models import GlossaryHistory

    result = await db.execute(
        select(GlossaryHistory, EmailAccount.email)
        .outerjoin(EmailAccount, GlossaryHistory.changed_by == EmailAccount.id)
        .where(GlossaryHistory.supplier_id == supplier_id)
        .order_by(GlossaryHistory.changed_at.desc())
        .offset(offset)
        .limit(limit)
    )

    histories = []
    for row in result.all():
        history = row[0]
        changer_email = row[1]
        histories.append(GlossaryHistoryResponse(
            id=history.id,
            glossary_id=history.glossary_id,
            supplier_id=history.supplier_id,
            term_source=history.term_source,
            term_target=history.term_target,
            term_source_old=history.term_source_old,
            term_target_old=history.term_target_old,
            action=history.action,
            changed_by=history.changed_by,
            changed_at=history.changed_at,
            change_reason=history.change_reason,
            changer_email=changer_email
        ))

    return histories


@router.get("/glossary/term/{term_id}/history", response_model=List[GlossaryHistoryResponse])
async def get_term_history(
    term_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取单个术语的修改历史"""
    from database.models import GlossaryHistory

    result = await db.execute(
        select(GlossaryHistory, EmailAccount.email)
        .outerjoin(EmailAccount, GlossaryHistory.changed_by == EmailAccount.id)
        .where(GlossaryHistory.glossary_id == term_id)
        .order_by(GlossaryHistory.changed_at.desc())
    )

    histories = []
    for row in result.all():
        history = row[0]
        changer_email = row[1]
        histories.append(GlossaryHistoryResponse(
            id=history.id,
            glossary_id=history.glossary_id,
            supplier_id=history.supplier_id,
            term_source=history.term_source,
            term_target=history.term_target,
            term_source_old=history.term_source_old,
            term_target_old=history.term_target_old,
            action=history.action,
            changed_by=history.changed_by,
            changed_at=history.changed_at,
            change_reason=history.change_reason,
            changer_email=changer_email
        ))

    return histories


@router.post("/glossary/term/{term_id}/rollback")
async def rollback_glossary_term(
    term_id: int,
    history_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """回滚术语到指定历史版本"""
    from database.models import GlossaryHistory

    # 获取历史记录
    history_result = await db.execute(
        select(GlossaryHistory).where(
            GlossaryHistory.id == history_id,
            GlossaryHistory.glossary_id == term_id
        )
    )
    history = history_result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="历史记录不存在")

    # 获取当前术语
    term_result = await db.execute(select(Glossary).where(Glossary.id == term_id))
    term = term_result.scalar_one_or_none()

    if not term:
        # 如果术语已删除，需要重新创建
        if history.action == "delete":
            raise HTTPException(status_code=400, detail="无法回滚删除操作，术语已不存在")

        # 重新创建术语
        term = Glossary(
            id=term_id,  # 使用原ID
            supplier_id=history.supplier_id,
            term_source=history.term_source_old or history.term_source,
            term_target=history.term_target_old or history.term_target,
            source_lang=history.source_lang,
            target_lang=history.target_lang,
            context=history.context
        )
        db.add(term)

        # 记录回滚历史
        rollback_history = GlossaryHistory(
            glossary_id=term_id,
            supplier_id=history.supplier_id,
            term_source=term.term_source,
            term_target=term.term_target,
            source_lang=history.source_lang,
            target_lang=history.target_lang,
            action="create",
            changed_by=account.id,
            change_reason=f"回滚到历史记录 #{history_id}"
        )
        db.add(rollback_history)
    else:
        # 术语存在，回滚到历史版本的旧值
        old_source = term.term_source
        old_target = term.term_target

        # 如果是更新操作，回滚到更新前的值
        if history.action == "update" and history.term_source_old and history.term_target_old:
            term.term_source = history.term_source_old
            term.term_target = history.term_target_old
        else:
            # 否则使用历史记录中的当前值
            term.term_source = history.term_source
            term.term_target = history.term_target

        # 记录回滚历史
        rollback_history = GlossaryHistory(
            glossary_id=term_id,
            supplier_id=term.supplier_id,
            term_source=term.term_source,
            term_target=term.term_target,
            term_source_old=old_source,
            term_target_old=old_target,
            source_lang=term.source_lang,
            target_lang=term.target_lang,
            action="update",
            changed_by=account.id,
            change_reason=f"回滚到历史记录 #{history_id}"
        )
        db.add(rollback_history)

    await db.commit()
    return {"message": "已回滚到指定版本", "history_id": history_id}


@router.get("/glossary/history/stats")
async def get_glossary_history_stats(
    supplier_id: Optional[int] = None,
    days: int = 30,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取术语表修改统计"""
    from database.models import GlossaryHistory

    cutoff = datetime.utcnow() - timedelta(days=days)

    # 基础查询条件
    conditions = [GlossaryHistory.changed_at >= cutoff]
    if supplier_id:
        conditions.append(GlossaryHistory.supplier_id == supplier_id)

    # 按操作类型统计
    action_stats = await db.execute(
        select(GlossaryHistory.action, func.count(GlossaryHistory.id))
        .where(*conditions)
        .group_by(GlossaryHistory.action)
    )
    action_counts = {row[0]: row[1] for row in action_stats.all()}

    # 按用户统计
    user_stats = await db.execute(
        select(EmailAccount.email, func.count(GlossaryHistory.id))
        .join(GlossaryHistory, GlossaryHistory.changed_by == EmailAccount.id)
        .where(*conditions)
        .group_by(EmailAccount.email)
        .order_by(func.count(GlossaryHistory.id).desc())
        .limit(10)
    )
    top_contributors = [{"email": row[0], "changes": row[1]} for row in user_stats.all()]

    # 总修改次数
    total_result = await db.execute(
        select(func.count(GlossaryHistory.id)).where(*conditions)
    )
    total_changes = total_result.scalar() or 0

    return {
        "period_days": days,
        "total_changes": total_changes,
        "action_stats": {
            "created": action_counts.get("create", 0),
            "updated": action_counts.get("update", 0),
            "deleted": action_counts.get("delete", 0)
        },
        "top_contributors": top_contributors
    }


# ============ 缓存管理 API ============
@router.get("/cache/stats")
async def get_cache_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取翻译缓存统计"""
    # 总缓存条目
    total_result = await db.execute(select(func.count(TranslationCache.id)))
    total_entries = total_result.scalar()

    # 总命中次数
    hits_result = await db.execute(select(func.sum(TranslationCache.hit_count)))
    total_hits = hits_result.scalar() or 0

    # 节省的 API 调用次数 = 总命中 - 总条目（因为第一次不算命中）
    api_calls_saved = max(0, total_hits - total_entries)

    # 最热门的缓存（命中最多）
    top_result = await db.execute(
        select(TranslationCache)
        .order_by(TranslationCache.hit_count.desc())
        .limit(5)
    )
    top_entries = top_result.scalars().all()

    return {
        "total_entries": total_entries,
        "total_hits": total_hits,
        "api_calls_saved": api_calls_saved,
        "top_cached": [
            {
                "text": entry.source_text[:50] + "..." if len(entry.source_text) > 50 else entry.source_text,
                "hit_count": entry.hit_count,
                "target_lang": entry.target_lang
            }
            for entry in top_entries
        ]
    }


@router.delete("/cache")
async def clear_cache(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """清空翻译缓存"""
    from sqlalchemy import delete

    result = await db.execute(delete(TranslationCache))
    await db.commit()
    return {"message": f"已清空 {result.rowcount} 条缓存"}


# ============ 翻译质量反馈 API ============

class FeedbackCreate(BaseModel):
    email_id: Optional[int] = None
    feedback_type: str  # inaccurate, missing, wrong_term, other
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    suggested_text: Optional[str] = None
    comment: Optional[str] = None
    provider: Optional[str] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    account_id: int
    email_id: Optional[int]
    feedback_type: str
    original_text: Optional[str]
    translated_text: Optional[str]
    suggested_text: Optional[str]
    comment: Optional[str]
    provider: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_translation_feedback(
    feedback: FeedbackCreate,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    提交翻译质量反馈

    反馈类型:
    - inaccurate: 翻译不准确
    - missing: 内容遗漏
    - wrong_term: 术语错误
    - other: 其他问题
    """
    from database.models import TranslationFeedback

    # 验证反馈类型
    valid_types = ["inaccurate", "missing", "wrong_term", "other"]
    if feedback.feedback_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的反馈类型，可选: {', '.join(valid_types)}"
        )

    new_feedback = TranslationFeedback(
        account_id=account.id,
        email_id=feedback.email_id,
        feedback_type=feedback.feedback_type,
        original_text=feedback.original_text,
        translated_text=feedback.translated_text,
        suggested_text=feedback.suggested_text,
        comment=feedback.comment,
        provider=feedback.provider,
        source_lang=feedback.source_lang,
        target_lang=feedback.target_lang,
        status="pending"
    )

    db.add(new_feedback)
    await db.commit()
    await db.refresh(new_feedback)

    return new_feedback


@router.get("/feedback", response_model=List[FeedbackResponse])
async def get_feedbacks(
    status: Optional[str] = None,
    limit: int = 50,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取翻译反馈列表"""
    from database.models import TranslationFeedback

    query = select(TranslationFeedback).order_by(TranslationFeedback.created_at.desc()).limit(limit)

    if status:
        query = query.where(TranslationFeedback.status == status)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/feedback/stats")
async def get_feedback_stats(
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """获取翻译反馈统计"""
    from database.models import TranslationFeedback
    from sqlalchemy import case

    result = await db.execute(
        select(
            func.count(TranslationFeedback.id).label("total"),
            func.sum(case((TranslationFeedback.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((TranslationFeedback.status == "reviewed", 1), else_=0)).label("reviewed"),
            func.sum(case((TranslationFeedback.status == "applied", 1), else_=0)).label("applied"),
            func.sum(case((TranslationFeedback.feedback_type == "inaccurate", 1), else_=0)).label("inaccurate"),
            func.sum(case((TranslationFeedback.feedback_type == "wrong_term", 1), else_=0)).label("wrong_term"),
            func.sum(case((TranslationFeedback.feedback_type == "missing", 1), else_=0)).label("missing")
        )
    )

    stats = result.one()

    return {
        "total": stats.total or 0,
        "pending": stats.pending or 0,
        "reviewed": stats.reviewed or 0,
        "applied": stats.applied or 0,
        "by_type": {
            "inaccurate": stats.inaccurate or 0,
            "wrong_term": stats.wrong_term or 0,
            "missing": stats.missing or 0
        }
    }
