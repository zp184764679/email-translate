import httpx
from typing import List, Dict, Optional
import json
import re
import os
import hmac
import hashlib
from datetime import datetime, timezone


class TranslateService:
    """Translation service supporting DeepL, Claude API, Ollama, and Tencent TMT

    统一 API 模式：
    - ollama: 本地测试用
    - claude: 正式 API（支持实时和 Batch）
    - deepl: DeepL API
    - tencent: 腾讯翻译 API（机器翻译，速度快，格式保持好）

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
        "requests_log": [],  # 最近的请求记录
        # Prompt Cache 统计
        "cache_creation_tokens": 0,   # 缓存创建 token（首次请求，+25%费用）
        "cache_read_tokens": 0,       # 缓存读取 token（后续请求，-90%费用）
        "cache_hits": 0,              # 缓存命中次数
        "cache_misses": 0             # 缓存未命中次数
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
                 claude_model: str = None, tencent_secret_id: str = None, tencent_secret_key: str = None):
        """
        Initialize translate service

        Args:
            api_key: API key (DeepL or Claude)
            provider: "deepl", "claude", "ollama", or "tencent"
            proxy_url: Proxy URL (e.g., "http://127.0.0.1:7890")
            is_free_api: For DeepL, whether using free API (default True)
            ollama_base_url: Ollama API base URL (e.g., "http://localhost:11434")
            ollama_model: Ollama model name (e.g., "qwen3:8b")
            claude_model: Claude model name (e.g., "claude-sonnet-4-20250514")
            tencent_secret_id: Tencent Cloud SecretId
            tencent_secret_key: Tencent Cloud SecretKey
        """
        self.api_key = api_key
        self.provider = provider
        self.is_free_api = is_free_api
        self.ollama_base_url = ollama_base_url or "http://localhost:11434"
        self.ollama_model = ollama_model or "qwen3:8b"
        self.claude_model = claude_model or "claude-sonnet-4-20250514"
        self.tencent_secret_id = tencent_secret_id
        self.tencent_secret_key = tencent_secret_key

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
                # 兼容字典和其他格式
                if isinstance(g, dict):
                    all_terms[g.get('source', '')] = g.get('target', '')
                # 跳过非字典类型（如字符串）

        lines = ["| 原文 | 译文 |", "|------|------|"]
        for term, translation in all_terms.items():
            if term and translation:
                lines.append(f"| {term} | {translation} |")
        return "\n".join(lines)

    def _build_translation_prompt(self, text: str, target_lang: str, source_lang: str = None,
                                   glossary: List[Dict] = None, use_think: bool = True,
                                   is_short_text: bool = False) -> str:
        """构建优化后的翻译 prompt（基于邮件样本分析优化）

        Args:
            use_think: 是否使用 /think 模式（Ollama 翻译时启用，提高质量）
            is_short_text: 是否是短文本（如邮件主题），需要更严格的限制
        """
        lang_names = {
            "zh": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文"
        }

        target_name = lang_names.get(target_lang, target_lang)
        source_name = lang_names.get(source_lang, "原文") if source_lang else "原文"

        # 短文本使用简化的严格 prompt
        if is_short_text:
            return f"""将以下文本翻译为{target_name}。

严格要求：
- 只翻译，不解释
- 不要添加任何原文没有的内容
- 译文长度应与原文相当
- 直接输出译文，不要有任何前缀

原文: {text}
译文:"""

        # 术语表（核心术语 + 供应商特定术语）
        glossary_table = self._format_glossary_table(glossary)

        # /think 前缀（仅 Ollama 使用）
        think_prefix = "/think\n" if use_think else ""

        # 优化后的 prompt（基于 202 封邮件样本分析）
        prompt = f"""{think_prefix}你是精密机械行业的商务翻译专家。翻译采购部门与海外供应商的往来邮件。

## 任务
将以下{source_name}邮件翻译为{target_name}。**只输出译文，不要输出任何解释或思考过程。**

## 格式要求（最重要！）
1. **逐行翻译**：原文每一行对应译文的一行
2. **保持空行**：原文有空行的地方，译文也要有空行；原文没有空行，译文也不要加空行
3. **不要合并段落**：即使原文是短句，也不要把多行合并成一行
4. **不要添加内容**：不要添加原文没有的空行、分隔线、编号等

## 保持原样不翻译
- 人名、公司名、产品型号、邮箱、电话、地址

## 核心术语
{glossary_table}

---
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
        # 短文本（<100字符且无换行）使用简化的严格 prompt，防止 LLM 过度扩展
        is_short_text = len(text) < 100 and '\n' not in text
        prompt = self._build_translation_prompt(text, target_lang, source_lang, glossary,
                                                 use_think=not is_short_text,
                                                 is_short_text=is_short_text)

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

            # 去除 qwen3 的思考标签 <think>...</think>
            translated = re.sub(r'<think>.*?</think>', '', translated, flags=re.DOTALL)
            translated = translated.strip()

            print(f"[Ollama/{self.ollama_model}] Translated to {target_lang}")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Ollama translation error: {e}")
            raise

    # ============ Claude API Translation ============
    def _build_claude_system_prompt(self, target_lang: str, source_lang: str = None,
                                     glossary: List[Dict] = None) -> str:
        """
        构建 Claude 系统提示（用于 Prompt Cache）

        注意：Claude Prompt Cache 要求最少 1024 tokens 才能缓存
        当前系统提示设计为 ~1100 tokens，确保缓存生效
        """
        lang_names = {
            "zh": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文"
        }

        target_name = lang_names.get(target_lang, target_lang)
        source_name = lang_names.get(source_lang, "原文") if source_lang else "原文"

        # 术语表
        glossary_table = self._format_glossary_table(glossary)

        # 系统提示（会被缓存，需要 >= 1024 tokens）
        system_prompt = f"""你是精密机械行业的资深商务翻译专家，专门翻译采购部门与海外供应商的往来邮件。你精通英语、日语、韩语与中文的互译，熟悉精密机械、汽车零部件、品质管理等领域的专业术语。

## 任务
将{source_name}邮件翻译为{target_name}。**只输出译文，不要输出任何解释、思考过程或额外说明。**

## 格式要求（最重要！）
1. **逐行翻译**：原文每一行对应译文的一行，保持原文的换行结构
2. **保持空行**：原文有空行的地方，译文也要有空行；原文没有空行，译文也不要加空行
3. **不要合并段落**：即使原文是短句，也不要把多行合并成一行
4. **不要添加内容**：不要添加原文没有的空行、分隔线、编号、标点等
5. **保持列表格式**：如果原文有编号列表（1. 2. 3.）或符号列表（- * •），保持相同格式

## 保持原样不翻译的内容
- 人名（如 John Smith, 田中太郎, Wang Wei）
- 公司名（如 Toyota, Bosch, Jingzhicheng）
- 产品型号和零件编号（如 ABC-12345, Part No. 678）
- 邮箱地址（如 xxx@company.com）
- 电话号码和传真号码
- 物理地址和邮编
- 日期格式保持原样（如 2024/12/08, Dec 8, 2024）
- 金额和货币符号（如 $100, ¥5000, €200）
- 网址和链接

## 翻译风格要求
- 使用正式的商务语言，保持专业性
- 避免过度意译，保持原文的信息完整性
- 技术术语使用行业通用译法
- 日语敬语翻译时保持礼貌程度

## 常见邮件结构处理
- 问候语：保持原文的礼貌程度（Dear Mr. → 尊敬的...先生）
- 签名块：保持原格式，人名公司名不翻译
- 附件说明：如"Please find attached"翻译为"请查收附件"
- 邮件引用：带 > 的引用内容也需翻译

## 日语特殊处理
- 「お世話になっております」→「承蒙关照」（商务标准译法）
- 「よろしくお願いします」→「请多关照」
- 「ご確認ください」→「请确认」
- 「ご検討ください」→「请评估/请考虑」
- 敬语保持相应的礼貌程度

## 核心术语表
{glossary_table}

## 翻译示例

### 示例1：简单确认邮件
原文：
Thank you for your email.
The shipment has been confirmed.

译文：
谢谢您的邮件。
发货已确认。

### 示例2：带列表的邮件
原文：
Please check the following items:
1. Invoice No. 12345
2. Packing list
3. COA (Certificate of Analysis)

译文：
请确认以下项目：
1. Invoice No. 12345
2. 装箱单
3. COA（分析证书）

### 示例3：日语邮件
原文：
お世話になっております。
納期の件、ご確認ください。

译文：
承蒙关照。
关于交期事宜，请确认。"""

        return system_prompt

    def translate_with_claude(self, text: str, target_lang: str = "zh",
                               source_lang: str = None, glossary: List[Dict] = None,
                               use_cache: bool = True) -> str:
        """
        Translate text using Claude API (Anthropic)

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary: List of term mappings for context
            use_cache: Whether to use prompt caching (default True)

        Prompt Caching:
            - 系统提示（翻译规则、术语表）会被缓存
            - 缓存有效期 5 分钟，期间重复请求可节省 ~90% input token
            - 首次请求会写入缓存（有额外 25% 费用），后续请求读取缓存（节省 90%）
        """
        # 构建系统提示和用户消息
        system_prompt = self._build_claude_system_prompt(target_lang, source_lang, glossary)
        user_message = f"请翻译以下邮件：\n\n{text}"

        # 请求头
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # 构建请求体
        if use_cache:
            # 使用 Prompt Cache：系统提示带 cache_control
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"
            request_body = {
                "model": self.claude_model,
                "max_tokens": 4096,
                "system": [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}  # 5分钟缓存
                    }
                ],
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            }
        else:
            # 不使用缓存：传统方式
            request_body = {
                "model": self.claude_model,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            }

        try:
            response = self.http_client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=request_body
            )
            response.raise_for_status()

            result = response.json()
            translated = result["content"][0]["text"].strip()

            # 记录 token 使用情况（包含缓存信息）
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
            cache_read_tokens = usage.get("cache_read_input_tokens", 0)

            self._record_token_usage(input_tokens, output_tokens, len(text),
                                     cache_creation_tokens, cache_read_tokens)

            # 日志显示缓存状态
            cache_status = ""
            if cache_read_tokens > 0:
                cache_status = f", cache_read={cache_read_tokens}"
            elif cache_creation_tokens > 0:
                cache_status = f", cache_created={cache_creation_tokens}"

            print(f"[Claude] Translated to {target_lang} (in={input_tokens}, out={output_tokens}{cache_status})")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"Claude API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Claude translation error: {e}")
            raise

    # ============ Tencent TMT Translation ============
    def _get_tencent_auth_headers(self, payload: str) -> Dict:
        """生成腾讯云 API 签名 V3"""
        service = "tmt"
        host = "tmt.tencentcloudapi.com"
        algorithm = "TC3-HMAC-SHA256"

        # 获取当前时间
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp())
        date = now.strftime("%Y-%m-%d")

        # 步骤1: 拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:texttranslate\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (http_request_method + "\n" + canonical_uri + "\n" +
                           canonical_querystring + "\n" + canonical_headers + "\n" +
                           signed_headers + "\n" + hashed_request_payload)

        # 步骤2: 拼接待签名字符串
        credential_scope = date + "/" + service + "/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = (algorithm + "\n" + str(timestamp) + "\n" +
                         credential_scope + "\n" + hashed_canonical_request)

        # 步骤3: 计算签名
        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = sign(("TC3" + self.tencent_secret_key).encode("utf-8"), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # 步骤4: 拼接 Authorization
        authorization = (algorithm + " " +
                        "Credential=" + self.tencent_secret_id + "/" + credential_scope + ", " +
                        "SignedHeaders=" + signed_headers + ", " +
                        "Signature=" + signature)

        return {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": host,
            "X-TC-Action": "TextTranslate",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2018-03-21",
            "X-TC-Region": "ap-guangzhou",  # 广州区域
        }

    def translate_with_tencent(self, text: str, target_lang: str = "zh",
                                source_lang: str = None) -> str:
        """
        使用腾讯翻译 API 翻译文本

        优点：速度快，格式保持好，价格便宜
        文档：https://cloud.tencent.com/document/api/551/15619

        注意：腾讯翻译单次请求限制 6000 字符，超长文本会自动分段翻译
        """
        # 先检查额度是否可用
        if not self._check_tencent_quota():
            raise Exception("腾讯翻译本月免费额度已用完，请等待下月重置或使用其他翻译引擎")

        # 腾讯翻译单次限制 5000 字符（留一些余量）
        MAX_LENGTH = 5000

        # 如果文本超长，分段翻译
        if len(text) > MAX_LENGTH:
            return self._translate_long_text_tencent(text, target_lang, source_lang)

        return self._translate_single_tencent(text, target_lang, source_lang)

    def _check_tencent_quota(self) -> bool:
        """检查腾讯翻译额度是否可用"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在异步上下文中，无法同步等待结果，默认允许
                return True
            else:
                return loop.run_until_complete(self._check_tencent_quota_async())
        except RuntimeError:
            return asyncio.run(self._check_tencent_quota_async())

    async def _check_tencent_quota_async(self) -> bool:
        """异步检查腾讯翻译额度"""
        try:
            from services.usage_service import check_translation_quota
            result = await check_translation_quota("tencent")
            if not result.get('available', True):
                print(f"[UsageService] 腾讯翻译不可用: 已使用 {result.get('usage_percent', 0)*100:.1f}%")
                return False
            return True
        except Exception as e:
            print(f"[UsageService] 额度检查失败: {e}，默认允许翻译")
            return True

    def _translate_long_text_tencent(self, text: str, target_lang: str, source_lang: str) -> str:
        """分段翻译长文本（按段落分割，保持格式）"""
        MAX_LENGTH = 5000

        # 按双换行分段（段落）
        paragraphs = text.split('\n\n')
        translated_parts = []
        current_chunk = ""

        for para in paragraphs:
            # 如果当前块加上这段不超限，就合并
            if len(current_chunk) + len(para) + 2 < MAX_LENGTH:
                if current_chunk:
                    current_chunk += '\n\n' + para
                else:
                    current_chunk = para
            else:
                # 当前块已满，先翻译它
                if current_chunk:
                    translated_parts.append(self._translate_single_tencent(current_chunk, target_lang, source_lang))
                # 如果单段就超长，需要按行分割
                if len(para) > MAX_LENGTH:
                    lines = para.split('\n')
                    line_chunk = ""
                    for line in lines:
                        if len(line_chunk) + len(line) + 1 < MAX_LENGTH:
                            if line_chunk:
                                line_chunk += '\n' + line
                            else:
                                line_chunk = line
                        else:
                            if line_chunk:
                                translated_parts.append(self._translate_single_tencent(line_chunk, target_lang, source_lang))
                            line_chunk = line
                    if line_chunk:
                        current_chunk = line_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = para

        # 翻译最后一块
        if current_chunk:
            translated_parts.append(self._translate_single_tencent(current_chunk, target_lang, source_lang))

        return '\n\n'.join(translated_parts)

    def _translate_single_tencent(self, text: str, target_lang: str, source_lang: str) -> str:
        """单次腾讯翻译请求"""
        # 语言代码映射
        lang_map = {
            "zh": "zh",
            "en": "en",
            "ja": "ja",
            "ko": "ko",
            "de": "de",
            "fr": "fr",
            "es": "es",
            "pt": "pt",
            "ru": "ru",
        }

        target = lang_map.get(target_lang, target_lang)
        source = lang_map.get(source_lang, "auto") if source_lang else "auto"

        payload = json.dumps({
            "SourceText": text,
            "Source": source,
            "Target": target,
            "ProjectId": 0
        })

        headers = self._get_tencent_auth_headers(payload)

        try:
            response = self.http_client.post(
                "https://tmt.tencentcloudapi.com",
                content=payload,
                headers=headers
            )
            response.raise_for_status()

            result = response.json()

            if "Response" in result and "TargetText" in result["Response"]:
                translated = result["Response"]["TargetText"]
                char_count = len(text)
                print(f"[Tencent TMT] Translated {source} → {target} ({char_count} chars)")

                # 记录用量统计（同步方式）
                self._record_tencent_usage(char_count)

                return translated
            elif "Response" in result and "Error" in result["Response"]:
                error = result["Response"]["Error"]
                raise Exception(f"Tencent API error: {error.get('Code')} - {error.get('Message')}")
            else:
                raise Exception(f"Unexpected response: {result}")

        except httpx.HTTPStatusError as e:
            print(f"Tencent API HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"Tencent translation error: {e}")
            raise

    def _record_tencent_usage(self, char_count: int):
        """同步记录腾讯翻译用量"""
        import asyncio
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步上下文中，创建后台任务（忽略结果）
                task = asyncio.create_task(self._record_tencent_usage_async(char_count))
                # 添加回调来忽略任务被取消的情况
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
            else:
                # 同步执行
                loop.run_until_complete(self._record_tencent_usage_async(char_count))
        except RuntimeError:
            # 没有事件循环，创建新的
            asyncio.run(self._record_tencent_usage_async(char_count))

    async def _record_tencent_usage_async(self, char_count: int):
        """异步记录腾讯翻译用量"""
        try:
            from services.usage_service import record_translation_usage
            result = await record_translation_usage("tencent", char_count)
            if result.get('warning'):
                print(f"[UsageService] {result['warning']}")
            if result.get('is_disabled'):
                print(f"[UsageService] ⚠️ 腾讯翻译已自动禁用，请下月再使用或手动重新启用")
        except Exception as e:
            print(f"[UsageService] Failed to record usage: {e}")

    def _record_token_usage(self, input_tokens: int, output_tokens: int, text_length: int,
                            cache_creation_tokens: int = 0, cache_read_tokens: int = 0):
        """记录 token 使用情况（含缓存统计）"""
        if self._token_stats["session_start"] is None:
            self._token_stats["session_start"] = datetime.now().isoformat()

        self._token_stats["total_input_tokens"] += input_tokens
        self._token_stats["total_output_tokens"] += output_tokens
        self._token_stats["total_requests"] += 1

        # Prompt Cache 统计
        self._token_stats["cache_creation_tokens"] += cache_creation_tokens
        self._token_stats["cache_read_tokens"] += cache_read_tokens
        if cache_read_tokens > 0:
            self._token_stats["cache_hits"] += 1
        elif cache_creation_tokens > 0:
            self._token_stats["cache_misses"] += 1

        # 保留最近 100 条记录
        self._token_stats["requests_log"].append({
            "timestamp": datetime.now().isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "text_length": text_length,
            "cache_creation": cache_creation_tokens,
            "cache_read": cache_read_tokens
        })
        if len(self._token_stats["requests_log"]) > 100:
            self._token_stats["requests_log"] = self._token_stats["requests_log"][-100:]

    @classmethod
    def get_token_stats(cls) -> Dict:
        """获取 token 统计信息（含 Prompt Cache）"""
        stats = cls._token_stats.copy()
        total_tokens = stats["total_input_tokens"] + stats["total_output_tokens"]

        # Claude Sonnet 价格:
        # - 普通 input: $3/M
        # - 普通 output: $15/M
        # - Cache write (creation): $3.75/M (+25%)
        # - Cache read: $0.30/M (-90%)
        input_cost = stats["total_input_tokens"] / 1_000_000 * 3
        output_cost = stats["total_output_tokens"] / 1_000_000 * 15
        cache_write_cost = stats.get("cache_creation_tokens", 0) / 1_000_000 * 3.75
        cache_read_cost = stats.get("cache_read_tokens", 0) / 1_000_000 * 0.30
        total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost

        # 计算缓存节省的费用（如果没有缓存，这些 token 要按 $3/M 计费）
        cache_read_tokens = stats.get("cache_read_tokens", 0)
        saved_cost = cache_read_tokens / 1_000_000 * (3 - 0.30)  # 节省 $2.70/M

        # 计算平均值
        avg_input = stats["total_input_tokens"] / max(stats["total_requests"], 1)
        avg_output = stats["total_output_tokens"] / max(stats["total_requests"], 1)

        # 缓存命中率
        cache_hits = stats.get("cache_hits", 0)
        cache_misses = stats.get("cache_misses", 0)
        cache_total = cache_hits + cache_misses
        cache_hit_rate = (cache_hits / cache_total * 100) if cache_total > 0 else 0

        return {
            "total_input_tokens": stats["total_input_tokens"],
            "total_output_tokens": stats["total_output_tokens"],
            "total_tokens": total_tokens,
            "total_requests": stats["total_requests"],
            "avg_input_tokens_per_request": round(avg_input, 1),
            "avg_output_tokens_per_request": round(avg_output, 1),
            "estimated_cost_usd": round(total_cost, 4),
            "session_start": stats["session_start"],
            "recent_requests": stats["requests_log"][-10:],  # 最近 10 条
            # Prompt Cache 统计
            "cache": {
                "creation_tokens": stats.get("cache_creation_tokens", 0),
                "read_tokens": cache_read_tokens,
                "hits": cache_hits,
                "misses": cache_misses,
                "hit_rate_percent": round(cache_hit_rate, 1),
                "saved_cost_usd": round(saved_cost, 4)
            }
        }

    @classmethod
    def reset_token_stats(cls):
        """重置 token 统计"""
        cls._token_stats = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_requests": 0,
            "session_start": None,
            "requests_log": [],
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "cache_hits": 0,
            "cache_misses": 0
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
        elif self.provider == "tencent":
            return self.translate_with_tencent(text, target_lang, source_lang)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def translate_with_smart_routing(self, text: str, subject: str = "",
                                      target_lang: str = "zh",
                                      glossary: List[Dict] = None,
                                      source_lang: str = None) -> Dict:
        """
        智能路由翻译 - 基于复杂度选择最优引擎

        策略：
        1. Ollama 快速评估复杂度（规则优先，必要时用LLM）
        2. 根据复杂度选择引擎：
           - 简单(≤30分): Ollama 直接翻译（分析+翻译一起做，省时）
           - 中等(31-70): 腾讯翻译（速度快，格式好）
           - 复杂(>70): 拆分翻译（正文用Claude，签名用腾讯省钱）

        额度保护：
        - 腾讯/DeepL 额度用完时自动降级
        - Claude 作为最终兜底

        Returns:
            {
                "translated_text": str,
                "provider_used": str,
                "complexity": {"level", "score"},
                "fallback_reason": str | None
            }
        """
        from services.email_analyzer import get_email_analyzer, ComplexityLevel

        # 1. 评估复杂度
        try:
            analyzer = get_email_analyzer(self.ollama_base_url, self.ollama_model)
            complexity, score = analyzer.quick_complexity_check(text, subject)
            print(f"[SmartRouting] Complexity: {complexity.value} (score={score})")
        except Exception as e:
            print(f"[SmartRouting] Complexity check failed: {e}, defaulting to MEDIUM")
            complexity = ComplexityLevel.MEDIUM
            score = 50

        # 2. 根据复杂度选择策略
        if complexity == ComplexityLevel.SIMPLE:
            # 简单邮件：Ollama 直接翻译（已经调用过 Ollama 评估，直接翻译更快）
            return self._translate_simple(text, target_lang, source_lang, glossary, score)

        elif complexity == ComplexityLevel.MEDIUM:
            # 中等邮件：优先腾讯翻译
            return self._translate_medium(text, target_lang, source_lang, glossary, score)

        else:
            # 复杂邮件：拆分翻译
            return self._translate_complex(text, subject, target_lang, source_lang, glossary, score)

    def _translate_simple(self, text: str, target_lang: str, source_lang: str,
                          glossary: List[Dict], score: int) -> Dict:
        """简单邮件翻译 - Ollama 直接翻译"""
        try:
            print(f"[SmartRouting] Simple email -> Ollama")
            translated = self.translate_with_ollama(text, target_lang, source_lang, glossary)
            return {
                "translated_text": translated,
                "provider_used": "ollama",
                "complexity": {"level": "simple", "score": score},
                "fallback_reason": None
            }
        except Exception as e:
            print(f"[SmartRouting] Ollama failed: {e}, falling back to tencent")
            # 回退到腾讯翻译
            return self._translate_with_fallback(text, target_lang, source_lang, glossary,
                                                  {"level": "simple", "score": score})

    def _translate_medium(self, text: str, target_lang: str, source_lang: str,
                          glossary: List[Dict], score: int) -> Dict:
        """
        中等邮件翻译 - 拆分翻译策略

        使用 Ollama + /think 拆分邮件结构：
        - 正文 → DeepL（翻译质量高）
        - 签名/地址/问候语 → 腾讯翻译（格式保持好）
        """
        from services.email_analyzer import get_email_analyzer

        try:
            # 使用 Ollama + /think 分析邮件结构
            analyzer = get_email_analyzer(self.ollama_base_url, self.ollama_model)
            analysis = analyzer.analyze_email(text, "")  # 中等邮件不需要主题

            # 如果成功拆分出正文
            if analysis.structure.body:
                print(f"[SmartRouting] Medium email -> Split: greeting={bool(analysis.structure.greeting)}, signature={bool(analysis.structure.signature)}")

                translated_parts = []

                # 翻译问候语（用腾讯，格式好）
                if analysis.structure.greeting:
                    try:
                        greeting_translated = self._translate_with_tencent_or_fallback(
                            analysis.structure.greeting, target_lang, source_lang
                        )
                        translated_parts.append(greeting_translated)
                    except:
                        translated_parts.append(analysis.structure.greeting)

                # 翻译正文（用 DeepL，质量高）
                try:
                    body_translated = self._translate_body_with_deepl(
                        analysis.structure.body, target_lang, source_lang, glossary
                    )
                    translated_parts.append(body_translated)
                    body_provider = "deepl"
                except Exception as e:
                    print(f"[SmartRouting] DeepL failed for body: {e}, falling back to tencent")
                    body_translated = self._translate_with_tencent_or_fallback(
                        analysis.structure.body, target_lang, source_lang
                    )
                    translated_parts.append(body_translated)
                    body_provider = "tencent"

                # 翻译签名（用腾讯，格式好）
                if analysis.structure.signature:
                    try:
                        sig_translated = self._translate_with_tencent_or_fallback(
                            analysis.structure.signature, target_lang, source_lang
                        )
                        translated_parts.append(sig_translated)
                    except:
                        translated_parts.append(analysis.structure.signature)

                return {
                    "translated_text": "\n\n".join(translated_parts),
                    "provider_used": f"{body_provider}+tencent",
                    "complexity": {"level": "medium", "score": score},
                    "fallback_reason": None,
                    "split_translation": True
                }

        except Exception as e:
            print(f"[SmartRouting] Medium split failed: {e}, using fallback")

        # 拆分失败，使用整体翻译回退
        return self._translate_with_fallback(text, target_lang, source_lang, glossary,
                                              {"level": "medium", "score": score})

    def _translate_complex(self, text: str, subject: str, target_lang: str,
                           source_lang: str, glossary: List[Dict], score: int) -> Dict:
        """
        复杂邮件翻译 - 拆分翻译策略

        正文用 Claude（理解能力强），签名用腾讯（省钱）
        """
        from services.email_analyzer import get_email_analyzer

        try:
            # 获取完整分析（包含结构拆分）
            analyzer = get_email_analyzer(self.ollama_base_url, self.ollama_model)
            analysis = analyzer.analyze_email(text, subject)

            if analysis.should_split and analysis.structure.body:
                print(f"[SmartRouting] Complex email -> Split translation")

                translated_parts = []

                # 翻译问候语（用腾讯）
                if analysis.structure.greeting:
                    try:
                        greeting_translated = self._translate_with_tencent_or_fallback(
                            analysis.structure.greeting, target_lang, source_lang
                        )
                        translated_parts.append(greeting_translated)
                    except:
                        translated_parts.append(analysis.structure.greeting)

                # 翻译正文（用 Claude）
                body_translated = self._translate_body_with_claude(
                    analysis.structure.body, target_lang, source_lang, glossary
                )
                translated_parts.append(body_translated)

                # 翻译签名（用腾讯）
                if analysis.structure.signature:
                    try:
                        sig_translated = self._translate_with_tencent_or_fallback(
                            analysis.structure.signature, target_lang, source_lang
                        )
                        translated_parts.append(sig_translated)
                    except:
                        translated_parts.append(analysis.structure.signature)

                return {
                    "translated_text": "\n\n".join(translated_parts),
                    "provider_used": "claude+tencent",
                    "complexity": {"level": "complex", "score": score},
                    "fallback_reason": None,
                    "split_translation": True
                }

        except Exception as e:
            print(f"[SmartRouting] Split translation failed: {e}")

        # 拆分失败，整体用 Claude 翻译
        return self._translate_with_claude_fallback(text, target_lang, source_lang, glossary,
                                                     {"level": "complex", "score": score})

    def _translate_with_tencent_or_fallback(self, text: str, target_lang: str,
                                             source_lang: str) -> str:
        """腾讯翻译，失败则用 DeepL"""
        if self.tencent_secret_id and self._check_tencent_quota():
            try:
                return self.translate_with_tencent(text, target_lang, source_lang)
            except Exception as e:
                print(f"[SmartRouting] Tencent failed: {e}")

        if self.api_key and self._check_deepl_quota():
            try:
                result = self.translate_with_deepl(text, target_lang, source_lang)
                self._record_deepl_usage(len(text))
                return result
            except Exception as e:
                print(f"[SmartRouting] DeepL failed: {e}")

        raise Exception("腾讯和DeepL都不可用")

    def _translate_body_with_deepl(self, text: str, target_lang: str,
                                    source_lang: str, glossary: List[Dict]) -> str:
        """用 DeepL 翻译正文（中等邮件用）"""
        deepl_key = self.api_key if self.provider == "deepl" else os.environ.get("DEEPL_API_KEY")

        if deepl_key and self._check_deepl_quota():
            try:
                if self.provider == "deepl":
                    result = self.translate_with_deepl(text, target_lang, source_lang)
                else:
                    temp_service = TranslateService(
                        api_key=deepl_key,
                        provider="deepl",
                        is_free_api=os.environ.get("DEEPL_FREE_API", "true").lower() == "true"
                    )
                    result = temp_service.translate_with_deepl(text, target_lang, source_lang)

                self._record_deepl_usage(len(text))
                print(f"[SmartRouting] Body translated with DeepL ({len(text)} chars)")
                return result
            except Exception as e:
                print(f"[SmartRouting] DeepL body translation failed: {e}")
                raise

        raise Exception("DeepL 不可用或额度不足")

    def _translate_body_with_claude(self, text: str, target_lang: str,
                                     source_lang: str, glossary: List[Dict]) -> str:
        """用 Claude 翻译正文（复杂邮件用）"""
        claude_key = self.api_key if self.provider == "claude" else os.environ.get("CLAUDE_API_KEY")

        if claude_key:
            try:
                if self.provider == "claude":
                    return self.translate_with_claude(text, target_lang, source_lang, glossary)
                else:
                    temp_service = TranslateService(
                        api_key=claude_key,
                        provider="claude",
                        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
                    )
                    return temp_service.translate_with_claude(text, target_lang, source_lang, glossary)
            except Exception as e:
                print(f"[SmartRouting] Claude failed: {e}")

        # Claude 不可用，回退到其他引擎
        return self._translate_with_tencent_or_fallback(text, target_lang, source_lang)

    def _translate_with_fallback(self, text: str, target_lang: str, source_lang: str,
                                  glossary: List[Dict], complexity: Dict) -> Dict:
        """带回退的翻译（腾讯 → DeepL → Ollama → Claude）"""
        providers_tried = []

        # 1. 腾讯翻译
        if self.tencent_secret_id and self.tencent_secret_key:
            if self._check_tencent_quota():
                try:
                    translated = self.translate_with_tencent(text, target_lang, source_lang)
                    return {
                        "translated_text": translated,
                        "provider_used": "tencent",
                        "complexity": complexity,
                        "fallback_reason": None
                    }
                except Exception as e:
                    providers_tried.append(("tencent", str(e)))
            else:
                providers_tried.append(("tencent", "额度用完"))

        # 2. DeepL
        if self.api_key and self._check_deepl_quota():
            try:
                translated = self.translate_with_deepl(text, target_lang, source_lang)
                self._record_deepl_usage(len(text))
                return {
                    "translated_text": translated,
                    "provider_used": "deepl",
                    "complexity": complexity,
                    "fallback_reason": f"腾讯不可用: {providers_tried}"
                }
            except Exception as e:
                providers_tried.append(("deepl", str(e)))

        # 3. Ollama
        if self.ollama_base_url:
            try:
                translated = self.translate_with_ollama(text, target_lang, source_lang, glossary)
                return {
                    "translated_text": translated,
                    "provider_used": "ollama",
                    "complexity": complexity,
                    "fallback_reason": f"前序引擎不可用: {[p[0] for p in providers_tried]}"
                }
            except Exception as e:
                providers_tried.append(("ollama", str(e)))

        # 4. Claude
        return self._translate_with_claude_fallback(text, target_lang, source_lang, glossary, complexity)

    def _translate_with_claude_fallback(self, text: str, target_lang: str, source_lang: str,
                                         glossary: List[Dict], complexity: Dict) -> Dict:
        """Claude 兜底翻译"""
        claude_key = self.api_key if self.provider == "claude" else os.environ.get("CLAUDE_API_KEY")

        if claude_key:
            try:
                if self.provider == "claude":
                    translated = self.translate_with_claude(text, target_lang, source_lang, glossary)
                else:
                    temp_service = TranslateService(
                        api_key=claude_key,
                        provider="claude",
                        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
                    )
                    translated = temp_service.translate_with_claude(text, target_lang, source_lang, glossary)

                return {
                    "translated_text": translated,
                    "provider_used": "claude",
                    "complexity": complexity,
                    "fallback_reason": "所有免费引擎不可用"
                }
            except Exception as e:
                raise Exception(f"所有翻译引擎都失败，包括 Claude: {e}")

        raise Exception("没有可用的翻译引擎")

    def _check_deepl_quota(self) -> bool:
        """检查 DeepL 额度是否可用"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return True  # 异步上下文中默认允许
            else:
                return loop.run_until_complete(self._check_deepl_quota_async())
        except RuntimeError:
            return asyncio.run(self._check_deepl_quota_async())

    async def _check_deepl_quota_async(self) -> bool:
        """异步检查 DeepL 额度"""
        try:
            from services.usage_service import check_translation_quota
            result = await check_translation_quota("deepl")
            return result.get('available', True)
        except Exception as e:
            print(f"[UsageService] Error checking DeepL quota: {e}")
            return True  # 出错时默认允许

    def _record_deepl_usage(self, char_count: int):
        """记录 DeepL 用量"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步上下文中，创建后台任务（忽略结果）
                task = asyncio.create_task(self._record_deepl_usage_async(char_count))
                # 添加回调来忽略任务被取消的情况
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
            else:
                loop.run_until_complete(self._record_deepl_usage_async(char_count))
        except RuntimeError:
            asyncio.run(self._record_deepl_usage_async(char_count))

    async def _record_deepl_usage_async(self, char_count: int):
        """异步记录 DeepL 用量"""
        try:
            from services.usage_service import record_translation_usage
            result = await record_translation_usage("deepl", char_count)
            if result.get('warning'):
                print(f"[UsageService] {result['warning']}")
        except Exception as e:
            print(f"[UsageService] Failed to record DeepL usage: {e}")

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
