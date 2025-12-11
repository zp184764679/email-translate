"""
通知服务

提供统一的通知接口，支持：
- WebSocket 实时推送
- 可扩展支持其他通知方式（邮件、推送等）
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio


class NotificationManager:
    """
    通知管理器

    负责将消息路由到不同的通知通道
    """

    def __init__(self):
        self._websocket_manager = None
        self._initialized = False

    @property
    def websocket_manager(self):
        """延迟加载 WebSocket 管理器（避免循环导入）"""
        if self._websocket_manager is None:
            from websocket import manager
            self._websocket_manager = manager
        return self._websocket_manager

    async def broadcast(self, account_id: int, event_type: str, data: dict):
        """
        向指定账户广播消息

        Args:
            account_id: 目标账户ID
            event_type: 事件类型
            data: 事件数据
        """
        try:
            await self.websocket_manager.broadcast(account_id, event_type, data)
        except Exception as e:
            print(f"[Notification] Failed to broadcast: {e}")

    async def broadcast_global(self, event_type: str, data: dict):
        """
        全局广播消息

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        try:
            await self.websocket_manager.broadcast_global(event_type, data)
        except Exception as e:
            print(f"[Notification] Failed to broadcast global: {e}")

    async def notify_translation_complete(
        self,
        account_id: int,
        email_id: int,
        provider: str,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        通知翻译完成

        Args:
            account_id: 账户ID
            email_id: 邮件ID
            provider: 使用的翻译引擎
            success: 是否成功
            error: 错误信息（如果失败）
        """
        event_type = "translation_complete" if success else "translation_failed"
        data = {
            "email_id": email_id,
            "provider": provider,
            "success": success
        }
        if error:
            data["error"] = error

        await self.broadcast(account_id, event_type, data)

    async def notify_email_sent(
        self,
        account_id: int,
        draft_id: int,
        to_address: str,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        通知邮件发送完成

        Args:
            account_id: 账户ID
            draft_id: 草稿ID
            to_address: 收件人地址
            success: 是否成功
            error: 错误信息
        """
        event_type = "email_sent" if success else "send_failed"
        data = {
            "draft_id": draft_id,
            "to": to_address,
            "success": success
        }
        if error:
            data["error"] = error

        await self.broadcast(account_id, event_type, data)

    async def notify_fetch_progress(
        self,
        account_id: int,
        current: int,
        total: int,
        new_count: int
    ):
        """
        通知邮件拉取进度

        Args:
            account_id: 账户ID
            current: 当前进度
            total: 总数
            new_count: 新邮件数量
        """
        await self.broadcast(account_id, "fetch_progress", {
            "current": current,
            "total": total,
            "progress": int(current / total * 100) if total > 0 else 0,
            "new_count": new_count
        })

    async def notify_fetch_complete(
        self,
        account_id: int,
        new_count: int,
        total_count: int,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        通知邮件拉取完成

        Args:
            account_id: 账户ID
            new_count: 新邮件数量
            total_count: 总处理数量
            success: 是否成功
            error: 错误信息
        """
        event_type = "fetch_complete" if success else "fetch_failed"
        data = {
            "new_count": new_count,
            "total_count": total_count,
            "success": success
        }
        if error:
            data["error"] = error

        await self.broadcast(account_id, event_type, data)

    async def notify_extraction_complete(
        self,
        account_id: int,
        email_id: int,
        data: dict,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        通知 AI 提取完成

        Args:
            account_id: 账户ID
            email_id: 邮件ID
            data: 提取的数据
            success: 是否成功
            error: 错误信息
        """
        event_type = "extraction_complete" if success else "extraction_failed"
        payload = {
            "email_id": email_id,
            "success": success,
            "data": data if success else None
        }
        if error:
            payload["error"] = error

        await self.broadcast(account_id, event_type, payload)

    async def notify_batch_complete(
        self,
        account_id: int,
        batch_type: str,
        total: int,
        completed: int,
        failed: int
    ):
        """
        通知批量操作完成

        Args:
            account_id: 账户ID
            batch_type: 批量操作类型（translate, extract, export）
            total: 总数
            completed: 成功数
            failed: 失败数
        """
        await self.broadcast(account_id, f"batch_{batch_type}_complete", {
            "total": total,
            "completed": completed,
            "failed": failed,
            "success_rate": int(completed / total * 100) if total > 0 else 0
        })

    async def notify_export_ready(
        self,
        account_id: int,
        download_url: str,
        file_size: int,
        email_count: int
    ):
        """
        通知导出完成

        Args:
            account_id: 账户ID
            download_url: 下载链接
            file_size: 文件大小（字节）
            email_count: 导出邮件数量
        """
        await self.broadcast(account_id, "export_ready", {
            "download_url": download_url,
            "file_size": file_size,
            "email_count": email_count
        })


# 全局通知管理器实例
notification_manager = NotificationManager()


# 便捷函数
async def notify(account_id: int, event_type: str, data: dict):
    """
    发送通知的便捷函数

    Args:
        account_id: 账户ID
        event_type: 事件类型
        data: 事件数据
    """
    await notification_manager.broadcast(account_id, event_type, data)


def notify_sync(account_id: int, event_type: str, data: dict):
    """
    同步发送通知（用于 Celery 任务中）

    Args:
        account_id: 账户ID
        event_type: 事件类型
        data: 事件数据
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果已有事件循环，创建任务
            asyncio.create_task(
                notification_manager.broadcast(account_id, event_type, data)
            )
        else:
            # 否则运行同步
            loop.run_until_complete(
                notification_manager.broadcast(account_id, event_type, data)
            )
    except RuntimeError:
        # 没有事件循环，创建新的
        asyncio.run(notification_manager.broadcast(account_id, event_type, data))
