# shared/auth_middleware.py
# -*- coding: utf-8 -*-
"""
统一认证授权中间件
可被所有子系统（HR、CRM、SCM、EAM、SHM、MES、采购、报价）共用
"""
import jwt
import os
from functools import wraps
from flask import request, jsonify, g
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 从环境变量获取配置 - 必须与 shared/auth/jwt_utils.py 保持一致
JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'jzchardware-sso-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', 24))


def generate_token(user_id, username, role='user', extra_claims=None):
    """
    生成JWT Token

    Args:
        user_id: 用户ID
        username: 用户名
        role: 用户角色
        extra_claims: 额外的claims数据

    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }

    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_token(token):
    """
    解码JWT Token

    Returns:
        dict: 解码后的payload

    Raises:
        jwt.ExpiredSignatureError: Token过期
        jwt.InvalidTokenError: Token无效
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def requires_auth(f):
    """
    认证装饰器 - 要求请求必须携带有效的JWT Token

    使用方式:
        @app.route('/api/protected')
        @requires_auth
        def protected_route():
            user = g.current_user
            return jsonify({'message': f'Hello {user["username"]}'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 跳过OPTIONS预检请求
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        # 从Header获取Token
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({
                'success': False,
                'error': '缺少认证Token',
                'code': 'AUTH_REQUIRED'
            }), 401

        # 支持 "Bearer <token>" 格式
        token = auth_header
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

        try:
            payload = decode_token(token)

            # 将用户信息存入Flask g对象
            g.current_user = {
                'user_id': payload.get('user_id'),
                'username': payload.get('username'),
                'role': payload.get('role', 'user')
            }

            # 同时支持旧版Header格式（向后兼容）
            if not g.current_user['user_id']:
                user_id = request.headers.get('User-ID')
                if user_id:
                    g.current_user['user_id'] = int(user_id)

            return f(*args, **kwargs)

        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired for request: {request.path}")
            return jsonify({
                'success': False,
                'error': 'Token已过期，请重新登录',
                'code': 'TOKEN_EXPIRED'
            }), 401

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return jsonify({
                'success': False,
                'error': '无效的Token',
                'code': 'INVALID_TOKEN'
            }), 401

        except Exception as e:
            logger.error(f"Auth error: {str(e)}")
            return jsonify({
                'success': False,
                'error': '认证失败',
                'code': 'AUTH_ERROR'
            }), 401

    return decorated


def requires_role(*roles):
    """
    角色授权装饰器 - 要求用户必须具有指定角色

    使用方式:
        @app.route('/api/admin')
        @requires_auth
        @requires_role('admin', 'super_admin')
        def admin_route():
            return jsonify({'message': 'Admin area'})
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            current_user = getattr(g, 'current_user', None)

            if not current_user:
                return jsonify({
                    'success': False,
                    'error': '未认证',
                    'code': 'NOT_AUTHENTICATED'
                }), 401

            user_role = current_user.get('role', '')

            if user_role not in roles:
                logger.warning(f"User {current_user.get('user_id')} with role '{user_role}' "
                             f"attempted to access {request.path} (requires: {roles})")
                return jsonify({
                    'success': False,
                    'error': f'权限不足，需要角色: {", ".join(roles)}',
                    'code': 'INSUFFICIENT_ROLE'
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def optional_auth(f):
    """
    可选认证装饰器 - Token存在则验证，不存在也允许访问

    使用方式:
        @app.route('/api/public')
        @optional_auth
        def public_route():
            user = getattr(g, 'current_user', None)
            if user:
                return jsonify({'message': f'Hello {user["username"]}'})
            else:
                return jsonify({'message': 'Hello Guest'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization')

        if auth_header:
            token = auth_header
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]

            try:
                payload = decode_token(token)
                g.current_user = {
                    'user_id': payload.get('user_id'),
                    'username': payload.get('username'),
                    'role': payload.get('role', 'user')
                }
            except Exception:
                # Token无效但不阻止访问
                g.current_user = None
        else:
            g.current_user = None

        return f(*args, **kwargs)

    return decorated


def get_current_user_id():
    """获取当前用户ID的便捷方法"""
    current_user = getattr(g, 'current_user', None)
    if current_user:
        return current_user.get('user_id')

    # 向后兼容：尝试从Header获取
    user_id = request.headers.get('User-ID')
    if user_id:
        try:
            return int(user_id)
        except ValueError:
            pass

    return None


def get_current_user():
    """获取当前用户信息的便捷方法"""
    return getattr(g, 'current_user', None)


# ===========================
# 跨系统认证支持
# ===========================

def validate_service_token(service_name):
    """
    验证服务间调用Token
    用于微服务之间的安全通信

    使用方式:
        @app.route('/api/internal/sync')
        @validate_service_token('procurement')
        def internal_sync():
            return jsonify({'status': 'ok'})
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            service_token = request.headers.get('X-Service-Token')
            expected_token = os.getenv(f'{service_name.upper()}_SERVICE_TOKEN')

            if not service_token or not expected_token:
                return jsonify({
                    'success': False,
                    'error': '缺少服务认证',
                    'code': 'SERVICE_AUTH_REQUIRED'
                }), 401

            if service_token != expected_token:
                return jsonify({
                    'success': False,
                    'error': '服务认证失败',
                    'code': 'SERVICE_AUTH_FAILED'
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


# ===========================
# 统一响应格式辅助函数
# ===========================

def success_response(data=None, message='操作成功', **kwargs):
    """
    统一成功响应格式

    Args:
        data: 返回数据
        message: 成功消息
        **kwargs: 其他参数（如 pagination）

    Returns:
        dict: 统一格式的响应
    """
    response = {
        'success': True,
        'message': message
    }

    if data is not None:
        response['data'] = data

    response.update(kwargs)
    return response


def error_response(error, code='ERROR', status_code=400):
    """
    统一错误响应格式

    Args:
        error: 错误消息
        code: 错误代码
        status_code: HTTP状态码

    Returns:
        tuple: (响应字典, HTTP状态码)
    """
    return jsonify({
        'success': False,
        'error': error,
        'code': code
    }), status_code


def paginated_response(items, total, page=1, per_page=20):
    """
    统一分页响应格式

    Args:
        items: 数据列表
        total: 总数
        page: 当前页
        per_page: 每页数量

    Returns:
        dict: 包含分页信息的响应
    """
    return {
        'success': True,
        'data': items,
        'pagination': {
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
    }
