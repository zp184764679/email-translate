#!/usr/bin/env python3
"""
客户端自动更新服务

功能：
1. 接收 GitHub Release Webhook 通知
2. 自动下载新版本到 updates 目录
3. 通过 API 提供版本信息给客户端

运行方式：
    pm2 start scripts/update_service.py --name email-update --interpreter python3
"""

import os
import sys
import json
import hmac
import hashlib
import base64
import asyncio
import requests
import yaml
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse
import uvicorn

# 配置
GITHUB_OWNER = "zp184764679"
GITHUB_REPO = "email-translate"
UPDATES_DIR = Path("/www/email-translate/updates")
STATE_FILE = UPDATES_DIR / ".last_release"
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "email-translate-webhook-2024")  # 在 GitHub 配置
LOG_FILE = Path("/var/log/email-translate-update.log")

# 代理配置
PROXY_URL = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:10900")
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL
}

# 下载重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

# 确保目录存在
UPDATES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Email-Translate Update Service")


def log(msg: str):
    """写入日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_msg + '\n')
    except Exception:
        pass


def verify_signature(payload: bytes, signature: str) -> bool:
    """验证 GitHub Webhook 签名"""
    if not signature:
        return False

    expected = 'sha256=' + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def get_latest_release():
    """获取最新 Release 信息"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        resp = requests.get(url, headers=headers, timeout=30, proxies=PROXIES)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log(f"获取 Release 失败: {e}")
        return None


def compute_sha512(file_path: Path) -> str:
    """计算文件的 SHA512 哈希值（Base64 编码）"""
    sha512_hash = hashlib.sha512()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha512_hash.update(chunk)
    return base64.b64encode(sha512_hash.digest()).decode('utf-8')


def download_file(url: str, dest_path: Path, expected_size: int = None, expected_sha512: str = None) -> bool:
    """下载文件，带重试和校验"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"开始下载 (尝试 {attempt}/{MAX_RETRIES}): {url}")
            log(f"  使用代理: {PROXY_URL}")

            # 如果文件已存在，先删除
            if dest_path.exists():
                dest_path.unlink()

            with requests.get(url, stream=True, timeout=600, proxies=PROXIES) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0

                with open(dest_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

            actual_size = os.path.getsize(dest_path)

            # 校验文件大小
            if expected_size and actual_size != expected_size:
                log(f"文件大小不匹配: 期望 {expected_size}, 实际 {actual_size}")
                if attempt < MAX_RETRIES:
                    log(f"等待 {RETRY_DELAY} 秒后重试...")
                    import time
                    time.sleep(RETRY_DELAY)
                    continue
                return False

            # 校验 SHA512 (如果提供)
            if expected_sha512:
                actual_sha512 = compute_sha512(dest_path)
                if actual_sha512 != expected_sha512:
                    log(f"SHA512 不匹配!")
                    log(f"  期望: {expected_sha512}")
                    log(f"  实际: {actual_sha512}")
                    if attempt < MAX_RETRIES:
                        log(f"等待 {RETRY_DELAY} 秒后重试...")
                        import time
                        time.sleep(RETRY_DELAY)
                        continue
                    return False
                log(f"SHA512 校验通过")

            log(f"下载完成: {dest_path.name} ({actual_size} 字节)")
            return True

        except Exception as e:
            log(f"下载失败 (尝试 {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                log(f"等待 {RETRY_DELAY} 秒后重试...")
                import time
                time.sleep(RETRY_DELAY)
            else:
                return False

    return False


def delayed_download_release(release: dict, delay_seconds: int = 60):
    """延迟下载 Release（等待 GitHub 文件上传完成）"""
    import time
    tag_name = release.get("tag_name", "")
    log(f"等待 {delay_seconds} 秒后开始下载版本 {tag_name}...")
    time.sleep(delay_seconds)
    log(f"延迟结束，开始下载版本 {tag_name}")
    return download_release(release)


def download_release(release: dict) -> bool:
    """下载 Release 的所有资源，带完整校验"""
    tag_name = release.get("tag_name", "")
    version = tag_name.lstrip("v")
    assets = release.get("assets", [])

    log(f"开始下载版本 {version} 的资源")

    # 1. 先找到并下载 latest.yml
    yml_asset = None
    exe_assets = []
    for asset in assets:
        name = asset.get("name", "")
        if name == "latest.yml":
            yml_asset = asset
        elif name.endswith(".exe"):
            exe_assets.append(asset)

    if not yml_asset:
        log("错误: 没有找到 latest.yml")
        return False

    # 下载 latest.yml
    yml_path = UPDATES_DIR / "latest.yml"
    if not download_file(yml_asset["browser_download_url"], yml_path):
        log("错误: 下载 latest.yml 失败")
        return False

    # 2. 解析 latest.yml 获取正确的文件名、大小和 SHA512
    try:
        yml_content = yml_path.read_text(encoding='utf-8')
        yml_data = yaml.safe_load(yml_content)

        expected_filename = yml_data.get("path", "")
        expected_sha512 = yml_data.get("sha512", "")
        expected_size = None

        # 从 files 数组获取大小
        files = yml_data.get("files", [])
        if files:
            expected_size = files[0].get("size")

        log(f"latest.yml 解析成功:")
        log(f"  文件名: {expected_filename}")
        log(f"  大小: {expected_size}")
        log(f"  SHA512: {expected_sha512[:20]}...")

    except Exception as e:
        log(f"错误: 解析 latest.yml 失败: {e}")
        return False

    # 3. 找到对应的 exe 文件并下载
    # electron-builder 生成的文件名可能和 latest.yml 中的不同
    # 所以我们下载后重命名为 latest.yml 中指定的文件名
    if not exe_assets:
        log("错误: 没有找到 .exe 文件")
        return False

    # 选择最大的 exe 文件（通常是安装包）
    exe_asset = max(exe_assets, key=lambda a: a.get("size", 0))
    exe_url = exe_asset["browser_download_url"]

    # 使用 latest.yml 中指定的文件名
    dest_path = UPDATES_DIR / expected_filename

    # 下载并校验
    success = download_file(
        exe_url,
        dest_path,
        expected_size=expected_size,
        expected_sha512=expected_sha512
    )

    if not success:
        log(f"错误: 下载 {expected_filename} 失败，已尝试 {MAX_RETRIES} 次")
        # 清理失败的文件
        if dest_path.exists():
            dest_path.unlink()
        return False

    # 4. 全部成功，保存版本记录
    STATE_FILE.write_text(version)
    log(f"版本 {version} 下载完成并校验通过!")

    # 清理旧版本
    cleanup_old_versions()

    return True


def cleanup_old_versions():
    """清理旧版本，保留最新2个"""
    exe_files = sorted(
        UPDATES_DIR.glob("*.exe"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    for old_file in exe_files[2:]:
        log(f"删除旧版本: {old_file.name}")
        old_file.unlink()


def check_and_download():
    """检查并下载新版本"""
    log("检查 GitHub Release...")

    release = get_latest_release()
    if not release:
        return False

    tag_name = release.get("tag_name", "")
    version = tag_name.lstrip("v")

    # 读取已下载的版本
    last_version = STATE_FILE.read_text().strip() if STATE_FILE.exists() else None

    log(f"最新版本: {version}, 上次下载: {last_version or '无'}")

    if last_version == version:
        log("已是最新版本")
        return False

    return download_release(release)


# ========== API 端点 ==========

@app.get("/")
async def root():
    """服务状态"""
    return {"service": "email-translate-update", "status": "running"}


@app.get("/api/updates/check")
async def check_updates():
    """检查是否有新版本（客户端调用）"""
    release = get_latest_release()
    if not release:
        raise HTTPException(status_code=404, detail="No release found")

    version = release.get("tag_name", "").lstrip("v")

    # 检查本地是否有此版本
    filename = f"供应商邮件翻译系统 Setup {version}.exe"
    exe_path = UPDATES_DIR / filename
    yml_path = UPDATES_DIR / "latest.yml"

    # URL 编码文件名（处理中文和空格）
    encoded_filename = quote(filename)

    return {
        "version": version,
        "available": exe_path.exists() and yml_path.exists(),
        "release_date": release.get("published_at"),
        "release_notes": release.get("body", ""),
        "download_url": f"/email-updates/{encoded_filename}"
    }


@app.get("/api/updates/latest")
async def get_latest_version():
    """获取最新版本信息（兼容 electron-updater）"""
    yml_path = UPDATES_DIR / "latest.yml"
    if not yml_path.exists():
        raise HTTPException(status_code=404, detail="latest.yml not found")

    content = yml_path.read_text(encoding='utf-8')
    return PlainTextResponse(content, media_type="text/yaml; charset=utf-8")


@app.post("/api/updates/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    GitHub Webhook 接收端点

    在 GitHub 仓库设置:
    - Payload URL: https://your-server/email/api/updates/webhook
    - Content type: application/json
    - Secret: email-translate-webhook-2024
    - Events: Release
    """
    # 验证签名
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload = await request.body()

    # 开发时可跳过验证
    # if not verify_signature(payload, signature):
    #     log("Webhook 签名验证失败")
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    # 解析事件
    event = request.headers.get("X-GitHub-Event", "")
    data = json.loads(payload)

    log(f"收到 GitHub Webhook: {event}")

    if event == "release":
        action = data.get("action", "")
        if action in ["published", "released"]:
            release = data.get("release", {})
            tag_name = release.get("tag_name", "")
            log(f"新版本发布: {tag_name}")

            # 后台下载（延迟60秒等待 GitHub 文件上传完成）
            background_tasks.add_task(delayed_download_release, release, 60)

            return {"status": "ok", "message": f"60秒后开始下载版本 {tag_name}"}

    elif event == "ping":
        log("Webhook ping 成功")
        return {"status": "ok", "message": "pong"}

    return {"status": "ok", "message": "Event ignored"}


@app.post("/api/updates/trigger")
async def trigger_download(background_tasks: BackgroundTasks):
    """手动触发检查和下载"""
    background_tasks.add_task(check_and_download)
    return {"status": "ok", "message": "已触发检查"}


if __name__ == "__main__":
    log("启动 Email-Translate 更新服务")
    log(f"代理配置: {PROXY_URL}")
    uvicorn.run(app, host="127.0.0.1", port=8010, log_level="info")
