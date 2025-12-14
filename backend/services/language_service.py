"""
Ollama 语言检测服务

使用本地 Ollama 模型进行语言检测，替代 langdetect 库
提供更高的准确率，特别是对于英德混淆等问题
"""

import httpx
import re
from functools import lru_cache


@lru_cache()
def get_language_service():
    """获取语言检测服务单例"""
    return LanguageService()


class LanguageService:
    """使用 Ollama 进行语言检测"""

    def __init__(self):
        from config import get_settings
        settings = get_settings()
        self.ollama_base_url = settings.ollama_base_url
        self.ollama_model = settings.ollama_model
        self.http_client = httpx.Client(timeout=30.0)

    def detect_language(self, text: str) -> str:
        """
        检测文本语言，返回语言代码

        Args:
            text: 要检测的文本

        Returns:
            语言代码 (zh, en, ja, ko, de, fr, es, pt, ru, it, nl) 或 "unknown"
        """
        if not text or len(text.strip()) < 10:
            return "unknown"

        # 清理文本
        clean_text = self._clean_text(text)
        if len(clean_text.strip()) < 20:
            return "unknown"

        # 截取前500字符进行检测（足够判断语言，又不会太长）
        sample = clean_text[:500].strip()

        prompt = f"""你是语言识别专家。识别以下文本的主要语言。

只输出一个语言代码，不要其他任何内容：
- zh: 中文
- en: 英语
- ja: 日语
- ko: 韩语
- de: 德语
- fr: 法语
- es: 西班牙语
- pt: 葡萄牙语
- ru: 俄语
- it: 意大利语
- nl: 荷兰语
- unknown: 无法识别

文本：
{sample}

语言代码："""

        try:
            response = self.http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # 低温度，更确定性的输出
                        "num_predict": 16    # 只需要输出语言代码
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("response", "").strip()

            # 解析语言代码（处理可能的 /think 输出或额外内容）
            lang_code = self._parse_language_code(raw_response)

            print(f"[LanguageService] Detected: {lang_code} (raw: {raw_response[:50]}...)")
            return lang_code

        except Exception as e:
            print(f"[LanguageService] Ollama detection failed: {e}")
            return "unknown"

    def _clean_text(self, text: str) -> str:
        """清理文本，移除噪音"""
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 移除 URL
        text = re.sub(r'http[s]?://\S+', ' ', text)
        # 移除邮箱地址
        text = re.sub(r'\S+@\S+\.\S+', ' ', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _parse_language_code(self, response: str) -> str:
        """
        解析 Ollama 返回的语言代码
        处理可能的 /think 模式输出或额外内容
        """
        valid_codes = {"zh", "en", "ja", "ko", "de", "fr", "es", "pt", "ru", "it", "nl"}

        # 1. 首先尝试直接匹配（最简单情况）
        response_lower = response.lower().strip()
        if response_lower in valid_codes:
            return response_lower

        # 2. 如果有 </think> 标签，取其后的内容
        if "</think>" in response:
            after_think = response.split("</think>")[-1].strip().lower()
            if after_think in valid_codes:
                return after_think
            # 尝试从后续内容中提取
            for code in valid_codes:
                if code in after_think:
                    return code

        # 3. 尝试从整个响应中找到第一个有效代码
        # 按行检查
        for line in response.split('\n'):
            line = line.strip().lower()
            if line in valid_codes:
                return line

        # 4. 最后尝试在整个文本中搜索
        for code in valid_codes:
            # 使用单词边界匹配
            if re.search(rf'\b{code}\b', response_lower):
                return code

        return "unknown"

    def close(self):
        """关闭 HTTP 客户端"""
        self.http_client.close()
