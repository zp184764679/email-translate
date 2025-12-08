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

router = APIRouter(prefix="/api/translate", tags=["translate"])
settings = get_settings()


# ============ 缓存工具函数 ============
def compute_cache_key(text: str, source_lang: str, target_lang: str) -> str:
    """计算缓存键（SHA256）"""
    content = f"{text}|{source_lang or 'auto'}|{target_lang}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


async def get_cached_translation(db: AsyncSession, text: str, source_lang: str, target_lang: str) -> Optional[str]:
    """从缓存获取翻译结果"""
    cache_key = compute_cache_key(text, source_lang, target_lang)
    result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    cached = result.scalar_one_or_none()

    if cached:
        # 更新命中次数
        cached.hit_count += 1
        await db.commit()
        print(f"[Cache HIT] hit_count={cached.hit_count}, text={text[:30]}...")
        return cached.translated_text

    return None


async def save_to_cache(db: AsyncSession, text: str, translated: str, source_lang: str, target_lang: str):
    """保存翻译结果到缓存"""
    cache_key = compute_cache_key(text, source_lang, target_lang)

    # 检查是否已存在（避免重复插入）
    result = await db.execute(
        select(TranslationCache).where(TranslationCache.text_hash == cache_key)
    )
    if result.scalar_one_or_none():
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
    print(f"[Cache SAVE] text={text[:30]}...")


def get_translate_service() -> TranslateService:
    """Get configured translation service instance

    切换方式：修改 .env 中的 TRANSLATE_PROVIDER
    - ollama: 本地测试（免费）
    - claude: Claude API（正式使用）
    - deepl: DeepL API
    """
    if settings.translate_provider == "deepl":
        return TranslateService(
            api_key=settings.deepl_api_key,
            provider="deepl",
            is_free_api=settings.deepl_free_api
        )
    elif settings.translate_provider == "claude":
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
    """Translate text in real-time (with cache)"""
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
        translated = service.translate_text(
            text=request.text,
            target_lang=request.target_lang,
            glossary=glossary,
            context=request.context
        )

        # 保存到缓存
        await save_to_cache(db, request.text, translated, None, request.target_lang)

        return TranslateResponse(translated_text=translated)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")


@router.post("/reverse", response_model=TranslateResponse)
async def translate_reply(
    request: TranslateRequest,
    account: EmailAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db)
):
    """Translate Chinese reply to target language (with cache)"""
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
        translated = service.translate_text(
            text=request.text,
            target_lang=request.target_lang,
            glossary=glossary,
            context=request.context
        )

        # 保存到缓存
        await save_to_cache(db, request.text, translated, "zh", request.target_lang)

        return TranslateResponse(translated_text=translated)
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


@router.get("/usage")
async def get_translation_usage(account: EmailAccount = Depends(get_current_account)):
    """Get translation API usage (DeepL only)"""
    if settings.translate_provider != "deepl":
        return {"message": "仅DeepL支持用量查询"}

    try:
        service = get_translate_service()
        usage = service.get_usage()
        return usage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
