import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { getStorageKey } from '@/api'

/**
 * 集中的邮件状态管理
 *
 * 功能：
 * 1. 统一管理邮件列表数据
 * 2. 选择状态跨页面持久化
 * 3. 缓存邮件详情
 * 4. 状态同步（已读/星标等）
 */
export const useEmailStore = defineStore('emails', () => {
  // ========== 邮件列表 ==========
  const emails = ref([])
  const totalCount = ref(0)
  const loading = ref(false)
  const currentPage = ref(1)
  const pageSize = ref(20)

  // ========== 选择状态（跨页面持久化） ==========
  const selectedIds = ref(new Set(
    JSON.parse(sessionStorage.getItem(getStorageKey('selectedEmailIds')) || '[]')
  ))

  // 当前是否全选
  const isAllSelected = computed(() => {
    if (emails.value.length === 0) return false
    return emails.value.every(e => selectedIds.value.has(e.id))
  })

  // 选中的邮件数量
  const selectedCount = computed(() => selectedIds.value.size)

  // ========== 邮件详情缓存 ==========
  const emailCache = ref(new Map())

  // ========== 选择操作 ==========
  function toggleSelect(emailId) {
    if (selectedIds.value.has(emailId)) {
      selectedIds.value.delete(emailId)
    } else {
      selectedIds.value.add(emailId)
    }
    _persistSelection()
  }

  function selectAll() {
    emails.value.forEach(e => selectedIds.value.add(e.id))
    _persistSelection()
  }

  function deselectAll() {
    selectedIds.value.clear()
    _persistSelection()
  }

  function toggleSelectAll() {
    if (isAllSelected.value) {
      deselectAll()
    } else {
      selectAll()
    }
  }

  function _persistSelection() {
    sessionStorage.setItem(
      getStorageKey('selectedEmailIds'),
      JSON.stringify([...selectedIds.value])
    )
  }

  // ========== 邮件列表操作 ==========
  async function loadEmails(filters = {}) {
    loading.value = true
    try {
      const response = await api.getEmails({
        page: currentPage.value,
        page_size: pageSize.value,
        ...filters
      })
      emails.value = response.items || response
      totalCount.value = response.total || emails.value.length
      return emails.value
    } finally {
      loading.value = false
    }
  }

  // ========== 状态更新 ==========
  function updateEmailStatus(emailId, changes) {
    const email = emails.value.find(e => e.id === emailId)
    if (email) {
      Object.assign(email, changes)
    }
    // 同时更新缓存
    if (emailCache.value.has(emailId)) {
      const cached = emailCache.value.get(emailId)
      Object.assign(cached, changes)
    }
  }

  function updateEmailsStatus(emailIds, changes) {
    emailIds.forEach(id => updateEmailStatus(id, changes))
  }

  // ========== 邮件详情缓存 ==========
  async function getEmailDetail(emailId, forceRefresh = false) {
    if (!forceRefresh && emailCache.value.has(emailId)) {
      return emailCache.value.get(emailId)
    }

    const detail = await api.getEmailDetail(emailId)
    emailCache.value.set(emailId, detail)
    return detail
  }

  function invalidateCache(emailId) {
    emailCache.value.delete(emailId)
  }

  function clearCache() {
    emailCache.value.clear()
  }

  // ========== 批量操作后清理选择 ==========
  function clearSelectionAfterAction() {
    selectedIds.value.clear()
    _persistSelection()
  }

  // ========== 清理（登出时调用） ==========
  function reset() {
    emails.value = []
    selectedIds.value.clear()
    emailCache.value.clear()
    sessionStorage.removeItem(getStorageKey('selectedEmailIds'))
  }

  return {
    // 状态
    emails,
    totalCount,
    loading,
    currentPage,
    pageSize,
    selectedIds,
    isAllSelected,
    selectedCount,

    // 选择操作
    toggleSelect,
    selectAll,
    deselectAll,
    toggleSelectAll,
    clearSelectionAfterAction,

    // 邮件操作
    loadEmails,
    updateEmailStatus,
    updateEmailsStatus,

    // 缓存
    getEmailDetail,
    invalidateCache,
    clearCache,

    // 清理
    reset
  }
})
