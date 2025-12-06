@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   供应商邮件翻译系统 - 打包脚本
echo ============================================
echo.

:: 检查项目根目录
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: 第一步：安装后端依赖
echo [1/5] 检查后端依赖...
cd backend

:: 检查是否有虚拟环境
if exist "venv\Scripts\activate.bat" (
    echo 使用虚拟环境...
    call venv\Scripts\activate.bat
) else (
    echo 提示：建议创建虚拟环境 (python -m venv venv)
)

:: 安装依赖
pip install -r requirements.txt -q
if errorlevel 1 (
    echo 错误：安装后端依赖失败
    pause
    exit /b 1
)

:: 安装 PyInstaller
pip install pyinstaller -q
if errorlevel 1 (
    echo 错误：安装 PyInstaller 失败
    pause
    exit /b 1
)
echo    后端依赖安装完成

:: 第二步：打包后端
echo.
echo [2/5] 打包后端...
if exist "dist" rd /s /q dist
if exist "build" rd /s /q build

pyinstaller backend.spec --noconfirm
if errorlevel 1 (
    echo 错误：后端打包失败
    pause
    exit /b 1
)

:: 检查打包结果
if not exist "dist\backend.exe" (
    echo 错误：未找到打包后的 backend.exe
    pause
    exit /b 1
)
echo    后端打包完成: backend\dist\backend.exe

:: 第三步：安装前端依赖
echo.
echo [3/5] 安装前端依赖...
cd "%ROOT_DIR%frontend"

call npm install
if errorlevel 1 (
    echo 错误：安装前端依赖失败
    pause
    exit /b 1
)
echo    前端依赖安装完成

:: 第四步：构建前端
echo.
echo [4/5] 构建前端资源...
call npm run build
if errorlevel 1 (
    echo 错误：前端构建失败
    pause
    exit /b 1
)
echo    前端构建完成

:: 第五步：打包 Electron
echo.
echo [5/5] 打包 Electron 应用...
call npx electron-builder --win
if errorlevel 1 (
    echo 错误：Electron 打包失败
    pause
    exit /b 1
)

echo.
echo ============================================
echo   打包完成！
echo ============================================
echo.
echo 安装程序位置:
echo   %ROOT_DIR%frontend\dist_electron\
echo.

:: 打开输出目录
explorer "%ROOT_DIR%frontend\dist_electron"

pause
