from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from pathlib import Path
from dotenv import load_dotenv

# 确保 .env 文件在模块加载时就被读取
load_dotenv()


def get_database_path() -> Path:
    """根据环境变量或默认路径获取数据库路径（仅SQLite使用）"""
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        # 使用 Electron 传递的数据目录
        db_path = Path(data_dir) / "email_translate.db"
    else:
        # 开发模式：使用相对路径
        db_path = Path("./data/email_translate.db")

    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return db_path.absolute()


def get_database_url() -> str:
    """获取数据库连接URL - 支持 SQLite 和 MySQL"""
    db_type = os.environ.get("DB_TYPE", "sqlite").lower()

    if db_type == "mysql":
        # MySQL 配置
        host = os.environ.get("MYSQL_HOST", "localhost")
        port = os.environ.get("MYSQL_PORT", "3306")
        user = os.environ.get("MYSQL_USER", "root")
        password = os.environ.get("MYSQL_PASSWORD", "")
        database = os.environ.get("MYSQL_DATABASE", "email_translate")

        # 使用 aiomysql 异步驱动
        return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    else:
        # SQLite 配置（默认）
        db_path = get_database_path()
        return f"sqlite+aiosqlite:///{db_path}"


class Settings(BaseSettings):
    # Application
    app_name: str = "供应商邮件翻译系统"
    debug: bool = False

    # Database
    db_type: str = "sqlite"  # "sqlite" or "mysql"
    mysql_host: str = "localhost"
    mysql_port: str = "3306"
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "email_translate"

    # Translation API
    translate_provider: str = "ollama"  # "deepl", "claude", or "ollama"
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

    # JWT Auth
    secret_key: str = "email-translate-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Email polling
    email_poll_interval: int = 300  # 5 minutes

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略 .env 中未定义的字段


@lru_cache()
def get_settings():
    return Settings()
