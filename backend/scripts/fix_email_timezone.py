"""
修复邮件时间时区问题

问题：之前解析邮件日期时，没有将带时区的 datetime 转换为本地时间，
导致 UTC 时间被当作本地时间存储。

例如：UTC 09:08 应该是北京时间 17:08，但被错误存储为 09:08

此脚本重新从 IMAP 获取邮件头，解析正确的时间并更新数据库。
"""
import asyncio
import imaplib
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import async_session
from database.models import Email, EmailAccount
from sqlalchemy import select, update
from utils.crypto import decrypt_password

# 中国时区
CHINA_TZ = timezone(timedelta(hours=8))


def convert_to_local_time(dt: datetime) -> datetime:
    """将带时区的 datetime 转换为中国本地时间"""
    if dt.tzinfo is not None:
        local_dt = dt.astimezone(CHINA_TZ)
        return local_dt.replace(tzinfo=None)
    return dt


async def fix_email_times():
    """修复所有邮件的时间"""
    async with async_session() as db:
        # 获取所有账户
        result = await db.execute(select(EmailAccount))
        accounts = result.scalars().all()

        for account in accounts:
            print(f"\n处理账户: {account.email}")

            try:
                password = decrypt_password(account.password)
            except Exception as e:
                print(f"  ✗ 解密密码失败: {e}")
                continue

            # 连接 IMAP
            try:
                mail = imaplib.IMAP4_SSL('imap-ent.21cn.com', 993)
                mail.login(account.email, password)
                mail.select('INBOX')
            except Exception as e:
                print(f"  ✗ IMAP 连接失败: {e}")
                continue

            # 获取该账户的所有邮件
            email_result = await db.execute(
                select(Email)
                .where(Email.account_id == account.id)
                .order_by(Email.received_at.desc())
            )
            emails = email_result.scalars().all()

            fixed_count = 0
            error_count = 0

            for email_obj in emails:
                if not email_obj.message_id:
                    continue

                # 搜索邮件
                try:
                    # 使用 HEADER 搜索 Message-ID
                    search_criteria = f'HEADER Message-ID "{email_obj.message_id}"'
                    _, msg_nums = mail.search(None, search_criteria)

                    if not msg_nums[0]:
                        # 尝试去掉尖括号搜索
                        clean_id = email_obj.message_id.strip('<>')
                        search_criteria = f'HEADER Message-ID "{clean_id}"'
                        _, msg_nums = mail.search(None, search_criteria)

                    if not msg_nums[0]:
                        continue

                    # 获取邮件头
                    msg_num = msg_nums[0].split()[-1]
                    _, data = mail.fetch(msg_num, '(BODY.PEEK[HEADER.FIELDS (DATE)])')

                    if not data[0]:
                        continue

                    header = data[0][1].decode('utf-8', errors='replace')

                    # 解析 Date
                    for line in header.split('\n'):
                        if line.lower().startswith('date:'):
                            date_str = line[5:].strip()
                            try:
                                parsed_dt = parsedate_to_datetime(date_str)
                                correct_time = convert_to_local_time(parsed_dt)

                                # 检查是否需要更新
                                if email_obj.received_at != correct_time:
                                    old_time = email_obj.received_at
                                    email_obj.received_at = correct_time
                                    fixed_count += 1
                                    print(f"  修复 ID {email_obj.id}: {old_time} -> {correct_time}")
                            except Exception as e:
                                error_count += 1
                            break

                except Exception as e:
                    error_count += 1
                    continue

            await db.commit()
            mail.logout()

            print(f"  ✓ 完成: 修复 {fixed_count} 封, 错误 {error_count} 封")


async def fix_single_email(email_id: int):
    """修复单封邮件的时间"""
    async with async_session() as db:
        # 获取邮件
        result = await db.execute(
            select(Email).where(Email.id == email_id)
        )
        email_obj = result.scalar()

        if not email_obj:
            print(f"邮件 ID {email_id} 不存在")
            return

        # 获取账户
        account_result = await db.execute(
            select(EmailAccount).where(EmailAccount.id == email_obj.account_id)
        )
        account = account_result.scalar()

        if not account:
            print("账户不存在")
            return

        print(f"邮件: {email_obj.subject_original}")
        print(f"当前时间: {email_obj.received_at}")
        print(f"Message-ID: {email_obj.message_id}")

        # 连接 IMAP
        password = decrypt_password(account.password)
        mail = imaplib.IMAP4_SSL('imap-ent.21cn.com', 993)
        mail.login(account.email, password)
        mail.select('INBOX')

        # 搜索邮件
        search_criteria = f'HEADER Message-ID "{email_obj.message_id}"'
        _, msg_nums = mail.search(None, search_criteria)

        if not msg_nums[0]:
            clean_id = email_obj.message_id.strip('<>')
            search_criteria = f'HEADER Message-ID "{clean_id}"'
            _, msg_nums = mail.search(None, search_criteria)

        if msg_nums[0]:
            msg_num = msg_nums[0].split()[-1]
            _, data = mail.fetch(msg_num, '(BODY.PEEK[HEADER.FIELDS (DATE)])')

            if data[0]:
                header = data[0][1].decode('utf-8', errors='replace')
                print(f"原始 Date 头: {header.strip()}")

                for line in header.split('\n'):
                    if line.lower().startswith('date:'):
                        date_str = line[5:].strip()
                        try:
                            parsed_dt = parsedate_to_datetime(date_str)
                            print(f"解析结果: {parsed_dt} (时区: {parsed_dt.tzinfo})")

                            correct_time = convert_to_local_time(parsed_dt)
                            print(f"正确的本地时间: {correct_time}")

                            email_obj.received_at = correct_time
                            await db.commit()
                            print("✓ 已更新")
                        except Exception as e:
                            print(f"解析失败: {e}")
                        break
        else:
            print("在 IMAP 中找不到该邮件")

        mail.logout()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 修复单封邮件
        email_id = int(sys.argv[1])
        print(f"修复邮件 ID: {email_id}")
        asyncio.run(fix_single_email(email_id))
    else:
        # 修复所有邮件
        print("修复所有邮件的时区问题...")
        print("这可能需要一些时间...")
        asyncio.run(fix_email_times())
