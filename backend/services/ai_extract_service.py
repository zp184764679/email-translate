"""
AI 邮件信息提取服务
使用 Ollama 本地模型提取邮件中的关键信息

改进功能：
- 智能文本截断（保留重要部分）
- 金额格式标准化
- 详细错误信息
"""

import json
import re
import httpx
from typing import Optional, Dict, Any, List
from config import get_settings

settings = get_settings()

# 提取状态
EXTRACTION_STATUS_SUCCESS = "success"
EXTRACTION_STATUS_TIMEOUT = "timeout"
EXTRACTION_STATUS_ERROR = "error"
EXTRACTION_STATUS_EMPTY = "empty"

# 货币符号映射
CURRENCY_SYMBOLS = {
    "$": "USD",
    "¥": "CNY",
    "€": "EUR",
    "£": "GBP",
    "₩": "KRW",
    "₹": "INR",
}

# 已知货币代码
KNOWN_CURRENCIES = {
    "USD", "CNY", "EUR", "GBP", "JPY", "KRW", "HKD", "SGD", "AUD", "CAD",
    "CHF", "INR", "RUB", "BRL", "MXN", "TWD", "THB", "MYR", "VND", "PHP",
}


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


def smart_truncate(text: str, max_length: int, preserve_end_ratio: float = 0.2) -> str:
    """
    智能截断文本，保留开头和结尾的重要内容

    Args:
        text: 原始文本
        max_length: 最大长度
        preserve_end_ratio: 保留结尾的比例（0.2 = 20%）

    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_length:
        return text or ""

    # 计算保留的头尾长度
    end_length = int(max_length * preserve_end_ratio)
    start_length = max_length - end_length - 50  # 留出 50 字符给分隔符

    # 提取头部和尾部
    start_part = text[:start_length]
    end_part = text[-end_length:] if end_length > 0 else ""

    # 组合
    if end_part:
        return f"{start_part}\n\n[...内容已截断，保留结尾...]\n\n{end_part}"
    return start_part


async def extract_email_info(
    subject: str,
    body: str,
    body_translated: Optional[str] = None
) -> Dict[str, Any]:
    """
    使用 Ollama 提取邮件中的关键信息

    优先使用翻译后的内容（如果有），因为中文更容易理解

    Returns:
        Dict 包含:
        - status: 提取状态 (success/timeout/error/empty)
        - error_message: 错误信息（如果有）
        - 其他提取字段...
    """
    # 长度限制常量（增大限制，配合智能截断）
    MAX_SUBJECT_LENGTH = 500
    MAX_BODY_LENGTH = 8000  # 增大到 8000，通过智能截断保留重要内容

    # 优先使用翻译后的内容
    content_to_analyze = (body_translated if body_translated else body) or ""
    subject_to_analyze = (subject or "")[:MAX_SUBJECT_LENGTH]

    # 如果内容为空
    if not content_to_analyze.strip() and not subject_to_analyze.strip():
        result = get_empty_extraction()
        result["status"] = EXTRACTION_STATUS_EMPTY
        result["error_message"] = "邮件内容为空"
        return result

    # 清理输入，防止提示注入
    subject_to_analyze = sanitize_for_prompt(subject_to_analyze)
    content_to_analyze = sanitize_for_prompt(
        smart_truncate(content_to_analyze, MAX_BODY_LENGTH)
    )

    # 构建提示
    prompt = EXTRACT_PROMPT.format(
        subject=subject_to_analyze,
        body=content_to_analyze
    )

    try:
        # 调用 Ollama API（增加超时时间）
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # 低温度，更确定性的输出
                        "num_predict": 2500  # 增加输出长度
                    }
                }
            )

            if response.status_code != 200:
                error_msg = f"Ollama API 返回错误 (HTTP {response.status_code})"
                print(f"[AIExtract] {error_msg}")
                result = get_empty_extraction()
                result["status"] = EXTRACTION_STATUS_ERROR
                result["error_message"] = error_msg
                return result

            result = response.json()
            response_text = result.get("response", "")

            # 尝试解析 JSON
            extraction = parse_extraction_response(response_text)
            extraction["status"] = EXTRACTION_STATUS_SUCCESS
            extraction["error_message"] = None

            # 标准化金额格式
            extraction["amounts"] = normalize_amounts(extraction.get("amounts", []))

            return extraction

    except httpx.TimeoutException:
        error_msg = "AI 提取超时，邮件内容可能过长，请稍后重试"
        print(f"[AIExtract] {error_msg}")
        result = get_empty_extraction()
        result["status"] = EXTRACTION_STATUS_TIMEOUT
        result["error_message"] = error_msg
        return result

    except httpx.ConnectError:
        error_msg = "无法连接到 AI 服务，请检查 Ollama 是否启动"
        print(f"[AIExtract] {error_msg}")
        result = get_empty_extraction()
        result["status"] = EXTRACTION_STATUS_ERROR
        result["error_message"] = error_msg
        return result

    except Exception as e:
        error_msg = f"AI 提取出错: {str(e)}"
        print(f"[AIExtract] {error_msg}")
        result = get_empty_extraction()
        result["status"] = EXTRACTION_STATUS_ERROR
        result["error_message"] = error_msg
        return result


def normalize_amounts(amounts: List[Dict]) -> List[Dict]:
    """
    标准化金额格式

    - 统一货币代码
    - 移除金额中的非数字字符
    - 验证货币代码有效性
    """
    normalized = []

    for item in amounts:
        if not isinstance(item, dict):
            continue

        amount = item.get("amount")
        currency = item.get("currency", "")
        context = item.get("context", "")

        # 处理金额
        if isinstance(amount, str):
            # 移除货币符号和千位分隔符
            clean_amount = re.sub(r'[^\d.\-]', '', amount)
            try:
                amount = float(clean_amount) if clean_amount else 0
            except ValueError:
                amount = 0

        # 标准化货币
        if currency:
            currency_upper = currency.upper().strip()

            # 检查是否是货币符号
            for symbol, code in CURRENCY_SYMBOLS.items():
                if symbol in currency:
                    currency_upper = code
                    break

            # 如果不是已知货币，尝试从上下文推断
            if currency_upper not in KNOWN_CURRENCIES:
                # 常见中文货币表述
                if "人民币" in context or "元" in currency.lower():
                    currency_upper = "CNY"
                elif "美元" in context or "美金" in context:
                    currency_upper = "USD"
                elif "欧元" in context:
                    currency_upper = "EUR"
                else:
                    # 保留原值，但标记为未知
                    currency_upper = currency_upper or "UNKNOWN"

            currency = currency_upper

        normalized.append({
            "amount": amount,
            "currency": currency,
            "context": context
        })

    return normalized


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
        "key_points": [],
        "status": EXTRACTION_STATUS_EMPTY,
        "error_message": None
    }
