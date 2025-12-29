"""
API 速率限制工具

提供基于内存的速率限制功能，用于保护敏感 API 端点。
"""
import time
from collections import defaultdict
from typing import Dict, Tuple
from functools import wraps
from fastapi import HTTPException, Request


class RateLimiter:
    """基于滑动窗口的速率限制器"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Args:
            max_requests: 时间窗口内允许的最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """检查是否允许请求

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.time()
        window_start = now - self.window_seconds

        # 清理过期记录
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        if len(self.requests[key]) >= self.max_requests:
            # 计算需要等待的时间
            oldest = min(self.requests[key])
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, retry_after

        # 记录本次请求
        self.requests[key].append(now)
        return True, 0

    def get_remaining(self, key: str) -> int:
        """获取剩余请求次数"""
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        return max(0, self.max_requests - len(self.requests[key]))

    def check(self, key: str) -> None:
        """检查速率限制，超限则抛出 HTTPException"""
        allowed, retry_after = self.is_allowed(key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请 {retry_after} 秒后重试",
                headers={"Retry-After": str(retry_after)}
            )


def get_client_ip(request: Request) -> str:
    """获取客户端 IP 地址"""
    # 优先使用 X-Forwarded-For（反向代理场景）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # 其次使用 X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # 最后使用直接连接 IP
    return request.client.host if request.client else "unknown"


# ============ 预定义的速率限制器实例 ============

# 登录：每 IP 每分钟 5 次
login_limiter = RateLimiter(max_requests=5, window_seconds=60)

# 翻译：每用户每分钟 30 次
translate_limiter = RateLimiter(max_requests=30, window_seconds=60)

# 邮件发送：每用户每分钟 10 次
send_limiter = RateLimiter(max_requests=10, window_seconds=60)

# 批量操作：每用户每分钟 20 次
batch_limiter = RateLimiter(max_requests=20, window_seconds=60)

# 邮件拉取：每用户每分钟 5 次
fetch_limiter = RateLimiter(max_requests=5, window_seconds=60)

# AI 提取：每用户每分钟 20 次
ai_limiter = RateLimiter(max_requests=20, window_seconds=60)
