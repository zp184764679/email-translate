"""
邮件复杂度评估服务

智能路由策略：
- 简单邮件 → Ollama (免费)
- 中等邮件 → Claude Batch (半价)
- 复杂邮件 → DeepL / Claude 实时

评估方式：规则快筛 (70%) + 大模型兜底 (30%)
"""

import re
import httpx
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Tuple


class ComplexityLevel(Enum):
    """复杂度等级"""
    LOW = "low"         # 简单 → Ollama
    MEDIUM = "medium"   # 中等 → Claude Batch
    HIGH = "high"       # 复杂 → DeepL/Claude 实时


@dataclass
class ComplexityResult:
    """复杂度评估结果"""
    level: ComplexityLevel
    score: int          # 1-5 分
    reason: str         # 评估理由
    method: str         # 评估方式: "rule" 或 "model"


class ComplexityService:
    """邮件复杂度评估服务"""

    # 简单邮件关键词（多语言）
    SIMPLE_PATTERNS = [
        # 英文
        r'\b(thanks?|thank you|regards|best regards|sincerely|cheers)\b',
        r'\b(received|confirmed|noted|ok|okay|got it|will do)\b',
        r'\b(hello|hi|dear|good morning|good afternoon)\b',
        # 常见简短回复
        r'^(ok|yes|no|sure|agreed|approved)\.?$',
    ]

    # 复杂邮件关键词
    COMPLEX_PATTERNS = [
        # 技术/规格相关
        r'\b(specification|tolerance|dimension|parameter|technical)\b',
        r'\b(drawing|blueprint|schematic|diagram)\b',
        # 商务/合同相关
        r'\b(contract|agreement|terms|conditions|clause)\b',
        r'\b(quotation|quote|pricing|cost breakdown|unit price)\b',
        r'\b(warranty|liability|indemnity|penalty)\b',
        # 质量/问题相关
        r'\b(NCR|non.?conformance|defect|failure|reject)\b',
        r'\b(root cause|corrective action|8D|CAPA)\b',
        # 数字密集（可能是报价单/规格表）
        r'(\d+\.?\d*\s*(mm|cm|kg|pcs|USD|EUR|RMB)){3,}',
    ]

    # 签名档特征
    SIGNATURE_PATTERNS = [
        r'(best regards|kind regards|sincerely|yours truly)',
        r'(tel:|phone:|mobile:|fax:|email:)',
        r'(address:|website:|www\.)',
    ]

    def __init__(self, ollama_base_url: str = "http://172.24.228.215:11434",
                 ollama_model: str = "qwen3:8b"):
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.http_client = httpx.Client(timeout=60.0)

    def evaluate(self, text: str, subject: str = "") -> ComplexityResult:
        """
        评估邮件复杂度

        Args:
            text: 邮件正文
            subject: 邮件主题

        Returns:
            ComplexityResult: 复杂度评估结果
        """
        combined_text = f"{subject}\n{text}".lower()

        # 第一步：规则快筛
        rule_result = self._evaluate_by_rules(text, subject)
        if rule_result is not None:
            return rule_result

        # 第二步：大模型兜底
        return self._evaluate_by_model(text, subject)

    def _evaluate_by_rules(self, text: str, subject: str) -> Optional[ComplexityResult]:
        """规则快筛"""
        combined = f"{subject}\n{text}"
        combined_lower = combined.lower()
        text_length = len(text)

        # === 规则0: 优先检查复杂邮件特征（避免被简单规则误判）===
        complex_matches = sum(1 for p in self.COMPLEX_PATTERNS
                             if re.search(p, combined_lower, re.IGNORECASE))

        # 复杂特征 >= 2 个，或者主题包含复杂关键词
        subject_complex = any(kw in subject.lower() for kw in
                             ['ncr', 'specification', 'quotation', 'contract', 'technical'])
        if complex_matches >= 2 or (complex_matches >= 1 and subject_complex):
            return ComplexityResult(
                level=ComplexityLevel.HIGH,
                score=5 if complex_matches >= 3 else 4,
                reason=f"包含{complex_matches}个复杂邮件特征（技术/商务术语）",
                method="rule"
            )

        # === 规则1: 超短邮件 → 简单 ===
        if text_length < 100:
            return ComplexityResult(
                level=ComplexityLevel.LOW,
                score=1,
                reason="邮件很短（<100字符）",
                method="rule"
            )

        # === 规则2: 纯签名档 → 简单 ===
        if self._is_mostly_signature(text):
            return ComplexityResult(
                level=ComplexityLevel.LOW,
                score=1,
                reason="主要是签名档",
                method="rule"
            )

        # === 规则3: 简单问候/确认邮件 → 简单 ===
        simple_matches = sum(1 for p in self.SIMPLE_PATTERNS
                            if re.search(p, combined_lower, re.IGNORECASE))
        if simple_matches >= 2 and text_length < 500:
            return ComplexityResult(
                level=ComplexityLevel.LOW,
                score=2,
                reason=f"包含{simple_matches}个简单邮件特征",
                method="rule"
            )

        # === 规则4: 超长邮件 → 复杂 ===
        if text_length > 5000:
            return ComplexityResult(
                level=ComplexityLevel.HIGH,
                score=4,
                reason="邮件很长（>5000字符）",
                method="rule"
            )

        # === 规则5: 中等长度 + 表格/列表结构 → 中等 ===
        if self._has_table_structure(text):
            return ComplexityResult(
                level=ComplexityLevel.MEDIUM,
                score=3,
                reason="包含表格或列表结构",
                method="rule"
            )

        # === 规则6: 中等长度普通邮件 → 中等 ===
        if text_length > 500:
            return ComplexityResult(
                level=ComplexityLevel.MEDIUM,
                score=3,
                reason="中等长度邮件",
                method="rule"
            )

        # 规则无法判定，返回 None 交给模型
        return None

    def _evaluate_by_model(self, text: str, subject: str) -> ComplexityResult:
        """大模型评估（兜底）"""
        prompt = f"""你是邮件复杂度评估专家。请评估以下邮件的翻译难度。

## 评估标准
- 1-2分（简单）：问候、确认、简短回复、签名
- 3分（中等）：普通业务沟通、订单确认、物流信息
- 4-5分（复杂）：技术规格、合同条款、质量问题分析、报价单

## 邮件主题
{subject}

## 邮件正文
{text[:2000]}

## 请直接输出JSON格式（不要输出其他内容）
{{"score": 数字1-5, "reason": "简短理由"}}"""

        try:
            response = self.http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            result_text = response.json().get("response", "")

            # 去除思考标签
            result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL)

            # 解析 JSON
            json_match = re.search(r'\{[^}]+\}', result_text)
            if json_match:
                import json
                data = json.loads(json_match.group())
                score = int(data.get("score", 3))
                reason = data.get("reason", "模型评估")

                # 分数映射到等级
                if score <= 2:
                    level = ComplexityLevel.LOW
                elif score <= 3:
                    level = ComplexityLevel.MEDIUM
                else:
                    level = ComplexityLevel.HIGH

                return ComplexityResult(
                    level=level,
                    score=score,
                    reason=reason,
                    method="model"
                )
        except Exception as e:
            print(f"[ComplexityService] Model evaluation error: {e}")

        # 模型调用失败，默认返回中等
        return ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            score=3,
            reason="模型评估失败，默认中等",
            method="fallback"
        )

    def _is_mostly_signature(self, text: str) -> bool:
        """判断是否主要是签名档"""
        lines = text.strip().split('\n')
        if len(lines) < 3:
            return False

        # 统计签名特征行数
        sig_lines = 0
        for line in lines:
            line_lower = line.lower()
            for pattern in self.SIGNATURE_PATTERNS:
                if re.search(pattern, line_lower):
                    sig_lines += 1
                    break

        # 超过 50% 是签名特征
        return sig_lines / len(lines) > 0.5

    def _has_table_structure(self, text: str) -> bool:
        """判断是否包含表格结构"""
        # 检测制表符分隔或多个连续空格分隔的数据行
        lines = text.split('\n')
        table_like_lines = 0

        for line in lines:
            # 制表符分隔
            if '\t' in line and line.count('\t') >= 2:
                table_like_lines += 1
            # 多列数据（数字+单位组合）
            elif re.search(r'(\d+\.?\d*\s+){3,}', line):
                table_like_lines += 1

        return table_like_lines >= 3

    def get_recommended_provider(self, result: ComplexityResult) -> str:
        """根据复杂度推荐翻译引擎"""
        if result.level == ComplexityLevel.LOW:
            return "ollama"
        elif result.level == ComplexityLevel.MEDIUM:
            return "claude_batch"  # 或 ollama，取决于成本考量
        else:
            return "deepl"  # 或 claude


# 便捷函数
_service_instance: Optional[ComplexityService] = None

def get_complexity_service(ollama_base_url: str = None, ollama_model: str = None) -> ComplexityService:
    """获取单例服务"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ComplexityService(
            ollama_base_url=ollama_base_url or "http://172.24.228.215:11434",
            ollama_model=ollama_model or "qwen3:8b"
        )
    return _service_instance


def evaluate_complexity(text: str, subject: str = "") -> ComplexityResult:
    """快捷评估函数"""
    return get_complexity_service().evaluate(text, subject)
