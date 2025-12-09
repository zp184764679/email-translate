"""
密码加密迁移脚本

将数据库中已存在的明文密码加密。
此脚本可以安全地多次运行（幂等性）。

用法:
    cd backend
    python -m migrations.encrypt_passwords
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from database.database import init_db, async_session
from database.models import EmailAccount
from utils.crypto import encrypt_password, is_encrypted, mask_email


async def migrate_passwords():
    """加密所有未加密的密码"""
    print("=" * 50)
    print("密码加密迁移脚本")
    print("=" * 50)

    # 初始化数据库
    await init_db()

    async with async_session() as db:
        # 获取所有账户
        result = await db.execute(select(EmailAccount))
        accounts = result.scalars().all()

        print(f"\n找到 {len(accounts)} 个账户")

        encrypted_count = 0
        already_encrypted = 0
        errors = 0

        for account in accounts:
            email_masked = mask_email(account.email)

            if not account.password:
                print(f"  [{email_masked}] 跳过：密码为空")
                continue

            if is_encrypted(account.password):
                print(f"  [{email_masked}] 已加密，跳过")
                already_encrypted += 1
                continue

            try:
                # 加密密码
                account.password = encrypt_password(account.password)
                encrypted_count += 1
                print(f"  [{email_masked}] 已加密")
            except Exception as e:
                print(f"  [{email_masked}] 加密失败: {e}")
                errors += 1

        # 提交更改
        await db.commit()

        print("\n" + "=" * 50)
        print("迁移完成")
        print(f"  - 新加密: {encrypted_count}")
        print(f"  - 已加密: {already_encrypted}")
        print(f"  - 错误: {errors}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(migrate_passwords())
