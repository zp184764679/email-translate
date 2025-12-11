"""
AI 邮件信息提取服务
使用 Ollama 本地模型提取邮件中的关键信息
"""

import json
import httpx
from typing import Optional, Dict, Any
from config import get_settings

settings = get_settings()


EXTRACT_PROMPT = """分析以下邮件内容，提取关键信息。请以 JSON 格式返回，包含以下字段：

1. summary: 邮件内容的简短摘要（1-2句话）
2. dates: 提取的日期时间列表，每个包含 {{"date": "YYYY-MM-DD", "time": "HH:MM"或null, "context": "上下文说明", "is_meeting": true/false}}
   - 重要：如果提到具体时间（如"下午3点"、"15:00"），必须填写 time 字段
   - is_meeting: 如果是会议/电话会议/视频会议，设为 true
3. amounts: 提取的金额列表，每个包含 {{"amount": 数字, "currency": "货币", "context": "上下文说明"}}
4. contacts: 提取的联系人，每个包含 {{"name": "姓名", "email": "邮箱", "phone": "电话", "role": "角色"}}
5. action_items: 待办事项列表，每个包含 {{"task": "任务描述", "priority": "high/medium/low", "deadline": "截止日期或null"}}
6. key_points: 关键信息点列表（字符串数组）

如果某个字段没有相关信息，返回空数组 []。

邮件主题：{subject}

邮件正文：
{body}

请直接返回 JSON，不要添加任何解释或 markdown 标记。"""


def sanitize_for_prompt(text: str) -> str:
    """
    清理文本，防止提示注入攻击
    移除可能干扰 AI 解析的特殊模式
    """
    if not text:
        return ""
    # 移除可能的提示注入模式
    dangerous_patterns = [
        "```",          # 代码块标记
        "---",          # 分隔符
        "===",          # 分隔符
        "忽略上面",      # 常见注入
        "ignore above", # 常见注入
        "new instruction", # 注入尝试
    ]
    result = text
    for pattern in dangerous_patterns:
        result = result.replace(pattern, " ")
    return result.strip()


async def extract_email_info(
    subject: str,
    body: str,
    body_translated: Optional[str] = None
) -> Dict[str, Any]:
    """
    使用 Ollama 提取邮件中的关键信息

    优先使用翻译后的内容（如果有），因为中文更容易理解
    """
    # 长度限制常量
    MAX_SUBJECT_LENGTH = 500
    MAX_BODY_LENGTH = 4000

    # 优先使用翻译后的内容，并应用长度限制
    content_to_analyze = (body_translated if body_translated else body) or ""
    subject_to_analyze = (subject or "")[:MAX_SUBJECT_LENGTH]

    # 清理输入，防止提示注入
    subject_to_analyze = sanitize_for_prompt(subject_to_analyze)
    content_to_analyze = sanitize_for_prompt(content_to_analyze[:MAX_BODY_LENGTH])

    # 构建提示
    prompt = EXTRACT_PROMPT.format(
        subject=subject_to_analyze,
        body=content_to_analyze
    )

    try:
        # 调用 Ollama API
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # 低温度，更确定性的输出
                        "num_predict": 2000
                    }
                }
            )

            if response.status_code != 200:
                print(f"[AIExtract] Ollama API error: {response.status_code}")
                return get_empty_extraction()

            result = response.json()
            response_text = result.get("response", "")

            # 尝试解析 JSON
            extraction = parse_extraction_response(response_text)
            return extraction

    except httpx.TimeoutException:
        print("[AIExtract] Ollama request timeout")
        return get_empty_extraction()
    except Exception as e:
        print(f"[AIExtract] Error: {e}")
        return get_empty_extraction()


def parse_extraction_response(response_text: str) -> Dict[str, Any]:
    """解析 AI 返回的 JSON 响应"""
    # 清理响应文本
    text = response_text.strip()

    # 尝试找到 JSON 块
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    try:
        data = json.loads(text)

        # 验证并规范化数据结构
        return {
            "summary": data.get("summary", ""),
            "dates": validate_list(data.get("dates", [])),
            "amounts": validate_list(data.get("amounts", [])),
            "contacts": validate_list(data.get("contacts", [])),
            "action_items": validate_list(data.get("action_items", [])),
            "key_points": validate_list(data.get("key_points", []))
        }
    except json.JSONDecodeError as e:
        print(f"[AIExtract] JSON parse error: {e}")
        print(f"[AIExtract] Response text: {text[:500]}")
        return get_empty_extraction()


def validate_list(value) -> list:
    """确保值是列表"""
    if isinstance(value, list):
        return value
    return []


def get_empty_extraction() -> Dict[str, Any]:
    """返回空的提取结果"""
    return {
        "summary": "",
        "dates": [],
        "amounts": [],
        "contacts": [],
        "action_items": [],
        "key_points": []
    }
