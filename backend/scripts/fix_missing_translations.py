#!/usr/bin/env python3
"""
修复缺失翻译的脚本

扫描所有应该有翻译但 body_translated 为空的邮件，
从 SharedEmailTranslation 表回填翻译。

用法:
    cd backend
    python -m scripts.fix_missing_translations [--dry-run] [--limit N]
"""

import asyncio
import argparse
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import async_session
from database.models import Email, SharedEmailTranslation


async def fix_missing_translations(dry_run: bool = False, limit: int = None):
    """修复缺失翻译的邮件"""

    print("=" * 60)
    print("修复缺失翻译脚本")
    print("=" * 60)
    print(f"模式: {'预览模式 (不会修改数据)' if dry_run else '执行模式'}")
    print(f"限制: {limit if limit else '无限制'}")
    print()

    async with async_session() as db:
        # 查询需要修复的邮件：语言非中文，但 body_translated 为空
        query = select(Email).where(
            and_(
                Email.language_detected.isnot(None),
                Email.language_detected != 'zh',
                Email.language_detected != 'unknown',
                Email.message_id.isnot(None),
                or_(
                    Email.body_translated.is_(None),
                    Email.body_translated == ''
                )
            )
        ).order_by(Email.received_at.desc())

        if limit:
            query = query.limit(limit)

        result = await db.execute(query)
        emails = result.scalars().all()

        print(f"找到 {len(emails)} 封需要检查的邮件")
        print()

        fixed_count = 0
        no_translation_count = 0

        for email in emails:
            # 查询共享翻译表
            shared_result = await db.execute(
                select(SharedEmailTranslation).where(
                    SharedEmailTranslation.message_id == email.message_id
                )
            )
            shared = shared_result.scalar_one_or_none()

            if shared and shared.body_translated:
                print(f"[修复] 邮件 {email.id}: {email.subject_original[:50]}...")
                print(f"       语言: {email.language_detected}, Message-ID: {email.message_id[:50]}...")

                if not dry_run:
                    email.body_translated = shared.body_translated
                    if shared.subject_translated and not email.subject_translated:
                        email.subject_translated = shared.subject_translated
                    email.is_translated = True
                    email.translation_status = "completed"

                fixed_count += 1
            else:
                print(f"[无翻译] 邮件 {email.id}: {email.subject_original[:50]}...")
                print(f"         语言: {email.language_detected}")
                no_translation_count += 1

        if not dry_run and fixed_count > 0:
            await db.commit()
            print()
            print("已提交更改到数据库")

        print()
        print("=" * 60)
        print("统计结果:")
        print(f"  - 已修复: {fixed_count} 封")
        print(f"  - 无共享翻译: {no_translation_count} 封")
        print("=" * 60)

        return fixed_count, no_translation_count


async def main():
    parser = argparse.ArgumentParser(description='修复缺失翻译的邮件')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不修改数据')
    parser.add_argument('--limit', type=int, default=None, help='限制处理数量')
    args = parser.parse_args()

    await fix_missing_translations(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
