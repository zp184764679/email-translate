"""
Claude Batch API 批量翻译服务

功能：
1. 收集未翻译邮件，创建批次
2. 提交到 Claude Batch API（价格减半）
3. 轮询检查批次状态
4. 处理结果，更新邮件翻译

优势：
- Batch API 价格是实时 API 的 50%
- 结合 Prompt Cache，可节省 ~95% 费用
- 适合后台批量处理非紧急翻译

使用场景：
- 定时任务自动翻译未读邮件
- 批量翻译历史邮件
"""

import httpx
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio
import aiomysql


class BatchTranslationService:
    """Claude Batch API 批量翻译服务"""

    BATCH_API_URL = "https://api.anthropic.com/v1/messages/batches"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("CLAUDE_API_KEY")
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            self.http_client = httpx.Client(proxy=proxy, timeout=120.0)
        else:
            self.http_client = httpx.Client(timeout=120.0)

        self.db_config = {
            'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
            'port': int(os.environ.get('MYSQL_PORT', 3306)),
            'user': os.environ.get('MYSQL_USER', 'root'),
            'password': os.environ.get('MYSQL_PASSWORD', ''),
            'db': os.environ.get('MYSQL_DATABASE', 'email_translate'),
            'charset': 'utf8mb4'
        }

    async def _get_connection(self):
        """获取数据库连接"""
        return await aiomysql.connect(**self.db_config)

    def _build_system_prompt(self, target_lang: str = "zh") -> str:
        """构建系统提示（与 translate_service 保持一致，支持 Prompt Cache）"""
        # 导入以复用相同的 prompt
        from services.translate_service import TranslateService
        service = TranslateService(provider="claude")
        return service._build_claude_system_prompt(target_lang)

    def _build_batch_request(self, custom_id: str, text: str,
                              target_lang: str = "zh") -> Dict:
        """
        构建单个批次请求

        Args:
            custom_id: 自定义 ID（用于匹配结果）
            text: 要翻译的文本
            target_lang: 目标语言

        Returns:
            JSONL 格式的请求对象
        """
        system_prompt = self._build_system_prompt(target_lang)
        user_message = f"请翻译以下邮件：\n\n{text}"

        return {
            "custom_id": custom_id,
            "params": {
                "model": self.model,
                "max_tokens": 4096,
                "system": [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}  # Batch 也支持 Prompt Cache
                    }
                ],
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            }
        }

    async def create_batch(self, items: List[Dict]) -> Dict:
        """
        创建批次并提交到 Claude

        Args:
            items: 待翻译项列表 [{"email_id": int, "text": str, "source_lang": str}, ...]

        Returns:
            {
                "batch_id": str,       # Claude 批次 ID
                "db_batch_id": int,    # 数据库批次 ID
                "total_requests": int,
                "status": str
            }
        """
        if not items:
            return {"error": "No items to translate"}

        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                # 1. 创建数据库批次记录
                await cur.execute('''
                    INSERT INTO translation_batches
                        (status, total_requests, created_at)
                    VALUES ('pending', %s, NOW())
                ''', (len(items),))
                db_batch_id = cur.lastrowid

                # 2. 构建 JSONL 请求
                requests = []
                for i, item in enumerate(items):
                    custom_id = f"batch_{db_batch_id}_item_{i}_email_{item['email_id']}"
                    request = self._build_batch_request(
                        custom_id=custom_id,
                        text=item['text'],
                        target_lang=item.get('target_lang', 'zh')
                    )
                    requests.append(request)

                    # 插入批次项记录
                    await cur.execute('''
                        INSERT INTO translation_batch_items
                            (batch_id, custom_id, email_id, source_text,
                             source_lang, target_lang, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                    ''', (
                        db_batch_id,
                        custom_id,
                        item['email_id'],
                        item['text'][:10000],  # 限制存储长度
                        item.get('source_lang'),
                        item.get('target_lang', 'zh')
                    ))

                await conn.commit()

                # 3. 提交到 Claude Batch API
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "message-batches-2024-09-24,prompt-caching-2024-07-31",
                    "content-type": "application/json"
                }

                # 将请求转为 JSONL 格式
                jsonl_content = "\n".join(json.dumps(req) for req in requests)

                response = self.http_client.post(
                    self.BATCH_API_URL,
                    headers=headers,
                    json={"requests": requests}
                )
                response.raise_for_status()

                result = response.json()
                claude_batch_id = result.get("id")
                status = result.get("processing_status", "in_progress")

                # 4. 更新数据库批次状态
                expires_at = datetime.utcnow() + timedelta(hours=24)
                await cur.execute('''
                    UPDATE translation_batches
                    SET batch_id = %s, status = %s, submitted_at = NOW(), expires_at = %s
                    WHERE id = %s
                ''', (claude_batch_id, status, expires_at, db_batch_id))
                await conn.commit()

                print(f"[BatchService] Created batch {claude_batch_id} with {len(items)} requests")

                return {
                    "batch_id": claude_batch_id,
                    "db_batch_id": db_batch_id,
                    "total_requests": len(items),
                    "status": status
                }

        except httpx.HTTPStatusError as e:
            print(f"[BatchService] API error: {e.response.status_code} - {e.response.text}")
            # 更新数据库状态为失败
            async with conn.cursor() as cur:
                await cur.execute('''
                    UPDATE translation_batches SET status = 'failed' WHERE id = %s
                ''', (db_batch_id,))
                await conn.commit()
            return {"error": str(e), "db_batch_id": db_batch_id}

        except Exception as e:
            print(f"[BatchService] Error creating batch: {e}")
            return {"error": str(e)}

        finally:
            conn.close()

    async def check_batch_status(self, batch_id: str) -> Dict:
        """
        检查批次状态

        Args:
            batch_id: Claude 批次 ID

        Returns:
            {
                "id": str,
                "processing_status": str,  # in_progress, ended, failed, expired, canceled
                "request_counts": {
                    "processing": int,
                    "succeeded": int,
                    "errored": int,
                    "canceled": int,
                    "expired": int
                }
            }
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "message-batches-2024-09-24"
        }

        try:
            response = self.http_client.get(
                f"{self.BATCH_API_URL}/{batch_id}",
                headers=headers
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            print(f"[BatchService] Error checking batch {batch_id}: {e}")
            return {"error": str(e)}

    async def get_batch_results(self, batch_id: str) -> List[Dict]:
        """
        获取批次结果

        Args:
            batch_id: Claude 批次 ID

        Returns:
            结果列表 [{custom_id, result}, ...]
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "message-batches-2024-09-24"
        }

        try:
            response = self.http_client.get(
                f"{self.BATCH_API_URL}/{batch_id}/results",
                headers=headers
            )
            response.raise_for_status()

            # 结果是 JSONL 格式
            results = []
            for line in response.text.strip().split("\n"):
                if line:
                    results.append(json.loads(line))

            return results

        except Exception as e:
            print(f"[BatchService] Error getting results for {batch_id}: {e}")
            return []

    async def process_batch_results(self, db_batch_id: int) -> Dict:
        """
        处理批次结果，更新邮件翻译

        Args:
            db_batch_id: 数据库批次 ID

        Returns:
            {
                "processed": int,
                "succeeded": int,
                "failed": int
            }
        """
        conn = await self._get_connection()
        processed = succeeded = failed = 0

        try:
            async with conn.cursor() as cur:
                # 获取批次信息
                await cur.execute('''
                    SELECT batch_id, status FROM translation_batches WHERE id = %s
                ''', (db_batch_id,))
                row = await cur.fetchone()

                if not row:
                    return {"error": "Batch not found"}

                claude_batch_id, status = row

                if not claude_batch_id:
                    return {"error": "Batch not submitted yet"}

                # 检查状态
                batch_status = await self.check_batch_status(claude_batch_id)
                processing_status = batch_status.get("processing_status")

                if processing_status != "ended":
                    return {
                        "status": processing_status,
                        "message": f"Batch still {processing_status}"
                    }

                # 获取结果
                results = await self.get_batch_results(claude_batch_id)

                for result in results:
                    processed += 1
                    custom_id = result.get("custom_id")
                    result_type = result.get("result", {}).get("type")

                    if result_type == "succeeded":
                        # 提取翻译结果
                        message = result.get("result", {}).get("message", {})
                        content = message.get("content", [{}])[0]
                        translated_text = content.get("text", "").strip()

                        # 获取 token 统计
                        usage = message.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)

                        # 更新批次项
                        await cur.execute('''
                            UPDATE translation_batch_items
                            SET translated_text = %s, status = 'succeeded',
                                input_tokens = %s, output_tokens = %s, completed_at = NOW()
                            WHERE custom_id = %s
                        ''', (translated_text, input_tokens, output_tokens, custom_id))

                        # 更新邮件翻译（如果有关联）
                        await cur.execute('''
                            SELECT email_id FROM translation_batch_items WHERE custom_id = %s
                        ''', (custom_id,))
                        item_row = await cur.fetchone()
                        if item_row and item_row[0]:
                            email_id = item_row[0]
                            await cur.execute('''
                                UPDATE emails
                                SET body_translated = %s, is_translated = 1
                                WHERE id = %s
                            ''', (translated_text, email_id))

                        succeeded += 1

                    else:
                        # 记录错误
                        error_msg = result.get("result", {}).get("error", {}).get("message", "Unknown error")
                        await cur.execute('''
                            UPDATE translation_batch_items
                            SET status = 'failed', error_message = %s, completed_at = NOW()
                            WHERE custom_id = %s
                        ''', (error_msg, custom_id))
                        failed += 1

                # 更新批次状态
                await cur.execute('''
                    UPDATE translation_batches
                    SET status = 'ended', completed_requests = %s, failed_requests = %s,
                        completed_at = NOW()
                    WHERE id = %s
                ''', (succeeded, failed, db_batch_id))

                await conn.commit()

                print(f"[BatchService] Processed batch {db_batch_id}: {succeeded} succeeded, {failed} failed")

                return {
                    "processed": processed,
                    "succeeded": succeeded,
                    "failed": failed
                }

        except Exception as e:
            print(f"[BatchService] Error processing results: {e}")
            return {"error": str(e)}

        finally:
            conn.close()

    async def collect_untranslated_emails(self, limit: int = 50) -> List[Dict]:
        """
        收集未翻译的邮件

        Args:
            limit: 最多收集数量

        Returns:
            [{email_id, text, source_lang}, ...]
        """
        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                # 查找未翻译且非中文的邮件
                await cur.execute('''
                    SELECT id, body_original, language_detected
                    FROM emails
                    WHERE is_translated = 0
                      AND language_detected IS NOT NULL
                      AND language_detected != 'zh'
                      AND body_original IS NOT NULL
                      AND body_original != ''
                    ORDER BY received_at DESC
                    LIMIT %s
                ''', (limit,))

                rows = await cur.fetchall()
                items = []

                for row in rows:
                    email_id, body, lang = row
                    if body and len(body.strip()) > 0:
                        items.append({
                            "email_id": email_id,
                            "text": body,
                            "source_lang": lang,
                            "target_lang": "zh"
                        })

                return items

        except Exception as e:
            print(f"[BatchService] Error collecting emails: {e}")
            return []

        finally:
            conn.close()

    async def run_batch_translation(self, limit: int = 50) -> Dict:
        """
        执行一次批量翻译（收集 + 提交）

        Args:
            limit: 最多处理邮件数

        Returns:
            创建批次的结果
        """
        items = await self.collect_untranslated_emails(limit)

        if not items:
            return {"message": "No untranslated emails found"}

        return await self.create_batch(items)

    async def poll_and_process_batches(self) -> Dict:
        """
        轮询检查所有进行中的批次，处理已完成的

        Returns:
            {
                "checked": int,
                "completed": int,
                "results": [...]
            }
        """
        conn = await self._get_connection()
        checked = completed = 0
        results = []

        try:
            async with conn.cursor() as cur:
                # 查找进行中的批次
                await cur.execute('''
                    SELECT id, batch_id FROM translation_batches
                    WHERE status IN ('submitted', 'in_progress')
                      AND batch_id IS NOT NULL
                ''')
                rows = await cur.fetchall()

            for row in rows:
                db_batch_id, claude_batch_id = row
                checked += 1

                # 检查状态
                status = await self.check_batch_status(claude_batch_id)
                processing_status = status.get("processing_status")

                if processing_status == "ended":
                    # 处理结果
                    result = await self.process_batch_results(db_batch_id)
                    results.append({
                        "batch_id": db_batch_id,
                        "result": result
                    })
                    completed += 1

                elif processing_status in ("failed", "expired", "canceled"):
                    # 更新失败状态
                    async with conn.cursor() as cur:
                        await cur.execute('''
                            UPDATE translation_batches SET status = %s WHERE id = %s
                        ''', (processing_status, db_batch_id))
                        await conn.commit()

            return {
                "checked": checked,
                "completed": completed,
                "results": results
            }

        except Exception as e:
            print(f"[BatchService] Error polling batches: {e}")
            return {"error": str(e)}

        finally:
            conn.close()

    def close(self):
        """关闭 HTTP 客户端"""
        self.http_client.close()


# 单例
_batch_service: Optional[BatchTranslationService] = None


def get_batch_service() -> BatchTranslationService:
    """获取批量翻译服务单例"""
    global _batch_service
    if _batch_service is None:
        _batch_service = BatchTranslationService()
    return _batch_service


# 便捷异步函数
async def run_batch_translation(limit: int = 50) -> Dict:
    """执行批量翻译"""
    return await get_batch_service().run_batch_translation(limit)


async def poll_batches() -> Dict:
    """轮询并处理批次"""
    return await get_batch_service().poll_and_process_batches()
