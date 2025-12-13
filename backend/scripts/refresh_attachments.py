"""
重新扫描所有邮件的附件信息

使用场景：
1. 附件检测逻辑优化后，需要更新历史邮件
2. 修复附件丢失或显示不正确的问题

运行方式：
python -m scripts.refresh_attachments
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from database.database import async_session_maker
from database.models import Email, EmailAccount, Attachment
from services.email_service import EmailService
from utils.crypto import decrypt_password
import imaplib


async def refresh_all_attachments():
    """重新扫描所有邮件的附件"""

    async with async_session_maker() as db:
        # 获取所有活跃账户
        result = await db.execute(
            select(EmailAccount).where(EmailAccount.is_active == True)
        )
        accounts = result.scalars().all()

        if not accounts:
            print("❌ 没有找到活跃的邮箱账户")
            return

        total_updated = 0
        total_attachments = 0

        for account in accounts:
            print(f"\n📧 处理账户: {account.email}")

            # 获取该账户的所有邮件
            result = await db.execute(
                select(Email).where(Email.account_id == account.id)
            )
            emails = result.scalars().all()

            if not emails:
                print(f"   ℹ️  该账户没有邮件")
                continue

            print(f"   📊 找到 {len(emails)} 封邮件")

            # 解密密码
            password = decrypt_password(account.password)

            # 创建邮件服务
            service = EmailService(
                email=account.email,
                password=password,
                imap_server=account.imap_server,
                smtp_server=account.smtp_server,
                imap_port=account.imap_port,
                smtp_port=account.smtp_port
            )

            try:
                # 连接 IMAP
                print(f"   🔌 连接 IMAP 服务器...")
                imap = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
                imap.login(account.email, password)
                imap.select("INBOX")

                updated_count = 0
                new_attachments = 0

                for email in emails:
                    # 通过 Message-ID 查找邮件
                    if not email.message_id:
                        continue

                    # 搜索邮件
                    status, msg_ids = imap.search(None, f'HEADER Message-ID "{email.message_id}"')
                    if status != 'OK' or not msg_ids[0]:
                        print(f"   ⚠️  未找到邮件: {email.subject_original[:50]}")
                        continue

                    # 获取邮件内容
                    msg_id = msg_ids[0].split()[0]
                    status, msg_data = imap.fetch(msg_id, '(RFC822)')

                    if status != 'OK':
                        continue

                    # 解析邮件
                    import email as email_lib
                    msg = email_lib.message_from_bytes(msg_data[0][1])

                    # 删除旧附件记录
                    await db.execute(
                        Attachment.__table__.delete().where(Attachment.email_id == email.id)
                    )

                    # 重新提取附件
                    attachments = service._get_attachments(msg, email.message_id)

                    # 保存新附件记录
                    for att_data in attachments:
                        attachment = Attachment(
                            email_id=email.id,
                            filename=att_data['filename'],
                            content_type=att_data['content_type'],
                            file_size=att_data['file_size'],
                            file_path=att_data['file_path']
                        )
                        db.add(attachment)

                    if attachments:
                        updated_count += 1
                        new_attachments += len(attachments)
                        print(f"   ✅ {email.subject_original[:40]}: {len(attachments)} 个附件")

                await db.commit()

                print(f"   📈 更新了 {updated_count} 封邮件，新增 {new_attachments} 个附件")
                total_updated += updated_count
                total_attachments += new_attachments

                imap.logout()

            except Exception as e:
                print(f"   ❌ 处理账户 {account.email} 时出错: {e}")
                await db.rollback()
                continue

        print(f"\n" + "="*60)
        print(f"✨ 完成！共更新 {total_updated} 封邮件，{total_attachments} 个附件")


async def refresh_single_email(email_id: int):
    """重新扫描单个邮件的附件"""

    async with async_session_maker() as db:
        # 获取邮件
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()

        if not email:
            print(f"❌ 未找到邮件 ID: {email_id}")
            return

        # 获取账户
        result = await db.execute(select(EmailAccount).where(EmailAccount.id == email.account_id))
        account = result.scalar_one_or_none()

        if not account:
            print(f"❌ 未找到账户")
            return

        print(f"📧 重新扫描邮件: {email.subject_original}")

        # 解密密码
        password = decrypt_password(account.password)

        # 创建邮件服务
        service = EmailService(
            email=account.email,
            password=password,
            imap_server=account.imap_server,
            smtp_server=account.smtp_server,
            imap_port=account.imap_port,
            smtp_port=account.smtp_port
        )

        try:
            # 连接 IMAP
            imap = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
            imap.login(account.email, password)
            imap.select("INBOX")

            # 搜索邮件
            status, msg_ids = imap.search(None, f'HEADER Message-ID "{email.message_id}"')
            if status != 'OK' or not msg_ids[0]:
                print(f"❌ 在 IMAP 服务器上未找到该邮件")
                return

            # 获取邮件内容
            msg_id = msg_ids[0].split()[0]
            status, msg_data = imap.fetch(msg_id, '(RFC822)')

            if status != 'OK':
                print(f"❌ 获取邮件失败")
                return

            # 解析邮件
            import email as email_lib
            msg = email_lib.message_from_bytes(msg_data[0][1])

            # 删除旧附件记录
            await db.execute(
                Attachment.__table__.delete().where(Attachment.email_id == email.id)
            )

            # 重新提取附件
            attachments = service._get_attachments(msg, email.message_id)

            # 保存新附件记录
            for att_data in attachments:
                attachment = Attachment(
                    email_id=email.id,
                    filename=att_data['filename'],
                    content_type=att_data['content_type'],
                    file_size=att_data['file_size'],
                    file_path=att_data['file_path']
                )
                db.add(attachment)

            await db.commit()

            print(f"✅ 成功更新，找到 {len(attachments)} 个附件:")
            for att in attachments:
                print(f"   📎 {att['filename']} ({att['file_size']} bytes)")

            imap.logout()

        except Exception as e:
            print(f"❌ 处理邮件时出错: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='重新扫描邮件附件')
    parser.add_argument('--email-id', type=int, help='指定邮件 ID（不指定则处理所有邮件）')
    args = parser.parse_args()

    print("🔄 开始重新扫描附件...")
    print("="*60)

    if args.email_id:
        asyncio.run(refresh_single_email(args.email_id))
    else:
        asyncio.run(refresh_all_attachments())
