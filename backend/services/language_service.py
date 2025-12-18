"""
Ollama 语言检测服务

使用本地 Ollama 模型进行语言检测，替代 langdetect 库
提供更高的准确率，特别是对于英德混淆等问题

检测策略：
1. 先用快速规则检测（基于字符特征）
2. 规则不确定时，调用 Ollama
3. Ollama 失败时，回退到规则结果或 unknown
"""

import httpx
import re
from functools import lru_cache

# 预编译正则表达式（性能优化）
_CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
_JAPANESE_PATTERN = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')  # 平假名+片假名
_KOREAN_PATTERN = re.compile(r'[\uac00-\ud7af\u1100-\u11ff]')
_CYRILLIC_PATTERN = re.compile(r'[\u0400-\u04ff]')  # 俄语等斯拉夫语言
_VALID_CODES = frozenset({"zh", "en", "ja", "ko", "de", "fr", "es", "pt", "ru", "it", "nl"})


@lru_cache()
def get_language_service():
    """获取语言检测服务单例"""
    return LanguageService()


class LanguageService:
    """使用 Ollama 进行语言检测，带规则回退"""

    def __init__(self):
        from config import get_settings
        settings = get_settings()
        self.ollama_base_url = settings.ollama_base_url
        self.ollama_model = settings.ollama_model
        # 使用较短超时，避免长时间阻塞
        self.http_client = httpx.Client(timeout=15.0)

    def detect_language(self, text: str) -> str:
        """
        检测文本语言，返回语言代码

        检测策略（带降级方案）：
        1. 先用快速规则检测（中/日/韩/俄等非拉丁语言）
        2. 规则不确定时（返回 unknown），调用 Ollama
        3. Ollama 失败时，回退到规则结果

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

        # 1. 先用快速规则检测（对于明显的非拉丁语言字符非常准确）
        quick_result = self._quick_detect(clean_text)
        if quick_result != "unknown":
            print(f"[LanguageService] Quick detect: {quick_result}")
            return quick_result

        # 2. 规则不确定（可能是拉丁语言），尝试 Ollama
        ollama_result = self._ollama_detect(clean_text)
        if ollama_result != "unknown":
            return ollama_result

        # 3. Ollama 也失败了，尝试一些启发式规则
        # 对于拉丁字母文本，默认假设是英语（因为这是最常见的商务语言）
        latin_text = re.sub(r'[^a-zA-ZäöüßÄÖÜàâçéèêëïîôùûüÿœæÀÂÇÉÈÊËÏÎÔÙÛÜŸŒÆñÑáéíóúüÁÉÍÓÚÜ]', '', clean_text)
        if len(latin_text) > len(clean_text) * 0.3:
            # 大部分是拉丁字母，可能是英语、德语、法语等
            # 检查一些常见的德语特征
            german_chars = len(re.findall(r'[äöüßÄÖÜ]', clean_text))
            if german_chars > 3:
                print("[LanguageService] Fallback to German (found umlauts)")
                return "de"

            # 检查法语特征
            french_chars = len(re.findall(r'[àâçéèêëïîôùûüÿœæÀÂÇÉÈÊËÏÎÔÙÛÜŸŒÆ]', clean_text))
            if french_chars > 3:
                print("[LanguageService] Fallback to French (found accents)")
                return "fr"

            # 检查西班牙语特征
            spanish_chars = len(re.findall(r'[ñÑáéíóúüÁÉÍÓÚÜ¿¡]', clean_text))
            if spanish_chars > 3:
                print("[LanguageService] Fallback to Spanish (found Spanish chars)")
                return "es"

            # 默认英语
            print("[LanguageService] Fallback to English (default for Latin text)")
            return "en"

        print("[LanguageService] Could not detect language")
        return "unknown"

    def _quick_detect(self, text: str) -> str:
        """
        基于字符特征的快速语言检测

        适用于明显的语言特征（如中文字符、日文假名等）
        对于拉丁字母语言（英德法等）返回 unknown，交给 Ollama
        """
        # 统计各类字符数量
        chinese_count = len(_CHINESE_PATTERN.findall(text))
        japanese_count = len(_JAPANESE_PATTERN.findall(text))
        korean_count = len(_KOREAN_PATTERN.findall(text))
        cyrillic_count = len(_CYRILLIC_PATTERN.findall(text))

        total_len = len(text)
        if total_len == 0:
            return "unknown"

        # 计算比例
        chinese_ratio = chinese_count / total_len
        japanese_ratio = japanese_count / total_len
        korean_ratio = korean_count / total_len
        cyrillic_ratio = cyrillic_count / total_len

        # 中文：汉字占比 > 20%（考虑到可能夹杂英文）
        if chinese_ratio > 0.2:
            # 检查是否为日语（日语也有汉字，但会有假名）
            if japanese_ratio > 0.05:
                return "ja"
            return "zh"

        # 日语：有假名
        if japanese_ratio > 0.1:
            return "ja"

        # 韩语：有韩文字符
        if korean_ratio > 0.1:
            return "ko"

        # 俄语：有西里尔字符
        if cyrillic_ratio > 0.2:
            return "ru"

        # 拉丁字母语言无法通过字符判断，交给 Ollama
        return "unknown"

    def _ollama_detect(self, text: str) -> str:
        """
        使用 Ollama 进行语言检测
        """
        # 截取前500字符
        sample = text[:500].strip()

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
                        "temperature": 0.1,
                        "num_predict": 16
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("response", "").strip()

            lang_code = self._parse_language_code(raw_response)
            print(f"[LanguageService] Ollama detect: {lang_code} (raw: {raw_response[:50]}...)")
            return lang_code

        except httpx.TimeoutException:
            print("[LanguageService] Ollama timeout, using fallback")
            return "unknown"
        except httpx.ConnectError:
            print("[LanguageService] Ollama connection failed, using fallback")
            return "unknown"
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
        # 使用全局预定义的有效代码集合
        valid_codes = _VALID_CODES

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
