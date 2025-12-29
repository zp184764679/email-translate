"""
任务提取 Celery 任务

功能：
- extract_task_info_for_email: 从邮件中提取任务信息
- batch_extract_tasks: 批量提取任务信息

翻译完成后自动触发，结果存入 task_extractions 表
Portal 项目管理系统导入时直接读取，实现秒级响应
"""
import json
import re
import requests
from datetime import datetime
from celery.exceptions import SoftTimeLimitExceeded

from celery_app import celery_app
from tasks.translate_tasks import get_db_session, notify_completion


# 任务提取 Prompt 模板（同时支持项目和任务信息提取）
TASK_EXTRACTION_PROMPT = """请分析以下供应商邮件内容，提取项目和任务相关信息。

邮件主题：
{subject}

邮件正文：
{body}

【重要提取规则】
1. **项目名称提取规则**：
   - 优先从邮件主题中提取关键信息
   - NCR 邮件格式：如 "NCR: O-2507-03 JZC 2J3060 Dirt on Shaft" 应提取为 "NCR O-2507-03 2J3060 轴污问题"
   - 保留品番号（如 2J3060、2J1030）作为项目名称的一部分
   - 英文专业术语必须准确翻译成中文：
     * Dirt on Shaft = 轴污/轴脏污
     * Scratch = 划痕
     * Dent = 凹痕
     * Crack = 裂纹
     * Rust = 锈蚀
     * Burr = 毛刺
     * Dimension = 尺寸问题
     * Surface = 表面问题
     * Coating = 涂层问题

2. **品番号（part_number）提取规则**：
   - 格式通常为：字母+数字组合，如 2J3060、2J1030、OA-25-023
   - 可能出现在主题或正文中
   - 如有多个品番号，用逗号分隔

3. **订单号（order_no）提取规则**：
   - 格式如：PO-xxx、O-xxx-xx（如 O-2507-03）
   - NCR 编号也可作为 order_no

请识别邮件中涉及的项目和任务信息，并提取以下字段。如果某个字段无法确定，请设为 null。

返回严格的 JSON 格式（不要包含其他文字）：
{{
    "project_name": "项目名称（根据邮件主题和内容推断，必须包含品番号和问题中文描述，不超过50字）",
    "customer_name": "客户/供应商名称（发件人所在公司或邮件中提到的客户名）",
    "order_no": "订单号/PO号/NCR编号（如有）",
    "part_number": "品番号/部件号（如 2J3060，可能有多个用逗号分隔）",
    "title": "任务标题（简洁描述主要工作内容，包含品番号和问题描述，不超过50字）",
    "description": "任务详细描述（包含关键要求和背景信息）",
    "task_type": "任务类型",
    "priority": "优先级",
    "due_date": "截止日期（YYYY-MM-DD格式，如无明确日期则为null）",
    "start_date": "开始日期（YYYY-MM-DD格式，如无明确日期则为null）",
    "assignee_name": "负责人姓名（如邮件中提到具体人名）",
    "action_items": ["待办事项1", "待办事项2"],
    "confidence": {{
        "project_name": 0.8,
        "title": 0.9,
        "priority": 0.7
    }}
}}

任务类型可选值：
- ncr(品质问题): 包含 NCR、品质、不良、不合格等
- general(常规), design(设计), development(开发), testing(测试), review(审查), deployment(部署), documentation(文档), meeting(会议), other(其他)

优先级可选值：low(低), normal(普通), high(高), urgent(紧急)

判断优先级依据：
- urgent: 包含"紧急"、"立即"、"urgent"、"ASAP"、NCR 邮件
- high: 包含"重要"、"尽快"、"优先"等词
- normal: 普通工作邮件
- low: 非紧急事项、FYI 类邮件
"""


def call_vllm_extract(subject: str, body: str, settings) -> dict:
    """调用 vLLM 提取任务信息（OpenAI 兼容 API）"""
    prompt = TASK_EXTRACTION_PROMPT.format(
        subject=subject or "(无主题)",
        body=body or "(无正文)"
    )

    try:
        response = requests.post(
            f"{settings.vllm_base_url}/v1/chat/completions",
            json={
                "model": settings.vllm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 3000
            },
            timeout=300  # 5分钟超时
        )
        response.raise_for_status()

        result = response.json()
        response_text = result["choices"][0]["message"]["content"].strip()

        # 尝试解析 JSON
        # 有时 LLM 会返回 ```json ... ``` 格式
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            extracted = json.loads(json_match.group())
            return {
                "success": True,
                "data": extracted
            }
        else:
            return {
                "success": False,
                "error": "无法从 LLM 响应中解析 JSON",
                "raw_response": response_text[:500]
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "vLLM 请求超时"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "无法连接到 vLLM 服务"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 解析失败: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def parse_date(date_str: str) -> datetime:
    """解析日期字符串"""
    if not date_str:
        return None

    # 尝试多种格式
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y年%m月%d日",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


@celery_app.task(bind=True, max_retries=2, soft_time_limit=300, time_limit=360)
def extract_task_info_for_email(self, email_id: int, account_id: int = None):
    """
    从邮件中提取任务信息

    Args:
        email_id: 邮件ID
        account_id: 账户ID（用于WebSocket通知，可选）

    Returns:
        dict: 提取结果
    """
    from database.models import Email, TaskExtraction
    from config import get_settings

    settings = get_settings()
    db = get_db_session()

    try:
        # 1. 获取邮件
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            return {"success": False, "error": "Email not found", "email_id": email_id}

        # 2. 检查是否已有提取记录
        existing = db.query(TaskExtraction).filter(
            TaskExtraction.email_id == email_id
        ).first()

        if existing and existing.status == "completed":
            # 已完成提取，直接返回
            return {
                "success": True,
                "email_id": email_id,
                "cached": True,
                "data": existing.to_dict()
            }

        # 3. 创建或更新提取记录
        if not existing:
            extraction = TaskExtraction(
                email_id=email_id,
                status="processing"
            )
            db.add(extraction)
        else:
            extraction = existing
            extraction.status = "processing"
            extraction.error_message = None

        db.commit()

        # 4. 获取邮件内容（优先使用翻译后的内容）
        subject = email.subject_translated or email.subject_original or ""
        body = email.body_translated or email.body_original or ""

        # 5. 调用 vLLM 提取
        print(f"[TaskExtract] Extracting task info for email {email_id}...")
        result = call_vllm_extract(subject, body, settings)

        if not result.get("success"):
            # 提取失败
            extraction.status = "failed"
            extraction.error_message = result.get("error", "Unknown error")
            db.commit()

            if account_id:
                notify_completion(account_id, "task_extraction_failed", {
                    "email_id": email_id,
                    "error": extraction.error_message
                })

            return {
                "success": False,
                "email_id": email_id,
                "error": extraction.error_message
            }

        # 6. 解析并存储结果
        data = result.get("data", {})

        # 项目字段
        extraction.project_name = data.get("project_name")
        extraction.customer_name = data.get("customer_name")
        extraction.order_no = data.get("order_no")
        # 任务字段
        extraction.title = data.get("title")
        extraction.description = data.get("description")
        extraction.task_type = data.get("task_type", "general")
        extraction.priority = data.get("priority", "normal")
        extraction.due_date = parse_date(data.get("due_date"))
        extraction.start_date = parse_date(data.get("start_date"))
        extraction.part_number = data.get("part_number")
        extraction.assignee_name = data.get("assignee_name")
        extraction.action_items = data.get("action_items")
        extraction.confidence = data.get("confidence")
        extraction.status = "completed"
        extraction.extracted_at = datetime.utcnow()

        db.commit()

        print(f"[TaskExtract] Successfully extracted task info for email {email_id}")

        # 7. 发送完成通知
        if account_id:
            notify_completion(account_id, "task_extraction_complete", {
                "email_id": email_id,
                "success": True,
                "data": extraction.to_dict()
            })

        return {
            "success": True,
            "email_id": email_id,
            "data": extraction.to_dict()
        }

    except SoftTimeLimitExceeded:
        # 超时，标记为失败并重试
        try:
            extraction = db.query(TaskExtraction).filter(
                TaskExtraction.email_id == email_id
            ).first()
            if extraction:
                extraction.status = "failed"
                extraction.error_message = "提取超时"
                db.commit()
        except Exception as cleanup_err:
            print(f"[TaskExtract] Cleanup failed during timeout: {cleanup_err}")

        raise self.retry(countdown=30 * (2 ** self.request.retries))

    except Exception as e:
        db.rollback()
        print(f"[TaskExtract] Error extracting task for email {email_id}: {e}")

        # 更新状态为失败
        try:
            extraction = db.query(TaskExtraction).filter(
                TaskExtraction.email_id == email_id
            ).first()
            if extraction:
                extraction.status = "failed"
                extraction.error_message = str(e)[:500]
                db.commit()
        except Exception as cleanup_err:
            print(f"[TaskExtract] Cleanup failed: {cleanup_err}")

        if account_id:
            notify_completion(account_id, "task_extraction_failed", {
                "email_id": email_id,
                "error": str(e)
            })

        raise self.retry(exc=e, countdown=10)

    finally:
        db.close()


@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860)
def batch_extract_tasks(self, email_ids: list, account_id: int):
    """
    批量提取任务信息

    Args:
        email_ids: 邮件ID列表
        account_id: 账户ID（用于通知）

    Returns:
        dict: 批量提取结果
    """
    from celery import group
    import time

    total = len(email_ids)
    completed = 0
    failed = 0

    print(f"[BatchTaskExtract] Starting batch extraction: {total} emails")

    # 创建子任务组
    tasks = group(
        extract_task_info_for_email.s(email_id, account_id)
        for email_id in email_ids
    )

    # 执行
    result = tasks.apply_async()

    try:
        # 等待完成（最长30分钟）
        batch_results = result.get(timeout=1800)

        for r in batch_results:
            if r.get("success"):
                completed += 1
            else:
                failed += 1

    except Exception as e:
        print(f"[BatchTaskExtract] Error: {e}")
        failed = total - completed

    # 发送完成通知
    notify_completion(account_id, "batch_task_extraction_complete", {
        "total": total,
        "completed": completed,
        "failed": failed
    })

    print(f"[BatchTaskExtract] Completed: {completed}/{total} success, {failed} failed")

    return {
        "success": True,
        "total": total,
        "completed": completed,
        "failed": failed
    }
