const { app, BrowserWindow, ipcMain, Notification, Menu, Tray, dialog } = require('electron')
const path = require('path')
const { autoUpdater } = require('electron-updater')
const https = require('https')

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

// 单实例锁定 - 开发版和生产版使用不同的锁，可以同时运行
// 开发版使用 'email-translate-dev'，生产版使用默认锁
const lockKey = isDev ? { additionalData: { dev: true } } : undefined
const gotTheLock = app.requestSingleInstanceLock(lockKey)

if (!gotTheLock) {
  console.log(`另一个${isDev ? '开发版' : '生产版'}实例已在运行，退出当前实例`)
  app.quit()
}

let mainWindow = null
let tray = null

// 后端配置 - 统一部署在服务器
const BACKEND_URL = 'https://jzchardware.cn:8888/email/api'

/**
 * 检查服务器后端是否可用
 */
function checkBackendHealth() {
  return new Promise((resolve) => {
    const req = https.get(`${BACKEND_URL}/health`, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(5000, () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, '../public/favicon.ico'),
    title: '供应商邮件翻译系统',
    show: false  // 先隐藏，等加载完成后显示
  })

  // Load the app
  if (isDev) {
    mainWindow.loadURL('http://localhost:4567')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // 页面加载完成后显示窗口
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // Handle window close
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
    return false
  })

  // Check for updates
  if (!isDev) {
    autoUpdater.checkForUpdatesAndNotify()
  }
}

function createTray() {
  // 开发模式和生产模式使用不同的图标路径
  const iconPath = isDev
    ? path.join(__dirname, '../public/favicon.ico')
    : path.join(process.resourcesPath, 'app.asar', 'dist', 'favicon.ico')

  // 备用路径
  const fallbackPaths = [
    path.join(__dirname, '../public/favicon.ico'),
    path.join(__dirname, '../dist/favicon.ico'),
    path.join(process.resourcesPath || '', 'app.asar', 'dist', 'favicon.ico')
  ]

  const fs = require('fs')
  let finalIconPath = iconPath

  if (!fs.existsSync(finalIconPath)) {
    // 尝试备用路径
    finalIconPath = fallbackPaths.find(p => fs.existsSync(p))
    if (!finalIconPath) {
      console.log('Tray icon not found in any path, skipping tray creation')
      console.log('Tried paths:', fallbackPaths)
      return
    }
  }

  console.log('Creating tray with icon:', finalIconPath)

  try {
    tray = new Tray(finalIconPath)
  } catch (error) {
    console.log('Failed to create tray, skipping:', error.message)
    return
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '打开主窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
        }
      }
    },
    {
      label: '检查更新',
      click: () => {
        autoUpdater.checkForUpdatesAndNotify()
      }
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.isQuitting = true
        app.quit()
      }
    }
  ])

  tray.setToolTip('供应商邮件翻译系统')
  tray.setContextMenu(contextMenu)

  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.show()
    }
  })
}

// 创建启动画面
let splashWindow = null

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  })

  splashWindow.loadURL(`data:text/html;charset=utf-8,
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          margin: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          height: 100vh;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          color: white;
          border-radius: 12px;
        }
        .title { font-size: 24px; margin-bottom: 20px; font-weight: 600; }
        .spinner {
          width: 40px;
          height: 40px;
          border: 3px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .status { margin-top: 20px; font-size: 14px; opacity: 0.9; }
      </style>
    </head>
    <body>
      <div class="title">供应商邮件翻译系统</div>
      <div class="spinner"></div>
      <div class="status">正在启动服务...</div>
    </body>
    </html>
  `)
}

function closeSplash() {
  if (splashWindow) {
    splashWindow.close()
    splashWindow = null
  }
}

// 当第二个实例尝试启动时，聚焦已有窗口
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
})

// App events
app.whenReady().then(async () => {
  // 显示启动画面
  if (!isDev) {
    createSplash()
  }

  try {
    // 检查服务器后端是否可用
    const backendOk = await checkBackendHealth()
    if (!backendOk) {
      console.warn('服务器后端暂时不可用，但仍继续启动应用')
    }

    // 创建主窗口
    await createWindow()
    createTray()

    // 关闭启动画面
    closeSplash()

  } catch (error) {
    console.error('启动失败:', error)
    closeSplash()

    // 显示错误对话框
    const { dialog } = require('electron')
    await dialog.showMessageBox({
      type: 'error',
      title: '启动失败',
      message: '应用启动失败，请检查网络连接',
      detail: error.message
    })

    app.quit()
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  app.isQuitting = true
})

// IPC handlers
ipcMain.handle('show-notification', (event, { title, body }) => {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show()
  }
})

ipcMain.handle('get-app-version', () => {
  return app.getVersion()
})

// Auto updater events
autoUpdater.on('checking-for-update', () => {
  console.log('正在检查更新...')
})

autoUpdater.on('update-available', (info) => {
  console.log('发现新版本:', info.version)
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '发现新版本',
    message: `发现新版本 ${info.version}，正在下载...`,
    buttons: ['确定']
  })
  mainWindow.webContents.send('update-available')
})

autoUpdater.on('update-not-available', () => {
  console.log('当前已是最新版本')
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '检查更新',
    message: '当前已是最新版本',
    buttons: ['确定']
  })
})

autoUpdater.on('update-downloaded', (info) => {
  console.log('更新下载完成:', info.version)
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '更新就绪',
    message: `新版本 ${info.version} 已下载完成，是否立即安装？`,
    buttons: ['立即安装', '稍后']
  }).then((result) => {
    if (result.response === 0) {
      autoUpdater.quitAndInstall()
    }
  })
  mainWindow.webContents.send('update-downloaded')
})

autoUpdater.on('error', (error) => {
  console.error('Update error:', error)
  dialog.showMessageBox(mainWindow, {
    type: 'error',
    title: '更新失败',
    message: `检查更新失败: ${error.message}`,
    buttons: ['确定']
  })
})

autoUpdater.on('download-progress', (progress) => {
  console.log(`下载进度: ${Math.round(progress.percent)}%`)
})

ipcMain.handle('install-update', () => {
  autoUpdater.quitAndInstall()
})

ipcMain.handle('check-for-updates', () => {
  autoUpdater.checkForUpdatesAndNotify()
})
