"""
邮件分类服务

使用 vLLM 自动分类邮件类型：
- inquiry: 询价/询问
- order: 订单确认/订单相关
- logistics: 物流/发货通知
- payment: 付款/发票相关
- quality: 质量问题/投诉
- urgent: 紧急事项
- quotation: 报价单
- technical: 技术支持/技术问题
- other: 其他
"""
import os
import httpx
import json
from datetime import datetime
from typing import Optional, Tuple, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Email


# vLLM 配置
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:5080")
VLLM_MODEL = os.getenv("VLLM_MODEL", "/home/aaa/models/Qwen3-VL-8B-Instruct")

# 分类定义
EMAIL_CATEGORIES = {
    "inquiry": "询价/询问 - 客户询问产品信息、价格、供货能力等",
    "order": "订单相关 - 订单确认、订单修改、订单取消等",
    "logistics": "物流通知 - 发货通知、物流跟踪、到货确认等",
    "payment": "付款相关 - 付款确认、发票请求、账单问题等",
    "quality": "质量问题 - 质量投诉、退货申请、产品问题等",
    "urgent": "紧急事项 - 需要立即处理的紧急问题",
    "quotation": "报价单 - 正式报价、价格确认等",
    "technical": "技术支持 - 技术问题咨询、规格确认、图纸讨论等",
    "other": "其他 - 不属于以上类别的邮件"
}

CLASSIFICATION_PROMPT = """请分析这封邮件的内容，将其分类到以下类别之一：

可用类别:
- inquiry: 询价/询问 - 客户询问产品信息、价格、供货能力等
- order: 订单相关 - 订单确认、订单修改、订单取消等
- logistics: 物流通知 - 发货通知、物流跟踪、到货确认等
- payment: 付款相关 - 付款确认、发票请求、账单问题等
- quality: 质量问题 - 质量投诉、退货申请、产品问题等
- urgent: 紧急事项 - 需要立即处理的紧急问题（如生产线停止等）
- quotation: 报价单 - 正式报价、价格确认等
- technical: 技术支持 - 技术问题咨询、规格确认、图纸讨论等
- other: 其他 - 不属于以上类别的邮件

邮件主题: {subject}
邮件正文:
{body}

请以JSON格式返回分类结果:
{{"category": "类别代码", "confidence": 0.0-1.0之间的置信度, "reason": "简短的分类理由"}}

只返回JSON，不要其他内容。"""


class EmailClassifierService:
    """邮件分类服务"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()

    async def classify_email(
        self,
        subject: str,
        body: str
    ) -> Tuple[str, float, str]:
        """
        使用 vLLM 分类邮件

        Args:
            subject: 邮件主题
            body: 邮件正文

        Returns:
            Tuple[category, confidence, reason]
        """
        # 截取正文前2000字符（避免token超限）
        body_truncated = body[:2000] if body else ""

        prompt = CLASSIFICATION_PROMPT.format(
            subject=subject or "(无主题)",
            body=body_truncated or "(无正文)"
        )

        try:
            response = await self.client.post(
                f"{VLLM_BASE_URL}/v1/chat/completions",
                json={
                    "model": VLLM_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.1  # 低温度保证稳定性
                }
            )
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"].strip()

            # 解析JSON响应
            # 清理可能的markdown包装
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            parsed = json.loads(content)
            category = parsed.get("category", "other")
            confidence = float(parsed.get("confidence", 0.5))
            reason = parsed.get("reason", "")

            # 验证类别有效性
            if category not in EMAIL_CATEGORIES:
                category = "other"
                confidence = 0.3

            return category, confidence, reason

        except json.JSONDecodeError as e:
            print(f"[Classifier] JSON解析失败: {e}, 内容: {content[:200]}")
            return "other", 0.3, "分类响应格式错误"
        except Exception as e:
            print(f"[Classifier] 分类失败: {e}")
            return "other", 0.1, str(e)

    async def classify_and_save(
        self,
        db: AsyncSession,
        email_id: int,
        force: bool = False
    ) -> Optional[dict]:
        """
        分类邮件并保存结果

        Args:
            db: 数据库会话
            email_id: 邮件ID
            force: 是否强制重新分类

        Returns:
            分类结果字典
        """
        # 获取邮件
        result = await db.execute(
            select(Email).where(Email.id == email_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            return None

        # 已分类且不强制重新分类
        if email.ai_category and not force:
            return {
                "id": email.id,
                "category": email.ai_category,
                "confidence": email.ai_category_confidence,
                "categorized_at": email.ai_categorized_at
            }

        # 使用翻译后的内容（如果有）
        subject = email.subject_translated or email.subject_original or ""
        body = email.body_translated or email.body_original or ""

        # 分类
        category, confidence, reason = await self.classify_email(subject, body)

        # 保存结果
        email.ai_category = category
        email.ai_category_confidence = confidence
        email.ai_categorized_at = datetime.utcnow()

        await db.commit()

        return {
            "id": email.id,
            "category": category,
            "confidence": confidence,
            "reason": reason,
            "categorized_at": email.ai_categorized_at
        }

    async def batch_classify(
        self,
        db: AsyncSession,
        email_ids: List[int],
        force: bool = False
    ) -> dict:
        """
        批量分类邮件

        Args:
            db: 数据库会话
            email_ids: 邮件ID列表
            force: 是否强制重新分类

        Returns:
            分类统计
        """
        results = {
            "total": len(email_ids),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "categories": {}
        }

        for email_id in email_ids:
            try:
                result = await self.classify_and_save(db, email_id, force)
                if result:
                    if result.get("category"):
                        results["success"] += 1
                        cat = result["category"]
                        results["categories"][cat] = results["categories"].get(cat, 0) + 1
                    else:
                        results["skipped"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                print(f"[Classifier] 批量分类失败 email_id={email_id}: {e}")
                results["failed"] += 1

        return results


# 全局实例
classifier_service = EmailClassifierService()


async def get_classifier_service():
    return classifier_service
