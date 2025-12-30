"""
邮件模板服务 - 模板 CRUD 和翻译功能

功能：
1. 模板 CRUD（创建、读取、更新、删除）
2. 模板翻译（使用 vLLM 翻译为多语言版本）
3. 模板共享（个人模板可共享给全公司）
4. 变量替换（将占位符替换为实际值）
"""

import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import EmailTemplate, EmailTemplateTranslation, EmailAccount
from services.translate_service import TranslateService


logger = logging.getLogger(__name__)


# 模板分类定义
TEMPLATE_CATEGORIES = {
    "inquiry": {"name_cn": "询价", "name_en": "Inquiry", "icon": "Search"},
    "order": {"name_cn": "订单确认", "name_en": "Order Confirmation", "icon": "Document"},
    "logistics": {"name_cn": "物流跟踪", "name_en": "Logistics", "icon": "Van"},
    "payment": {"name_cn": "付款相关", "name_en": "Payment", "icon": "Money"},
    "quality": {"name_cn": "质量问题", "name_en": "Quality", "icon": "Warning"},
    "general": {"name_cn": "日常沟通", "name_en": "General", "icon": "ChatDotRound"},
}

# 可用变量定义
AVAILABLE_VARIABLES = {
    "supplier_name": {"description": "供应商名称", "example": "ABC Trading Co."},
    "contact_name": {"description": "联系人姓名", "example": "张经理"},
    "order_number": {"description": "订单号", "example": "PO-2024-001"},
    "product_name": {"description": "产品名称", "example": "不锈钢螺丝"},
    "quantity": {"description": "数量", "example": "1000"},
    "unit_price": {"description": "单价", "example": "0.5"},
    "total_amount": {"description": "总金额", "example": "500"},
    "currency": {"description": "货币单位", "example": "USD"},
    "date": {"description": "当前日期", "example": "2024-12-30"},
    "delivery_date": {"description": "交货日期", "example": "2025-01-15"},
    "shipping_address": {"description": "收货地址", "example": "广东省东莞市"},
    "my_name": {"description": "我的姓名", "example": "李明"},
    "my_company": {"description": "我的公司", "example": "精之成精密五金有限公司"},
    "my_phone": {"description": "我的电话", "example": "0769-12345678"},
}

# 支持的翻译语言
SUPPORTED_LANGUAGES = {
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "vi": "Tiếng Việt",
    "th": "ไทย",
}


class TemplateService:
    """邮件模板服务类"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.translate_service = TranslateService()

    async def get_categories(self) -> List[Dict[str, Any]]:
        """获取模板分类列表"""
        return [
            {"code": code, **info}
            for code, info in TEMPLATE_CATEGORIES.items()
        ]

    async def get_available_variables(self) -> List[Dict[str, Any]]:
        """获取可用变量列表"""
        return [
            {"name": name, **info}
            for name, info in AVAILABLE_VARIABLES.items()
        ]

    async def get_supported_languages(self) -> List[Dict[str, str]]:
        """获取支持的翻译语言列表"""
        return [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ]

    async def get_templates(
        self,
        account_id: int,
        category: Optional[str] = None,
        include_shared: bool = True,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        获取模板列表

        Args:
            account_id: 当前用户账户ID
            category: 分类筛选
            include_shared: 是否包含共享模板
            search: 搜索关键词
            page: 页码
            page_size: 每页数量

        Returns:
            分页的模板列表
        """
        # 构建查询条件
        conditions = []

        if include_shared:
            # 我的模板 + 共享模板
            conditions.append(
                or_(
                    EmailTemplate.account_id == account_id,
                    EmailTemplate.is_shared == True
                )
            )
        else:
            # 仅我的模板
            conditions.append(EmailTemplate.account_id == account_id)

        if category:
            conditions.append(EmailTemplate.category == category)

        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    EmailTemplate.name.like(search_pattern),
                    EmailTemplate.description.like(search_pattern),
                    EmailTemplate.subject_cn.like(search_pattern),
                    EmailTemplate.body_cn.like(search_pattern)
                )
            )

        # 查询总数
        count_query = select(func.count(EmailTemplate.id)).where(and_(*conditions))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # 查询模板列表
        query = (
            select(EmailTemplate)
            .where(and_(*conditions))
            .options(selectinload(EmailTemplate.translations))
            .options(selectinload(EmailTemplate.account))
            .order_by(EmailTemplate.use_count.desc(), EmailTemplate.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(query)
        templates = result.scalars().all()

        return {
            "items": [self._template_to_dict(t, account_id) for t in templates],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size
        }

    async def get_template(self, template_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单个模板详情

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID

        Returns:
            模板详情，包含所有翻译版本
        """
        query = (
            select(EmailTemplate)
            .where(
                and_(
                    EmailTemplate.id == template_id,
                    or_(
                        EmailTemplate.account_id == account_id,
                        EmailTemplate.is_shared == True
                    )
                )
            )
            .options(selectinload(EmailTemplate.translations))
            .options(selectinload(EmailTemplate.account))
        )

        result = await self.db.execute(query)
        template = result.scalar_one_or_none()

        if not template:
            return None

        return self._template_to_dict(template, account_id, include_translations=True)

    async def create_template(
        self,
        account_id: int,
        name: str,
        body_cn: str,
        subject_cn: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        variables: Optional[List[str]] = None,
        is_shared: bool = False
    ) -> Dict[str, Any]:
        """
        创建模板

        Args:
            account_id: 创建者账户ID
            name: 模板名称
            body_cn: 中文正文
            subject_cn: 中文主题
            description: 模板描述
            category: 分类
            variables: 使用的变量列表
            is_shared: 是否共享

        Returns:
            创建的模板
        """
        # 自动检测变量
        if variables is None:
            variables = self._detect_variables(body_cn, subject_cn)

        template = EmailTemplate(
            account_id=account_id,
            name=name,
            body_cn=body_cn,
            subject_cn=subject_cn,
            description=description,
            category=category,
            variables=variables,
            is_shared=is_shared
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Created template '{name}' (id={template.id}) by account {account_id}")

        return self._template_to_dict(template, account_id)

    async def update_template(
        self,
        template_id: int,
        account_id: int,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        更新模板

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID（必须是模板所有者）
            **kwargs: 要更新的字段

        Returns:
            更新后的模板，如果无权限或不存在则返回None
        """
        query = (
            select(EmailTemplate)
            .where(
                and_(
                    EmailTemplate.id == template_id,
                    EmailTemplate.account_id == account_id  # 只能修改自己的模板
                )
            )
            .options(selectinload(EmailTemplate.translations))
        )

        result = await self.db.execute(query)
        template = result.scalar_one_or_none()

        if not template:
            return None

        # 更新字段
        allowed_fields = ['name', 'body_cn', 'subject_cn', 'description', 'category', 'variables', 'is_shared']
        for field in allowed_fields:
            if field in kwargs and kwargs[field] is not None:
                setattr(template, field, kwargs[field])

        # 如果更新了正文或主题，重新检测变量
        if 'body_cn' in kwargs or 'subject_cn' in kwargs:
            template.variables = self._detect_variables(
                template.body_cn,
                template.subject_cn
            )

        template.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Updated template {template_id}")

        return self._template_to_dict(template, account_id, include_translations=True)

    async def delete_template(self, template_id: int, account_id: int) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID

        Returns:
            是否删除成功
        """
        query = (
            select(EmailTemplate)
            .where(
                and_(
                    EmailTemplate.id == template_id,
                    EmailTemplate.account_id == account_id  # 只能删除自己的模板
                )
            )
        )

        result = await self.db.execute(query)
        template = result.scalar_one_or_none()

        if not template:
            return False

        await self.db.delete(template)
        await self.db.commit()

        logger.info(f"Deleted template {template_id}")

        return True

    async def translate_template(
        self,
        template_id: int,
        account_id: int,
        target_lang: str,
        force_retranslate: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        翻译模板为指定语言

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID
            target_lang: 目标语言代码
            force_retranslate: 是否强制重新翻译

        Returns:
            翻译结果，包含翻译后的主题和正文
        """
        if target_lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {target_lang}")

        # 获取模板
        query = (
            select(EmailTemplate)
            .where(
                and_(
                    EmailTemplate.id == template_id,
                    or_(
                        EmailTemplate.account_id == account_id,
                        EmailTemplate.is_shared == True
                    )
                )
            )
            .options(selectinload(EmailTemplate.translations))
        )

        result = await self.db.execute(query)
        template = result.scalar_one_or_none()

        if not template:
            return None

        # 检查是否已有翻译
        existing_translation = None
        for t in template.translations:
            if t.target_lang == target_lang:
                existing_translation = t
                break

        if existing_translation and not force_retranslate:
            return {
                "template_id": template_id,
                "target_lang": target_lang,
                "subject_translated": existing_translation.subject_translated,
                "body_translated": existing_translation.body_translated,
                "translated_at": existing_translation.translated_at.isoformat(),
                "cached": True
            }

        # 执行翻译
        logger.info(f"Translating template {template_id} to {target_lang}")

        # 翻译主题
        subject_translated = None
        if template.subject_cn:
            subject_result = await self.translate_service.translate_text(
                text=template.subject_cn,
                target_lang=target_lang,
                source_lang="zh"
            )
            subject_translated = subject_result.get("translated_text", template.subject_cn)

        # 翻译正文
        body_result = await self.translate_service.translate_text(
            text=template.body_cn,
            target_lang=target_lang,
            source_lang="zh"
        )
        body_translated = body_result.get("translated_text", template.body_cn)

        # 保存或更新翻译
        if existing_translation:
            existing_translation.subject_translated = subject_translated
            existing_translation.body_translated = body_translated
            existing_translation.translated_at = datetime.utcnow()
        else:
            new_translation = EmailTemplateTranslation(
                template_id=template_id,
                target_lang=target_lang,
                subject_translated=subject_translated,
                body_translated=body_translated
            )
            self.db.add(new_translation)

        await self.db.commit()

        logger.info(f"Template {template_id} translated to {target_lang}")

        return {
            "template_id": template_id,
            "target_lang": target_lang,
            "subject_translated": subject_translated,
            "body_translated": body_translated,
            "translated_at": datetime.utcnow().isoformat(),
            "cached": False
        }

    async def share_template(self, template_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """
        共享模板

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID

        Returns:
            更新后的模板
        """
        return await self.update_template(template_id, account_id, is_shared=True)

    async def unshare_template(self, template_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """
        取消共享模板

        Args:
            template_id: 模板ID
            account_id: 当前用户账户ID

        Returns:
            更新后的模板
        """
        return await self.update_template(template_id, account_id, is_shared=False)

    async def increment_use_count(self, template_id: int) -> None:
        """增加模板使用次数"""
        query = select(EmailTemplate).where(EmailTemplate.id == template_id)
        result = await self.db.execute(query)
        template = result.scalar_one_or_none()

        if template:
            template.use_count += 1
            await self.db.commit()

    def replace_variables(
        self,
        text: str,
        variables: Dict[str, str]
    ) -> str:
        """
        替换文本中的变量占位符

        Args:
            text: 原始文本
            variables: 变量名到值的映射

        Returns:
            替换后的文本
        """
        if not text:
            return text

        result = text
        for var_name, var_value in variables.items():
            placeholder = "{" + var_name + "}"
            result = result.replace(placeholder, str(var_value))

        return result

    def _detect_variables(self, body: str, subject: Optional[str] = None) -> List[str]:
        """检测文本中使用的变量"""
        text = (body or "") + " " + (subject or "")
        pattern = r'\{(\w+)\}'
        matches = re.findall(pattern, text)
        # 只返回已定义的变量
        return [m for m in set(matches) if m in AVAILABLE_VARIABLES]

    def _template_to_dict(
        self,
        template: EmailTemplate,
        current_account_id: int,
        include_translations: bool = False
    ) -> Dict[str, Any]:
        """将模板对象转换为字典"""
        data = {
            "id": template.id,
            "account_id": template.account_id,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "category_name": TEMPLATE_CATEGORIES.get(template.category, {}).get("name_cn"),
            "subject_cn": template.subject_cn,
            "body_cn": template.body_cn,
            "variables": template.variables or [],
            "is_shared": template.is_shared,
            "is_mine": template.account_id == current_account_id,
            "use_count": template.use_count,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        }

        # 添加创建者信息
        if template.account:
            data["author"] = {
                "id": template.account.id,
                "email": template.account.email
            }

        # 添加翻译版本
        if include_translations and template.translations:
            data["translations"] = [
                {
                    "id": t.id,
                    "target_lang": t.target_lang,
                    "target_lang_name": SUPPORTED_LANGUAGES.get(t.target_lang, t.target_lang),
                    "subject_translated": t.subject_translated,
                    "body_translated": t.body_translated,
                    "translated_at": t.translated_at.isoformat() if t.translated_at else None
                }
                for t in template.translations
            ]
        else:
            # 只返回已有翻译的语言列表
            data["translated_langs"] = [t.target_lang for t in template.translations] if template.translations else []

        return data
