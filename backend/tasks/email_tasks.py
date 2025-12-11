"""
邮件相关 Celery 任务

包含：
- fetch_emails_task: 拉取邮件
- send_email_task: 发送邮件
- export_emails_task: 导出邮件
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from zipfile import ZipFile
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from typing import Optional, List

from celery_app import celery_app


def get_db_session():
    """获取同步数据库会话"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DATABASE', 'email_translate')}?charset=utf8mb4"
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def notify_completion(account_id: int, event_type: str, data: dict):
    """发送任务完成通知"""
    try:
        from services.notification_service import notification_manager
        asyncio.get_event_loop().run_until_complete(
            notification_manager.broadcast(account_id, event_type, data)
        )
    except Exception as e:
        print(f"[Notify] Failed to send notification: {e}")


@celery_app.task(bind=True, max_retries=3, soft_time_limit=120, time_limit=150)
def fetch_emails_task(self, account_id: int, since_days: int = 30):
    """
    异步拉取邮件

    Args:
        account_id: 邮箱账户ID
        since_days: 拉取最近多少天的邮件

    Returns:
        dict: 拉取结果 {success, new_count, total_count}
    """
    from database.models import EmailAccount, Email
    from services.email_service import EmailService

    db = get_db_session()

    try:
        # 获取账户
        account = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account:
            return {"success": False, "error": "Account not found"}

        # 发送开始通知
        notify_completion(account_id, "fetch_started", {
            "account_id": account_id,
            "since_days": since_days
        })

        # 创建邮件服务
        service = EmailService(
            email=account.email,
            password=account.password,
            imap_server=account.imap_server,
            imap_port=account.imap_port,
            smtp_server=account.smtp_server,
            smtp_port=account.smtp_port
        )

        # 计算起始日期
        since_date = datetime.utcnow() - timedelta(days=since_days)

        # 拉取邮件
        emails = service.fetch_emails(since_date=since_date)

        new_count = 0
        total_count = len(emails)
        progress = 0

        for i, email_data in enumerate(emails):
            # 检查是否已存在
            existing = db.query(Email).filter(
                Email.message_id == email_data.get("message_id")
            ).first()

            if not existing:
                # 创建新邮件
                new_email = Email(
                    account_id=account_id,
                    message_id=email_data.get("message_id"),
                    subject_original=email_data.get("subject"),
                    body_original=email_data.get("body"),
                    from_email=email_data.get("from_email"),
                    to_email=email_data.get("to_email"),
                    cc_email=email_data.get("cc_email"),
                    received_at=email_data.get("date"),
                    language_detected=email_data.get("language"),
                    has_attachments=bool(email_data.get("attachments")),
                    is_read=False,
                    is_flagged=False,
                    is_translated=False
                )
                db.add(new_email)
                new_count += 1

            # 发送进度更新（每10封或最后一封）
            new_progress = int((i + 1) / total_count * 100)
            if new_progress - progress >= 10 or i == total_count - 1:
                progress = new_progress
                notify_completion(account_id, "fetch_progress", {
                    "current": i + 1,
                    "total": total_count,
                    "progress": progress,
                    "new_count": new_count
                })

        db.commit()

        # 发送完成通知
        notify_completion(account_id, "fetch_complete", {
            "success": True,
            "new_count": new_count,
            "total_count": total_count
        })

        return {
            "success": True,
            "new_count": new_count,
            "total_count": total_count
        }

    except SoftTimeLimitExceeded:
        notify_completion(account_id, "fetch_timeout", {
            "error": "Fetch operation timed out"
        })
        raise self.retry(countdown=30, max_retries=2)
    except Exception as e:
        db.rollback()
        print(f"[FetchEmails] Error: {e}")

        notify_completion(account_id, "fetch_failed", {
            "error": str(e)
        })

        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
def send_email_task(self, draft_id: int, account_id: int):
    """
    异步发送邮件

    Args:
        draft_id: 草稿ID
        account_id: 账户ID

    Returns:
        dict: 发送结果
    """
    from database.models import EmailAccount, Draft
    from services.email_service import EmailService

    db = get_db_session()

    try:
        # 获取草稿
        draft = db.query(Draft).filter(Draft.id == draft_id).first()
        if not draft:
            return {"success": False, "error": "Draft not found"}

        # 获取账户
        account = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account:
            return {"success": False, "error": "Account not found"}

        # 创建邮件服务
        service = EmailService(
            email=account.email,
            password=account.password,
            imap_server=account.imap_server,
            imap_port=account.imap_port,
            smtp_server=account.smtp_server,
            smtp_port=account.smtp_port
        )

        # 获取收件人
        to_addr = draft.to_address if draft.to_address else ""
        cc_addr = draft.cc_address if hasattr(draft, 'cc_address') and draft.cc_address else ""

        # 发送邮件
        success = service.send_email(
            to=to_addr,
            cc=cc_addr if cc_addr else None,
            subject=draft.subject_translated or draft.subject_original,
            body=draft.body_translated or draft.body_original,
            reply_to_message_id=draft.in_reply_to if hasattr(draft, 'in_reply_to') else None
        )

        if success:
            # 更新草稿状态
            draft.status = "sent"
            draft.sent_at = datetime.utcnow()
            db.commit()

            # 发送成功通知
            notify_completion(account_id, "email_sent", {
                "draft_id": draft_id,
                "to": to_addr,
                "success": True
            })

            return {
                "success": True,
                "draft_id": draft_id,
                "sent_at": datetime.utcnow().isoformat()
            }
        else:
            raise Exception("SMTP send failed")

    except SoftTimeLimitExceeded:
        notify_completion(account_id, "send_timeout", {
            "draft_id": draft_id,
            "error": "Send operation timed out"
        })
        raise self.retry(countdown=30)
    except Exception as e:
        db.rollback()
        print(f"[SendEmail] Error sending draft {draft_id}: {e}")

        notify_completion(account_id, "send_failed", {
            "draft_id": draft_id,
            "error": str(e)
        })

        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, soft_time_limit=120, time_limit=150)
def export_emails_task(self, email_ids: List[int], account_id: int, export_format: str = "eml"):
    """
    异步批量导出邮件

    Args:
        email_ids: 要导出的邮件ID列表
        account_id: 账户ID
        export_format: 导出格式 (eml, pdf)

    Returns:
        dict: 导出结果 {success, download_url, file_size}
    """
    from database.models import Email
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import tempfile

    db = get_db_session()

    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        zip_filename = f"emails_export_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        # 获取邮件
        emails = db.query(Email).filter(Email.id.in_(email_ids)).all()

        if not emails:
            return {"success": False, "error": "No emails found"}

        # 发送开始通知
        notify_completion(account_id, "export_started", {
            "total": len(emails)
        })

        # 创建ZIP文件
        with ZipFile(zip_path, 'w') as zf:
            for i, email in enumerate(emails):
                # 创建EML内容
                msg = MIMEMultipart()
                msg['Subject'] = email.subject_original or ""
                msg['From'] = email.from_email or ""
                msg['To'] = email.to_email or ""
                msg['Date'] = email.received_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if email.received_at else ""

                # 添加正文
                body = email.body_original or ""
                msg.attach(MIMEText(body, 'plain', 'utf-8'))

                # 写入ZIP
                eml_content = msg.as_string()
                safe_subject = "".join(c for c in (email.subject_original or "email")[:50] if c.isalnum() or c in " _-")
                zf.writestr(f"{email.id}_{safe_subject}.eml", eml_content)

                # 更新进度
                if (i + 1) % 10 == 0 or i == len(emails) - 1:
                    notify_completion(account_id, "export_progress", {
                        "current": i + 1,
                        "total": len(emails),
                        "progress": int((i + 1) / len(emails) * 100)
                    })

        # 获取文件大小
        file_size = os.path.getsize(zip_path)

        # 移动到可访问的下载目录
        download_dir = os.path.join(os.path.dirname(__file__), "..", "downloads")
        os.makedirs(download_dir, exist_ok=True)
        final_path = os.path.join(download_dir, zip_filename)
        os.rename(zip_path, final_path)

        # 生成下载URL（相对路径）
        download_url = f"/api/downloads/{zip_filename}"

        # 发送完成通知
        notify_completion(account_id, "export_complete", {
            "success": True,
            "download_url": download_url,
            "file_size": file_size,
            "email_count": len(emails)
        })

        return {
            "success": True,
            "download_url": download_url,
            "file_size": file_size,
            "email_count": len(emails)
        }

    except Exception as e:
        print(f"[ExportEmails] Error: {e}")

        notify_completion(account_id, "export_failed", {
            "error": str(e)
        })

        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()
