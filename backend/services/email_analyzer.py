"""
邮件分析服务 - 使用 Ollama 分析邮件结构和复杂度

功能：
1. 快速评估邮件复杂度（简单/中等/复杂）
2. 拆分邮件结构（发件人信息、正文、签名）
3. 根据复杂度决定翻译策略
"""

import httpx
import re
import json
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ComplexityLevel(Enum):
    """邮件复杂度等级"""
    SIMPLE = "simple"      # 简单：日常问候、简短确认
    MEDIUM = "medium"      # 中等：一般业务邮件
    COMPLEX = "complex"    # 复杂：技术文档、合同条款、多层嵌套


@dataclass
class EmailStructure:
    """邮件结构"""
    greeting: str = ""        # 问候语（如：Dear Mr. Wang）
    body: str = ""            # 正文内容
    signature: str = ""       # 签名块
    sender_info: str = ""     # 发件人信息（姓名、职位、公司等）


@dataclass
class AnalysisResult:
    """分析结果"""
    complexity: ComplexityLevel
    score: int                    # 0-100 复杂度分数
    structure: EmailStructure
    reason: str                   # 复杂度判断原因
    should_split: bool            # 是否需要拆分翻译


class EmailAnalyzer:
    """邮件分析器 - 使用 Ollama 本地模型"""

    def __init__(self, ollama_base_url: str = "http://localhost:11434",
                 ollama_model: str = "qwen3:8b"):
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.http_client = httpx.Client(timeout=60.0)

    def analyze_email(self, text: str, subject: str = "") -> AnalysisResult:
        """
        分析邮件，返回复杂度和结构

        Args:
            text: 邮件正文
            subject: 邮件主题

        Returns:
            AnalysisResult: 包含复杂度、结构、是否需要拆分
        """
        # 先用规则快速判断简单邮件（避免调用 LLM）
        quick_result = self._quick_analysis(text, subject)
        if quick_result:
            return quick_result

        # 复杂邮件用 Ollama 分析
        return self._llm_analysis(text, subject)

    def _quick_analysis(self, text: str, subject: str = "") -> Optional[AnalysisResult]:
        """
        快速规则分析 - 不调用 LLM

        简单邮件特征：
        - 长度 < 500 字符
        - 无表格、无列表
        - 无技术术语密集区
        """
        text_len = len(text)

        # 超短邮件直接判定为简单
        if text_len < 200:
            structure = self._extract_structure_by_rules(text)
            return AnalysisResult(
                complexity=ComplexityLevel.SIMPLE,
                score=10,
                structure=structure,
                reason="超短邮件（<200字符）",
                should_split=False
            )

        # 检查复杂特征
        complex_indicators = 0

        # 表格检测
        if re.search(r'\|.*\|.*\|', text) or re.search(r'\t.*\t', text):
            complex_indicators += 2

        # 列表检测（多个编号项）
        if len(re.findall(r'^\s*[\d]+[.、)]\s', text, re.MULTILINE)) > 3:
            complex_indicators += 1

        # 技术术语密度
        tech_terms = len(re.findall(
            r'\b(NCR|CPK|PCP|SPDA|AWB|ETD|ETA|QA|QC|PO|SIR|spec|tolerance|dimension)\b',
            text, re.IGNORECASE
        ))
        if tech_terms > 5:
            complex_indicators += 2

        # 长度因素
        if text_len > 2000:
            complex_indicators += 2
        elif text_len > 1000:
            complex_indicators += 1

        # 嵌套引用
        if text.count('>') > 10 or text.count('-----Original Message-----') > 0:
            complex_indicators += 1

        # 根据指标判断
        if complex_indicators == 0 and text_len < 500:
            structure = self._extract_structure_by_rules(text)
            return AnalysisResult(
                complexity=ComplexityLevel.SIMPLE,
                score=20,
                structure=structure,
                reason="短邮件，无复杂结构",
                should_split=False
            )

        if complex_indicators >= 4:
            # 复杂邮件，需要 LLM 分析结构
            return None

        if complex_indicators >= 2:
            structure = self._extract_structure_by_rules(text)
            return AnalysisResult(
                complexity=ComplexityLevel.MEDIUM,
                score=50,
                structure=structure,
                reason=f"中等复杂度（指标={complex_indicators}）",
                should_split=False
            )

        return None  # 需要 LLM 进一步分析

    def _extract_structure_by_rules(self, text: str) -> EmailStructure:
        """用规则提取邮件结构"""
        lines = text.strip().split('\n')
        structure = EmailStructure()

        if not lines:
            structure.body = text
            return structure

        # 提取问候语（前1-2行）
        greeting_patterns = [
            r'^(Dear|Hi|Hello|Hey|Good\s+(morning|afternoon|evening))',
            r'^(お世話になっております|いつもお世話になっております)',
            r'^(尊敬的|您好|你好)',
        ]

        for i, line in enumerate(lines[:3]):
            for pattern in greeting_patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    structure.greeting = '\n'.join(lines[:i + 1])
                    lines = lines[i + 1:]
                    break
            if structure.greeting:
                break

        # 提取签名（从后往前找）
        signature_patterns = [
            r'^(Best\s+regards|Kind\s+regards|Regards|Sincerely|Thanks|Thank\s+you)',
            r'^(よろしくお願い|宜しくお願い)',
            r'^(此致|祝好|谢谢)',
            r'^--+$',  # 分隔线
        ]

        signature_start = len(lines)
        for i in range(len(lines) - 1, max(len(lines) - 15, -1), -1):
            line = lines[i].strip()
            for pattern in signature_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    signature_start = i
                    break
            if signature_start != len(lines):
                break

        if signature_start < len(lines):
            structure.signature = '\n'.join(lines[signature_start:])
            structure.body = '\n'.join(lines[:signature_start])
        else:
            structure.body = '\n'.join(lines)

        return structure

    def _llm_analysis(self, text: str, subject: str = "") -> AnalysisResult:
        """使用 Ollama 分析复杂邮件（使用 /think 模式提高准确性）"""
        prompt = f"""/think
分析以下邮件，返回 JSON 格式结果。

邮件主题：{subject}
邮件内容：
{text[:3000]}  # 限制长度

请返回以下 JSON 格式（只返回JSON，不要其他内容）：
{{
    "complexity": "simple|medium|complex",
    "score": 0-100,
    "reason": "复杂度判断原因",
    "greeting": "问候语部分（如有）",
    "body": "正文主体部分",
    "signature": "签名部分（如有）",
    "should_split": true/false
}}

判断标准：
- simple (0-30分): 简短确认、日常问候、单一事项
- medium (31-70分): 一般业务邮件、多个事项
- complex (71-100分): 技术文档、合同条款、表格数据、多层嵌套引用

should_split: 只有 complex 级别且正文>500字符时才为 true"""

        try:
            response = self.http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1024
                    }
                }
            )
            response.raise_for_status()

            result_text = response.json().get("response", "")

            # 去除 qwen3 的思考标签
            result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL)
            result_text = result_text.strip()

            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                data = json.loads(json_match.group())

                complexity_map = {
                    "simple": ComplexityLevel.SIMPLE,
                    "medium": ComplexityLevel.MEDIUM,
                    "complex": ComplexityLevel.COMPLEX
                }

                return AnalysisResult(
                    complexity=complexity_map.get(data.get("complexity", "medium"), ComplexityLevel.MEDIUM),
                    score=data.get("score", 50),
                    structure=EmailStructure(
                        greeting=data.get("greeting", ""),
                        body=data.get("body", text),
                        signature=data.get("signature", "")
                    ),
                    reason=data.get("reason", "LLM分析"),
                    should_split=data.get("should_split", False)
                )

        except Exception as e:
            print(f"[EmailAnalyzer] LLM analysis failed: {e}")

        # 失败时返回默认中等复杂度
        return AnalysisResult(
            complexity=ComplexityLevel.MEDIUM,
            score=50,
            structure=self._extract_structure_by_rules(text),
            reason="LLM分析失败，使用默认值",
            should_split=False
        )

    def quick_complexity_check(self, text: str, subject: str = "") -> Tuple[ComplexityLevel, int]:
        """
        快速复杂度检查（不拆分结构）

        用于决定翻译策略，不需要完整分析
        """
        result = self._quick_analysis(text, subject)
        if result:
            return result.complexity, result.score

        # 需要 LLM 判断的情况，用简化 prompt（使用 /think 模式提高准确性）
        prompt = f"""/think
评估邮件复杂度，只返回一个数字（0-100）：
- 0-30: 简单（短邮件、单一事项）
- 31-70: 中等（一般业务）
- 71-100: 复杂（技术文档、表格、合同）

主题：{subject}
内容（前500字）：{text[:500]}

只返回数字："""

        try:
            response = self.http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 10}
                }
            )
            response.raise_for_status()

            result_text = response.json().get("response", "").strip()
            # 去除思考标签
            result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()

            # 提取数字
            score_match = re.search(r'\d+', result_text)
            if score_match:
                score = int(score_match.group())
                score = min(100, max(0, score))

                if score <= 30:
                    return ComplexityLevel.SIMPLE, score
                elif score <= 70:
                    return ComplexityLevel.MEDIUM, score
                else:
                    return ComplexityLevel.COMPLEX, score

        except Exception as e:
            print(f"[EmailAnalyzer] Quick check failed: {e}")

        return ComplexityLevel.MEDIUM, 50


# 单例
_analyzer: Optional[EmailAnalyzer] = None


def get_email_analyzer(ollama_base_url: str = None, ollama_model: str = None) -> EmailAnalyzer:
    """获取邮件分析器单例"""
    global _analyzer
    if _analyzer is None:
        import os
        _analyzer = EmailAnalyzer(
            ollama_base_url=ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=ollama_model or os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        )
    return _analyzer
