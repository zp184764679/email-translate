from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from config import get_settings
from database.database import init_db
from routers import emails_router, users_router, translate_router, drafts_router, suppliers_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up...")
    await init_db()
    print("Database initialized")
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
    import os
    port = int(os.environ.get("BACKEND_PORT", 8000))
    # 直接使用 app 对象而非字符串，确保 PyInstaller 打包后能正常运行
    uvicorn.run(app, host="0.0.0.0", port=port)
