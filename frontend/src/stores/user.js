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

  function logout() {
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

  // 显示新邮件桌面通知
  function showNewEmailNotification(count) {
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

  return {
    token,
    email,
    accountId,
    emailRefreshKey,
    lastFetchTime,
    isFetching,
    isLoggedIn,
    layoutMode,
    login,
    logout,
    fetchAccountInfo,
    triggerEmailRefresh,
    setLayoutMode,
    autoFetchEmails,
    startAutoFetch,
    stopAutoFetch,
    showNewEmailNotification
  }
})
