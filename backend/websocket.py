"""
WebSocket 连接管理

提供实时推送功能，用于通知任务完成等事件
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Tuple
import base64
import asyncio
from datetime import datetime
import jwt
from config import get_settings


def verify_websocket_token(token: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    验证 WebSocket 连接的 JWT token

    Args:
        token: JWT token 字符串

    Returns:
        (is_valid, account_id, error_message)
    """
    if not token:
        return False, None, "Token is required"

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        account_id = payload.get("account_id")
        if account_id is None:
            return False, None, "Invalid token payload"
        return True, account_id, None
    except jwt.ExpiredSignatureError:
        return False, None, "Token has expired"
    except jwt.InvalidTokenError:
        return False, None, "Invalid token"
    except Exception as e:
        return False, None, f"Token verification failed: {str(e)}"


def extract_token_from_subprotocol(websocket: WebSocket) -> Optional[str]:
    """
    从 WebSocket subprotocol 中提取 token

    客户端使用 Sec-WebSocket-Protocol header 传递 token：
    格式：auth.<base64-encoded-token>

    这比 URL query 参数更安全，因为：
    1. 不会出现在 URL 或浏览器历史中
    2. 不会被记录在 HTTP 访问日志中
    3. 不会被缓存

    Args:
        websocket: WebSocket 连接

    Returns:
        提取的 JWT token，如果未找到则返回 None
    """
    # 获取请求的 subprotocols
    subprotocols = websocket.scope.get("subprotocols", [])

    for protocol in subprotocols:
        if protocol.startswith("auth."):
            try:
                # 提取 base64 编码的 token
                encoded_token = protocol[5:]  # 移除 "auth." 前缀
                # 补全 base64 padding
                padding = 4 - len(encoded_token) % 4
                if padding != 4:
                    encoded_token += "=" * padding
                # 解码
                token = base64.b64decode(encoded_token).decode('utf-8')
                return token
            except Exception as e:
                print(f"[WebSocket] Failed to decode token from subprotocol: {e}")
                return None

    return None


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 按账户ID存储活跃连接
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # 全局广播连接（管理员等）
        self.global_connections: List[WebSocket] = []
        # 心跳间隔（秒）
        self.heartbeat_interval = 30

    async def connect(self, websocket: WebSocket, account_id: Optional[int] = None, subprotocol: Optional[str] = None):
        """
        接受 WebSocket 连接

        Args:
            websocket: WebSocket 连接
            account_id: 账户ID（用于按账户推送）
            subprotocol: 接受的 subprotocol（用于 token 认证响应）
        """
        # 如果使用了 subprotocol 认证，需要在响应中确认
        await websocket.accept(subprotocol=subprotocol)

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


async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None, account_id: Optional[int] = None):
    """
    WebSocket 端点处理函数（带 JWT 认证）

    支持两种认证方式（优先级从高到低）：
    1. Subprotocol: Sec-WebSocket-Protocol header 中的 auth.<base64-token>（推荐，更安全）
    2. Query 参数: ?token=xxx（兼容旧版客户端）

    Args:
        websocket: WebSocket 连接
        token: JWT token（query 参数，兼容旧版）
        account_id: 账户ID（已弃用，不再使用）

    Security Note:
        - Subprotocol 方式更安全，token 不会出现在 URL 或日志中
        - Query 参数方式保留以兼容旧版客户端，建议尽快升级
    """
    # 优先从 subprotocol 提取 token（更安全）
    subprotocol_token = extract_token_from_subprotocol(websocket)
    final_token = subprotocol_token or token

    # 验证 token
    if final_token:
        is_valid, verified_account_id, error = verify_websocket_token(final_token)
        if not is_valid:
            await websocket.close(code=4001, reason=error or "Authentication failed")
            return
        account_id = verified_account_id
    else:
        # 没有 token 的连接被拒绝
        await websocket.close(code=4001, reason="Token is required")
        return

    # 如果使用了 subprotocol 认证，需要在响应中确认该 protocol
    accepted_protocol = None
    if subprotocol_token:
        # 找到客户端请求的 auth protocol 并确认
        subprotocols = websocket.scope.get("subprotocols", [])
        for protocol in subprotocols:
            if protocol.startswith("auth."):
                accepted_protocol = protocol
                break

    await manager.connect(websocket, account_id, subprotocol=accepted_protocol)

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
