import httpx
from typing import List, Dict, Optional
import json
import re
import os
from datetime import datetime


class TranslateService:
    """Translation service supporting DeepL, Claude API, and Ollama

    统一 API 模式：
    - ollama: 本地测试用
    - claude: 正式 API（支持实时和 Batch）
    - deepl: DeepL API

    切换方式：修改 .env 中的 TRANSLATE_PROVIDER
    """

    # DeepL API endpoints
    DEEPL_API_FREE = "https://api-free.deepl.com/v2/translate"
    DEEPL_API_PRO = "https://api.deepl.com/v2/translate"

    # Token 统计（类级别，跨实例累计）
    _token_stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_requests": 0,
        "session_start": None,
        "requests_log": []  # 最近的请求记录
    }

    # 核心术语表（优化版 - 仅收录高频+易错术语）
    CORE_GLOSSARY = {
        # 行业缩写 - 必须明确定义
        "NCR": "不合格品报告",
        "SA": "选别申请",
        "5M Application": "5M申请",
        "SPDA": "供应商零件偏差授权",
        "CPK": "工程能力指数",
        "PCP": "工序控制计划",
        "AWB": "空运运单号",
        "P/L": "装箱单",
        "SIR": "出货检验报告",
        "LSM": "激光矫直机",
        "ETD": "预计离港日",
        "ETA": "预计到港日",
        "N.W.": "净重",
        "G.W.": "毛重",
        "HS Code": "海关编码",
        "QA": "品质保证",
        "QC": "品质控制",
        "PO": "采购订单",
        # 易错术语 - 字面意思与行业含义不同
        "Escapee": "流出原因",
        "Occurrence": "发生原因",
        "Run-out": "跳动量",
        "Checkpoint": "检测点",
        "Trend": "趋势数据",
        "Impex": "进出口部门",
        "Initial Part Qualification": "初物认定",
        # 日语固定商务表达
        "お世話になっております": "承蒙关照",
        "よろしくお願いします": "请多关照",
        "よろしくお願い致します": "请多关照",
        "宜しくお願い致します": "请多关照",
        "検討依頼": "评估请求",
        "納期": "交期",
        "見積": "报价",
        "出荷": "出货",
        "船便": "海运",
        "添付図面": "附件图纸",
        "弊社": "我司",
        "当社": "我司",
        "御社": "贵司",
        "貴社": "贵司",
        # 产品相关专业术语
        "Shaft": "轴",
        "Plating Thickness": "镀层厚度",
        "Stain Test": "污渍测试",
        "Bending Test": "弯曲测试",
        "Silica Gel": "干燥剂",
        "Dirt": "脏污/异物",
        "Rust": "锈蚀",
    }

    def __init__(self, api_key: str = None, provider: str = "deepl", proxy_url: str = None,
                 is_free_api: bool = True, ollama_base_url: str = None, ollama_model: str = None,
                 claude_model: str = None):
        """
        Initialize translate service

        Args:
            api_key: API key (DeepL or Claude)
            provider: "deepl", "claude", or "ollama"
            proxy_url: Proxy URL (e.g., "http://127.0.0.1:7890")
            is_free_api: For DeepL, whether using free API (default True)
            ollama_base_url: Ollama API base URL (e.g., "http://localhost:11434")
            ollama_model: Ollama model name (e.g., "qwen3:8b")
            claude_model: Claude model name (e.g., "claude-sonnet-4-20250514")
        """
        self.api_key = api_key
        self.provider = provider
        self.is_free_api = is_free_api
        self.ollama_base_url = ollama_base_url or "http://localhost:11434"
        self.ollama_model = ollama_model or "qwen3:8b"
        self.claude_model = claude_model or "claude-sonnet-4-20250514"

        # Get proxy from parameter or env var
        proxy = proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

        if proxy and provider != "ollama":
            print(f"[TranslateService] Using proxy: {proxy}")
            self.http_client = httpx.Client(proxy=proxy, timeout=120.0)
        elif provider == "ollama":
            # Ollama 本地模型需要更长的超时时间
            self.http_client = httpx.Client(timeout=300.0)
        else:
            self.http_client = httpx.Client(timeout=120.0)

        # DeepL API URL
        self.deepl_url = self.DEEPL_API_FREE if is_free_api else self.DEEPL_API_PRO

    def _detect_language_type(self, text: str) -> str:
        """
        Detect if text contains Japanese characters

        Returns:
            'ja' if Japanese detected, 'en' otherwise
        """
        if not text:
            return 'en'

        # Check for Hiragana or Katakana (definitely Japanese)
        japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')

        if japanese_pattern.search(text):
            return 'JA'

        return 'EN'

    def _map_lang_code(self, lang: str, for_target: bool = True) -> str:
        """Map our language codes to DeepL codes"""
        # DeepL language codes
        mapping = {
            "zh": "ZH",
            "en": "EN",
            "ja": "JA",
            "ko": "KO",
        }

        # For target language, Chinese needs to specify variant
        if for_target and lang == "zh":
            return "ZH-HANS"  # Simplified Chinese

        return mapping.get(lang, lang.upper())

    # ============ DeepL Translation ============
    def translate_with_deepl(self, text: str, target_lang: str = "zh",
                              source_lang: str = None, glossary_id: str = None) -> str:
        """
        Translate text using DeepL API

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary_id: DeepL glossary ID (optional)
        """
        target = self._map_lang_code(target_lang, for_target=True)

        data = {
            "auth_key": self.api_key,
            "text": text,
            "target_lang": target,
        }

        if source_lang:
            data["source_lang"] = self._map_lang_code(source_lang, for_target=False)

        if glossary_id:
            data["glossary_id"] = glossary_id

        try:
            response = self.http_client.post(self.deepl_url, data=data)
            response.raise_for_status()

            result = response.json()
            translated = result["translations"][0]["text"]
            detected_lang = result["translations"][0].get("detected_source_language", "")

            print(f"[DeepL] Translated from {detected_lang} to {target}")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"DeepL API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Translation error: {e}")
            raise

    # ============ 翻译 Prompt 模板 ============
    def _format_glossary_table(self, glossary: List[Dict] = None) -> str:
        """格式化术语表为 Markdown 表格"""
        # 合并核心术语表和供应商特定术语表
        all_terms = dict(self.CORE_GLOSSARY)
        if glossary:
            for g in glossary:
                all_terms[g.get('source', '')] = g.get('target', '')

        lines = ["| 原文 | 译文 |", "|------|------|"]
        for term, translation in all_terms.items():
            if term and translation:
                lines.append(f"| {term} | {translation} |")
        return "\n".join(lines)

    def _build_translation_prompt(self, text: str, target_lang: str, source_lang: str = None,
                                   glossary: List[Dict] = None) -> str:
        """构建优化后的翻译 prompt（基于邮件样本分析优化）"""
        lang_names = {
            "zh": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文"
        }

        target_name = lang_names.get(target_lang, target_lang)
        source_name = lang_names.get(source_lang, "原文") if source_lang else "原文"

        # 术语表（核心术语 + 供应商特定术语）
        glossary_table = self._format_glossary_table(glossary)

        # 优化后的 prompt（基于 202 封邮件样本分析）
        prompt = f"""你是精密机械行业的商务翻译专家，翻译采购部门与海外供应商（菲律宾、日本、韩国）的往来邮件。

## 任务
将以下{source_name}邮件翻译为{target_name}。只输出译文。

## 保持原样不翻译
- 人名：Michelle, Karen, Rose, Noel, KS Bae, 张茂华 等
- 公司名：Archem, GNG TECH, Jingzhicheng 等
- 产品型号：2J1011, 2KP5102, 1QT00-211304 等
- 邮箱、电话、地址、账号编码

## 核心术语
{glossary_table}

## 格式要求
- 保留段落、换行、引用结构（>符号）
- 历史邮件引用部分也翻译，保持引用格式
- 签名档中的描述性内容翻译，其余保持原样

---
邮件原文：
{text}"""
        return prompt

    # ============ Ollama Translation ============
    def translate_with_ollama(self, text: str, target_lang: str = "zh",
                               source_lang: str = None, glossary: List[Dict] = None) -> str:
        """
        Translate text using local Ollama model

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary: List of term mappings for context
        """
        prompt = self._build_translation_prompt(text, target_lang, source_lang, glossary)

        try:
            response = self.http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 2048
                    }
                }
            )
            response.raise_for_status()

            result = response.json()
            translated = result.get("response", "").strip()

            print(f"[Ollama/{self.ollama_model}] Translated to {target_lang}")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Ollama translation error: {e}")
            raise

    # ============ Claude API Translation ============
    def translate_with_claude(self, text: str, target_lang: str = "zh",
                               source_lang: str = None, glossary: List[Dict] = None) -> str:
        """
        Translate text using Claude API (Anthropic)

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary: List of term mappings for context
        """
        # 使用统一的 prompt 模板
        prompt = self._build_translation_prompt(text, target_lang, source_lang, glossary)

        try:
            response = self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.claude_model,
                    "max_tokens": 4096,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            response.raise_for_status()

            result = response.json()
            translated = result["content"][0]["text"].strip()

            # 记录 token 使用情况
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            self._record_token_usage(input_tokens, output_tokens, len(text))

            print(f"[Claude] Translated to {target_lang} (tokens: {input_tokens} in / {output_tokens} out)")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"Claude API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Claude translation error: {e}")
            raise

    def _record_token_usage(self, input_tokens: int, output_tokens: int, text_length: int):
        """记录 token 使用情况"""
        if self._token_stats["session_start"] is None:
            self._token_stats["session_start"] = datetime.now().isoformat()

        self._token_stats["total_input_tokens"] += input_tokens
        self._token_stats["total_output_tokens"] += output_tokens
        self._token_stats["total_requests"] += 1

        # 保留最近 100 条记录
        self._token_stats["requests_log"].append({
            "timestamp": datetime.now().isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "text_length": text_length
        })
        if len(self._token_stats["requests_log"]) > 100:
            self._token_stats["requests_log"] = self._token_stats["requests_log"][-100:]

    @classmethod
    def get_token_stats(cls) -> Dict:
        """获取 token 统计信息"""
        stats = cls._token_stats.copy()
        total_tokens = stats["total_input_tokens"] + stats["total_output_tokens"]

        # Claude Sonnet 价格: $3/M input, $15/M output
        input_cost = stats["total_input_tokens"] / 1_000_000 * 3
        output_cost = stats["total_output_tokens"] / 1_000_000 * 15
        total_cost = input_cost + output_cost

        # 计算平均值
        avg_input = stats["total_input_tokens"] / max(stats["total_requests"], 1)
        avg_output = stats["total_output_tokens"] / max(stats["total_requests"], 1)

        return {
            "total_input_tokens": stats["total_input_tokens"],
            "total_output_tokens": stats["total_output_tokens"],
            "total_tokens": total_tokens,
            "total_requests": stats["total_requests"],
            "avg_input_tokens_per_request": round(avg_input, 1),
            "avg_output_tokens_per_request": round(avg_output, 1),
            "estimated_cost_usd": round(total_cost, 4),
            "session_start": stats["session_start"],
            "recent_requests": stats["requests_log"][-10:]  # 最近 10 条
        }

    @classmethod
    def reset_token_stats(cls):
        """重置 token 统计"""
        cls._token_stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_requests": 0,
            "session_start": None,
            "requests_log": []
        }

    # ============ Main Translation Method ============
    def translate_text(self, text: str, target_lang: str = "zh",
                       glossary: List[Dict] = None, context: str = None,
                       source_lang: str = None) -> str:
        """
        Translate text (main entry point)

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            glossary: List of term mappings (not used for DeepL basic)
            context: Previous conversation context (not used for DeepL)
            source_lang: Source language hint
        """
        if self.provider == "deepl":
            return self.translate_with_deepl(text, target_lang, source_lang)
        elif self.provider == "ollama":
            return self.translate_with_ollama(text, target_lang, source_lang, glossary)
        elif self.provider == "claude":
            return self.translate_with_claude(text, target_lang, source_lang, glossary)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def translate_email_reply(self, chinese_text: str, target_lang: str,
                              conversation_history: List[Dict] = None,
                              glossary: List[Dict] = None) -> str:
        """
        Translate Chinese reply to target language
        """
        return self.translate_text(chinese_text, target_lang, glossary, source_lang="zh")

    # ============ Batch Translation ============
    def translate_batch(self, texts: List[str], target_lang: str = "zh") -> List[str]:
        """
        Translate multiple texts (DeepL supports batch)
        """
        target = self._map_lang_code(target_lang, for_target=True)

        data = {
            "auth_key": self.api_key,
            "text": texts,  # DeepL accepts list of texts
            "target_lang": target,
        }

        try:
            response = self.http_client.post(self.deepl_url, data=data)
            response.raise_for_status()

            result = response.json()
            translations = [t["text"] for t in result["translations"]]
            return translations

        except Exception as e:
            print(f"Batch translation error: {e}")
            raise

    def create_batch_translation(self, emails: List[Dict]) -> Dict:
        """
        Translate multiple emails

        Args:
            emails: List of emails [{id, subject, body, target_lang, source_lang}, ...]

        Returns:
            Dict with results (DeepL is synchronous, so returns immediately)
        """
        results = []

        for email in emails:
            try:
                target_lang = email.get("target_lang", "zh")
                source_lang = email.get("source_lang")

                # Translate subject and body separately
                subject_translated = ""
                body_translated = ""

                if email.get("subject"):
                    subject_translated = self.translate_with_deepl(
                        email["subject"], target_lang, source_lang
                    )

                if email.get("body"):
                    body_translated = self.translate_with_deepl(
                        email["body"], target_lang, source_lang
                    )

                results.append({
                    "email_id": email["id"],
                    "subject_translated": subject_translated,
                    "body_translated": body_translated,
                    "success": True
                })

            except Exception as e:
                results.append({
                    "email_id": email["id"],
                    "success": False,
                    "error": str(e)
                })

        return {"results": results, "total": len(emails)}

    # ============ Utility Methods ============
    def extract_new_content(self, body: str) -> str:
        """Extract only new content from email body (remove quoted text)"""
        lines = body.split("\n")
        new_lines = []

        quote_markers = [
            ">",
            "On ", "在 ",
            "wrote:", "写道:",
            "------Original Message------",
            "-------- 原始邮件 --------",
            "From:", "发件人:",
            "Sent:", "发送时间:",
            "-----"
        ]

        for line in lines:
            is_quote = False
            for marker in quote_markers:
                if line.strip().startswith(marker):
                    is_quote = True
                    break

            if is_quote:
                break
            new_lines.append(line)

        return "\n".join(new_lines).strip()

    def get_usage(self) -> Dict:
        """Get DeepL API usage statistics"""
        usage_url = self.deepl_url.replace("/translate", "/usage")

        try:
            response = self.http_client.post(usage_url, data={"auth_key": self.api_key})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting usage: {e}")
            return {}

    def close(self):
        """Close HTTP client"""
        self.http_client.close()
