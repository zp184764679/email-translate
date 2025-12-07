"""
翻译最新的5封邮件（直接调用翻译服务）
"""
import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import Session
from database.models import Email
from services.translate_service import TranslateService
from config import get_settings, get_database_url

settings = get_settings()

# 使用同步引擎 (pymysql 而非 aiomysql)
async_url = get_database_url()
sync_url = async_url.replace('+aiomysql', '+pymysql')
engine = create_engine(sync_url, echo=False)


def translate_latest_emails(count: int = 5):
    """翻译最新的几封邮件"""
    # 根据配置初始化翻译服务
    if settings.translate_provider == "ollama":
        translate_service = TranslateService(
            provider="ollama",
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model
        )
    elif settings.translate_provider == "claude":
        translate_service = TranslateService(
            provider="claude",
            api_key=settings.claude_api_key,
            claude_model=settings.claude_model
        )
    else:  # deepl
        translate_service = TranslateService(
            provider="deepl",
            api_key=settings.deepl_api_key,
            is_free_api=settings.deepl_free_api
        )

    with Session(engine) as db:
        # 获取最新的非中文邮件
        result = db.execute(
            select(Email)
            .where(Email.language_detected != 'zh')
            .where(Email.language_detected != 'unknown')
            .where(Email.language_detected.isnot(None))
            .order_by(desc(Email.received_at))
            .limit(count)
        )
        emails = result.scalars().all()

        if not emails:
            print("没有找到需要翻译的邮件")
            return

        print(f"找到 {len(emails)} 封邮件")
        print(f"使用翻译引擎: {settings.translate_provider}")
        print("-" * 60)

        translated_count = 0
        for i, email in enumerate(emails, 1):
            status = "已翻译" if email.is_translated else "未翻译"
            print(f"\n[{i}/{len(emails)}] ID: {email.id}")
            print(f"  主题: {email.subject_original[:60] if email.subject_original else '(无)'}...")
            print(f"  语言: {email.language_detected}")
            print(f"  状态: {status}")

            if email.is_translated:
                print("  → 跳过（已翻译）")
                continue

            try:
                # 翻译主题
                if email.subject_original:
                    print("  → 翻译主题中...")
                    subject_result = translate_service.translate_text(
                        text=email.subject_original,
                        source_lang=email.language_detected,
                        target_lang='zh'
                    )
                    email.subject_translated = subject_result

                # 翻译正文
                if email.body_original:
                    body_text = email.body_original[:3000]  # 限制长度
                    print(f"  → 翻译正文中... ({len(body_text)} 字符)")
                    body_result = translate_service.translate_text(
                        text=body_text,
                        source_lang=email.language_detected,
                        target_lang='zh'
                    )
                    email.body_translated = body_result

                email.is_translated = True
                db.commit()
                translated_count += 1
                print("  ✓ 翻译完成")

            except Exception as e:
                print(f"  ✗ 翻译失败: {e}")
                db.rollback()

        print("\n" + "=" * 60)
        print(f"翻译完成! 共翻译 {translated_count} 封邮件")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    translate_latest_emails(count)
