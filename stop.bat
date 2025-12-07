@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   停止开发服务
echo ========================================
echo.

:: 停止后端 (端口 2000)
echo 停止后端服务 (端口 2000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":2000 "') do (
    echo   停止 PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

:: 停止前端 (端口 4567)
echo 停止前端服务 (端口 4567)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":4567 "') do (
    echo   停止 PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

:: 停止 Electron
echo 停止 Electron...
taskkill /IM electron.exe /F >nul 2>&1

echo.
echo 所有服务已停止
pause
