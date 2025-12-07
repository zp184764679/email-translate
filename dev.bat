@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   供应商邮件翻译系统 - 开发环境
echo ========================================
echo.

:: 禁用代理（解决 Vite 代理连接问题）
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NO_PROXY=127.0.0.1,localhost

:: 检查端口是否被占用
echo [1/4] 检查端口占用...

:: 检查后端端口 2000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":2000 "') do (
    echo   端口 2000 被占用 (PID: %%a)，正在停止...
    taskkill /PID %%a /F >nul 2>&1
)

:: 检查前端端口 4567
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4567 "') do (
    echo   端口 4567 被占用 (PID: %%a)，正在停止...
    taskkill /PID %%a /F >nul 2>&1
)

:: 关闭可能存在的 Electron 进程
taskkill /IM electron.exe /F >nul 2>&1

echo   端口检查完成
echo.

:: 启动后端
echo [2/4] 启动后端服务 (端口 2000)...
cd backend
start "Backend" cmd /c "python main.py"
cd ..
echo   后端已启动
echo.

:: 等待后端就绪
echo [3/4] 等待后端就绪...
:wait_backend
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:2000/health >nul 2>&1
if errorlevel 1 (
    echo   等待后端启动...
    goto wait_backend
)
echo   后端已就绪
echo.

:: 启动前端 + Electron（禁用代理）
echo [4/4] 启动前端和 Electron...
cd frontend
start "Frontend" cmd /c "set HTTP_PROXY= && set HTTPS_PROXY= && set http_proxy= && set https_proxy= && npm run electron:dev"
cd ..
echo   前端和 Electron 已启动
echo.

echo ========================================
echo   启动完成！
echo ========================================
echo.
echo   后端 API: http://127.0.0.1:2000
echo   前端 Dev: http://127.0.0.1:4567
echo.
echo   提示: 关闭此窗口不会停止服务
echo   停止: 运行 stop.bat 或手动关闭窗口
echo.
pause
