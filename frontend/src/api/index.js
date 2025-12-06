import axios from 'axios'
import { ElMessage } from 'element-plus'

// Create axios instance
const instance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 30000
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
instance.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response

      if (status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('email')
        localStorage.removeItem('accountId')
        window.location.href = '/#/login'
        ElMessage.error('登录已过期，请重新登录')
      } else if (status === 403) {
        ElMessage.error(data.detail || '没有权限执行此操作')
      } else if (status === 404) {
        ElMessage.error(data.detail || '请求的资源不存在')
      } else {
        ElMessage.error(data.detail || '请求失败')
      }
    } else {
      ElMessage.error('网络错误，请检查连接')
    }
    return Promise.reject(error)
  }
)

// API methods
const api = {
  // Auth - 使用邮箱登录
  async login(email, password) {
    return instance.post('/users/login', { email, password })
  },

  async getCurrentAccount() {
    return instance.get('/users/me')
  },

  async logout() {
    return instance.post('/users/logout')
  },

  // Emails
  async getEmails(params = {}) {
    return instance.get('/emails', { params })
  },

  async getEmail(id) {
    return instance.get(`/emails/${id}`)
  },

  async getEmailThread(threadId) {
    return instance.get(`/emails/thread/${threadId}`)
  },

  async fetchEmails(sinceDays = 7) {
    return instance.post('/emails/fetch', { since_days: sinceDays })
  },

  async getEmailStats() {
    return instance.get('/emails/stats/summary')
  },

  // Translation
  async translate(text, targetLang = 'zh', supplierId = null, context = null) {
    return instance.post('/translate', {
      text,
      target_lang: targetLang,
      supplier_id: supplierId,
      context
    })
  },

  async translateReply(text, targetLang, supplierId = null, context = null) {
    return instance.post('/translate/reverse', {
      text,
      target_lang: targetLang,
      supplier_id: supplierId,
      context
    })
  },

  async createBatchTranslation(emailIds) {
    return instance.post('/translate/batch', { email_ids: emailIds })
  },

  async getTranslationUsage() {
    return instance.get('/translate/usage')
  },

  // Glossary
  async getGlossary(supplierId) {
    return instance.get(`/translate/glossary/${supplierId}`)
  },

  async addGlossaryTerm(data) {
    return instance.post('/translate/glossary', data)
  },

  async deleteGlossaryTerm(termId) {
    return instance.delete(`/translate/glossary/${termId}`)
  },

  // Drafts
  async getDrafts() {
    return instance.get('/drafts')
  },

  async getMyDrafts() {
    return instance.get('/drafts')
  },

  async createDraft(data) {
    return instance.post('/drafts', data)
  },

  async updateDraft(id, data) {
    return instance.put(`/drafts/${id}`, data)
  },

  async sendDraft(id) {
    return instance.post(`/drafts/${id}/send`)
  },

  async submitDraft(id) {
    return instance.post(`/drafts/${id}/send`)
  },

  async deleteDraft(id) {
    return instance.delete(`/drafts/${id}`)
  },

  // Email Actions
  async translateEmail(id) {
    return instance.post(`/emails/${id}/translate`)
  },

  async markAsRead(id) {
    return instance.patch(`/emails/${id}/read`)
  },

  async markAsUnread(id) {
    return instance.patch(`/emails/${id}/unread`)
  },

  async flagEmail(id) {
    return instance.patch(`/emails/${id}/flag`)
  },

  async unflagEmail(id) {
    return instance.patch(`/emails/${id}/unflag`)
  },

  async deleteEmail(id) {
    return instance.delete(`/emails/${id}`)
  },

  async sendEmail(data) {
    return instance.post('/emails/send', data)
  },

  // Suppliers
  async getSuppliers() {
    return instance.get('/suppliers')
  },

  async getSupplier(id) {
    return instance.get(`/suppliers/${id}`)
  },

  async createSupplier(data) {
    return instance.post('/suppliers', data)
  },

  async updateSupplier(id, data) {
    return instance.put(`/suppliers/${id}`, data)
  },

  async deleteSupplier(id) {
    return instance.delete(`/suppliers/${id}`)
  }
}

export default api
