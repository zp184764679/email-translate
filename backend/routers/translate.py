from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional
import hashlib

from database.database import get_db
from database import crud
from database.models import EmailAccount, Glossary, TranslationCache
from services.translate_service import TranslateService
from routers.users import get_current_account
from config import get_settings
from shared.cache_config import cache_get, cache_set

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


def get_translate_service(for_smart_routing: bool = False) -> TranslateService:
    """Get configured translation service instance

    智能路由模式（smart_routing_enabled=True 或 for_smart_routing=True）：
    创建包含所有引擎配置的服务，支持自动切换：
    优先级：Ollama → Claude

    单引擎模式：
    根据 TRANSLATE_PROVIDER 使用单一引擎
    """
    if for_smart_routing or settings.smart_routing_enabled:
        # 智能路由模式：配置所有可用的引擎
        return TranslateService(
            # 主要配置（决定 translate_text 使用哪个引擎）
            provider=settings.translate_provider,
            # API key (Claude)
            api_key=settings.claude_api_key,
            # Ollama 配置
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            # Claude 配置
            claude_model=settings.claude_model,
        )

    # 单引擎模式
    if settings.translate_provider == "claude":
        return TranslateService(
            api_key=settings.claude_api_key,
            provider="claude",
            claude_model=settings.claude_model
        )
    else:  # ollama (default for local testing)
        return TranslateService(
            provider="ollama",
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model
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
    """Translate text using smart routing (with cache)

    智能路由优先级：Ollama → Claude
    自动根据复杂度选择引擎
    """
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

        # 使用智能路由
        if settings.smart_routing_enabled:
            result = service.translate_with_smart_routing(
                text=request.text,
                target_lang=request.target_lang,
                glossary=glossary
            )
            translated = result["translated_text"]
            source_lang = result["provider_used"]
        else:
            translated = service.translate_text(
                text=request.text,
                target_lang=request.target_lang,
                glossary=glossary,
                context=request.context
            )
            source_lang = settings.translate_provider

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
    """Translate Chinese reply to target language using smart routing (with cache)

    智能路由优先级：Ollama → Claude
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

        # 使用智能路由
        if settings.smart_routing_enabled:
            result = service.translate_with_smart_routing(
                text=request.text,
                target_lang=request.target_lang,
                glossary=glossary,
                source_lang="zh"
            )
            translated = result["translated_text"]
            source_lang = result["provider_used"]
        else:
            translated = service.translate_text(
                text=request.text,
                target_lang=request.target_lang,
                glossary=glossary,
                context=request.context
            )
            source_lang = settings.translate_provider

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
        result = service.create_batch_translation(batch_data)

        for item in result.get("results", []):
            if item.get("success"):
                await crud.update_email_translation(
                    db,
                    item["email_id"],
                    item["subject_translated"],
                    item["body_translated"]
                )

        await db.commit()

        success_count = len([r for r in result.get("results", []) if r.get("success")])
        return {
            "message": f"已翻译 {success_count}/{len(batch_data)} 封邮件",
            "results": result
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


@router.get("/token-stats")
async def get_token_stats(account: EmailAccount = Depends(get_current_account)):
    """获取 Claude API Token 使用统计"""
    stats = TranslateService.get_token_stats()
    stats["provider"] = settings.translate_provider
    return stats


@router.post("/token-stats/reset")
async def reset_token_stats(account: EmailAccount = Depends(get_current_account)):
    """重置 Token 统计"""
    TranslateService.reset_token_stats()
    return {"message": "Token 统计已重置"}


# ============ 翻译用量统计 ============
@router.get("/usage-stats")
async def get_usage_stats(
    provider: Optional[str] = None,
    account: EmailAccount = Depends(get_current_account)
):
    """
    获取翻译 API 用量统计

    参数:
    - provider: 可选，指定翻译引擎 (ollama, claude)
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
    - provider: 翻译引擎名称 (ollama, claude)
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
    """Add new glossary term"""
    new_term = await crud.add_glossary_term(
        db,
        supplier_id=term.supplier_id,
        term_source=term.term_source,
        term_target=term.term_target,
        source_lang=term.source_lang,
        target_lang=term.target_lang
    )
    await db.commit()
    return new_term


@router.delete("/glossary/{term_id}")
async def delete_glossary_term(
    term_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Delete glossary term"""
    from sqlalchemy import delete

    await db.execute(delete(Glossary).where(Glossary.id == term_id))
    await db.commit()
    return {"message": "术语已删除"}


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


# ============ Claude Batch API 路由 ============
@router.post("/batch/create")
async def create_claude_batch(
    limit: int = 50,
    account: EmailAccount = Depends(get_current_account)
):
    """
    创建 Claude Batch API 批次

    自动收集未翻译邮件并提交到 Claude Batch API（价格减半）

    参数:
    - limit: 最多处理邮件数量（默认50）

    返回:
    - batch_id: Claude 批次 ID
    - db_batch_id: 数据库批次 ID
    - total_requests: 请求数量
    - status: 状态
    """
    from services.batch_service import get_batch_service

    try:
        service = get_batch_service()
        result = await service.run_batch_translation(limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建批次失败: {str(e)}")


@router.get("/batch/status/{batch_id}")
async def get_batch_status(
    batch_id: str,
    account: EmailAccount = Depends(get_current_account)
):
    """
    查询 Claude Batch 状态

    参数:
    - batch_id: Claude 批次 ID

    返回:
    - id: 批次 ID
    - processing_status: 状态 (in_progress, ended, failed, expired, canceled)
    - request_counts: 请求统计
    """
    from services.batch_service import get_batch_service

    try:
        service = get_batch_service()
        result = await service.check_batch_status(batch_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询状态失败: {str(e)}")


@router.post("/batch/poll")
async def poll_and_process_batches(
    account: EmailAccount = Depends(get_current_account)
):
    """
    轮询并处理已完成的批次

    检查所有进行中的批次，处理已完成的结果。
    建议由定时任务调用，也可手动触发。

    返回:
    - checked: 检查的批次数
    - completed: 完成的批次数
    - results: 处理结果详情
    """
    from services.batch_service import get_batch_service

    try:
        service = get_batch_service()
        result = await service.poll_and_process_batches()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"轮询处理失败: {str(e)}")


@router.get("/batch/list")
async def list_batches(
    status: Optional[str] = None,
    limit: int = 20,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取批次列表

    参数:
    - status: 可选，筛选状态 (pending, submitted, in_progress, ended, failed)
    - limit: 返回数量（默认20）

    返回:
    - batches: 批次列表
    """
    from database.models import TranslationBatch

    query = select(TranslationBatch).order_by(TranslationBatch.created_at.desc()).limit(limit)

    if status:
        query = query.where(TranslationBatch.status == status)

    result = await db.execute(query)
    batches = result.scalars().all()

    return {
        "batches": [
            {
                "id": b.id,
                "batch_id": b.batch_id,
                "status": b.status,
                "total_requests": b.total_requests,
                "completed_requests": b.completed_requests,
                "failed_requests": b.failed_requests,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None,
                "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            }
            for b in batches
        ]
    }


@router.get("/batch/{db_batch_id}/items")
async def get_batch_items(
    db_batch_id: int,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """
    获取批次项详情

    参数:
    - db_batch_id: 数据库批次 ID

    返回:
    - items: 批次项列表
    """
    from database.models import TranslationBatchItem

    result = await db.execute(
        select(TranslationBatchItem)
        .where(TranslationBatchItem.batch_id == db_batch_id)
        .order_by(TranslationBatchItem.id)
    )
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": item.id,
                "custom_id": item.custom_id,
                "email_id": item.email_id,
                "status": item.status,
                "source_lang": item.source_lang,
                "target_lang": item.target_lang,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "error_message": item.error_message,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in items
        ]
    }
