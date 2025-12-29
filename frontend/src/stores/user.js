import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getStorageKey } from '@/api'

// 自动收件配置
const AUTO_FETCH_INTERVAL = 5 * 60 * 1000  // 5分钟

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem(getStorageKey('token')) || '')
  const email = ref(localStorage.getItem(getStorageKey('email')) || '')
  const accountId = ref(localStorage.getItem(getStorageKey('accountId')) || null)
  const emailRefreshKey = ref(0)  // 用于触发邮件列表刷新
  const lastFetchTime = ref(null)  // 上次拉取时间
  const autoFetchTimer = ref(null)  // 自动拉取定时器
  const isFetching = ref(false)  // 是否正在拉取
  const selectedEmailIds = ref([])  // 当前选中的邮件ID列表

  // 布局设置：list（列表）, right（右侧预览）, bottom（底部预览）
  const layoutMode = ref(localStorage.getItem(getStorageKey('layoutMode')) || 'list')

  function setLayoutMode(mode) {
    layoutMode.value = mode
    localStorage.setItem(getStorageKey('layoutMode'), mode)
  }

  const isLoggedIn = computed(() => !!token.value)

  function triggerEmailRefresh() {
    emailRefreshKey.value++
  }

  async function login(emailAddr, password) {
    const response = await api.login(emailAddr, password)
    token.value = response.access_token
    email.value = response.email
    accountId.value = response.account_id
    localStorage.setItem(getStorageKey('token'), token.value)
    localStorage.setItem(getStorageKey('email'), email.value)
    localStorage.setItem(getStorageKey('accountId'), accountId.value)
    return response
  }

  async function logout() {
    // 停止自动拉取定时器
    stopAutoFetch()
    // 清除选中的邮件
    selectedEmailIds.value = []

    // 重置邮件 store（需要延迟导入避免循环依赖）
    // 使用 await 确保在导航到登录页之前完成重置
    try {
      const { useEmailStore } = await import('./emails')
      const emailStore = useEmailStore()
      emailStore.reset()
    } catch (e) {
      console.error('[Logout] Failed to reset email store:', e)
    }

    token.value = ''
    email.value = ''
    accountId.value = null
    localStorage.removeItem(getStorageKey('token'))
    localStorage.removeItem(getStorageKey('email'))
    localStorage.removeItem(getStorageKey('accountId'))
  }

  async function fetchAccountInfo() {
    if (token.value) {
      try {
        const info = await api.getCurrentAccount()
        email.value = info.email
        accountId.value = info.id
      } catch (e) {
        logout()
      }
    }
  }

  // 自动拉取邮件
  async function autoFetchEmails() {
    if (!isLoggedIn.value || isFetching.value) return

    isFetching.value = true
    try {
      const result = await api.fetchEmails(30)
      lastFetchTime.value = new Date()

      // 如果有新邮件，触发刷新和通知
      if (result.new_count > 0) {
        triggerEmailRefresh()
        showNewEmailNotification(result.new_count)
      }

      return result
    } catch (e) {
      console.error('Auto fetch emails failed:', e)
    } finally {
      isFetching.value = false
    }
  }

  // 播放新邮件提示音
  function playNotificationSound() {
    try {
      // 使用 Web Audio API 播放简单的提示音
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const oscillator = audioContext.createOscillator()
      const gainNode = audioContext.createGain()

      oscillator.connect(gainNode)
      gainNode.connect(audioContext.destination)

      // 设置音调和音量
      oscillator.frequency.setValueAtTime(880, audioContext.currentTime) // A5 音符
      oscillator.type = 'sine'
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime)
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3)

      // 播放
      oscillator.start(audioContext.currentTime)
      oscillator.stop(audioContext.currentTime + 0.3)
    } catch (e) {
      console.log('播放提示音失败:', e)
    }
  }

  // 显示新邮件桌面通知
  function showNewEmailNotification(count) {
    // 播放提示音
    playNotificationSound()

    // 检查是否在 Electron 环境
    if (typeof window !== 'undefined' && window.Notification) {
      if (Notification.permission === 'granted') {
        new Notification('新邮件', {
          body: `您有 ${count} 封新邮件`,
          icon: '/favicon.ico'
        })
      } else if (Notification.permission !== 'denied') {
        Notification.requestPermission()
      }
    }
  }

  // 启动自动拉取定时器
  function startAutoFetch() {
    // 未登录时不启动
    if (!isLoggedIn.value) {
      console.log('未登录，跳过自动收件')
      return
    }

    if (autoFetchTimer.value) {
      clearInterval(autoFetchTimer.value)
    }

    // 立即执行一次
    autoFetchEmails()

    // 设置定时器
    autoFetchTimer.value = setInterval(() => {
      autoFetchEmails()
    }, AUTO_FETCH_INTERVAL)

    console.log(`自动收件已启动，间隔 ${AUTO_FETCH_INTERVAL / 1000} 秒`)
  }

  // 停止自动拉取
  function stopAutoFetch() {
    if (autoFetchTimer.value) {
      clearInterval(autoFetchTimer.value)
      autoFetchTimer.value = null
      console.log('自动收件已停止')
    }
  }

  // 设置选中的邮件ID
  function setSelectedEmailIds(ids) {
    selectedEmailIds.value = ids
  }

  return {
    token,
    email,
    accountId,
    emailRefreshKey,
    lastFetchTime,
    isFetching,
    isLoggedIn,
    layoutMode,
    selectedEmailIds,
    login,
    logout,
    fetchAccountInfo,
    triggerEmailRefresh,
    setLayoutMode,
    setSelectedEmailIds,
    autoFetchEmails,
    startAutoFetch,
    stopAutoFetch,
    showNewEmailNotification
  }
})
