# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件
打包命令: pyinstaller backend.spec
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录
backend_dir = Path('.').resolve()

a = Analysis(
    ['main.py'],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[
        # 包含配置文件模板
        ('.env.example', '.') if Path('.env.example').exists() else ('', ''),
    ],
    hiddenimports=[
        # FastAPI 相关
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',

        # SQLAlchemy 相关
        'sqlalchemy',
        'sqlalchemy.ext.asyncio',
        'aiosqlite',

        # 邮件相关
        'imaplib',
        'smtplib',
        'email',

        # 翻译相关
        'httpx',
        'langdetect',

        # passlib 完整依赖
        'passlib',
        'passlib.context',
        'passlib.handlers',
        'passlib.handlers.bcrypt',
        'passlib.handlers.sha2_crypt',
        'passlib.handlers.des_crypt',
        'passlib.handlers.md5_crypt',
        'passlib.handlers.pbkdf2',
        'passlib.handlers.argon2',
        'passlib.handlers.misc',
        'bcrypt',

        # 其他
        'pydantic',
        'pydantic_settings',
        'jose',
        'jose.jwt',
        'jose.constants',
        'multipart',
        'python_multipart',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台窗口便于调试
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 暂不使用图标
)
