"""
邮件引用解析服务

将邮件正文按回复层级拆分，分离出各层引用内容。
用于前端分层显示邮件内容。
"""
import re
from typing import List, Dict, Optional, Tuple


# 引用标记模式（从 translate_service.py 复用）
QUOTE_PATTERNS = [
    # Gmail: "On Mon, Nov 26, 2025 at 11:26 PM xxx wrote:"
    (r'(On .{10,100} wrote:)\s*\n', 'gmail'),
    # Outlook: "-----Original Message-----"
    (r'(-{3,}Original Message-{3,})\n', 'outlook'),
    # Outlook 完整引用头
    (r'(From: .+\n(?:Sent|Date): .+\n(?:To: .+\n)?(?:Subject: .+\n)?)', 'outlook_full'),
    # 中文客户端
    (r'(\*?发件人[：:].+\n(?:\*?(?:发送时间|日期)[：:].+\n)?)', 'chinese'),
    # 日文引用标记
    (r'(-{3,}元のメッセージ-{3,})\n', 'japanese'),
    # 韩文引用标记
    (r'(-{3,}원래 메시지-{3,})\n', 'korean'),
]

# 连续 > 引用符号模式
INLINE_QUOTE_PATTERN = r'^(>+\s?)'


def parse_email_quotes(
    body_original: str,
    body_translated: str = None
) -> List[Dict]:
    """
    解析邮件正文，分离出各层引用

    Args:
        body_original: 邮件原文
        body_translated: 邮件翻译（可选）

    Returns:
        分层引用列表，每项包含:
        - type: "latest" 或 "quote"
        - original: 原文内容
        - translated: 翻译内容（如有）
        - header: 引用头信息（如 "On xxx wrote:"）
        - depth: 嵌套深度（0 = 最新内容）
    """
    if not body_original:
        return []

    # 统一换行符
    body_original = body_original.replace('\r\n', '\n').replace('\r', '\n')
    if body_translated:
        body_translated = body_translated.replace('\r\n', '\n').replace('\r', '\n')

    # 查找所有引用标记的位置
    quote_markers = _find_quote_markers(body_original)

    if not quote_markers:
        # 没有引用，整个正文作为最新内容
        return [{
            "type": "latest",
            "original": body_original.strip(),
            "translated": body_translated.strip() if body_translated else None,
            "header": None,
            "depth": 0
        }]

    # 按位置排序
    quote_markers.sort(key=lambda x: x['position'])

    # 分割内容
    parts = []
    last_pos = 0

    for i, marker in enumerate(quote_markers):
        pos = marker['position']
        header = marker['header']

        # 提取引用标记之前的内容
        content = body_original[last_pos:pos].strip()

        if content:
            part_type = "latest" if i == 0 else "quote"
            depth = i

            # 尝试匹配翻译内容
            translated_content = _extract_corresponding_translation(
                content, body_translated, depth
            ) if body_translated else None

            parts.append({
                "type": part_type,
                "original": content,
                "translated": translated_content,
                "header": quote_markers[i-1]['header'] if i > 0 else None,
                "depth": depth
            })

        last_pos = pos + len(header) if header else pos

    # 处理最后一段（最深层引用）
    remaining = body_original[last_pos:].strip()
    if remaining:
        # 清理 > 符号
        cleaned, _ = _clean_inline_quotes(remaining)

        translated_remaining = _extract_corresponding_translation(
            remaining, body_translated, len(quote_markers)
        ) if body_translated else None

        parts.append({
            "type": "quote",
            "original": cleaned,
            "translated": translated_remaining,
            "header": quote_markers[-1]['header'] if quote_markers else None,
            "depth": len(quote_markers)
        })

    return parts


def _find_quote_markers(body: str) -> List[Dict]:
    """
    查找所有引用标记的位置

    Returns:
        [{"position": int, "header": str, "type": str}, ...]
    """
    markers = []

    for pattern, marker_type in QUOTE_PATTERNS:
        for match in re.finditer(pattern, body, re.IGNORECASE | re.MULTILINE):
            markers.append({
                "position": match.start(),
                "header": match.group(1).strip(),
                "type": marker_type
            })

    # 检测连续 > 引用块的起始位置
    lines = body.split('\n')
    consecutive_quotes = 0
    quote_block_start = None

    for i, line in enumerate(lines):
        if re.match(INLINE_QUOTE_PATTERN, line):
            if consecutive_quotes == 0:
                # 计算该行在原文中的位置
                quote_block_start = sum(len(l) + 1 for l in lines[:i])
            consecutive_quotes += 1
        else:
            if consecutive_quotes >= 3 and quote_block_start is not None:
                # 至少3行连续引用才认为是引用块
                markers.append({
                    "position": quote_block_start,
                    "header": "> (引用内容)",
                    "type": "inline_quote"
                })
            consecutive_quotes = 0
            quote_block_start = None

    # 处理末尾的引用块
    if consecutive_quotes >= 3 and quote_block_start is not None:
        markers.append({
            "position": quote_block_start,
            "header": "> (引用内容)",
            "type": "inline_quote"
        })

    return markers


def _clean_inline_quotes(text: str) -> Tuple[str, int]:
    """
    清理行内 > 引用符号

    Returns:
        (清理后的文本, 最大引用深度)
    """
    lines = text.split('\n')
    cleaned_lines = []
    max_depth = 0

    for line in lines:
        match = re.match(r'^(>+)\s?', line)
        if match:
            depth = len(match.group(1))
            max_depth = max(max_depth, depth)
            cleaned_lines.append(line[match.end():])
        else:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines), max_depth


def _extract_corresponding_translation(
    original_part: str,
    full_translated: str,
    depth: int
) -> Optional[str]:
    """
    尝试从完整翻译中提取对应部分的翻译

    由于翻译可能不是精确对应的，这里使用启发式方法：
    1. 如果翻译中有 "--- 以下为引用内容 ---" 等分隔符，按分隔符拆分
    2. 否则返回整个翻译（深度0）或 None
    """
    if not full_translated:
        return None

    # 检查是否有引用分隔符
    separators = [
        r'---+\s*以下为引用内容.*?---+',
        r'---+\s*引用.*?---+',
        r'---+\s*Original Message.*?---+',
    ]

    for sep_pattern in separators:
        parts = re.split(sep_pattern, full_translated, flags=re.IGNORECASE)
        if len(parts) > 1:
            if depth < len(parts):
                return parts[depth].strip()
            return None

    # 没有分隔符，只返回深度0的翻译
    if depth == 0:
        return full_translated.strip()

    return None


def parse_email_quotes_simple(body_original: str) -> List[Dict]:
    """
    简化版解析，只分离最新内容和引用部分（不区分多层）

    用于快速处理，不需要翻译对齐时使用
    """
    if not body_original:
        return []

    body_original = body_original.replace('\r\n', '\n').replace('\r', '\n')

    # 查找第一个引用标记
    earliest_pos = len(body_original)
    earliest_header = None

    for pattern, _ in QUOTE_PATTERNS:
        match = re.search(pattern, body_original, re.IGNORECASE | re.MULTILINE)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()
            earliest_header = match.group(1).strip()

    # 检测连续 > 引用
    quote_block_match = re.search(r'\n(>[^\n]*\n){3,}', body_original)
    if quote_block_match and quote_block_match.start() < earliest_pos:
        earliest_pos = quote_block_match.start()
        earliest_header = "> (引用内容)"

    parts = []

    if earliest_pos < len(body_original):
        # 有引用
        latest = body_original[:earliest_pos].strip()
        quoted = body_original[earliest_pos:].strip()

        if latest:
            parts.append({
                "type": "latest",
                "original": latest,
                "translated": None,
                "header": None,
                "depth": 0
            })

        if quoted:
            parts.append({
                "type": "quote",
                "original": quoted,
                "translated": None,
                "header": earliest_header,
                "depth": 1
            })
    else:
        # 没有引用
        parts.append({
            "type": "latest",
            "original": body_original.strip(),
            "translated": None,
            "header": None,
            "depth": 0
        })

    return parts
