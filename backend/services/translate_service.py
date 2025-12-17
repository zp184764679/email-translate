import httpx
from typing import List, Dict, Optional, Tuple
import json
import re
import os
from datetime import datetime, timezone


class TranslateService:
    """Translation service supporting Ollama and Claude API

    统一 API 模式：
    - ollama: 本地 LLM 翻译（免费，质量好，主力引擎）
    - claude: Claude API（复杂邮件用）

    切换方式：修改 .env 中的 TRANSLATE_PROVIDER
    """

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
        # ========== 行业缩写 ==========
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
        "MOQ": "最小起订量",
        "RFQ": "询价请求",
        "BOM": "物料清单",
        "OEM": "原厂委托制造",
        "FOB": "离岸价",
        "CIF": "到岸价",
        "L/C": "信用证",
        "T/T": "电汇",
        "COD": "货到付款",
        "NCV": "不合格品确认单",
        "ACP": "异常品处理",

        # ========== 公司名称 ==========
        "Jingzhicheng": "精之成",
        "JZC": "精之成",
        "Shenzhen Jingzhicheng": "深圳精之成",
        "Dongguan Jingzhicheng": "东莞精之成",

        # ========== 易错术语（字面意思≠行业含义）==========
        "treatment": "处理方式",  # 不是"治疗"
        "Escapee": "流出原因",
        "Occurrence": "发生原因",
        "Run-out": "跳动量",
        "Checkpoint": "检测点",
        "Trend": "趋势数据",
        "Impex": "进出口部门",
        "Initial Part Qualification": "初物认定",
        "For Schedule": "待排期",  # 不是"对于时间表"
        "Pick up": "提货/取货",
        "Remarks": "备注",

        # ========== 品质缺陷相关 ==========
        "Plating peel-off": "电镀脱落",
        "Collapsed boxes": "箱体塌陷",
        "Detached strap": "捆扎带脱落",
        "Defect": "缺陷",
        "Plating Thickness": "镀层厚度",
        "Stain Test": "污渍测试",
        "Bending Test": "弯曲测试",
        "Dirt": "脏污/异物",
        "Rust": "锈蚀",
        "Scratch": "划痕",
        "Dent": "凹痕",
        "Burr": "毛刺",
        "Crack": "裂纹",
        "Deformation": "变形",

        # ========== 产品/物流相关 ==========
        "Shaft": "轴类零件",  # 不是简单的"轴"
        "Pallet": "托盘",
        "Container": "集装箱",
        "20ft": "20尺柜",
        "40ft": "40尺柜",
        "Blue Ring": "蓝圈（产品型号）",  # 型号保持原样
        "MM": "MM（产品型号）",  # 型号保持原样，不是"毫米"
        "Silica Gel": "干燥剂",
        "Packaging": "包装",
        "Strap": "捆扎带",

        # ========== 金额/数量相关 ==========
        "Amt": "金额",
        "Qty": "数量",
        "Unit Price": "单价",
        "Total": "合计",

        # ========== 日语固定商务表达 ==========
        # 问候/结束语
        "お世話になっております": "承蒙关照",
        "いつもお世話になっております": "一直承蒙关照",
        "初めまして": "初次见面",
        "よろしくお願いします": "请多关照",
        "よろしくお願い致します": "请多关照",
        "宜しくお願い致します": "请多关照",
        "以上、よろしくお願いいたします": "以上，请多关照",
        "ご担当者様": "负责人",
        "お忙しいところ恐縮ですが": "百忙之中打扰了",
        "お手数おかけしますが": "麻烦您了",
        "ご確認のほどよろしくお願いいたします": "请您确认",
        "ご検討いただければ幸いです": "如能考虑将不胜感激",
        "お早めにご連絡ください": "请尽早联系",
        "ご確認ください": "请确认",
        "ご連絡ください": "请联系",
        "ありがとうございます": "谢谢",
        "お疲れ様です": "辛苦了",

        # 业务用语
        "検討依頼": "评估请求",
        "納期": "交期",
        "納期回答": "交期答复",
        "見積": "报价",
        "お見積り": "报价",
        "お見積書": "报价单",
        "発注書": "订单",
        "ご注文": "订购",
        "納品書": "送货单",
        "請求書": "发票/账单",
        "出荷": "出货",
        "出荷予定": "预计发货",
        "船便": "海运",
        "航空便": "空运",
        "船積み": "装船",
        "通関": "清关",
        "検品": "验货",
        "在庫": "库存",
        "在庫確認": "库存确认",
        "入荷": "到货",
        "添付図面": "附件图纸",
        "不良品": "不良品",
        "数量": "数量",
        "単価": "单价",
        "合計金額": "总金额",
        "支払条件": "付款条件",
        "前払い": "预付款",
        "弊社": "我司",
        "当社": "我司",
        "御社": "贵司",
        "貴社": "贵司",

        # ========== 日语技术术语（机加工/五金）==========
        # 加工方式
        "旋盤加工": "车削加工",
        "フライス加工": "铣削加工",
        "研削加工": "磨削加工",
        "放電加工": "电火花加工",
        "ワイヤーカット": "线切割",
        "板金加工": "钣金加工",
        "プレス加工": "冲压加工",
        "ダイカスト": "压铸",
        "鋳造": "铸造",
        "鍛造": "锻造",
        "切削": "切削",
        "穴あけ": "钻孔",
        "ねじ切り": "攻丝",

        # 材料
        "ステンレス": "不锈钢",
        "アルミ": "铝",
        "アルミニウム": "铝",
        "鉄": "铁",
        "銅": "铜",
        "真鍮": "黄铜",
        "樹脂": "树脂",
        "チタン": "钛",
        "炭素鋼": "碳钢",
        "合金鋼": "合金钢",

        # 表面处理
        "めっき": "电镀",
        "亜鉛めっき": "镀锌",
        "クロムめっき": "镀铬",
        "ニッケルめっき": "镀镍",
        "アルマイト": "阳极氧化",
        "塗装": "喷涂",
        "研磨": "抛光",
        "表面処理": "表面处理",
        "熱処理": "热处理",
        "焼入れ": "淬火",
        "焼戻し": "回火",

        # 尺寸/公差
        "公差": "公差",
        "寸法": "尺寸",
        "外径": "外径",
        "内径": "内径",
        "板厚": "板厚",
        "面取り": "倒角",
        "長さ": "长度",
        "幅": "宽度",
        "高さ": "高度",
        "厚み": "厚度",

        # ========== 机加工术语 ==========
        "CNC": "数控加工",
        "Turning": "车削",
        "Milling": "铣削",
        "Grinding": "磨削",
        "Drilling": "钻孔",
        "Tapping": "攻丝",
        "Threading": "螺纹加工",
        "Heat Treatment": "热处理",
        "Quenching": "淬火",
        "Tempering": "回火",
        "Annealing": "退火",
        "Hardness": "硬度",
        "HRC": "洛氏硬度",
        "Chamfer": "倒角",
        "Radius": "圆角",

        # ========== 检测/测量术语 ==========
        "CMM": "三坐标测量机",
        "Caliper": "卡尺",
        "Micrometer": "千分尺",
        "Tolerance": "公差",
        "Deviation": "偏差",
        "Out of Spec": "超差",
        "Within Spec": "合格",
        "Dimension": "尺寸",
        "Diameter": "直径",
        "Concentricity": "同心度",
        "Roundness": "圆度",
        "Flatness": "平面度",
        "Perpendicularity": "垂直度",

        # ========== 表面处理术语 ==========
        "Anodizing": "阳极氧化",
        "E-coating": "电泳涂装",
        "Powder Coating": "粉末喷涂",
        "Zinc Plating": "镀锌",
        "Nickel Plating": "镀镍",
        "Chrome Plating": "镀铬",
        "Blackening": "发黑处理",
        "Passivation": "钝化处理",
        "Polishing": "抛光",
        "Sandblasting": "喷砂",

        # ========== 材料术语 ==========
        "Stainless Steel": "不锈钢",
        "Carbon Steel": "碳钢",
        "Alloy Steel": "合金钢",
        "Aluminum": "铝/铝合金",
        "Brass": "黄铜",
        "Bronze": "青铜",
        "Copper": "铜",
        "Titanium": "钛",
        "SUS304": "304不锈钢",
        "SUS316": "316不锈钢",

        # ========== 韩语商务表达 ==========
        "안녕하세요": "您好",
        "감사합니다": "谢谢",
        "확인 부탁드립니다": "请确认",
        "납기": "交期",
        "견적": "报价",
        "발주": "下单",
        "수량": "数量",
        "단가": "单价",
    }

    def __init__(self, api_key: str = None, provider: str = "ollama", proxy_url: str = None,
                 ollama_base_url: str = None, ollama_model: str = None,
                 claude_model: str = None, **kwargs):
        """
        Initialize translate service

        Args:
            api_key: API key (Claude)
            provider: "ollama" or "claude"
            proxy_url: Proxy URL (e.g., "http://127.0.0.1:7890")
            ollama_base_url: Ollama API base URL (e.g., "http://localhost:11434")
            ollama_model: Ollama model name (e.g., "qwen3:8b")
            claude_model: Claude model name (e.g., "claude-sonnet-4-20250514")
        """
        self.api_key = api_key
        self.provider = provider
        self.ollama_base_url = ollama_base_url or "http://localhost:11434"
        self.ollama_model = ollama_model or "qwen3:8b"
        self.claude_model = claude_model or "claude-sonnet-4-20250514"

        # Get proxy from parameter or env var
        proxy = proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

        if proxy and provider != "ollama":
            print(f"[TranslateService] Using proxy: {proxy}")
            self.http_client = httpx.Client(proxy=proxy, timeout=120.0)
        elif provider == "ollama":
            # Ollama 本地模型需要更长的超时时间（支持 think mode）
            self.http_client = httpx.Client(timeout=600.0)
        else:
            self.http_client = httpx.Client(timeout=120.0)

        # 单独的 Ollama HTTP 客户端（智能路由用，超时更长）
        self.ollama_client = httpx.Client(timeout=600.0)

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

    # ============ 邮件链处理 ============
    def extract_latest_email(self, body: str) -> Tuple[str, str]:
        """
        从邮件链中提取最新一封邮件的内容，分离历史引用

        邮件链特征：包含 "On xxx wrote:" 或 "-----Original Message-----" 等引用标记
        只翻译最新邮件内容，历史引用部分保持原样（因为之前已翻译过）

        Args:
            body: 邮件正文原文

        Returns:
            (latest_content, quoted_content): 最新邮件内容, 引用部分
        """
        # 统一换行符
        body = body.replace('\r\n', '\n').replace('\r', '\n')

        # 可靠的引用标记模式（高置信度，不容易误匹配）
        reliable_patterns = [
            # Gmail: "On Mon, Nov 26, 2025 at 11:26 PM xxx wrote:"
            r'\nOn .{10,80} wrote:\s*\n',
            # Outlook: "-----Original Message-----"
            r'\n-{3,}Original Message-{3,}\n',
            # Outlook 完整引用头（From: + Sent: 或 Date:）
            r'\nFrom: .+\n(?:Sent|Date): .+\n',
            # 中文客户端完整引用头（发件人：+ 发送时间：或 日期：）
            r'\n\*?发件人[：:].+\n(?:\*?(?:发送时间|日期)[：:].+\n)',
            # 日文引用标记
            r'\n-{3,}元のメッセージ-{3,}\n',
        ]

        earliest_pos = len(body)

        # 优先检测可靠的引用标记
        for pattern in reliable_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()

        # 检测连续的 > 引用符号（至少3行连续以 > 开头）
        quote_block_match = re.search(r'\n(>[^\n]*\n){3,}', body)
        if quote_block_match and quote_block_match.start() < earliest_pos:
            earliest_pos = quote_block_match.start()

        # 如果找到引用标记，分割内容
        if earliest_pos < len(body):
            latest = body[:earliest_pos].strip()
            quoted = body[earliest_pos:].strip()
            return latest, quoted

        return body, ""

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

    def _clean_translation_output(self, translated: str, original: str, target_lang: str) -> str:
        """清理翻译输出，去除模型可能输出的原文重复

        有些模型会输出类似：
        - 原文 + 译文
        - 原文（重复）+ 译文
        - 带"原文："、"译文："前缀的格式

        Args:
            translated: 模型输出的翻译结果
            original: 原文
            target_lang: 目标语言
        """
        if not translated:
            return translated

        # 1. 去除常见的前缀标记
        prefixes_to_remove = [
            "译文：", "译文:", "翻译：", "翻译:",
            "Translation:", "Translation：",
            "译文\n", "翻译\n",
            "原文：", "原文:",  # 也去除原文标记
        ]
        for prefix in prefixes_to_remove:
            if translated.startswith(prefix):
                translated = translated[len(prefix):].strip()

        # 2. 如果输出包含分隔线，检测前后内容的语言分布
        separators = ["---", "===", "***", "———", "##"]
        for sep in separators:
            if sep in translated:
                parts = translated.split(sep, 1)  # 只分割第一个分隔线
                if len(parts) == 2:
                    before = parts[0].strip()
                    after = parts[1].strip()

                    if target_lang == "zh" and before and after:
                        # 计算前后部分的中文占比
                        before_chinese = len(re.findall(r'[\u4e00-\u9fff]', before))
                        before_ratio = before_chinese / max(len(before), 1)

                        after_chinese = len(re.findall(r'[\u4e00-\u9fff]', after))
                        after_ratio = after_chinese / max(len(after), 1)

                        # 如果前面主要是非中文（<10%），后面主要是中文（>30%），则只保留后面
                        if before_ratio < 0.1 and after_ratio > 0.3:
                            translated = after
                            break

        # 3. 检测并移除原文重复块（基于语言分布）
        # 如果翻译结果前半部分主要是非中文（原文），后半部分主要是中文（译文），只保留中文部分
        if target_lang == "zh":
            lines = translated.split('\n')
            first_chinese_line = -1

            for i, line in enumerate(lines):
                # 找到第一行包含至少3个连续中文字符的行
                if re.search(r'[\u4e00-\u9fff]{3,}', line):
                    first_chinese_line = i
                    break

            if first_chinese_line > 0:
                # 检查前面的行是否都是非中文（原文）
                before_lines = lines[:first_chinese_line]
                before_text = '\n'.join(before_lines)
                chinese_count = len(re.findall(r'[\u4e00-\u9fff]', before_text))
                chinese_ratio = chinese_count / max(len(before_text), 1)

                # 前面部分中文占比很低（<10%），很可能是原文重复
                if chinese_ratio < 0.1 and len(before_text) > 20:
                    translated = '\n'.join(lines[first_chinese_line:])

        # 4. 检查是否原文完整重复出现在开头
        original_stripped = original.strip()
        if len(original_stripped) > 20:
            if translated.startswith(original_stripped):
                translated = translated[len(original_stripped):].strip()

        # 5. 去除开头的空行和分隔符
        translated = translated.lstrip('\n')
        translated = re.sub(r'^[\-=\*—#]+\s*\n*', '', translated)  # 去除开头的分隔符行

        return translated

    def _build_translation_prompt(self, text: str, target_lang: str, source_lang: str = None,
                                   glossary: List[Dict] = None, use_think: bool = True,
                                   is_short_text: bool = False, is_long_text: bool = False) -> str:
        """构建优化后的翻译 prompt（基于邮件样本分析优化）

        Args:
            use_think: 是否使用 /think 模式（Ollama 翻译时启用，提高质量）
            is_short_text: 是否是短文本（如邮件主题），需要更严格的限制
            is_long_text: 是否是长文本（>8000字符），使用简洁提示防止摘要
        """
        lang_names = {
            "zh": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文"
        }

        target_name = lang_names.get(target_lang, target_lang)
        source_name = lang_names.get(source_lang, "原文") if source_lang else "原文"

        # 短文本使用简化的严格 prompt（不使用格式标签，避免模型输出原文）
        if is_short_text:
            return f"""翻译任务：将以下内容翻译为{target_name}。

要求：只输出译文，不输出原文，不添加任何标签或前缀。

{text}"""

        # 长文本使用简洁明确的提示词，防止模型做摘要（不使用 --- 分隔线）
        if is_long_text:
            return f"""你是专业翻译。将下面的{source_name}文本完整翻译为{target_name}。

关键要求：
1. 必须完整翻译每一句话，绝对不能省略或概括
2. 保持原文的段落和换行格式
3. 人名、公司名、产品型号、编号保持原样
4. 只输出译文，不要输出原文，不要任何解释或前缀

## 待翻译内容

{text}

## 输出
只输出上述内容的{target_name}翻译："""

        # 术语表（核心术语 + 供应商特定术语）
        glossary_table = self._format_glossary_table(glossary)

        # /think 前缀（仅 Ollama 使用）
        think_prefix = "/think\n" if use_think else ""

        # 完整版提示词（基于 Claude 提示词 + 采购行业深度优化）
        prompt = f"""{think_prefix}你是精密机械行业的资深商务翻译专家，专门翻译采购部门与海外供应商的往来邮件。你精通英语、日语、韩语与中文的互译，熟悉精密机械、汽车零部件、品质管理等领域的专业术语。

## 任务
将以下{source_name}邮件翻译为{target_name}。**只输出译文，不要输出任何解释、思考过程或额外说明。**

## 格式要求（最重要！）
1. **逐行翻译**：原文每一行对应译文的一行，保持原文的换行结构
2. **保持空行**：原文有空行的地方，译文也要有空行；原文没有空行，译文也不要加空行
3. **不要合并段落**：即使原文是短句，也不要把多行合并成一行
4. **不要添加内容**：不要添加原文没有的空行、分隔线、编号、标点等
5. **保持列表格式**：如果原文有编号列表（1. 2. 3.）或符号列表（- * •），保持相同格式
6. **表格保持对齐**：如果原文是表格数据，保持列对齐格式

## 保持原样不翻译的内容（非常重要！）
- 人名（如 John Smith, Karen, Noel, 田中太郎）
- 公司名（如 Toyota, Bosch, ACP, Jingzhicheng）
- **产品型号和零件编号**（如 2J1041, 2J1030, Blue Ring, MM, ABC-12345）— 这些是型号代码，不是普通单词！
- 单号/编号（如 ACP-NCV25-011, Part No. 678, Invoice No.）
- 邮箱地址（如 xxx@company.com）
- 电话号码和传真号码
- 物理地址和邮编
- 日期格式保持原样（如 2024/12/08, Dec 8, 2024）
- 金额和货币符号保持原格式（如 USD37,098.34, $100, ¥5000）
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

## 采购邮件易错翻译（字面意思≠行业含义）
- "treatment" = "处理方式"（不是"治疗"！）
- "shaft" = "轴类零件"（机械行业术语）
- "For Schedule" = "待排期/待安排"（不是"对于时间表"）
- "Pick up" = "提货/取货"
- "Defect" = "缺陷"
- "Remarks" = "备注"
- "Plating peel-off" = "电镀脱落"
- "Collapsed boxes" = "箱体塌陷"
- "Detached strap" = "捆扎带脱落"

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

### 示例2：带产品型号的邮件
原文：
Please check the treatment for 2J1041 shaft.
Container: 40ft Blue Ring

译文：
请确认 2J1041 轴类零件的处理方式。
集装箱：40尺柜 Blue Ring

### 示例3：日语邮件
原文：
お世話になっております。
納期の件、ご確認ください。

译文：
承蒙关照。
关于交期事宜，请确认。

## 待翻译邮件

{text}

## 输出要求
只输出上述邮件的{target_name}翻译，不要包含原文，不要添加任何前缀或标签："""
        return prompt

    # ============ Ollama Translation ============
    def translate_with_ollama(self, text: str, target_lang: str = "zh",
                               source_lang: str = None, glossary: List[Dict] = None,
                               complexity_score: int = None) -> str:
        """
        Translate text using local Ollama model

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary: List of term mappings for context
            complexity_score: Optional complexity score (0-100) from smart routing
        """
        text_len = len(text)
        # 短文本（<100字符且无换行）使用简化的严格 prompt，防止 LLM 过度扩展
        is_short_text = text_len < 100 and '\n' not in text
        # 长文本判断
        is_long_text = text_len > 8000

        # think 模式决策逻辑（基于复杂度而非单纯长度）
        # - 短文本：不需要 think（太简单）
        # - 长文本 + 低复杂度（<= 50）：不需要 think（如简单通知、新闻邮件）
        # - 长文本 + 高复杂度（> 50）：需要 think（如技术文档、合同条款）
        # - 正常文本：需要 think
        if is_short_text:
            use_think = False
        elif is_long_text:
            # 长文本根据复杂度决定：高复杂度仍启用 think
            # 如果没有传入复杂度分数，保守地禁用 think
            use_think = complexity_score is not None and complexity_score > 50
            if use_think:
                print(f"[Ollama] Long text ({text_len} chars) with high complexity ({complexity_score}) -> enabling think mode")
        else:
            use_think = True

        prompt = self._build_translation_prompt(text, target_lang, source_lang, glossary,
                                                 use_think=use_think,
                                                 is_short_text=is_short_text,
                                                 is_long_text=is_long_text)

        # 动态计算 num_predict：翻译到中文通常输出比英文短（约 0.6-0.8 倍）
        # 但我们给足够的空间，防止截断
        # 估算：1 个英文字符约 0.3 token，中文约 0.5 token
        estimated_tokens = max(4096, int(text_len * 0.8))
        # 限制最大值防止内存爆炸
        num_predict = min(estimated_tokens, 16384)

        try:
            # 使用专用的 Ollama 客户端（超时更长，支持 think mode）
            client = getattr(self, 'ollama_client', self.http_client)
            response = client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": num_predict  # 动态设置，支持长文本
                    }
                }
            )
            response.raise_for_status()

            result = response.json()
            translated = result.get("response", "").strip()

            # 去除 qwen3 的思考标签 <think>...</think>
            translated = re.sub(r'<think>.*?</think>', '', translated, flags=re.DOTALL)
            translated = translated.strip()

            # 去除可能的原文重复（模型有时会输出原文+译文）
            translated = self._clean_translation_output(translated, text, target_lang)

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
            glossary: List of term mappings
            context: Previous conversation context
            source_lang: Source language hint
        """
        if self.provider == "ollama":
            return self.translate_with_ollama(text, target_lang, source_lang, glossary)
        elif self.provider == "claude":
            return self.translate_with_claude(text, target_lang, source_lang, glossary)
        else:
            raise ValueError(f"Unknown provider: {self.provider}. Supported: ollama, claude")

    def translate_with_smart_routing(self, text: str, subject: str = "",
                                      target_lang: str = "zh",
                                      glossary: List[Dict] = None,
                                      source_lang: str = None,
                                      translate_subject: bool = True) -> Dict:
        """
        智能路由翻译 - 基于复杂度选择最优引擎

        策略：
        1. Ollama 快速评估复杂度（规则优先，必要时用LLM）
        2. 根据复杂度选择引擎：
           - 简单/中等(≤70分): Ollama 直接翻译（免费，质量好）
           - 复杂(>70): Claude（正文）+ Ollama（签名）

        Args:
            text: 邮件正文
            subject: 邮件标题（用于复杂度分析和联合翻译）
            translate_subject: 是否同时翻译标题（标题+正文一起翻译提高理解深度）

        Returns:
            {
                "translated_text": str,          # 正文翻译
                "subject_translated": str,       # 标题翻译（如果 translate_subject=True）
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
        # 阈值与 email_analyzer.py 中的复杂度等级对齐：
        #   - SIMPLE: <= 30 分
        #   - MEDIUM: 31-70 分
        #   - COMPLEX: > 70 分
        # SIMPLE 和 MEDIUM 使用 Ollama（免费），COMPLEX 使用 Claude（更强但付费）
        OLLAMA_THRESHOLD = 70  # 70分以下用 Ollama（覆盖 SIMPLE + MEDIUM）

        if score <= OLLAMA_THRESHOLD:
            # 简单/中等邮件：Ollama 直接翻译（免费，有提示词理解上下文）
            print(f"[SmartRouting] Score {score} <= {OLLAMA_THRESHOLD} (SIMPLE/MEDIUM) -> Ollama")
            return self._translate_simple(text, target_lang, source_lang, glossary, score,
                                          subject if translate_subject else None)
        else:
            # 复杂邮件：Claude（正文）+ Ollama（签名）
            print(f"[SmartRouting] Score {score} > {OLLAMA_THRESHOLD} (COMPLEX) -> Claude+Ollama")
            return self._translate_complex(text, subject, target_lang, source_lang, glossary, score,
                                           translate_subject)

    def _parse_combined_translation(self, translated: str, original_subject: str,
                                      original_body: str) -> Tuple[str, str]:
        """
        解析联合翻译结果，分离标题和正文翻译

        Args:
            translated: 模型输出的翻译结果（可能包含 [SUBJECT]...[/SUBJECT] 和 [BODY]...[/BODY]）
            original_subject: 原始标题（用于回退）
            original_body: 原始正文（用于长度估算）

        Returns:
            (subject_translated, body_translated)
        """
        # 方法1：尝试解析标记格式
        subject_match = re.search(r'\[SUBJECT\]\s*(.*?)\s*\[/SUBJECT\]', translated, re.DOTALL)
        body_match = re.search(r'\[BODY\]\s*(.*?)\s*\[/BODY\]', translated, re.DOTALL)

        if subject_match and body_match:
            return subject_match.group(1).strip(), body_match.group(1).strip()

        # 方法2：如果模型没有保留标记，尝试用换行分割
        # 假设第一段是标题翻译，其余是正文
        lines = translated.strip().split('\n', 1)
        if len(lines) == 2:
            first_line = lines[0].strip()
            rest = lines[1].strip()

            # 检查第一行是否像标题（较短，不包含段落标记）
            if len(first_line) < 200 and '\n\n' not in first_line:
                return first_line, rest

        # 方法3：使用原始标题长度比例估算
        # 假设翻译前后长度比例相似
        if original_subject and original_body:
            subject_ratio = len(original_subject) / (len(original_subject) + len(original_body))
            estimated_subject_len = int(len(translated) * subject_ratio * 1.2)  # 给一些余量

            # 在估算位置附近找换行符
            search_start = max(0, estimated_subject_len - 50)
            search_end = min(len(translated), estimated_subject_len + 50)

            newline_pos = translated.find('\n', search_start, search_end)
            if newline_pos != -1:
                return translated[:newline_pos].strip(), translated[newline_pos:].strip()

        # 方法4：回退 - 单独翻译标题
        print("[SmartRouting] Failed to parse combined translation, translating subject separately")
        try:
            subject_translated = self.translate_with_ollama(
                original_subject, "zh", None, None
            )
            # 整个翻译结果当作正文
            return subject_translated, translated
        except Exception as e:
            print(f"[SmartRouting] Fallback subject translation failed: {e}")
            # 最终回退：返回原始标题
            return original_subject, translated

    def _translate_simple(self, text: str, target_lang: str, source_lang: str,
                          glossary: List[Dict], score: int, subject: str = None) -> Dict:
        """简单邮件翻译 - Ollama 直接翻译

        注意：邮件链处理（提取新内容、复用历史翻译）已在 emails.py 中完成，
        这里只负责翻译传入的文本。

        Args:
            subject: 如果提供，则与正文一起翻译（提高标题翻译的上下文理解）
        """
        try:
            subject_translated = None

            if subject:
                # 标题+正文联合翻译，提高理解深度
                # 使用明确的分隔标记，便于解析
                combined = f"[SUBJECT]\n{subject}\n[/SUBJECT]\n\n[BODY]\n{text}\n[/BODY]"
                print(f"[SmartRouting] Simple email -> Ollama (subject+body, {len(combined)} chars, score={score})")

                translated_combined = self.translate_with_ollama(
                    combined, target_lang, source_lang, glossary,
                    complexity_score=score
                )

                # 解析翻译结果，分离标题和正文
                subject_translated, body_translated = self._parse_combined_translation(
                    translated_combined, subject, text
                )
            else:
                print(f"[SmartRouting] Simple email -> Ollama ({len(text)} chars, score={score})")
                body_translated = self.translate_with_ollama(text, target_lang, source_lang, glossary,
                                                              complexity_score=score)

            result = {
                "translated_text": body_translated,
                "provider_used": "ollama",
                "complexity": {"level": "simple", "score": score},
                "fallback_reason": None
            }
            if subject_translated:
                result["subject_translated"] = subject_translated

            return result

        except Exception as e:
            print(f"[SmartRouting] Ollama failed: {e}, falling back to Claude")
            return self._translate_with_fallback(text, target_lang, source_lang, glossary,
                                                  {"level": "simple", "score": score})

    def _translate_complex(self, text: str, subject: str, target_lang: str,
                           source_lang: str, glossary: List[Dict], score: int,
                           translate_subject: bool = True) -> Dict:
        """
        复杂邮件翻译 - 拆分翻译策略

        正文用 Claude（理解能力强），问候语/签名用 Ollama（免费）

        Args:
            translate_subject: 是否同时翻译标题
        """
        from services.email_analyzer import get_email_analyzer

        subject_translated = None

        # 如果需要翻译标题，与正文一起用 Claude 翻译（提高上下文理解）
        if translate_subject and subject:
            try:
                # 对于复杂邮件，标题也用 Claude 翻译（与正文一起提供上下文）
                combined = f"[SUBJECT]\n{subject}\n[/SUBJECT]\n\n[BODY]\n{text}\n[/BODY]"
                print(f"[SmartRouting] Complex email -> Claude with subject+body")

                translated_combined = self._translate_body_with_claude(
                    combined, target_lang, source_lang, glossary
                )
                subject_translated, text_translated = self._parse_combined_translation(
                    translated_combined, subject, text
                )

                result = {
                    "translated_text": text_translated,
                    "subject_translated": subject_translated,
                    "provider_used": "claude",
                    "complexity": {"level": "complex", "score": score},
                    "fallback_reason": None
                }
                return result
            except Exception as e:
                print(f"[SmartRouting] Combined subject+body translation failed: {e}")
                # 继续使用分拆策略

        try:
            # 获取完整分析（包含结构拆分）
            analyzer = get_email_analyzer(self.ollama_base_url, self.ollama_model)
            analysis = analyzer.analyze_email(text, subject)

            if analysis.should_split and analysis.structure.body:
                print(f"[SmartRouting] Complex email -> Split translation")

                translated_parts = []

                # 翻译问候语（用 Ollama）
                if analysis.structure.greeting:
                    try:
                        greeting_translated = self._translate_with_ollama_or_fallback(
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

                # 翻译签名（用 Ollama）
                if analysis.structure.signature:
                    try:
                        sig_translated = self._translate_with_ollama_or_fallback(
                            analysis.structure.signature, target_lang, source_lang
                        )
                        translated_parts.append(sig_translated)
                    except:
                        translated_parts.append(analysis.structure.signature)

                result = {
                    "translated_text": "\n\n".join(translated_parts),
                    "provider_used": "claude+ollama",
                    "complexity": {"level": "complex", "score": score},
                    "fallback_reason": None,
                    "split_translation": True
                }

                # 如果需要翻译标题，单独用 Ollama 翻译
                if translate_subject and subject and not subject_translated:
                    try:
                        subject_translated = self.translate_with_ollama(subject, target_lang, source_lang)
                        result["subject_translated"] = subject_translated
                    except Exception as e:
                        print(f"[SmartRouting] Subject translation failed: {e}")

                return result

        except Exception as e:
            print(f"[SmartRouting] Split translation failed: {e}")

        # 拆分失败，整体用 Claude 翻译
        result = self._translate_with_claude_fallback(text, target_lang, source_lang, glossary,
                                                       {"level": "complex", "score": score})

        # 如果需要翻译标题，单独用 Ollama 翻译
        if translate_subject and subject:
            try:
                subject_translated = self.translate_with_ollama(subject, target_lang, source_lang)
                result["subject_translated"] = subject_translated
            except Exception as e:
                print(f"[SmartRouting] Subject translation failed: {e}")

        return result

    def _translate_with_ollama_or_fallback(self, text: str, target_lang: str,
                                            source_lang: str, glossary: List[Dict] = None) -> str:
        """Ollama 翻译，失败则用 Claude 回退"""
        # 首选 Ollama（免费，质量好）
        if self.ollama_base_url:
            try:
                return self.translate_with_ollama(text, target_lang, source_lang, glossary)
            except Exception as e:
                print(f"[SmartRouting] Ollama failed: {e}")

        # 回退到 Claude
        claude_key = self.api_key or os.environ.get("CLAUDE_API_KEY")
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

        raise Exception("Ollama 和 Claude 都不可用")

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

        # Claude 不可用，回退到 Ollama
        return self._translate_with_ollama_or_fallback(text, target_lang, source_lang, glossary)

    def _translate_with_fallback(self, text: str, target_lang: str, source_lang: str,
                                  glossary: List[Dict], complexity: Dict) -> Dict:
        """带回退的翻译（Ollama → Claude，跳过腾讯和DeepL）

        对于邮件链，只翻译最新内容，历史引用保持原样
        """
        providers_tried = []

        # 检查是否是邮件链，提取最新内容
        latest_content, quoted_content = self.extract_latest_email(text)
        has_quote = bool(quoted_content)

        if has_quote:
            print(f"[SmartRouting] 检测到邮件链: 最新内容 {len(latest_content)} 字符, 引用 {len(quoted_content)} 字符")
            text_to_translate = latest_content
        else:
            text_to_translate = text

        # 1. Ollama 优先（免费，质量好）
        if self.ollama_base_url:
            try:
                # 传递复杂度分数，决定是否启用 think 模式
                complexity_score = complexity.get("score") if complexity else None
                translated = self.translate_with_ollama(text_to_translate, target_lang, source_lang, glossary,
                                                         complexity_score=complexity_score)

                # 如果有引用，拼接回去
                if has_quote:
                    translated = translated + "\n\n---\n[以下为历史邮件引用]\n" + quoted_content

                return {
                    "translated_text": translated,
                    "provider_used": "ollama",
                    "complexity": complexity,
                    "fallback_reason": None,
                    "has_quote": has_quote
                }
            except Exception as e:
                providers_tried.append(("ollama", str(e)))
                print(f"[SmartRouting] Ollama failed in fallback: {e}")

        # 2. Claude 兜底（同样只翻译最新内容）
        result = self._translate_with_claude_fallback(text_to_translate, target_lang, source_lang, glossary, complexity)

        # 如果有引用，拼接回去
        if has_quote:
            result["translated_text"] = result["translated_text"] + "\n\n---\n[以下为历史邮件引用]\n" + quoted_content
            result["has_quote"] = True

        return result

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

    def translate_email_reply(self, chinese_text: str, target_lang: str,
                              conversation_history: List[Dict] = None,
                              glossary: List[Dict] = None) -> str:
        """
        Translate Chinese reply to target language
        """
        return self.translate_text(chinese_text, target_lang, glossary, source_lang="zh")

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

    def close(self):
        """Close HTTP client"""
        self.http_client.close()
