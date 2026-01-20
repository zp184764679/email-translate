"""
修复未翻译邮件的脚本

问题：当 vLLM 服务不可用时，拉丁字母语言（英文、德文等）的邮件
无法检测语言，导致 language_detected = "unknown"，没有触发翻译。

解决：重新检测语言 + 翻译这些邮件

用法：
    cd backend
    python -m scripts.fix_untranslated_emails
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def fix_untranslated_emails():
    """修复未翻译的邮件"""
    from config import get_settings
    from database.models import Email, SharedEmailTranslation
    from services.language_service import get_language_service
    from services.translate_service import TranslateService

    settings = get_settings()

    # 创建数据库连接
    db_url = f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}?charset=utf8mb4"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 获取服务
    language_service = get_language_service()
    translate_service = TranslateService(
        vllm_base_url=settings.vllm_base_url,
        vllm_model=settings.vllm_model,
        vllm_api_key=settings.vllm_api_key,
    )

    async with async_session() as db:
        # 查找需要修复的邮件：
        # 1. language_detected = "unknown" 或为空
        # 2. is_translated = False
        # 3. 有正文内容
        result = await db.execute(
            select(Email).where(
                and_(
                    or_(
                        Email.language_detected == "unknown",
                        Email.language_detected == "",
                        Email.language_detected.is_(None)
                    ),
                    Email.is_translated == False,
                    Email.body_original.isnot(None),
                    Email.body_original != ""
                )
            ).order_by(Email.received_at.desc())
        )
        emails = result.scalars().all()

        print(f"\n找到 {len(emails)} 封需要修复的邮件\n")

        if not emails:
            print("没有需要修复的邮件")
            return

        fixed_count = 0
        failed_count = 0

        for email in emails:
            try:
                print(f"处理邮件 ID={email.id}: {email.subject_original[:50] if email.subject_original else '(无主题)'}...")

                # 1. 重新检测语言
                text_to_detect = email.body_original[:1000] if email.body_original else ""
                if email.subject_original:
                    text_to_detect = email.subject_original + " " + text_to_detect

                lang = language_service.detect_language(text_to_detect)
                print(f"  语言检测结果: {lang}")

                # 更新语言
                email.language_detected = lang

                # 2. 如果是非中文，进行翻译
                if lang and lang != "zh" and lang != "unknown":
                    try:
                        # 翻译主题
                        if email.subject_original:
                            email.subject_translated = translate_service.translate_text(
                                email.subject_original,
                                target_lang="zh",
                                source_lang=lang
                            )

                        # 翻译正文（使用 vLLM 智能路由）
                        if email.body_original:
                            result = translate_service.translate_with_smart_routing(
                                text=email.body_original,
                                subject=email.subject_original or "",
                                target_lang="zh",
                                source_lang=lang
                            )
                            email.body_translated = result["translated_text"]
                            print(f"  翻译成功 (provider: {result['provider_used']})")

                        email.is_translated = True

                        # 保存到共享翻译表
                        if email.message_id and (email.subject_translated or email.body_translated):
                            from sqlalchemy.dialects.mysql import insert as mysql_insert
                            stmt = mysql_insert(SharedEmailTranslation).values(
                                message_id=email.message_id,
                                subject_original=email.subject_original,
                                subject_translated=email.subject_translated,
                                body_original=email.body_original,
                                body_translated=email.body_translated,
                                source_lang=lang,
                                target_lang="zh",
                                translated_by=email.account_id
                            ).on_duplicate_key_update(
                                subject_translated=email.subject_translated,
                                body_translated=email.body_translated
                            )
                            await db.execute(stmt)

                        fixed_count += 1

                    except Exception as te:
                        print(f"  翻译失败: {te}")
                        failed_count += 1

                elif lang == "zh":
                    # 中文邮件，标记为已翻译（不需要翻译）
                    email.is_translated = True
                    fixed_count += 1
                    print(f"  中文邮件，跳过翻译")

                else:
                    print(f"  语言仍为 unknown，跳过")
                    failed_count += 1

                await db.commit()

            except Exception as e:
                print(f"  处理失败: {e}")
                failed_count += 1
                await db.rollback()

        print(f"\n修复完成！")
        print(f"  成功: {fixed_count}")
        print(f"  失败: {failed_count}")


if __name__ == "__main__":
    asyncio.run(fix_untranslated_emails())
