"""
翻译 API 用量统计服务

支持的翻译引擎：
- vllm: 服务器大模型（主力引擎，无限制，不统计）
- claude: Claude API（按 token 计费，无免费额度，统计用于成本追踪）

功能：
- 记录每次翻译的字符数/token数
- 按月统计用量
"""

import aiomysql
from datetime import datetime
from typing import Dict, Optional
import os


class UsageService:
    """翻译用量统计服务"""

    # 各引擎免费额度配置（字符/月）
    PROVIDER_QUOTAS = {
        'vllm': -1,             # 服务器模型：无限制（-1 表示不限制，主力引擎）
        'claude': 0,            # Claude：无免费额度，按 token 计费
    }

    # 各引擎显示名称
    PROVIDER_NAMES = {
        'vllm': '服务器模型 (vLLM)',
        'claude': 'Claude API',
    }

    # 警告阈值：使用超过 80% 时警告
    WARNING_THRESHOLD = 0.8
    # 禁用阈值：使用超过 95% 时自动禁用（留5%余量避免超额收费）
    DISABLE_THRESHOLD = 0.95

    def __init__(self):
        self.db_config = {
            'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
            'port': int(os.environ.get('MYSQL_PORT', 3306)),
            'user': os.environ.get('MYSQL_USER', 'root'),
            'password': os.environ.get('MYSQL_PASSWORD', ''),
            'db': os.environ.get('MYSQL_DATABASE', 'email_translate'),
            'charset': 'utf8mb4'
        }

    def _get_current_month(self) -> str:
        """获取当前年月 (格式: 2024-12)"""
        return datetime.now().strftime('%Y-%m')

    async def _get_connection(self):
        """获取数据库连接"""
        return await aiomysql.connect(**self.db_config)

    def _get_provider_quota(self, provider: str) -> int:
        """获取指定引擎的免费额度"""
        return self.PROVIDER_QUOTAS.get(provider, 0)

    def _get_provider_name(self, provider: str) -> str:
        """获取引擎的显示名称"""
        return self.PROVIDER_NAMES.get(provider, provider)

    async def record_usage(self, provider: str, char_count: int) -> Dict:
        """
        记录一次翻译用量

        Args:
            provider: 翻译引擎 (vllm, claude)
            char_count: 本次翻译的字符数

        Returns:
            {
                'success': bool,
                'total_chars': int,      # 本月累计字符数
                'free_quota': int,       # 免费额度
                'usage_percent': float,  # 使用百分比
                'warning': str|None,     # 警告信息
                'is_disabled': bool      # 是否已禁用
            }
        """
        # vLLM 服务器模型不需要统计
        if provider == 'vllm':
            return {
                'success': True,
                'total_chars': 0,
                'free_quota': -1,
                'usage_percent': 0,
                'warning': None,
                'is_disabled': False,
                'message': '服务器模型无用量限制'
            }

        year_month = self._get_current_month()
        free_quota = self._get_provider_quota(provider)
        provider_name = self._get_provider_name(provider)
        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                # 尝试插入或更新记录
                await cur.execute('''
                    INSERT INTO translation_usage
                        (provider, `year_month`, total_chars, total_requests, free_quota)
                    VALUES (%s, %s, %s, 1, %s)
                    ON DUPLICATE KEY UPDATE
                        total_chars = total_chars + VALUES(total_chars),
                        total_requests = total_requests + 1
                ''', (provider, year_month, char_count, free_quota))

                # 查询当前用量
                await cur.execute('''
                    SELECT total_chars, free_quota, is_disabled
                    FROM translation_usage
                    WHERE provider = %s AND `year_month` = %s
                ''', (provider, year_month))
                row = await cur.fetchone()

                if row:
                    total_chars, free_quota, is_disabled = row

                    # Claude 没有免费额度，只统计不限制
                    if provider == 'claude' or free_quota <= 0:
                        await conn.commit()
                        return {
                            'success': True,
                            'total_chars': total_chars,
                            'free_quota': free_quota,
                            'usage_percent': 0,
                            'warning': None,
                            'is_disabled': False,
                            'message': f'{provider_name} 按量计费，无额度限制'
                        }

                    usage_percent = total_chars / free_quota

                    warning = None
                    should_disable = False

                    # 检查是否需要警告
                    if usage_percent >= self.DISABLE_THRESHOLD:
                        warning = f"⚠️ 警告：{provider_name} 本月用量已达 {usage_percent*100:.1f}%，已自动禁用以避免超额收费"
                        should_disable = True
                    elif usage_percent >= self.WARNING_THRESHOLD:
                        warning = f"⚠️ 注意：{provider_name} 本月用量已达 {usage_percent*100:.1f}%，接近免费额度上限"

                    # 如果需要禁用，更新数据库
                    if should_disable and not is_disabled:
                        await cur.execute('''
                            UPDATE translation_usage
                            SET is_disabled = 1
                            WHERE provider = %s AND `year_month` = %s
                        ''', (provider, year_month))
                        is_disabled = True

                    await conn.commit()

                    return {
                        'success': True,
                        'total_chars': total_chars,
                        'free_quota': free_quota,
                        'usage_percent': usage_percent,
                        'warning': warning,
                        'is_disabled': bool(is_disabled)
                    }

            return {'success': False, 'error': 'Failed to record usage'}

        except Exception as e:
            print(f"[UsageService] Error recording usage: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()

    async def check_quota(self, provider: str) -> Dict:
        """
        检查翻译引擎是否可用（未超额）

        Args:
            provider: 翻译引擎名称

        Returns:
            {
                'available': bool,       # 是否可用
                'total_chars': int,      # 本月累计字符数
                'free_quota': int,       # 免费额度
                'remaining': int,        # 剩余额度
                'usage_percent': float,  # 使用百分比
                'is_disabled': bool      # 是否已禁用
            }
        """
        # vLLM 和 Claude 始终可用
        if provider == 'vllm':
            return {
                'available': True,
                'total_chars': 0,
                'free_quota': -1,
                'remaining': -1,
                'usage_percent': 0,
                'is_disabled': False,
                'message': '服务器模型无限制'
            }

        if provider == 'claude':
            return {
                'available': True,
                'total_chars': 0,
                'free_quota': 0,
                'remaining': 0,
                'usage_percent': 0,
                'is_disabled': False,
                'message': 'Claude API 按量计费'
            }

        year_month = self._get_current_month()
        free_quota = self._get_provider_quota(provider)
        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                await cur.execute('''
                    SELECT total_chars, free_quota, is_disabled
                    FROM translation_usage
                    WHERE provider = %s AND `year_month` = %s
                ''', (provider, year_month))
                row = await cur.fetchone()

                if row:
                    total_chars, db_quota, is_disabled = row
                    # 使用数据库中的额度（可能被手动修改过）
                    actual_quota = db_quota if db_quota > 0 else free_quota
                    remaining = max(0, actual_quota - total_chars)
                    usage_percent = total_chars / actual_quota if actual_quota > 0 else 0

                    return {
                        'available': not is_disabled and usage_percent < self.DISABLE_THRESHOLD,
                        'total_chars': total_chars,
                        'free_quota': actual_quota,
                        'remaining': remaining,
                        'usage_percent': usage_percent,
                        'is_disabled': bool(is_disabled)
                    }

                # 本月还没有记录，说明还没使用过
                return {
                    'available': True,
                    'total_chars': 0,
                    'free_quota': free_quota,
                    'remaining': free_quota,
                    'usage_percent': 0,
                    'is_disabled': False
                }

        except Exception as e:
            print(f"[UsageService] Error checking quota: {e}")
            # 出错时默认允许使用
            return {'available': True, 'error': str(e)}
        finally:
            conn.close()

    async def get_usage_stats(self, provider: str = None) -> Dict:
        """
        获取用量统计信息

        Args:
            provider: 可选，指定翻译引擎；为空则返回所有

        Returns:
            {
                'current_month': str,
                'providers': [{
                    'provider': str,
                    'provider_name': str,
                    'total_chars': int,
                    'total_requests': int,
                    'free_quota': int,
                    'remaining': int,
                    'usage_percent': float,
                    'is_disabled': bool,
                    'has_limit': bool
                }, ...]
            }
        """
        year_month = self._get_current_month()
        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                if provider:
                    await cur.execute('''
                        SELECT provider, total_chars, total_requests, free_quota, is_disabled
                        FROM translation_usage
                        WHERE provider = %s AND `year_month` = %s
                    ''', (provider, year_month))
                else:
                    await cur.execute('''
                        SELECT provider, total_chars, total_requests, free_quota, is_disabled
                        FROM translation_usage
                        WHERE `year_month` = %s
                    ''', (year_month,))

                rows = await cur.fetchall()
                providers = []

                for row in rows:
                    prov, total_chars, total_requests, free_quota, is_disabled = row
                    has_limit = prov not in ['vllm', 'claude'] and free_quota > 0
                    remaining = max(0, free_quota - total_chars) if has_limit else -1
                    usage_percent = (total_chars / free_quota * 100) if has_limit else 0

                    providers.append({
                        'provider': prov,
                        'provider_name': self._get_provider_name(prov),
                        'total_chars': total_chars,
                        'total_requests': total_requests,
                        'free_quota': free_quota,
                        'remaining': remaining,
                        'usage_percent': round(usage_percent, 2),
                        'is_disabled': bool(is_disabled),
                        'has_limit': has_limit
                    })

                # 添加未使用的引擎信息
                all_providers = set(self.PROVIDER_QUOTAS.keys())
                used_providers = set(p['provider'] for p in providers)
                for prov in all_providers - used_providers:
                    quota = self._get_provider_quota(prov)
                    has_limit = prov not in ['vllm', 'claude'] and quota > 0
                    providers.append({
                        'provider': prov,
                        'provider_name': self._get_provider_name(prov),
                        'total_chars': 0,
                        'total_requests': 0,
                        'free_quota': quota,
                        'remaining': quota if has_limit else -1,
                        'usage_percent': 0,
                        'is_disabled': False,
                        'has_limit': has_limit
                    })

                return {
                    'current_month': year_month,
                    'providers': providers
                }

        except Exception as e:
            print(f"[UsageService] Error getting stats: {e}")
            return {'current_month': year_month, 'providers': [], 'error': str(e)}
        finally:
            conn.close()

    async def reset_disabled(self, provider: str) -> bool:
        """
        手动重新启用被禁用的翻译引擎（下月会自动重置）

        Args:
            provider: 翻译引擎名称

        Returns:
            是否成功
        """
        year_month = self._get_current_month()
        conn = await self._get_connection()

        try:
            async with conn.cursor() as cur:
                await cur.execute('''
                    UPDATE translation_usage
                    SET is_disabled = 0
                    WHERE provider = %s AND `year_month` = %s
                ''', (provider, year_month))
                await conn.commit()
                return True
        except Exception as e:
            print(f"[UsageService] Error resetting disabled: {e}")
            return False
        finally:
            conn.close()


# 单例实例
_usage_service: Optional[UsageService] = None


def get_usage_service() -> UsageService:
    """获取用量服务单例"""
    global _usage_service
    if _usage_service is None:
        _usage_service = UsageService()
    return _usage_service


# 便捷异步函数
async def record_translation_usage(provider: str, char_count: int) -> Dict:
    """记录翻译用量"""
    return await get_usage_service().record_usage(provider, char_count)


async def check_translation_quota(provider: str) -> Dict:
    """检查翻译额度"""
    return await get_usage_service().check_quota(provider)


async def get_translation_usage_stats(provider: str = None) -> Dict:
    """获取用量统计"""
    return await get_usage_service().get_usage_stats(provider)
