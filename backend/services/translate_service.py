import httpx
from typing import List, Dict, Tuple
import re
import os


class TranslateService:
    """Translation service using local vLLM model

    使用本地 vLLM 大模型进行翻译，完全本地化，零 API 成本。
    通过 vLLM Gateway (OpenAI 兼容 API) 调用。
    """

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
        # NCR 常见缺陷组合词（重要！）
        "Dirt on Shaft": "轴污/轴脏污",
        "Scratch on Shaft": "轴划痕",
        "Rust on Shaft": "轴锈蚀",
        "Dent on Shaft": "轴凹痕",
        "Dirt on Surface": "表面脏污",
        "Scratch on Surface": "表面划痕",
        "Plating Defect": "电镀缺陷",
        "Surface Defect": "表面缺陷",
        "Dimension Out of Spec": "尺寸超差",
        "Out of Tolerance": "超差",

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

    def __init__(self, vllm_base_url: str = None, vllm_model: str = None,
                 vllm_api_key: str = None, **kwargs):
        """
        Initialize translate service (vLLM only)

        Args:
            vllm_base_url: vLLM API base URL (e.g., "http://localhost:5081")
            vllm_model: vLLM model name (e.g., "/home/aaa/models/Qwen3-VL-8B-Instruct")
            vllm_api_key: vLLM Gateway API key (e.g., "email_xxxxx")
        """
        self.vllm_base_url = vllm_base_url or "http://localhost:5081"
        self.vllm_model = vllm_model or "/home/aaa/models/Qwen3-VL-8B-Instruct"
        self.vllm_api_key = vllm_api_key or os.environ.get("VLLM_API_KEY")

        # vLLM headers (for Gateway authentication)
        self.vllm_headers = {}
        if self.vllm_api_key:
            self.vllm_headers["Authorization"] = f"Bearer {self.vllm_api_key}"

        # vLLM 本地模型需要较长的超时时间（600秒）
        self.http_client = httpx.Client(timeout=600.0, headers=self.vllm_headers)
        self.vllm_client = httpx.Client(timeout=600.0, headers=self.vllm_headers)

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

        original_translated = translated  # 保存原始结果，用于最小长度保护
        original_len = len(original.strip()) if original else 0

        # 1. 去除常见的前缀标记（安全操作，不会大幅缩短内容）
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

                        # 安全检查：只有当 after 部分足够长时才截取
                        # 要求：after 至少有原文 30% 的长度，或至少 100 字符
                        min_after_len = max(original_len * 0.3, 100)

                        # 如果前面主要是非中文（<10%），后面主要是中文（>30%），且后面够长
                        if before_ratio < 0.1 and after_ratio > 0.3 and len(after) >= min_after_len:
                            print(f"[TranslateClean] Separator split: keeping after part ({len(after)} chars)")
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

                # 计算截取后的内容长度
                after_lines = lines[first_chinese_line:]
                after_text = '\n'.join(after_lines)

                # 安全检查：截取后的内容至少要有原文 30% 的长度
                min_result_len = max(original_len * 0.3, 50)

                # 前面部分中文占比很低（<10%），很可能是原文重复，且截取后够长
                if chinese_ratio < 0.1 and len(before_text) > 20 and len(after_text) >= min_result_len:
                    print(f"[TranslateClean] Removing non-Chinese prefix ({len(before_text)} chars)")
                    translated = after_text

        # 4. 检查是否原文完整重复出现在开头
        original_stripped = original.strip() if original else ""
        if len(original_stripped) > 50:  # 只处理较长的原文（避免短文本误判）
            if translated.startswith(original_stripped):
                remaining = translated[len(original_stripped):].strip()
                # 安全检查：剩余部分至少有原文 30% 的长度
                if len(remaining) >= original_len * 0.3:
                    print(f"[TranslateClean] Removing duplicate original text from start")
                    translated = remaining

        # 5. 去除开头的空行和分隔符（安全操作）
        translated = translated.lstrip('\n')
        translated = re.sub(r'^[\-=\*—#]+\s*\n*', '', translated)  # 去除开头的分隔符行

        # 6. 最终安全检查：如果清理后太短，返回原始结果
        # 翻译结果不应该比原文短太多（至少 25%）
        min_acceptable_len = max(original_len * 0.25, 20)
        if len(translated.strip()) < min_acceptable_len and len(original_translated) > len(translated):
            print(f"[TranslateClean] WARNING: Cleaned result too short ({len(translated)} vs original {original_len}), returning unclean result")
            return original_translated

        return translated

    def _build_translation_prompt(self, text: str, target_lang: str, source_lang: str = None,
                                   glossary: List[Dict] = None, use_think: bool = True,
                                   is_short_text: bool = False, is_long_text: bool = False) -> str:
        """构建优化后的翻译 prompt（基于邮件样本分析优化）

        Args:
            use_think: 是否使用 /think 模式（vLLM 不支持，始终禁用）
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

        # /think 前缀（vLLM 不支持）
        think_prefix = "/think\n" if use_think else ""

        # 完整版提示词（采购行业深度优化）
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

## NCR 缺陷术语翻译（非常重要！常见于品质不良邮件主题）
- "Dirt on Shaft" = "轴污/轴脏污"（不是"轴上的泥土"！）
- "Scratch on Shaft" = "轴划痕"
- "Rust on Shaft" = "轴锈蚀"
- "Dent on Shaft" = "轴凹痕"
- "Dirt on Surface" = "表面脏污"
- "Scratch on Surface" = "表面划痕"
- "Plating Defect" = "电镀缺陷"
- "Surface Defect" = "表面缺陷"
- "Dimension Out of Spec" = "尺寸超差"
- "Out of Tolerance" = "超差"

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

    # ============ vLLM Translation (OpenAI 兼容 API) ============
    def translate_with_vllm(self, text: str, target_lang: str = "zh",
                             source_lang: str = None, glossary: List[Dict] = None,
                             complexity_score: int = None) -> str:
        """
        Translate text using local vLLM model (OpenAI compatible API)

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            source_lang: Source language (auto-detect if None)
            glossary: List of term mappings for context
            complexity_score: Optional complexity score (0-100) from smart routing
        """
        # 空文本检查
        if not text:
            return ""
        text_len = len(text)
        # 短文本（<100字符且无换行）使用简化的严格 prompt，防止 LLM 过度扩展
        is_short_text = text_len < 100 and '\n' not in text
        # 长文本判断
        is_long_text = text_len > 8000

        # vLLM 不支持 think 模式，始终禁用
        use_think = False

        prompt = self._build_translation_prompt(text, target_lang, source_lang, glossary,
                                                 use_think=use_think,
                                                 is_short_text=is_short_text,
                                                 is_long_text=is_long_text)

        # 动态计算 max_tokens：翻译到中文通常输出比英文短（约 0.6-0.8 倍）
        # 但我们给足够的空间，防止截断
        # 估算：1 个英文字符约 0.3 token，中文约 0.5 token
        estimated_tokens = max(4096, int(text_len * 0.8))
        # 限制最大值防止内存爆炸
        max_tokens = min(estimated_tokens, 16384)

        try:
            # 使用专用的 vLLM 客户端（超时更长）
            client = getattr(self, 'vllm_client', self.http_client)
            response = client.post(
                f"{self.vllm_base_url}/v1/chat/completions",
                json={
                    "model": self.vllm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()

            result = response.json()
            translated = result["choices"][0]["message"]["content"].strip()

            # 去除可能的原文重复（模型有时会输出原文+译文）
            translated = self._clean_translation_output(translated, text, target_lang)

            print(f"[vLLM/{self.vllm_model}] Translated to {target_lang}")
            return translated

        except httpx.HTTPStatusError as e:
            print(f"vLLM API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"vLLM translation error: {e}")
            raise

    # ============ Main Translation Method ============
    def translate_text(self, text: str, target_lang: str = "zh",
                       glossary: List[Dict] = None, context: str = None,
                       source_lang: str = None, **kwargs) -> str:
        """
        Translate text using vLLM (main entry point)

        Args:
            text: Text to translate
            target_lang: Target language (zh, en, ja)
            glossary: List of term mappings
            context: Previous conversation context
            source_lang: Source language hint

        Returns:
            Translated text
        """
        if not text:
            return ""
        return self.translate_with_vllm(text, target_lang, source_lang, glossary)

    def translate_with_smart_routing(self, text: str, subject: str = "",
                                      target_lang: str = "zh",
                                      glossary: List[Dict] = None,
                                      source_lang: str = None,
                                      translate_subject: bool = True) -> Dict:
        """
        翻译邮件（使用 vLLM 本地模型）

        Args:
            text: 邮件正文
            subject: 邮件标题
            target_lang: 目标语言
            glossary: 术语表
            source_lang: 源语言
            translate_subject: 是否同时翻译标题

        Returns:
            {
                "translated_text": str,
                "subject_translated": str,
                "provider_used": "vllm",
                "complexity": {"level", "score"},
                "fallback_reason": None
            }
        """
        from services.email_analyzer import get_email_analyzer, ComplexityLevel

        # 评估复杂度（仅用于日志）
        try:
            analyzer = get_email_analyzer(self.vllm_base_url, self.vllm_model)
            complexity, score = analyzer.quick_complexity_check(text, subject)
            print(f"[Translate] Complexity: {complexity.value} (score={score})")
        except Exception as e:
            print(f"[Translate] Complexity check failed: {e}, defaulting to MEDIUM")
            complexity = ComplexityLevel.MEDIUM
            score = 50

        # 统一使用 vLLM 翻译
        subject_translated = None

        # 翻译正文
        body_translated = self.translate_with_vllm(
            text, target_lang, source_lang, glossary,
            complexity_score=score
        )

        # 翻译标题
        if translate_subject and subject:
            subject_translated = self.translate_with_vllm(
                subject, target_lang, source_lang, glossary,
                complexity_score=score
            )

        result = {
            "translated_text": body_translated,
            "provider_used": "vllm",
            "complexity": {"level": complexity.value, "score": score},
            "fallback_reason": None
        }
        if subject_translated:
            result["subject_translated"] = subject_translated

        return result

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

    def translate_quoted_content(self, quoted: str, target_lang: str = "zh",
                                  source_lang: str = None) -> str:
        """
        翻译引用内容（带 > 前缀的邮件回复链）

        处理流程：
        1. 去除 > 前缀
        2. 翻译纯文本
        3. 重新添加 > 前缀保持引用格式

        Args:
            quoted: 引用内容（可能带 > 前缀）
            target_lang: 目标语言
            source_lang: 源语言

        Returns:
            翻译后的引用内容（带 > 前缀）
        """
        if not quoted or not quoted.strip():
            return ""

        # 去除 > 前缀，保存每行是否有前缀
        lines = quoted.split('\n')
        clean_lines = []
        line_prefixes = []  # 记录每行的前缀

        for line in lines:
            stripped = line.lstrip()
            # 检测引用前缀（可能有多层：> > >）
            prefix = ""
            while stripped.startswith('>'):
                prefix += '> '
                stripped = stripped[1:].lstrip()

            line_prefixes.append(prefix)
            clean_lines.append(stripped)

        # 合并纯文本进行翻译
        clean_text = '\n'.join(clean_lines)

        # 跳过太短或空的内容
        if len(clean_text.strip()) < 10:
            return quoted  # 内容太少，保持原样

        # 翻译
        try:
            translated = self.translate_text(clean_text, target_lang, source_lang=source_lang)
        except Exception as e:
            print(f"[TranslateQuoted] Failed to translate quoted content: {e}")
            return quoted  # 翻译失败，返回原文

        # 重新添加 > 前缀
        translated_lines = translated.split('\n')
        result_lines = []

        # 尽量匹配原始行数
        max_lines = max(len(line_prefixes), len(translated_lines))
        for i in range(max_lines):
            prefix = line_prefixes[i] if i < len(line_prefixes) else '> '
            content = translated_lines[i] if i < len(translated_lines) else ''

            if content.strip():
                result_lines.append(f"{prefix}{content}")
            else:
                result_lines.append("")  # 保留空行

        return '\n'.join(result_lines)

    def close(self):
        """Close HTTP client"""
        self.http_client.close()
