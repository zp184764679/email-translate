"""
WebSocket 连接管理

提供实时推送功能，用于通知任务完成等事件
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
import json
import asyncio
from datetime import datetime


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 按账户ID存储活跃连接
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # 全局广播连接（管理员等）
        self.global_connections: List[WebSocket] = []
        # 心跳间隔（秒）
        self.heartbeat_interval = 30

    async def connect(self, websocket: WebSocket, account_id: Optional[int] = None):
        """
        接受 WebSocket 连接

        Args:
            websocket: WebSocket 连接
            account_id: 账户ID（用于按账户推送）
        """
        await websocket.accept()

        if account_id:
            if account_id not in self.active_connections:
                self.active_connections[account_id] = []
            self.active_connections[account_id].append(websocket)
            print(f"[WebSocket] Account {account_id} connected. Total: {len(self.active_connections[account_id])}")
        else:
            self.global_connections.append(websocket)
            print(f"[WebSocket] Global connection added. Total: {len(self.global_connections)}")

    def disconnect(self, websocket: WebSocket, account_id: Optional[int] = None):
        """
        断开 WebSocket 连接

        Args:
            websocket: WebSocket 连接
            account_id: 账户ID
        """
        if account_id and account_id in self.active_connections:
            if websocket in self.active_connections[account_id]:
                self.active_connections[account_id].remove(websocket)
                print(f"[WebSocket] Account {account_id} disconnected. Remaining: {len(self.active_connections[account_id])}")
                # 清理空列表
                if not self.active_connections[account_id]:
                    del self.active_connections[account_id]
        elif websocket in self.global_connections:
            self.global_connections.remove(websocket)
            print(f"[WebSocket] Global connection removed. Remaining: {len(self.global_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        发送消息到单个连接

        Args:
            message: 消息内容（字典）
            websocket: 目标连接
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"[WebSocket] Failed to send message: {e}")

    async def broadcast(self, account_id: int, event_type: str, data: dict):
        """
        广播消息到指定账户的所有连接

        Args:
            account_id: 目标账户ID
            event_type: 事件类型
            data: 事件数据
        """
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # 发送到账户的所有连接
        if account_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[account_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"[WebSocket] Failed to broadcast to account {account_id}: {e}")
                    disconnected.append(connection)

            # 清理断开的连接
            for conn in disconnected:
                self.disconnect(conn, account_id)

    async def broadcast_global(self, event_type: str, data: dict):
        """
        全局广播消息

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        disconnected = []
        for connection in self.global_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def get_connection_count(self, account_id: Optional[int] = None) -> int:
        """
        获取连接数量

        Args:
            account_id: 账户ID，如果为None则返回全局连接数

        Returns:
            连接数量
        """
        if account_id:
            return len(self.active_connections.get(account_id, []))
        return len(self.global_connections)

    def get_all_account_ids(self) -> List[int]:
        """获取所有活跃账户ID"""
        return list(self.active_connections.keys())


# 全局连接管理器实例
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, account_id: int):
    """
    WebSocket 端点处理函数

    Args:
        websocket: WebSocket 连接
        account_id: 账户ID
    """
    await manager.connect(websocket, account_id)

    try:
        while True:
            # 等待客户端消息
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=manager.heartbeat_interval + 10
                )

                # 处理心跳
                if data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                # 处理其他消息类型
                elif data.get("type") == "subscribe":
                    # 订阅特定事件
                    events = data.get("events", [])
                    print(f"[WebSocket] Account {account_id} subscribed to: {events}")

            except asyncio.TimeoutError:
                # 发送心跳检测
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        manager.disconnect(websocket, account_id)
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        manager.disconnect(websocket, account_id)
