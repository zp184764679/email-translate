"""
AI 邮件回复建议服务

基于邮件内容和 AI 提取的信息，生成回复建议框架
"""
import os
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:5080")
VLLM_MODEL = os.getenv("VLLM_MODEL", "/home/aaa/models/Qwen3-VL-8B-Instruct")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")

def _get_vllm_headers():
    """获取 vLLM 请求头（包含认证）"""
    headers = {"Content-Type": "application/json"}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
    return headers


# 回复模板类型
REPLY_TEMPLATES = {
    "inquiry": {
        "name": "询价回复",
        "description": "回复供应商的询价请求",
        "context": "供应商发来询价邮件，询问产品价格、交期或规格"
    },
    "order_confirm": {
        "name": "订单确认",
        "description": "确认收到订单或订单变更",
        "context": "收到供应商的订单确认邮件，需要回复确认"
    },
    "logistics": {
        "name": "物流跟进",
        "description": "询问或确认物流信息",
        "context": "需要跟进货物运输状态或确认收货"
    },
    "quality": {
        "name": "质量反馈",
        "description": "反馈产品质量问题",
        "context": "发现产品质量问题，需要向供应商反馈"
    },
    "payment": {
        "name": "付款相关",
        "description": "确认付款或询问付款信息",
        "context": "涉及付款确认、发票请求或付款安排"
    },
    "general": {
        "name": "通用回复",
        "description": "一般业务沟通",
        "context": "日常业务沟通和信息交换"
    }
}


SUGGESTION_PROMPT = """你是一位专业的采购专员，需要帮助撰写邮件回复。

原始邮件信息：
发件人：{sender}
主题：{subject}
内容摘要：{body_summary}

{extraction_info}

回复场景：{reply_context}

请生成3个不同风格的中文回复建议：
1. 正式风格：适合正式商务场合，语气专业严谨
2. 友好风格：适合长期合作伙伴，语气温和亲切
3. 简洁风格：简短明了，适合快速回复

每个回复建议应该：
- 开头有适当的称呼
- 明确回应邮件中的主要问题
- 包含必要的信息确认
- 结尾有礼貌的结束语

请以JSON格式返回，格式如下：
{{
    "suggestions": [
        {{
            "style": "正式",
            "subject": "回复主题",
            "body": "回复正文内容..."
        }},
        {{
            "style": "友好",
            "subject": "回复主题",
            "body": "回复正文内容..."
        }},
        {{
            "style": "简洁",
            "subject": "回复主题",
            "body": "回复正文内容..."
        }}
    ],
    "key_points": ["需要回复的要点1", "要点2", ...]
}}

只返回JSON，不要有其他内容。"""


class ReplySuggestionService:
    """回复建议生成服务"""

    async def generate_suggestions(
        self,
        subject: str,
        body: str,
        sender: str,
        extraction: Optional[Dict[str, Any]] = None,
        reply_type: str = "general"
    ) -> Dict[str, Any]:
        """
        生成回复建议

        Args:
            subject: 邮件主题
            body: 邮件正文
            sender: 发件人
            extraction: AI 提取的信息（可选）
            reply_type: 回复类型（inquiry/order_confirm/logistics/quality/payment/general）

        Returns:
            包含回复建议的字典
        """
        # 获取回复模板上下文
        template = REPLY_TEMPLATES.get(reply_type, REPLY_TEMPLATES["general"])

        # 截取正文摘要
        body_summary = body[:1000] if len(body) > 1000 else body

        # 构建提取信息描述
        extraction_info = ""
        if extraction:
            info_parts = []
            if extraction.get("summary"):
                info_parts.append(f"邮件摘要：{extraction['summary']}")
            if extraction.get("key_dates"):
                dates = [f"{d.get('description', '')}: {d.get('date', '')}" for d in extraction['key_dates'][:3]]
                info_parts.append(f"重要日期：{', '.join(dates)}")
            if extraction.get("amounts"):
                amounts = [f"{a.get('description', '')}: {a.get('amount', '')}" for a in extraction['amounts'][:3]]
                info_parts.append(f"金额信息：{', '.join(amounts)}")
            if extraction.get("action_items"):
                items = [item.get('description', '') for item in extraction['action_items'][:3]]
                info_parts.append(f"待办事项：{', '.join(items)}")

            if info_parts:
                extraction_info = "AI 提取的关键信息：\n" + "\n".join(info_parts)

        # 构建提示
        prompt = SUGGESTION_PROMPT.format(
            sender=sender,
            subject=subject,
            body_summary=body_summary,
            extraction_info=extraction_info or "（无额外提取信息）",
            reply_context=template["context"]
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{VLLM_BASE_URL}/v1/chat/completions",
                    headers=_get_vllm_headers(),
                    json={
                        "model": VLLM_MODEL,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]

                    # 解析JSON
                    import json
                    # 尝试从内容中提取JSON
                    try:
                        # 移除可能的markdown代码块标记
                        content = content.strip()
                        if content.startswith("```json"):
                            content = content[7:]
                        if content.startswith("```"):
                            content = content[3:]
                        if content.endswith("```"):
                            content = content[:-3]

                        suggestions = json.loads(content.strip())
                        return {
                            "success": True,
                            "reply_type": reply_type,
                            "reply_type_name": template["name"],
                            "suggestions": suggestions.get("suggestions", []),
                            "key_points": suggestions.get("key_points", []),
                            "generated_at": datetime.utcnow().isoformat()
                        }
                    except json.JSONDecodeError:
                        # 如果无法解析JSON，返回原始内容作为单个建议
                        return {
                            "success": True,
                            "reply_type": reply_type,
                            "reply_type_name": template["name"],
                            "suggestions": [{
                                "style": "AI生成",
                                "subject": f"Re: {subject}",
                                "body": content
                            }],
                            "key_points": [],
                            "generated_at": datetime.utcnow().isoformat()
                        }
                else:
                    return {
                        "success": False,
                        "error": f"vLLM API 错误: {response.status_code}",
                        "generated_at": datetime.utcnow().isoformat()
                    }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "generated_at": datetime.utcnow().isoformat()
            }

    def get_reply_templates(self) -> List[Dict[str, str]]:
        """获取所有回复模板类型"""
        return [
            {"id": key, **value}
            for key, value in REPLY_TEMPLATES.items()
        ]


# 单例
_service: Optional[ReplySuggestionService] = None


def get_reply_suggestion_service() -> ReplySuggestionService:
    global _service
    if _service is None:
        _service = ReplySuggestionService()
    return _service
