import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const email = ref(localStorage.getItem('email') || '')
  const accountId = ref(localStorage.getItem('accountId') || null)
  const emailRefreshKey = ref(0)  // 用于触发邮件列表刷新

  const isLoggedIn = computed(() => !!token.value)

  function triggerEmailRefresh() {
    emailRefreshKey.value++
  }

  async function login(emailAddr, password) {
    const response = await api.login(emailAddr, password)
    token.value = response.access_token
    email.value = response.email
    accountId.value = response.account_id
    localStorage.setItem('token', token.value)
    localStorage.setItem('email', email.value)
    localStorage.setItem('accountId', accountId.value)
    return response
  }

  function logout() {
    token.value = ''
    email.value = ''
    accountId.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('email')
    localStorage.removeItem('accountId')
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

  return {
    token,
    email,
    accountId,
    emailRefreshKey,
    isLoggedIn,
    login,
    logout,
    fetchAccountInfo,
    triggerEmailRefresh
  }
})
