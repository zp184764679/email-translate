import axios from 'axios'
import { ElMessage } from 'element-plus'

// Create axios instance
// 开发环境直连本地后端，生产环境直连服务器
const isDev = import.meta.env.DEV
const baseURL = isDev ? 'http://127.0.0.1:2000/api' : 'https://jzchardware.cn/email/api'

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
    // 忽略被取消的请求（页面刷新、组件卸载等场景）
    if (error.code === 'ERR_CANCELED' || error.name === 'CanceledError') {
      console.log('[API] Request cancelled:', error.config?.url)
      return Promise.reject(error)
    }

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
    // 添加时间戳防止浏览器缓存
    return instance.get('/emails', { params: { ...params, _t: Date.now() }, signal: options.signal })
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

  async submitDraft(id, { approverId, approverGroupId, saveAsDefault = false } = {}) {
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

  // 定时发送
  async getScheduledDrafts() {
    return instance.get('/drafts/scheduled')
  },

  async scheduleDraft(id, scheduledAt) {
    // scheduledAt 应该是 ISO 格式的 UTC 时间字符串
    return instance.post(`/drafts/${id}/schedule`, { scheduled_at: scheduledAt })
  },

  async cancelScheduledDraft(id) {
    return instance.post(`/drafts/${id}/cancel-schedule`)
  },

  async rescheduleDraft(id, scheduledAt) {
    return instance.put(`/drafts/${id}/reschedule`, { scheduled_at: scheduledAt })
  },

  // Email Actions
  async translateEmail(id, { force = false, signal = null } = {}) {
    // 翻译可能需要较长时间（Ollama），设置 10 分钟超时
    // force=true 会清除已有翻译缓存，强制重新翻译
    const params = force ? { force: true } : {}
    return instance.post(`/emails/${id}/translate`, null, {
      params,
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

  async sendEmail(data, attachments = []) {
    // 如果有附件，使用 FormData 发送到专用端点
    if (attachments && attachments.length > 0) {
      const formData = new FormData()
      formData.append('to', data.to)
      formData.append('subject', data.subject)
      formData.append('body', data.body)
      if (data.cc) formData.append('cc', data.cc)

      // 添加所有附件
      for (const file of attachments) {
        formData.append('attachments', file, file.name)
      }

      return instance.post('/emails/send-with-attachments', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    }
    // 无附件时使用普通 JSON
    return instance.post('/emails/send', data)
  },

  // 附件打包下载（ZIP）
  async downloadAllAttachments(emailId) {
    const response = await instance.get(
      `/emails/${emailId}/attachments/download-all`,
      { responseType: 'blob' }
    )
    // 从 Content-Disposition 获取文件名，或使用默认
    const contentDisposition = response.headers?.['content-disposition'] || ''
    let filename = '附件.zip'
    const match = contentDisposition.match(/filename="?([^"]+)"?/)
    if (match) filename = decodeURIComponent(match[1])

    const url = window.URL.createObjectURL(new Blob([response]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },

  // 附件下载
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

  // 附件预览（返回 blob URL，调用者需要在使用后调用 revokeObjectURL）
  async previewAttachment(emailId, attachmentId) {
    const response = await instance.get(
      `/emails/${emailId}/attachment/${attachmentId}`,
      { responseType: 'blob' }
    )
    return window.URL.createObjectURL(new Blob([response]))
  },

  // ========== 附件管理 ==========

  // 附件搜索
  async searchAttachments(params = {}) {
    return instance.get('/attachments/search', { params })
  },

  // 附件存储统计
  async getAttachmentStats() {
    return instance.get('/attachments/stats')
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

  // Supplier AI Classification - AI 供应商分类
  async analyzeSupplierCategory(supplierId) {
    return instance.post(`/suppliers/${supplierId}/analyze-category`, null, { timeout: 60000 })
  },

  async batchAnalyzeSuppliers(supplierIds = null, forceReanalyze = false) {
    return instance.post('/suppliers/batch-analyze', {
      supplier_ids: supplierIds,
      force_reanalyze: forceReanalyze
    }, { timeout: 300000 })
  },

  async getSupplierCategoryStats() {
    return instance.get('/suppliers/category-stats')
  },

  async updateSupplierCategory(supplierId, category) {
    return instance.put(`/suppliers/${supplierId}/category`, { category })
  },

  // Supplier Domains - 供应商多域名管理
  async getSupplierDomains(supplierId) {
    return instance.get(`/suppliers/${supplierId}/domains`)
  },

  async addSupplierDomain(supplierId, data) {
    return instance.post(`/suppliers/${supplierId}/domains`, data)
  },

  async deleteSupplierDomain(supplierId, domainId) {
    return instance.delete(`/suppliers/${supplierId}/domains/${domainId}`)
  },

  // Supplier Contacts - 供应商联系人管理
  async getSupplierContacts(supplierId) {
    return instance.get(`/suppliers/${supplierId}/contacts`)
  },

  async addSupplierContact(supplierId, data) {
    return instance.post(`/suppliers/${supplierId}/contacts`, data)
  },

  async updateSupplierContact(supplierId, contactId, data) {
    return instance.put(`/suppliers/${supplierId}/contacts/${contactId}`, data)
  },

  async deleteSupplierContact(supplierId, contactId) {
    return instance.delete(`/suppliers/${supplierId}/contacts/${contactId}`)
  },

  // Supplier Tags - 供应商标签管理
  async getSupplierTags() {
    return instance.get('/suppliers/tags')
  },

  async createSupplierTag(data) {
    return instance.post('/suppliers/tags', data)
  },

  async updateSupplierTag(tagId, data) {
    return instance.put(`/suppliers/tags/${tagId}`, data)
  },

  async deleteSupplierTag(tagId) {
    return instance.delete(`/suppliers/tags/${tagId}`)
  },

  async getSupplierTagMappings(supplierId) {
    return instance.get(`/suppliers/${supplierId}/tags`)
  },

  async addTagToSupplier(supplierId, tagId) {
    return instance.post(`/suppliers/${supplierId}/tags/${tagId}`)
  },

  async removeTagFromSupplier(supplierId, tagId) {
    return instance.delete(`/suppliers/${supplierId}/tags/${tagId}`)
  },

  // ============ Customers - 客户管理 ============
  async getCustomers(params = {}) {
    return instance.get('/customers', { params })
  },

  async getCustomer(id) {
    return instance.get(`/customers/${id}`)
  },

  async createCustomer(data) {
    return instance.post('/customers', data)
  },

  async updateCustomer(id, data) {
    return instance.put(`/customers/${id}`, data)
  },

  async deleteCustomer(id) {
    return instance.delete(`/customers/${id}`)
  },

  // Customer Category - 客户分类
  async getCustomerCategoryStats() {
    return instance.get('/customers/category-stats')
  },

  async updateCustomerCategory(customerId, category) {
    return instance.put(`/customers/${customerId}/category`, { category })
  },

  // Customer Domains - 客户多域名管理
  async getCustomerDomains(customerId) {
    return instance.get(`/customers/${customerId}/domains`)
  },

  async addCustomerDomain(customerId, data) {
    return instance.post(`/customers/${customerId}/domains`, data)
  },

  async deleteCustomerDomain(customerId, domainId) {
    return instance.delete(`/customers/${customerId}/domains/${domainId}`)
  },

  // Customer Contacts - 客户联系人管理
  async getCustomerContacts(customerId) {
    return instance.get(`/customers/${customerId}/contacts`)
  },

  async addCustomerContact(customerId, data) {
    return instance.post(`/customers/${customerId}/contacts`, data)
  },

  async updateCustomerContact(customerId, contactId, data) {
    return instance.put(`/customers/${customerId}/contacts/${contactId}`, data)
  },

  async deleteCustomerContact(customerId, contactId) {
    return instance.delete(`/customers/${customerId}/contacts/${contactId}`)
  },

  // Customer Tags - 客户标签管理
  async getCustomerTags() {
    return instance.get('/customers/tags')
  },

  async createCustomerTag(data) {
    return instance.post('/customers/tags', data)
  },

  async updateCustomerTag(tagId, data) {
    return instance.put(`/customers/tags/${tagId}`, data)
  },

  async deleteCustomerTag(tagId) {
    return instance.delete(`/customers/tags/${tagId}`)
  },

  async getCustomerTagMappings(customerId) {
    return instance.get(`/customers/${customerId}/tags`)
  },

  async addTagToCustomer(customerId, tagId) {
    return instance.post(`/customers/${customerId}/tags/${tagId}`)
  },

  async removeTagFromCustomer(customerId, tagId) {
    return instance.delete(`/customers/${customerId}/tags/${tagId}`)
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

  async checkEventConflicts(startTime, endTime, excludeEventId = null) {
    return instance.post('/calendar/events/check-conflicts', {
      start_time: startTime,
      end_time: endTime,
      exclude_event_id: excludeEventId
    })
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
  },

  // Dashboard
  async getDashboardStats() {
    return instance.get('/dashboard/stats')
  },

  // Notifications
  async getNotifications(params = {}) {
    return instance.get('/notifications', { params })
  },

  async getUnreadNotificationCount() {
    return instance.get('/notifications/unread-count')
  },

  async markNotificationAsRead(notificationId) {
    return instance.patch(`/notifications/${notificationId}/read`)
  },

  async markAllNotificationsAsRead() {
    return instance.post('/notifications/read-all')
  },

  async deleteNotification(notificationId) {
    return instance.delete(`/notifications/${notificationId}`)
  },

  async clearAllNotifications() {
    return instance.delete('/notifications')
  },

  // Portal Task Integration - 任务提取与导入
  async getTaskExtraction(emailId) {
    return instance.get(`/task-extractions/emails/${emailId}`)
  },

  async triggerTaskExtraction(emailId, force = false) {
    return instance.post(`/task-extractions/emails/${emailId}/extract`, null, { params: { force } })
  },

  async matchProjects(emailId) {
    return instance.get(`/task-extractions/emails/${emailId}/match-projects`)
  },

  async createTaskFromEmail(emailId, data) {
    return instance.post(`/task-extractions/emails/${emailId}/create-task`, data)
  },

  async getEmployeesForAssignment(emailId, params = {}) {
    return instance.get(`/task-extractions/emails/${emailId}/employees`, { params })
  },

  async getImportStatus(emailId) {
    return instance.get(`/task-extractions/emails/${emailId}/import-status`)
  },

  // ============ Email Templates - 邮件模板 ============
  // 模板列表
  async getTemplates(params = {}) {
    return instance.get('/templates', { params })
  },

  // 模板详情
  async getTemplate(id) {
    return instance.get(`/templates/${id}`)
  },

  // 创建模板
  async createTemplate(data) {
    return instance.post('/templates', data)
  },

  // 更新模板
  async updateTemplate(id, data) {
    return instance.put(`/templates/${id}`, data)
  },

  // 删除模板
  async deleteTemplate(id) {
    return instance.delete(`/templates/${id}`)
  },

  // 翻译模板
  async translateTemplate(id, targetLang, forceRetranslate = false) {
    return instance.post(`/templates/${id}/translate`, {
      target_lang: targetLang,
      force_retranslate: forceRetranslate
    }, { timeout: 60000 })
  },

  // 共享模板
  async shareTemplate(id) {
    return instance.post(`/templates/${id}/share`)
  },

  // 取消共享模板
  async unshareTemplate(id) {
    return instance.post(`/templates/${id}/unshare`)
  },

  // 使用模板（增加计数+替换变量）
  async useTemplate(id, targetLang = null, variables = null) {
    return instance.post(`/templates/${id}/use`, {
      target_lang: targetLang,
      variables
    })
  },

  // 获取模板分类列表
  async getTemplateCategories() {
    return instance.get('/templates/categories')
  },

  // 获取可用变量列表
  async getTemplateVariables() {
    return instance.get('/templates/variables')
  },

  // 获取支持的翻译语言
  async getTemplateLanguages() {
    return instance.get('/templates/languages')
  },

  // ============ Archive - 邮件归档 ============
  // 归档文件夹列表
  async getArchiveFolders() {
    return instance.get('/archive/folders')
  },

  // 创建归档文件夹
  async createArchiveFolder(data) {
    return instance.post('/archive/folders', data)
  },

  // 更新归档文件夹
  async updateArchiveFolder(id, data) {
    return instance.put(`/archive/folders/${id}`, data)
  },

  // 删除归档文件夹
  async deleteArchiveFolder(id, force = false) {
    return instance.delete(`/archive/folders/${id}`, { params: { force } })
  },

  // 归档邮件
  async archiveEmail(emailId, folderId) {
    return instance.post(`/archive/emails/${emailId}`, { folder_id: folderId })
  },

  // 取消归档
  async unarchiveEmail(emailId) {
    return instance.post(`/archive/emails/${emailId}/unarchive`)
  },

  // 批量归档
  async batchArchiveEmails(emailIds, folderId) {
    return instance.post('/archive/batch', { email_ids: emailIds, folder_id: folderId })
  },

  // 批量取消归档
  async batchUnarchiveEmails(emailIds) {
    return instance.post('/archive/batch/unarchive', { email_ids: emailIds })
  },

  // 获取归档邮件列表
  async getArchivedEmails(params = {}) {
    return instance.get('/archive/emails', { params })
  },

  // 归档统计
  async getArchiveStats() {
    return instance.get('/archive/stats')
  },

  // 自动创建年份文件夹
  async autoCreateYearFolder(year) {
    return instance.post('/archive/folders/auto-create-year', null, { params: { year } })
  },

  // ============ Classification - 邮件分类 ============
  // 获取分类定义
  async getCategories() {
    return instance.get('/classification/categories')
  },

  // 分类单封邮件
  async classifyEmail(emailId, force = false) {
    return instance.post(`/classification/emails/${emailId}`, null, { params: { force } })
  },

  // 批量分类
  async batchClassifyEmails(emailIds, force = false) {
    return instance.post('/classification/batch', { email_ids: emailIds, force })
  },

  // 获取分类统计
  async getClassificationStats() {
    return instance.get('/classification/stats')
  },

  // 自动分类未分类邮件
  async autoClassifyEmails(limit = 100) {
    return instance.post('/classification/auto-classify', null, { params: { limit } })
  },

  // 获取邮件分类结果
  async getEmailClassification(emailId) {
    return instance.get(`/classification/emails/${emailId}`)
  },

  // ============ Statistics - 统计报表 ============
  // 概览统计
  async getStatisticsOverview() {
    return instance.get('/statistics/overview')
  },

  // 邮件量趋势
  async getEmailTrend(period = 'daily', days = 30) {
    return instance.get('/statistics/email-trend', { params: { period, days } })
  },

  // 供应商排行
  async getSupplierRanking(limit = 10, days = 30) {
    return instance.get('/statistics/supplier-ranking', { params: { limit, days } })
  },

  // 翻译引擎统计
  async getTranslationEngineStats(months = 1) {
    return instance.get('/statistics/translation-engine-stats', { params: { months } })
  },

  // 分类分布
  async getCategoryDistribution(days = 30) {
    return instance.get('/statistics/category-distribution', { params: { days } })
  },

  // 响应时间分析
  async getResponseTimeStats(days = 30) {
    return instance.get('/statistics/response-time', { params: { days } })
  },

  // 缓存统计
  async getCacheStats() {
    return instance.get('/statistics/cache-stats')
  },

  // 每日活动热力图
  async getDailyActivity(days = 7) {
    return instance.get('/statistics/daily-activity', { params: { days } })
  },

  // ============ Supplier Import/Export - 供应商导入导出 ============
  // 导出供应商CSV
  async exportSuppliersCsv() {
    return instance.get('/suppliers/export/csv', { responseType: 'blob' })
  },

  // 导入供应商CSV
  async importSuppliersCsv(file, skipExisting = true) {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/suppliers/import/csv', formData, {
      params: { skip_existing: skipExisting },
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 获取导入模板
  async getSupplierImportTemplate() {
    return instance.get('/suppliers/export/template', { responseType: 'blob' })
  },

  // ============ 术语表版本控制 API ============

  // 获取供应商术语表修改历史
  async getGlossaryHistory(supplierId, limit = 50, offset = 0) {
    return instance.get(`/translate/glossary/${supplierId}/history`, {
      params: { limit, offset }
    })
  },

  // 获取单个术语的修改历史
  async getTermHistory(termId) {
    return instance.get(`/translate/glossary/term/${termId}/history`)
  },

  // 回滚术语到指定历史版本
  async rollbackGlossaryTerm(termId, historyId) {
    return instance.post(`/translate/glossary/term/${termId}/rollback`, null, {
      params: { history_id: historyId }
    })
  },

  // 获取术语表修改统计
  async getGlossaryHistoryStats(supplierId = null, days = 30) {
    return instance.get('/translate/glossary/history/stats', {
      params: { supplier_id: supplierId, days }
    })
  },

  // 更新术语（带历史记录）
  async updateGlossaryTerm(termId, termSource, termTarget, reason = null) {
    return instance.put(`/translate/glossary/${termId}`, null, {
      params: { term_source: termSource, term_target: termTarget, reason }
    })
  },

  // 删除术语（带历史记录）
  async deleteGlossaryTermWithHistory(termId, reason = null) {
    return instance.delete(`/translate/glossary/${termId}`, {
      params: { reason }
    })
  },

  // ============ AI 回复建议 API ============

  // 获取回复模板类型列表
  async getReplyTemplates() {
    return instance.get('/ai/reply/templates')
  },

  // 为邮件生成回复建议
  async generateReplySuggestions(emailId, replyType = 'general') {
    return instance.post(`/ai/reply/${emailId}/suggest`, null, {
      params: { reply_type: replyType }
    })
  },

  // 为自定义内容生成回复建议
  async generateCustomReplySuggestions(subject, body, sender = '', replyType = 'general') {
    return instance.post('/ai/reply/custom/suggest', {
      subject,
      body,
      sender,
      reply_type: replyType
    })
  },

  // ============ 拼写和语法检查 API ============

  // 检查文本的语法和拼写
  async checkGrammar(text, language = 'zh') {
    return instance.post('/ai/grammar/check', {
      text,
      language
    })
  }
}

export default api
