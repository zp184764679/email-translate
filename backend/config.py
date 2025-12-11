from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from dotenv import load_dotenv

# 确保 .env 文件在模块加载时就被读取
load_dotenv()


def get_database_url() -> str:
    """获取 MySQL 数据库连接URL"""
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "email_translate")

    # 使用 aiomysql 异步驱动
    return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


class Settings(BaseSettings):
    # Application
    app_name: str = "供应商邮件翻译系统"
    debug: bool = False

    # MySQL Database
    mysql_host: str = "localhost"
    mysql_port: str = "3306"
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "email_translate"

    # Translation API
    translate_provider: str = "tencent"  # "deepl", "claude", "ollama", or "tencent"
    translate_enabled: bool = True

    # DeepL API
    deepl_api_key: str = ""
    deepl_free_api: bool = True

    # Claude API (Anthropic)
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Ollama (local LLM) - 本地测试用
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # Tencent TMT (腾讯翻译) - 速度快，格式好
    tencent_secret_id: str = ""
    tencent_secret_key: str = ""

    # 智能路由配置
    smart_routing_enabled: bool = True  # 是否启用智能路由（根据复杂度选择翻译引擎）

    # JWT Auth
    secret_key: str = "email-translate-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Email polling
    email_poll_interval: int = 300  # 5 minutes

    # Celery 配置
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_default_queue: str = "email_translate"
    celery_task_time_limit: int = 300  # 5 minutes max per task

    # WebSocket 配置
    websocket_enabled: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略 .env 中未定义的字段


@lru_cache()
def get_settings():
    return Settings()
