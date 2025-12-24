import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useNotificationStore = defineStore('notifications', () => {
  // 通知列表
  const notifications = ref([])
  const total = ref(0)
  const loading = ref(false)

  // 未读数量
  const unreadCount = ref(0)

  // 计算属性：是否有未读通知
  const hasUnread = computed(() => unreadCount.value > 0)

  // 加载通知列表
  async function loadNotifications(params = {}) {
    loading.value = true
    try {
      const response = await api.getNotifications(params)
      notifications.value = response.items
      total.value = response.total
      unreadCount.value = response.unread_count
      return response
    } catch (error) {
      console.error('Failed to load notifications:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  // 加载未读数量
  async function loadUnreadCount() {
    try {
      const response = await api.getUnreadNotificationCount()
      unreadCount.value = response.count
      return response.count
    } catch (error) {
      console.error('Failed to load unread count:', error)
      return unreadCount.value
    }
  }

  // 标记单个通知为已读
  async function markAsRead(notificationId) {
    try {
      await api.markNotificationAsRead(notificationId)
      // 更新本地状态
      const notification = notifications.value.find(n => n.id === notificationId)
      if (notification && !notification.is_read) {
        notification.is_read = true
        notification.read_at = new Date().toISOString()
        unreadCount.value = Math.max(0, unreadCount.value - 1)
      }
    } catch (error) {
      console.error('Failed to mark notification as read:', error)
      throw error
    }
  }

  // 标记所有通知为已读
  async function markAllAsRead() {
    try {
      await api.markAllNotificationsAsRead()
      // 更新本地状态
      notifications.value.forEach(n => {
        if (!n.is_read) {
          n.is_read = true
          n.read_at = new Date().toISOString()
        }
      })
      unreadCount.value = 0
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error)
      throw error
    }
  }

  // 删除通知
  async function deleteNotification(notificationId) {
    try {
      await api.deleteNotification(notificationId)
      // 更新本地状态
      const index = notifications.value.findIndex(n => n.id === notificationId)
      if (index > -1) {
        const wasUnread = !notifications.value[index].is_read
        notifications.value.splice(index, 1)
        total.value--
        if (wasUnread) {
          unreadCount.value = Math.max(0, unreadCount.value - 1)
        }
      }
    } catch (error) {
      console.error('Failed to delete notification:', error)
      throw error
    }
  }

  // 清空所有通知
  async function clearAll() {
    try {
      await api.clearAllNotifications()
      notifications.value = []
      total.value = 0
      unreadCount.value = 0
    } catch (error) {
      console.error('Failed to clear all notifications:', error)
      throw error
    }
  }

  // 添加新通知（用于 WebSocket 实时推送）
  function addNotification(notification) {
    // 添加到列表开头
    notifications.value.unshift(notification)
    total.value++
    if (!notification.is_read) {
      unreadCount.value++
    }
  }

  // 重置状态
  function reset() {
    notifications.value = []
    total.value = 0
    unreadCount.value = 0
    loading.value = false
  }

  return {
    // State
    notifications,
    total,
    loading,
    unreadCount,
    // Computed
    hasUnread,
    // Actions
    loadNotifications,
    loadUnreadCount,
    markAsRead,
    markAllAsRead,
    deleteNotification,
    clearAll,
    addNotification,
    reset
  }
})
