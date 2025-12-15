import axios from 'axios'
import { ElMessage } from 'element-plus'

// Create axios instance
// 开发环境直连本地后端，生产环境直连服务器
const isDev = import.meta.env.DEV
const baseURL = isDev ? 'http://127.0.0.1:2000/api' : 'https://jzchardware.cn:8888/email/api'

// 导出 API 基础地址供其他模块使用
export const API_BASE_URL = baseURL

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
        // 使用自定义事件通知应用进行清理，而不是直接操作 localStorage
        // 这样可以确保 store 状态、定时器、WebSocket 等都被正确清理
        window.dispatchEvent(new CustomEvent('auth:expired', {
          detail: { message: '登录已过期，请重新登录' }
        }))
        // 同时清理 localStorage 作为后备
        localStorage.removeItem(getStorageKey('token'))
        localStorage.removeItem(getStorageKey('email'))
        localStorage.removeItem(getStorageKey('accountId'))
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
  async getEmails(params = {}, options = {}) {
    return instance.get('/emails', { params, signal: options.signal })
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

  async sendDraft(id, { approverId, approverGroupId, saveAsDefault = false }) {
    return instance.post(`/drafts/${id}/send`, {
      approver_id: approverId || null,
      approver_group_id: approverGroupId || null,
      save_as_default: saveAsDefault
    })
  },

  async submitDraft(id, { approverId, approverGroupId, saveAsDefault = false }) {
    return instance.post(`/drafts/${id}/send`, {
      approver_id: approverId || null,
      approver_group_id: approverGroupId || null,
      save_as_default: saveAsDefault
    })
  },

  async deleteDraft(id) {
    return instance.delete(`/drafts/${id}`)
  },

  // 审批相关
  async getApprovers() {
    return instance.get('/users/approvers')
  },

  async getPendingDrafts() {
    return instance.get('/drafts/pending')
  },

  async approveDraft(id) {
    return instance.post(`/drafts/${id}/approve`)
  },

  async rejectDraft(id, reason) {
    return instance.post(`/drafts/${id}/reject`, { reason })
  },

  async setDefaultApprover(approverId) {
    return instance.put('/users/me/default-approver', { approver_id: approverId })
  },

  // Approval Groups - 审批人组
  async getApprovalGroups() {
    return instance.get('/approval-groups')
  },

  async getAvailableApprovalGroups() {
    return instance.get('/approval-groups/available')
  },

  async createApprovalGroup(data) {
    return instance.post('/approval-groups', data)
  },

  async updateApprovalGroup(id, data) {
    return instance.put(`/approval-groups/${id}`, data)
  },

  async deleteApprovalGroup(id) {
    return instance.delete(`/approval-groups/${id}`)
  },

  async addGroupMember(groupId, memberId) {
    return instance.post(`/approval-groups/${groupId}/members`, { member_id: memberId })
  },

  async removeGroupMember(groupId, memberId) {
    return instance.delete(`/approval-groups/${groupId}/members/${memberId}`)
  },

  // Email Actions
  async translateEmail(id, signal = null) {
    // 翻译可能需要较长时间（Ollama），设置 10 分钟超时
    return instance.post(`/emails/${id}/translate`, null, {
      timeout: 600000,  // 10 分钟
      signal  // AbortController signal，用于取消请求
    })
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
  },

  // Labels - 邮件标签
  async getLabels() {
    return instance.get('/labels')
  },

  async getLabel(id) {
    return instance.get(`/labels/${id}`)
  },

  async createLabel(data) {
    return instance.post('/labels', data)
  },

  async updateLabel(id, data) {
    return instance.put(`/labels/${id}`, data)
  },

  async deleteLabel(id) {
    return instance.delete(`/labels/${id}`)
  },

  async addLabelsToEmail(emailId, labelIds) {
    return instance.post(`/labels/emails/${emailId}`, { label_ids: labelIds })
  },

  async removeLabelFromEmail(emailId, labelId) {
    return instance.delete(`/labels/emails/${emailId}/${labelId}`)
  },

  async getEmailLabels(emailId) {
    return instance.get(`/labels/emails/${emailId}`)
  },

  // Folders - 文件夹
  async getFolders() {
    return instance.get('/folders')
  },

  async getFolder(id) {
    return instance.get(`/folders/${id}`)
  },

  async createFolder(data) {
    return instance.post('/folders', data)
  },

  async updateFolder(id, data) {
    return instance.put(`/folders/${id}`, data)
  },

  async deleteFolder(id) {
    return instance.delete(`/folders/${id}`)
  },

  async addEmailsToFolder(folderId, emailIds) {
    return instance.post(`/folders/${folderId}/emails`, { email_ids: emailIds })
  },

  async removeEmailFromFolder(folderId, emailId) {
    return instance.delete(`/folders/${folderId}/emails/${emailId}`)
  },

  async getFolderEmails(folderId, params = {}, options = {}) {
    return instance.get(`/folders/${folderId}/emails`, { params, signal: options.signal })
  },

  // Calendar - 日历事件
  async getCalendarEvents(params = {}) {
    return instance.get('/calendar/events', { params })
  },

  async getCalendarEvent(id) {
    return instance.get(`/calendar/events/${id}`)
  },

  async createCalendarEvent(data) {
    return instance.post('/calendar/events', data)
  },

  async updateCalendarEvent(id, data) {
    return instance.put(`/calendar/events/${id}`, data)
  },

  async deleteCalendarEvent(id) {
    return instance.delete(`/calendar/events/${id}`)
  },

  async createEventFromEmail(emailId, data) {
    return instance.post(`/calendar/events/from-email/${emailId}`, data)
  },

  async getEventsByEmail(emailId) {
    return instance.get(`/calendar/events/by-email/${emailId}`)
  },

  // AI Extract - AI 邮件信息提取
  async extractEmail(emailId, force = false) {
    return instance.post(`/ai/extract/${emailId}`, null, { params: { force } })
  },

  async getExtraction(emailId) {
    return instance.get(`/ai/extract/${emailId}`)
  },

  async deleteExtraction(emailId) {
    return instance.delete(`/ai/extract/${emailId}`)
  },

  // Rules - 邮件规则
  async getRules() {
    return instance.get('/rules')
  },

  async getRule(id) {
    return instance.get(`/rules/${id}`)
  },

  async createRule(data) {
    return instance.post('/rules', data)
  },

  async updateRule(id, data) {
    return instance.put(`/rules/${id}`, data)
  },

  async deleteRule(id) {
    return instance.delete(`/rules/${id}`)
  },

  async toggleRule(id) {
    return instance.post(`/rules/${id}/toggle`)
  },

  async reorderRules(ruleIds) {
    return instance.post('/rules/reorder', { rule_ids: ruleIds })
  },

  async testRules(emailData) {
    return instance.post('/rules/test', { email_data: emailData })
  },

  async applyRulesToEmails(emailIds) {
    return instance.post('/rules/apply', emailIds)
  },

  async getRuleFieldOptions() {
    return instance.get('/rules/fields/options')
  }
}

export default api
