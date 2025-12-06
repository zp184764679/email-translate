# shared/logging_config.py
"""
统一日志配置模块
所有子系统可导入此模块获得标准化日志配置
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = None,
    log_level: str = None,
    log_dir: str = "./logs",
    log_format: str = "standard",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
):
    """
    配置统一日志记录器

    Args:
        name: 日志记录器名称，None表示根记录器
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件存储目录
        log_format: 日志格式 ('standard', 'json', 'simple')
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的日志文件数量

    Returns:
        logger: 配置好的日志记录器
    """
    # 从环境变量获取配置
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    if log_format is None:
        log_format = os.getenv('LOG_FORMAT', 'standard')

    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # 获取日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # 清除现有处理器（避免重复）
    logger.handlers.clear()

    # 定义日志格式
    if log_format == 'json':
        # JSON格式 - 便于日志分析工具处理
        formatter = JsonFormatter()
    elif log_format == 'simple':
        # 简单格式
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # 标准格式（默认）
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（按大小轮转）
    app_name = name or 'app'
    log_file = os.path.join(log_dir, f"{app_name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 错误日志单独存储
    error_log_file = os.path.join(log_dir, f"{app_name}_error.log")
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


class JsonFormatter(logging.Formatter):
    """JSON格式的日志格式化器"""

    def format(self, record):
        import json
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False)


def get_logger(name: str = None):
    """
    获取已配置的日志记录器
    如果未配置，则使用默认配置

    Args:
        name: 日志记录器名称

    Returns:
        logger: 日志记录器
    """
    logger = logging.getLogger(name)

    # 如果没有处理器，进行默认配置
    if not logger.handlers:
        setup_logger(name)

    return logger


# 预定义的系统日志记录器
def get_system_logger(system_name: str):
    """
    获取特定系统的日志记录器

    Args:
        system_name: 系统名称 (quote, crm, hr, scm, eam, shm, mes, procurement)

    Returns:
        logger: 配置好的日志记录器
    """
    log_dir = os.getenv('LOG_DIR', './logs')
    return setup_logger(
        name=system_name,
        log_dir=log_dir
    )


# 便捷函数
def log_api_request(logger, method, path, user_id=None, request_id=None):
    """记录API请求"""
    extra = {
        'method': method,
        'path': path,
        'user_id': user_id,
        'request_id': request_id
    }
    logger.info(f"API Request: {method} {path}", extra={'extra_data': extra})


def log_api_response(logger, method, path, status_code, duration_ms, request_id=None):
    """记录API响应"""
    extra = {
        'method': method,
        'path': path,
        'status_code': status_code,
        'duration_ms': duration_ms,
        'request_id': request_id
    }
    logger.info(f"API Response: {method} {path} - {status_code} ({duration_ms}ms)", extra={'extra_data': extra})


def log_db_operation(logger, operation, table, duration_ms=None, affected_rows=None):
    """记录数据库操作"""
    extra = {
        'operation': operation,
        'table': table,
        'duration_ms': duration_ms,
        'affected_rows': affected_rows
    }
    logger.debug(f"DB {operation} on {table}", extra={'extra_data': extra})


def log_external_api_call(logger, service, endpoint, status_code, duration_ms):
    """记录外部API调用"""
    extra = {
        'service': service,
        'endpoint': endpoint,
        'status_code': status_code,
        'duration_ms': duration_ms
    }
    logger.info(f"External API: {service} {endpoint} - {status_code} ({duration_ms}ms)", extra={'extra_data': extra})
