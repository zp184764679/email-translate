"""
AI 供应商分类服务

使用本地 vLLM 模型分析供应商类型，基于：
1. 供应商名称关键词
2. 邮件内容主题词频
3. 产品/服务描述
4. 历史订单类型（如有）

分类类别：
- raw_material: 原材料供应商
- machining: 机加工供应商
- electronics: 电子元器件供应商
- packaging: 包装供应商
- logistics: 物流服务商
- service: 服务类供应商
- other: 其他
"""

import httpx
import re
import json
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


# 供应商类别定义
SUPPLIER_CATEGORIES = {
    "raw_material": {
        "name_cn": "原材料",
        "name_en": "Raw Material",
        "keywords": ["steel", "aluminum", "metal", "plastic", "rubber", "material", "raw",
                    "钢", "铝", "金属", "塑料", "橡胶", "材料", "原料"]
    },
    "machining": {
        "name_cn": "机加工",
        "name_en": "Machining",
        "keywords": ["machining", "cnc", "milling", "turning", "precision", "manufacturing",
                    "机加工", "数控", "铣", "车削", "精密", "制造", "五金"]
    },
    "electronics": {
        "name_cn": "电子",
        "name_en": "Electronics",
        "keywords": ["electronic", "circuit", "pcb", "chip", "semiconductor", "sensor",
                    "电子", "电路", "芯片", "半导体", "传感器", "元器件"]
    },
    "packaging": {
        "name_cn": "包装",
        "name_en": "Packaging",
        "keywords": ["package", "packaging", "box", "carton", "label", "print",
                    "包装", "纸箱", "标签", "印刷", "泡沫"]
    },
    "logistics": {
        "name_cn": "物流",
        "name_en": "Logistics",
        "keywords": ["logistics", "shipping", "freight", "transport", "delivery", "cargo",
                    "物流", "运输", "货运", "快递", "仓储"]
    },
    "service": {
        "name_cn": "服务",
        "name_en": "Service",
        "keywords": ["service", "consulting", "testing", "inspection", "certification",
                    "服务", "咨询", "检测", "认证", "审计"]
    },
    "other": {
        "name_cn": "其他",
        "name_en": "Other",
        "keywords": []
    }
}


@lru_cache()
def get_supplier_analysis_service():
    """获取供应商分析服务单例"""
    return SupplierAnalysisService()


class SupplierAnalysisService:
    """AI 供应商分类服务"""

    def __init__(self):
        from config import get_settings
        settings = get_settings()
        self.vllm_base_url = settings.vllm_base_url
        self.vllm_model = settings.vllm_model
        # 构建认证 headers
        headers = {}
        if settings.vllm_api_key:
            headers["Authorization"] = f"Bearer {settings.vllm_api_key}"
        self.http_client = httpx.AsyncClient(timeout=30.0, headers=headers)

    async def analyze_supplier(
        self,
        db: AsyncSession,
        supplier_id: int,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        分析单个供应商并返回分类结果

        Args:
            db: 数据库会话
            supplier_id: 供应商 ID
            force: 是否强制重新分析（忽略已有结果）

        Returns:
            分析结果字典
        """
        from database.models import Supplier, Email

        # 获取供应商信息
        result = await db.execute(
            select(Supplier).where(Supplier.id == supplier_id)
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            return {"error": "供应商不存在", "supplier_id": supplier_id}

        # 如果已有分类且非强制模式，直接返回
        if supplier.category and not force and not supplier.category_manual:
            return {
                "id": supplier_id,
                "supplier_id": supplier_id,
                "name": supplier.name,
                "category": supplier.category,
                "category_cn": SUPPLIER_CATEGORIES.get(supplier.category, {}).get("name_cn", supplier.category),
                "category_confidence": supplier.category_confidence,
                "category_reason": supplier.category_reason,
                "category_analyzed_at": supplier.category_analyzed_at.isoformat() if supplier.category_analyzed_at else None,
                "category_manual": supplier.category_manual,
                "status": "cached"
            }

        # 收集分析数据
        analysis_data = await self._collect_analysis_data(db, supplier)

        # 先尝试规则匹配
        rule_result = self._rule_based_classify(analysis_data)
        if rule_result["confidence"] >= 0.8:
            # 高置信度规则匹配，直接使用
            category = rule_result["category"]
            confidence = rule_result["confidence"]
            reason = rule_result["reason"]
            print(f"[SupplierAnalysis] Rule-based: {category} ({confidence:.2f})")
        else:
            # 调用 vLLM 进行 AI 分类
            ai_result = await self._vllm_classify(analysis_data)
            if ai_result["category"] != "unknown":
                category = ai_result["category"]
                confidence = ai_result["confidence"]
                reason = ai_result["reason"]
                print(f"[SupplierAnalysis] AI-based: {category} ({confidence:.2f})")
            else:
                # AI 也无法分类，使用规则结果或默认
                category = rule_result["category"] if rule_result["category"] != "unknown" else "other"
                confidence = rule_result["confidence"]
                reason = rule_result["reason"] or "无法自动分类，请手动设置"
                print(f"[SupplierAnalysis] Fallback: {category}")

        # 更新供应商分类
        supplier.category = category
        supplier.category_confidence = confidence
        supplier.category_reason = reason
        supplier.category_analyzed_at = datetime.utcnow()
        supplier.category_manual = False

        await db.commit()
        await db.refresh(supplier)

        return {
            "id": supplier_id,
            "supplier_id": supplier_id,
            "name": supplier.name,
            "category": category,
            "category_cn": SUPPLIER_CATEGORIES.get(category, {}).get("name_cn", category),
            "category_confidence": confidence,
            "category_reason": reason,
            "category_analyzed_at": supplier.category_analyzed_at.isoformat(),
            "category_manual": False,
            "status": "analyzed"
        }

    async def batch_analyze(
        self,
        db: AsyncSession,
        supplier_ids: Optional[List[int]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        批量分析供应商

        Args:
            db: 数据库会话
            supplier_ids: 供应商 ID 列表，None 表示分析所有未分类的
            force: 是否强制重新分析

        Returns:
            批量分析结果
        """
        from database.models import Supplier

        # 获取待分析的供应商
        query = select(Supplier)
        if supplier_ids:
            query = query.where(Supplier.id.in_(supplier_ids))
        elif not force:
            # 只分析未分类的
            query = query.where(Supplier.category.is_(None))

        result = await db.execute(query)
        suppliers = result.scalars().all()

        results = []
        success_count = 0
        error_count = 0

        for supplier in suppliers:
            try:
                analysis = await self.analyze_supplier(db, supplier.id, force=force)
                results.append(analysis)
                if analysis.get("status") in ["analyzed", "cached"]:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                results.append({
                    "supplier_id": supplier.id,
                    "supplier_name": supplier.name,
                    "error": str(e)
                })

        return {
            "total": len(suppliers),
            "success": success_count,
            "errors": error_count,
            "results": results
        }

    async def get_category_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        获取供应商分类统计

        Returns:
            分类统计信息
        """
        from database.models import Supplier

        # 统计各分类数量
        result = await db.execute(
            select(
                Supplier.category,
                func.count(Supplier.id).label("count")
            ).group_by(Supplier.category)
        )
        category_counts = {row.category or "unclassified": row.count for row in result}

        # 计算总数
        total = sum(category_counts.values())

        # 构建详细统计
        stats = []
        for cat_key, cat_info in SUPPLIER_CATEGORIES.items():
            count = category_counts.get(cat_key, 0)
            stats.append({
                "category": cat_key,
                "name_cn": cat_info["name_cn"],
                "name_en": cat_info["name_en"],
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0
            })

        # 添加未分类
        unclassified = category_counts.get("unclassified", 0) + category_counts.get(None, 0)
        stats.append({
            "category": "unclassified",
            "name_cn": "未分类",
            "name_en": "Unclassified",
            "count": unclassified,
            "percentage": round(unclassified / total * 100, 1) if total > 0 else 0
        })

        return {
            "total_suppliers": total,
            "stats": stats,
            "categories": SUPPLIER_CATEGORIES
        }

    async def set_manual_category(
        self,
        db: AsyncSession,
        supplier_id: int,
        category: str
    ) -> Dict[str, Any]:
        """
        手动设置供应商分类

        Args:
            db: 数据库会话
            supplier_id: 供应商 ID
            category: 分类代码

        Returns:
            更新结果
        """
        from database.models import Supplier

        if category not in SUPPLIER_CATEGORIES:
            return {"error": f"无效的分类: {category}"}

        result = await db.execute(
            select(Supplier).where(Supplier.id == supplier_id)
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            return {"error": "供应商不存在"}

        supplier.category = category
        supplier.category_confidence = 1.0
        supplier.category_reason = "人工设置"
        supplier.category_analyzed_at = datetime.utcnow()
        supplier.category_manual = True

        await db.commit()

        return {
            "id": supplier_id,
            "supplier_id": supplier_id,
            "name": supplier.name,
            "category": category,
            "category_cn": SUPPLIER_CATEGORIES[category]["name_cn"],
            "category_confidence": 1.0,
            "category_reason": "人工设置",
            "category_analyzed_at": supplier.category_analyzed_at.isoformat(),
            "category_manual": True,
            "status": "updated"
        }

    async def _collect_analysis_data(
        self,
        db: AsyncSession,
        supplier
    ) -> Dict[str, Any]:
        """收集用于分析的数据"""
        from database.models import Email

        # 获取该供应商的邮件样本
        result = await db.execute(
            select(Email)
            .where(Email.supplier_id == supplier.id)
            .order_by(Email.received_at.desc())
            .limit(10)
        )
        emails = result.scalars().all()

        # 提取邮件主题和内容样本
        subjects = []
        body_samples = []
        for email in emails:
            if email.subject_original:
                subjects.append(email.subject_original)
            if email.body_original:
                # 截取前500字符
                body_samples.append(email.body_original[:500])

        return {
            "supplier_name": supplier.name,
            "email_domain": supplier.email_domain or "",
            "notes": supplier.notes or "",
            "email_subjects": subjects[:5],  # 最多5个主题
            "email_samples": body_samples[:3]  # 最多3个样本
        }

    def _rule_based_classify(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于规则的分类

        使用关键词匹配进行快速分类
        """
        # 合并所有文本用于匹配
        text_to_match = " ".join([
            data["supplier_name"].lower(),
            data["email_domain"].lower(),
            data["notes"].lower(),
            " ".join(data.get("email_subjects", [])).lower()
        ])

        # 统计各分类的匹配得分
        scores = {}
        for cat_key, cat_info in SUPPLIER_CATEGORIES.items():
            if cat_key == "other":
                continue
            matches = sum(1 for kw in cat_info["keywords"] if kw.lower() in text_to_match)
            if matches > 0:
                scores[cat_key] = matches

        if not scores:
            return {
                "category": "unknown",
                "confidence": 0.0,
                "reason": None
            }

        # 找到最高得分的分类
        best_category = max(scores.keys(), key=lambda k: scores[k])
        best_score = scores[best_category]
        total_score = sum(scores.values())

        # 计算置信度（基于得分比例和绝对得分）
        confidence = min(0.5 + (best_score / max(total_score, 1)) * 0.3 + best_score * 0.05, 0.95)

        # 找到匹配的关键词
        matched_keywords = [
            kw for kw in SUPPLIER_CATEGORIES[best_category]["keywords"]
            if kw.lower() in text_to_match
        ]

        return {
            "category": best_category,
            "confidence": round(confidence, 2),
            "reason": f"关键词匹配: {', '.join(matched_keywords[:3])}"
        }

    async def _vllm_classify(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用 vLLM 进行 AI 分类
        """
        # 构建分析提示
        categories_desc = "\n".join([
            f"- {key}: {info['name_cn']}（{info['name_en']}）"
            for key, info in SUPPLIER_CATEGORIES.items()
        ])

        email_info = ""
        if data.get("email_subjects"):
            email_info = f"\n最近邮件主题：\n" + "\n".join(f"- {s}" for s in data["email_subjects"][:3])

        prompt = f"""你是供应商分类专家。请根据以下信息判断该供应商的类别。

供应商信息：
- 名称：{data['supplier_name']}
- 邮箱域名：{data['email_domain']}
- 备注：{data['notes'] or '无'}
{email_info}

可选类别：
{categories_desc}

请严格按照以下 JSON 格式输出，不要输出其他内容：
{{"category": "类别代码", "confidence": 0.0-1.0的置信度, "reason": "分类依据说明"}}

示例输出：
{{"category": "machining", "confidence": 0.85, "reason": "供应商名称包含五金、精密制造相关词汇"}}
"""

        try:
            response = await self.http_client.post(
                f"{self.vllm_base_url}/v1/chat/completions",
                json={
                    "model": self.vllm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 256
                }
            )
            response.raise_for_status()
            result = response.json()
            raw_response = result["choices"][0]["message"]["content"].strip()

            # 解析 JSON 响应
            return self._parse_classification_response(raw_response)

        except httpx.TimeoutException:
            print("[SupplierAnalysis] vLLM timeout")
            return {"category": "unknown", "confidence": 0.0, "reason": "AI 分析超时"}
        except httpx.ConnectError:
            print("[SupplierAnalysis] vLLM connection failed")
            return {"category": "unknown", "confidence": 0.0, "reason": "AI 服务不可用"}
        except Exception as e:
            print(f"[SupplierAnalysis] vLLM error: {e}")
            return {"category": "unknown", "confidence": 0.0, "reason": f"AI 分析错误: {str(e)}"}

    def _parse_classification_response(self, response: str) -> Dict[str, Any]:
        """解析 AI 分类响应"""
        # 尝试提取 JSON
        try:
            # 如果有 </think> 标签，取其后的内容
            if "</think>" in response:
                response = response.split("</think>")[-1].strip()

            # 查找 JSON 对象
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                category = data.get("category", "unknown")
                confidence = float(data.get("confidence", 0.5))
                reason = data.get("reason", "AI 分析")

                # 验证类别有效性
                if category not in SUPPLIER_CATEGORIES:
                    category = "other"

                return {
                    "category": category,
                    "confidence": min(max(confidence, 0.0), 1.0),
                    "reason": reason
                }
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[SupplierAnalysis] Parse error: {e}, response: {response[:100]}")

        return {"category": "unknown", "confidence": 0.0, "reason": "无法解析 AI 响应"}

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()
