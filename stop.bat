@echo off
chcp 65001 >nul
echo ========================================
echo   供应商邮件翻译系统 - 停止所有服务
echo ========================================
echo.

echo 使用 PM2 停止服务...
pm2 delete email-backend email-frontend email-electron 2>nul

echo 清理残留进程...
taskkill /F /IM electron.exe >nul 2>&1

:: 清理端口占用（以防有非 PM2 启动的进程）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4567"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo 所有服务已停止
echo.
pm2 status
echo.
pause
