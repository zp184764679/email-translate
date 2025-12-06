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
    ipcRenderer.on('update-available', callback)
  },
  onUpdateDownloaded: (callback) => {
    ipcRenderer.on('update-downloaded', callback)
  }
})
