"""
定时维护 Celery 任务

包含：
- warm_translation_cache: 缓存预热
- cleanup_old_translations: 清理过期翻译缓存
- cleanup_temp_files: 清理临时文件
- rebuild_contacts_index: 重建联系人索引
- reset_monthly_quota: 每月重置翻译配额
"""
import os
import shutil
from datetime import datetime, timedelta
from celery import shared_task

from celery_app import celery_app


def get_db_session():
    """获取同步数据库会话"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@celery_app.task(bind=True)
def warm_translation_cache(self):
    """
    预热翻译缓存

    从 MySQL 翻译缓存表加载高频翻译到 Redis
    """
    from database.models import TranslationCache
    from shared.cache_config import cache_set

    db = get_db_session()

    try:
        # 获取高频翻译（命中次数 > 5）
        high_freq_translations = db.query(TranslationCache).filter(
            TranslationCache.hit_count > 5
        ).order_by(TranslationCache.hit_count.desc()).limit(1000).all()

        warmed_count = 0
        for trans in high_freq_translations:
            try:
                cache_key = f"trans:{trans.text_hash}"
                cache_set(cache_key, trans.translated_text, ttl=7200)  # 2小时TTL
                warmed_count += 1
            except Exception as e:
                print(f"[CacheWarm] Failed to warm {trans.text_hash}: {e}")

        print(f"[CacheWarm] Warmed {warmed_count} translations")
        return {
            "success": True,
            "warmed_count": warmed_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"[CacheWarm] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True)
def cleanup_old_translations(self):
    """
    清理过期翻译缓存

    删除30天未使用且命中次数低的翻译缓存
    """
    from database.models import TranslationCache
    from sqlalchemy import and_

    db = get_db_session()

    try:
        cutoff = datetime.utcnow() - timedelta(days=30)

        # 删除30天未更新且命中次数 < 3 的缓存
        deleted = db.query(TranslationCache).filter(
            and_(
                TranslationCache.updated_at < cutoff,
                TranslationCache.hit_count < 3
            )
        ).delete(synchronize_session=False)

        db.commit()

        print(f"[CacheCleanup] Deleted {deleted} old translations")
        return {
            "success": True,
            "deleted_count": deleted,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        db.rollback()
        print(f"[CacheCleanup] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True)
def cleanup_temp_files(self):
    """
    清理临时文件

    删除72小时前的导出文件等临时文件
    """
    import glob

    try:
        cleaned_count = 0
        cutoff = datetime.utcnow() - timedelta(hours=72)
        cutoff_timestamp = cutoff.timestamp()

        # 清理导出目录
        downloads_dir = os.path.join(os.path.dirname(__file__), "..", "downloads")
        if os.path.exists(downloads_dir):
            for filepath in glob.glob(os.path.join(downloads_dir, "*.zip")):
                try:
                    if os.path.getmtime(filepath) < cutoff_timestamp:
                        os.remove(filepath)
                        cleaned_count += 1
                except Exception as e:
                    print(f"[TempCleanup] Failed to remove {filepath}: {e}")

        # 清理临时目录
        temp_dirs = [
            os.path.join(os.path.dirname(__file__), "..", "temp"),
            os.path.join(os.path.dirname(__file__), "..", "uploads", "temp"),
        ]

        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    try:
                        if os.path.getmtime(item_path) < cutoff_timestamp:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.remove(item_path)
                            cleaned_count += 1
                    except Exception as e:
                        print(f"[TempCleanup] Failed to remove {item_path}: {e}")

        print(f"[TempCleanup] Cleaned {cleaned_count} temp files")
        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"[TempCleanup] Error: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(bind=True)
def rebuild_contacts_index(self):
    """
    重建联系人索引

    从邮件表聚合联系人并缓存到 Redis
    """
    from database.models import Email, EmailAccount
    from shared.cache_config import cache_set
    from sqlalchemy import func, distinct
    import json

    db = get_db_session()

    try:
        # 获取所有账户
        accounts = db.query(EmailAccount).all()

        rebuilt_count = 0

        for account in accounts:
            # 聚合该账户的所有联系人
            contacts = {}

            # 从 from_email 提取
            from_emails = db.query(
                Email.from_email,
                func.count(Email.id).label('frequency')
            ).filter(
                Email.account_id == account.id,
                Email.from_email.isnot(None)
            ).group_by(Email.from_email).all()

            for email, freq in from_emails:
                if email:
                    email_lower = email.lower()
                    contacts[email_lower] = contacts.get(email_lower, 0) + freq

            # 从 to_email 提取（可能包含多个地址）
            to_emails = db.query(Email.to_email).filter(
                Email.account_id == account.id,
                Email.to_email.isnot(None)
            ).all()

            for (to_email,) in to_emails:
                if to_email:
                    for addr in to_email.split(','):
                        addr = addr.strip().lower()
                        if addr and '@' in addr:
                            contacts[addr] = contacts.get(addr, 0) + 1

            # 排序并取前100
            sorted_contacts = sorted(
                contacts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:100]

            # 缓存到 Redis
            cache_key = f"contacts:{account.id}"
            cache_data = [{"email": email, "frequency": freq} for email, freq in sorted_contacts]
            cache_set(cache_key, json.dumps(cache_data), ttl=86400)  # 24小时

            rebuilt_count += 1

        print(f"[ContactsIndex] Rebuilt index for {rebuilt_count} accounts")
        return {
            "success": True,
            "accounts_processed": rebuilt_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"[ContactsIndex] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True)
def reset_monthly_quota(self):
    """
    每月1日重置翻译配额

    重置所有翻译引擎的月度使用量
    """
    from database.models import UsageProvider

    db = get_db_session()

    try:
        today = datetime.utcnow().date()

        # 只在每月1日执行
        if today.day != 1:
            return {
                "success": True,
                "skipped": True,
                "reason": f"Not first day of month (today is {today.day})"
            }

        # 重置所有引擎的月度用量
        reset_count = db.query(UsageProvider).update({
            "current_month_chars": 0,
            "is_disabled": False,
            "last_reset_at": datetime.utcnow()
        }, synchronize_session=False)

        db.commit()

        print(f"[QuotaReset] Reset quota for {reset_count} providers")
        return {
            "success": True,
            "reset_count": reset_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        db.rollback()
        print(f"[QuotaReset] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True)
def cleanup_stuck_translations(self):
    """
    清理卡死的翻译状态

    将超过 10 分钟仍处于 "translating" 状态的邮件重置为可翻译状态
    防止因进程崩溃或异常导致邮件永远无法被重新翻译
    """
    from database.models import Email
    from sqlalchemy import and_

    db = get_db_session()

    try:
        # 10 分钟超时阈值
        cutoff = datetime.utcnow() - timedelta(minutes=10)

        # 查找卡死的翻译任务
        stuck_count = db.query(Email).filter(
            and_(
                Email.translation_status == "translating",
                Email.updated_at < cutoff
            )
        ).update({
            "translation_status": "failed"
        }, synchronize_session=False)

        db.commit()

        if stuck_count > 0:
            print(f"[TranslationCleanup] Reset {stuck_count} stuck translations")

        return {
            "success": True,
            "reset_count": stuck_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        db.rollback()
        print(f"[TranslationCleanup] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True)
def batch_language_detection(self, email_ids: list):
    """
    批量语言检测

    对指定邮件进行语言检测
    """
    from database.models import Email
    from langdetect import detect

    db = get_db_session()

    try:
        detected_count = 0
        failed_count = 0

        emails = db.query(Email).filter(
            Email.id.in_(email_ids),
            Email.language_detected.is_(None)
        ).all()

        for email in emails:
            try:
                text = email.subject_original or email.body_original or ""
                if text:
                    lang = detect(text[:500])  # 只检测前500字符
                    email.language_detected = lang
                    detected_count += 1
            except Exception as e:
                failed_count += 1
                print(f"[LangDetect] Failed for email {email.id}: {e}")

        db.commit()

        return {
            "success": True,
            "detected_count": detected_count,
            "failed_count": failed_count
        }

    except Exception as e:
        db.rollback()
        print(f"[LangDetect] Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()
