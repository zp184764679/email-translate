from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import os
import sys
import socket
import atexit

from config import get_settings
from database.database import init_db
from routers import emails_router, users_router, translate_router, drafts_router, suppliers_router

settings = get_settings()

# 单实例锁文件路径
LOCK_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "backend_2000.lock")
_lock_socket = None


def acquire_single_instance_lock(port: int = 8000) -> bool:
    """
    使用 socket 绑定实现单实例锁（比文件锁更可靠）
    如果端口已被占用，返回 False
    """
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        _lock_socket.bind(('127.0.0.1', port + 10000))  # 使用 18000 作为锁端口
        return True
    except OSError:
        return False


def release_single_instance_lock():
    """释放单实例锁"""
    global _lock_socket
    if _lock_socket:
        try:
            _lock_socket.close()
        except:
            pass
        _lock_socket = None


# 注册退出时释放锁
atexit.register(release_single_instance_lock)


def check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False


# 启动时立即检查单实例
PORT = int(os.environ.get("BACKEND_PORT", 2000))

if not acquire_single_instance_lock(PORT):
    print(f"错误：后端服务已在运行（端口 {PORT}）")
    print("请勿重复启动后端服务")
    sys.exit(1)

if not check_port_available(PORT):
    print(f"错误：端口 {PORT} 已被占用")
    print("请先关闭占用该端口的程序")
    release_single_instance_lock()
    sys.exit(1)

print(f"单实例检查通过，准备启动后端服务（端口 {PORT}）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    await init_db()
    print("Database initialized")

    # 预热数据库连接池 - 避免首次请求延迟
    from database.database import async_session
    from sqlalchemy import text
    print("Warming up database connection pool...")
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    print("Connection pool ready")

    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="供应商邮件翻译管理系统 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users_router)
app.include_router(emails_router)
app.include_router(translate_router)
app.include_router(drafts_router)
app.include_router(suppliers_router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}


# API for client version check
@app.get("/api/client/version")
async def get_client_version():
    return {
        "latest_version": "1.0.0",
        "min_version": "1.0.0",
        "download_url": "",
        "force_update": False,
        "changelog": "Initial release"
    }


if __name__ == "__main__":
    # 直接使用 app 对象而非字符串，确保 PyInstaller 打包后能正常运行
    uvicorn.run(app, host="0.0.0.0", port=PORT)
