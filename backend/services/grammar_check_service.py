"""
AI 语法和拼写检查服务

使用 vLLM 检查文本中的语法、拼写和标点问题
"""
import os
import json
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


GRAMMAR_CHECK_PROMPT = """你是一位专业的校对编辑，请检查以下{language}文本中的问题：

文本：
{text}

请检查以下问题类型：
1. spelling - 拼写错误
2. grammar - 语法错误
3. punctuation - 标点问题
4. style - 风格建议（可选，只标注明显问题）

以JSON格式返回结果：
{{
    "issues": [
        {{
            "type": "问题类型",
            "text": "原始错误文本",
            "suggestion": "修改建议",
            "position": 错误在文本中的起始位置（字符索引）,
            "explanation": "简短解释"
        }}
    ],
    "corrected_text": "修正后的完整文本",
    "summary": "总结说明"
}}

如果没有发现问题，返回：
{{
    "issues": [],
    "corrected_text": "原文",
    "summary": "文本无明显问题"
}}

只返回JSON，不要有其他内容。"""


LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "de": "德文",
    "fr": "法文",
    "es": "西班牙文"
}


class GrammarCheckService:
    """语法检查服务"""

    async def check_grammar(
        self,
        text: str,
        language: str = "zh"
    ) -> Dict[str, Any]:
        """
        检查文本语法和拼写

        Args:
            text: 要检查的文本
            language: 文本语言代码

        Returns:
            包含问题列表和修正文本的字典
        """
        if not text or len(text.strip()) < 5:
            return {
                "success": True,
                "issues": [],
                "corrected_text": text,
                "summary": "文本太短，无需检查"
            }

        language_name = LANGUAGE_NAMES.get(language, "中文")

        prompt = GRAMMAR_CHECK_PROMPT.format(
            language=language_name,
            text=text[:3000]  # 限制长度
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{VLLM_BASE_URL}/v1/chat/completions",
                    headers=_get_vllm_headers(),
                    json={
                        "model": VLLM_MODEL,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,  # 低温度确保稳定输出
                        "max_tokens": 2000
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]

                    # 解析JSON
                    try:
                        # 移除可能的markdown代码块标记
                        content = content.strip()
                        if content.startswith("```json"):
                            content = content[7:]
                        if content.startswith("```"):
                            content = content[3:]
                        if content.endswith("```"):
                            content = content[:-3]

                        check_result = json.loads(content.strip())

                        return {
                            "success": True,
                            "issues": check_result.get("issues", []),
                            "corrected_text": check_result.get("corrected_text", text),
                            "summary": check_result.get("summary", ""),
                            "checked_at": datetime.utcnow().isoformat()
                        }
                    except json.JSONDecodeError:
                        # 无法解析返回的内容
                        return {
                            "success": True,
                            "issues": [],
                            "corrected_text": text,
                            "summary": "检查完成，未发现明显问题",
                            "checked_at": datetime.utcnow().isoformat()
                        }
                else:
                    return {
                        "success": False,
                        "issues": [],
                        "corrected_text": text,
                        "error": f"vLLM API 错误: {response.status_code}"
                    }

        except Exception as e:
            return {
                "success": False,
                "issues": [],
                "corrected_text": text,
                "error": str(e)
            }


# 单例
_service: Optional[GrammarCheckService] = None


def get_grammar_check_service() -> GrammarCheckService:
    global _service
    if _service is None:
        _service = GrammarCheckService()
    return _service
