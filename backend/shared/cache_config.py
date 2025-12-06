# shared/cache_config.py
"""
统一Redis缓存配置模块
提供缓存连接和常用缓存操作
"""
import os
import json
from datetime import timedelta
from functools import wraps
from typing import Any, Optional, Callable

# 尝试导入Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("警告: redis-py 未安装，缓存功能不可用")


class CacheConfig:
    """缓存配置"""

    def __init__(self):
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.default_ttl = int(os.getenv('CACHE_DEFAULT_TTL', 3600))  # 默认1小时
        self.prefix = os.getenv('CACHE_PREFIX', 'app')
        self._client = None

    @property
    def client(self):
        """获取Redis客户端（懒加载）"""
        if not REDIS_AVAILABLE:
            return None

        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # 测试连接
                self._client.ping()
            except Exception as e:
                print(f"警告: Redis连接失败 - {e}")
                self._client = None

        return self._client

    def is_available(self) -> bool:
        """检查Redis是否可用"""
        return self.client is not None


# 全局缓存配置实例
cache_config = CacheConfig()


def get_cache_key(key: str) -> str:
    """生成带前缀的缓存键"""
    return f"{cache_config.prefix}:{key}"


def cache_get(key: str) -> Optional[Any]:
    """
    从缓存获取值

    Args:
        key: 缓存键

    Returns:
        缓存的值，如果不存在则返回None
    """
    if not cache_config.is_available():
        return None

    try:
        full_key = get_cache_key(key)
        value = cache_config.client.get(full_key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"缓存读取错误: {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = None) -> bool:
    """
    设置缓存值

    Args:
        key: 缓存键
        value: 要缓存的值（会自动JSON序列化）
        ttl: 过期时间（秒），默认使用全局配置

    Returns:
        是否成功
    """
    if not cache_config.is_available():
        return False

    try:
        full_key = get_cache_key(key)
        if ttl is None:
            ttl = cache_config.default_ttl
        cache_config.client.setex(
            full_key,
            ttl,
            json.dumps(value, ensure_ascii=False, default=str)
        )
        return True
    except Exception as e:
        print(f"缓存写入错误: {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    删除缓存

    Args:
        key: 缓存键

    Returns:
        是否成功
    """
    if not cache_config.is_available():
        return False

    try:
        full_key = get_cache_key(key)
        cache_config.client.delete(full_key)
        return True
    except Exception as e:
        print(f"缓存删除错误: {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    按模式删除缓存

    Args:
        pattern: 模式（支持通配符 *）

    Returns:
        删除的键数量
    """
    if not cache_config.is_available():
        return 0

    try:
        full_pattern = get_cache_key(pattern)
        keys = cache_config.client.keys(full_pattern)
        if keys:
            return cache_config.client.delete(*keys)
        return 0
    except Exception as e:
        print(f"缓存批量删除错误: {e}")
        return 0


def cache_exists(key: str) -> bool:
    """检查缓存键是否存在"""
    if not cache_config.is_available():
        return False

    try:
        full_key = get_cache_key(key)
        return cache_config.client.exists(full_key) > 0
    except Exception:
        return False


def cache_increment(key: str, amount: int = 1) -> Optional[int]:
    """
    增加计数器

    Args:
        key: 缓存键
        amount: 增加量

    Returns:
        新值
    """
    if not cache_config.is_available():
        return None

    try:
        full_key = get_cache_key(key)
        return cache_config.client.incrby(full_key, amount)
    except Exception as e:
        print(f"缓存计数器错误: {e}")
        return None


def cache_ttl(key: str) -> int:
    """获取缓存剩余过期时间（秒）"""
    if not cache_config.is_available():
        return -1

    try:
        full_key = get_cache_key(key)
        return cache_config.client.ttl(full_key)
    except Exception:
        return -1


def cached(ttl: int = None, key_func: Callable = None):
    """
    函数结果缓存装饰器

    Args:
        ttl: 过期时间（秒）
        key_func: 自定义缓存键生成函数

    Usage:
        @cached(ttl=3600)
        def get_user(user_id):
            # 昂贵的数据库查询
            return db.query(User).get(user_id)

        @cached(key_func=lambda *args, **kwargs: f"product:{kwargs.get('id')}")
        def get_product(**kwargs):
            pass
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 如果Redis不可用，直接执行函数
            if not cache_config.is_available():
                return f(*args, **kwargs)

            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数生成键
                key_parts = [f.__name__]
                key_parts.extend([str(arg) for arg in args])
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                cache_key = ":".join(key_parts)

            # 尝试从缓存获取
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            # 执行函数并缓存结果
            result = f(*args, **kwargs)
            cache_set(cache_key, result, ttl)
            return result

        # 添加缓存清除方法
        def clear_cache(*args, **kwargs):
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_parts = [f.__name__]
                key_parts.extend([str(arg) for arg in args])
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                cache_key = ":".join(key_parts)
            cache_delete(cache_key)

        wrapper.clear_cache = clear_cache
        return wrapper
    return decorator


class CacheManager:
    """
    缓存管理器 - 提供高级缓存功能
    """

    def __init__(self, namespace: str = None):
        """
        Args:
            namespace: 缓存命名空间（用于隔离不同模块）
        """
        self.namespace = namespace or ''

    def _make_key(self, key: str) -> str:
        """生成带命名空间的键"""
        if self.namespace:
            return f"{self.namespace}:{key}"
        return key

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        return cache_get(self._make_key(key))

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        return cache_set(self._make_key(key), value, ttl)

    def delete(self, key: str) -> bool:
        """删除缓存"""
        return cache_delete(self._make_key(key))

    def clear_namespace(self) -> int:
        """清除命名空间下所有缓存"""
        if self.namespace:
            return cache_delete_pattern(f"{self.namespace}:*")
        return 0

    def get_or_set(self, key: str, func: Callable, ttl: int = None) -> Any:
        """
        获取缓存，如果不存在则调用函数并缓存结果

        Args:
            key: 缓存键
            func: 生成值的函数
            ttl: 过期时间

        Returns:
            缓存的值或新生成的值
        """
        full_key = self._make_key(key)
        cached_value = cache_get(full_key)
        if cached_value is not None:
            return cached_value

        value = func()
        cache_set(full_key, value, ttl)
        return value


# 预定义的缓存管理器
user_cache = CacheManager('user')
product_cache = CacheManager('product')
config_cache = CacheManager('config')
session_cache = CacheManager('session')


def health_check() -> dict:
    """
    Redis健康检查

    Returns:
        健康状态信息
    """
    result = {
        'available': False,
        'url': cache_config.redis_url,
        'info': {}
    }

    if not REDIS_AVAILABLE:
        result['error'] = 'redis-py not installed'
        return result

    if cache_config.is_available():
        try:
            info = cache_config.client.info()
            result['available'] = True
            result['info'] = {
                'redis_version': info.get('redis_version'),
                'used_memory_human': info.get('used_memory_human'),
                'connected_clients': info.get('connected_clients'),
                'total_connections_received': info.get('total_connections_received'),
                'keyspace_hits': info.get('keyspace_hits'),
                'keyspace_misses': info.get('keyspace_misses'),
            }
        except Exception as e:
            result['error'] = str(e)
    else:
        result['error'] = 'Connection failed'

    return result
