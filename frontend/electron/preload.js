const { contextBridge, ipcRenderer } = require('electron')

// Expose protected methods to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
  // Notifications
  showNotification: (title, body) => {
    ipcRenderer.invoke('show-notification', { title, body })
  },

  // App version
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // Updates
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  installUpdate: () => ipcRenderer.invoke('install-update'),

  // Update events
  onUpdateAvailable: (callback) => {
    ipcRenderer.on('update-available', (event, version) => callback(version))
  },
  onUpdateDownloaded: (callback) => {
    ipcRenderer.on('update-downloaded', callback)
  },
  onDownloadStarted: (callback) => {
    ipcRenderer.on('download-started', (event, version) => callback(version))
  },
  onDownloadProgress: (callback) => {
    ipcRenderer.on('download-progress', (event, progress) => callback(progress))
  },
  onDownloadComplete: (callback) => {
    ipcRenderer.on('download-complete', (event, version) => callback(version))
  },
  onUpdateError: (callback) => {
    ipcRenderer.on('update-error', (event, error) => callback(error))
  }
})
