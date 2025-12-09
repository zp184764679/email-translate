import axios from 'axios'
import { ElMessage } from 'element-plus'

// Create axios instance
// 开发环境直连本地后端，生产环境直连服务器
const isDev = import.meta.env.DEV
const baseURL = isDev ? 'http://127.0.0.1:2000/api' : 'https://jzchardware.cn:8888/email/api'

// 环境隔离的 localStorage key，开发版和生产版各自独立存储
const ENV_PREFIX = isDev ? 'dev_' : 'prod_'
export const getStorageKey = (key) => ENV_PREFIX + key

const instance = axios.create({
  baseURL,
  timeout: 30000
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(getStorageKey('token'))
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
        localStorage.removeItem(getStorageKey('token'))
        localStorage.removeItem(getStorageKey('email'))
        localStorage.removeItem(getStorageKey('accountId'))
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
    // 添加时间戳防止浏览器缓存
    return instance.get(`/emails/${id}`, { params: { _t: Date.now() } })
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

  // Contacts - 历史联系人（用于自动补全）
  async getContacts() {
    return instance.get('/emails/contacts')
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

  async batchTranslateAll() {
    return instance.post('/translate/batch-all', {}, { timeout: 300000 })
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

  // 批量操作
  async batchMarkAsRead(emailIds) {
    return instance.post('/emails/batch/read', { email_ids: emailIds })
  },

  async batchMarkAsUnread(emailIds) {
    return instance.post('/emails/batch/unread', { email_ids: emailIds })
  },

  async batchDelete(emailIds) {
    return instance.post('/emails/batch/delete', { email_ids: emailIds })
  },

  async batchFlag(emailIds) {
    return instance.post('/emails/batch/flag', { email_ids: emailIds })
  },

  async batchUnflag(emailIds) {
    return instance.post('/emails/batch/unflag', { email_ids: emailIds })
  },

  async sendEmail(data) {
    return instance.post('/emails/send', data)
  },

  // 附件下载
  getAttachmentUrl(emailId, attachmentId) {
    const token = localStorage.getItem(getStorageKey('token'))
    return `${baseURL}/emails/${emailId}/attachment/${attachmentId}?token=${token}`
  },

  async downloadAttachment(emailId, attachmentId, filename) {
    const response = await instance.get(
      `/emails/${emailId}/attachment/${attachmentId}`,
      { responseType: 'blob' }
    )
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },

  // 邮件导出
  async exportEmail(emailId, filename) {
    const response = await instance.get(
      `/emails/${emailId}/export`,
      { responseType: 'blob' }
    )
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename || 'email.eml')
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
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
  },

  // Signatures
  async getSignatures() {
    return instance.get('/signatures')
  },

  async getDefaultSignature() {
    return instance.get('/signatures/default')
  },

  async getSignature(id) {
    return instance.get(`/signatures/${id}`)
  },

  async createSignature(data) {
    return instance.post('/signatures', data)
  },

  async updateSignature(id, data) {
    return instance.put(`/signatures/${id}`, data)
  },

  async deleteSignature(id) {
    return instance.delete(`/signatures/${id}`)
  },

  async setDefaultSignature(id) {
    return instance.post(`/signatures/${id}/set-default`)
  }
}

export default api
