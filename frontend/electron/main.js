const { app, BrowserWindow, ipcMain, Notification, Menu, Tray } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const { autoUpdater } = require('electron-updater')
const http = require('http')

let mainWindow = null
let tray = null
let backendProcess = null

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

// 后端配置
const BACKEND_PORT = 8000
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

// 绕过代理设置，直接连接本地后端
delete process.env.http_proxy
delete process.env.HTTP_PROXY
delete process.env.https_proxy
delete process.env.HTTPS_PROXY

/**
 * 启动后端服务
 */
function startBackend() {
  return new Promise((resolve, reject) => {
    if (isDev) {
      // 开发模式：假设后端已手动启动
      console.log('开发模式：请手动启动后端服务')
      resolve()
      return
    }

    // 生产模式：启动打包的后端exe
    const backendPath = path.join(process.resourcesPath, 'backend', 'backend.exe')
    const fs = require('fs')

    if (!fs.existsSync(backendPath)) {
      console.error('后端程序不存在:', backendPath)
      reject(new Error('后端程序不存在'))
      return
    }

    console.log('启动后端服务:', backendPath)

    // 设置数据目录
    const userDataPath = app.getPath('userData')
    const dataDir = path.join(userDataPath, 'data')

    // 确保数据目录存在
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true })
    }

    // 启动后端进程
    backendProcess = spawn(backendPath, [], {
      cwd: path.dirname(backendPath),
      env: {
        ...process.env,
        DATA_DIR: dataDir,
        BACKEND_PORT: BACKEND_PORT.toString()
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true
    })

    backendProcess.stdout.on('data', (data) => {
      console.log(`[Backend] ${data}`)
    })

    backendProcess.stderr.on('data', (data) => {
      console.error(`[Backend Error] ${data}`)
    })

    backendProcess.on('error', (error) => {
      console.error('后端启动失败:', error)
      reject(error)
    })

    backendProcess.on('exit', (code) => {
      console.log(`后端进程退出，退出码: ${code}`)
      backendProcess = null
    })

    // 等待后端启动完成
    waitForBackend(resolve, reject)
  })
}

/**
 * 等待后端服务就绪
 */
function waitForBackend(resolve, reject, retries = 60) {
  const checkBackend = () => {
    http.get(`${BACKEND_URL}/health`, (res) => {
      if (res.statusCode === 200) {
        console.log('后端服务已就绪')
        resolve()
      } else {
        retry()
      }
    }).on('error', (err) => {
      console.log(`等待后端服务... (剩余重试: ${retries}, 错误: ${err.code})`)
      retry()
    })
  }

  const retry = () => {
    retries--
    if (retries <= 0) {
      reject(new Error('后端服务启动超时'))
    } else {
      setTimeout(checkBackend, 1000)
    }
  }

  // 开始检查 - 给后端更多启动时间
  setTimeout(checkBackend, 3000)
}

/**
 * 停止后端服务
 */
function stopBackend() {
  if (backendProcess) {
    console.log('停止后端服务...')
    backendProcess.kill()
    backendProcess = null
  }
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
    mainWindow.loadURL('http://localhost:3456')
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
  const iconPath = path.join(__dirname, '../public/favicon.ico')
  const fs = require('fs')
  if (!fs.existsSync(iconPath)) {
    console.log('Tray icon not found, skipping tray creation')
    return
  }
  try {
    tray = new Tray(iconPath)
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

// App events
app.whenReady().then(async () => {
  // 显示启动画面
  if (!isDev) {
    createSplash()
  }

  try {
    // 启动后端服务
    await startBackend()

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
      message: '后端服务启动失败，请检查系统配置',
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
  stopBackend()
})

// 确保后端进程被清理
app.on('quit', () => {
  stopBackend()
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
autoUpdater.on('update-available', () => {
  mainWindow.webContents.send('update-available')
})

autoUpdater.on('update-downloaded', () => {
  mainWindow.webContents.send('update-downloaded')
})

autoUpdater.on('error', (error) => {
  console.error('Update error:', error)
})

ipcMain.handle('install-update', () => {
  autoUpdater.quitAndInstall()
})

ipcMain.handle('check-for-updates', () => {
  autoUpdater.checkForUpdatesAndNotify()
})
