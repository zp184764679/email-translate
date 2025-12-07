@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   供应商邮件翻译系统 - PM2 开发环境
echo ========================================
echo.

:: 检查 PM2 是否安装
pm2 --version >nul 2>&1
if errorlevel 1 (
    echo PM2 未安装，正在安装...
    npm install -g pm2
)

:: 先停止所有已运行的服务（防止重复）
echo [1/3] 清理旧进程...
pm2 delete email-backend email-frontend email-electron >nul 2>&1
echo   已清理
echo.

:: 启动后端和前端
echo [2/3] 启动后端和前端服务...
pm2 start ecosystem.config.js --only email-backend,email-frontend
echo.

:: 等待服务就绪
echo [3/3] 等待服务就绪...
:wait_services
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo   等待后端...
    goto wait_services
)
curl -s http://127.0.0.1:4567 >nul 2>&1
if errorlevel 1 (
    echo   等待前端...
    goto wait_services
)

echo   服务已就绪
echo.

:: 启动 Electron
echo 启动 Electron 应用...
pm2 start ecosystem.config.js --only email-electron

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo.
echo   后端: http://127.0.0.1:8000
echo   前端: http://127.0.0.1:4567
echo.
echo   常用命令:
echo   pm2 status     - 查看状态
echo   pm2 logs       - 查看日志
echo   pm2 monit      - 实时监控
echo   pm2 stop all   - 停止所有
echo   pm2 restart all - 重启所有
echo.
pause
