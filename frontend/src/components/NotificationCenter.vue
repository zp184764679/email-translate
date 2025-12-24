<template>
  <el-popover
    placement="bottom-end"
    :width="360"
    trigger="click"
    @show="handleOpen"
  >
    <template #reference>
      <div class="notification-trigger">
        <el-badge :value="notificationStore.unreadCount" :hidden="!notificationStore.hasUnread" :max="99">
          <el-button :icon="Bell" circle size="small" />
        </el-badge>
      </div>
    </template>

    <div class="notification-panel">
      <!-- 头部 -->
      <div class="notification-header">
        <span class="title">通知中心</span>
        <div class="actions">
          <el-button
            v-if="notificationStore.hasUnread"
            text
            size="small"
            @click="handleMarkAllRead"
          >
            全部已读
          </el-button>
          <el-button
            v-if="notificationStore.notifications.length > 0"
            text
            size="small"
            type="danger"
            @click="handleClearAll"
          >
            清空
          </el-button>
        </div>
      </div>

      <!-- 类型过滤 -->
      <div class="notification-tabs">
        <el-radio-group v-model="currentTab" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="new_email">邮件</el-radio-button>
          <el-radio-button value="translation_complete">翻译</el-radio-button>
          <el-radio-button value="approval_request">审批</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 通知列表 -->
      <div class="notification-list" v-loading="notificationStore.loading">
        <div
          v-for="notification in filteredNotifications"
          :key="notification.id"
          class="notification-item"
          :class="{ 'unread': !notification.is_read }"
          @click="handleNotificationClick(notification)"
        >
          <div class="notification-icon">
            <el-icon :class="getIconClass(notification.type)">
              <component :is="getIcon(notification.type)" />
            </el-icon>
          </div>
          <div class="notification-content">
            <div class="notification-title">{{ notification.title }}</div>
            <div class="notification-message" v-if="notification.message">
              {{ notification.message }}
            </div>
            <div class="notification-time">{{ formatTime(notification.created_at) }}</div>
          </div>
          <el-button
            class="delete-btn"
            :icon="Close"
            circle
            size="small"
            text
            @click.stop="handleDelete(notification)"
          />
        </div>

        <!-- 空状态 -->
        <el-empty
          v-if="!notificationStore.loading && filteredNotifications.length === 0"
          description="暂无通知"
          :image-size="80"
        />
      </div>

      <!-- 底部 -->
      <div class="notification-footer" v-if="notificationStore.total > 10">
        <el-button text size="small" @click="loadMore">查看更多</el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, Message, Document, Check, Close } from '@element-plus/icons-vue'
import { useNotificationStore } from '@/stores/notifications'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const router = useRouter()
const notificationStore = useNotificationStore()

// 当前选中的标签页
const currentTab = ref('all')

// 过滤后的通知
const filteredNotifications = computed(() => {
  if (currentTab.value === 'all') {
    return notificationStore.notifications
  }
  return notificationStore.notifications.filter(n => n.type === currentTab.value)
})

// 打开弹出框时加载通知
async function handleOpen() {
  try {
    await notificationStore.loadNotifications({ limit: 20 })
  } catch (error) {
    ElMessage.error('加载通知失败')
  }
}

// 获取图标
function getIcon(type) {
  switch (type) {
    case 'new_email':
      return Message
    case 'translation_complete':
      return Document
    case 'approval_request':
    case 'approval_result':
      return Check
    default:
      return Bell
  }
}

// 获取图标样式类
function getIconClass(type) {
  switch (type) {
    case 'new_email':
      return 'icon-email'
    case 'translation_complete':
      return 'icon-translate'
    case 'approval_request':
    case 'approval_result':
      return 'icon-approval'
    default:
      return 'icon-default'
  }
}

// 格式化时间
function formatTime(dateStr) {
  if (!dateStr) return ''
  return dayjs(dateStr).fromNow()
}

// 点击通知
async function handleNotificationClick(notification) {
  // 标记为已读
  if (!notification.is_read) {
    await notificationStore.markAsRead(notification.id)
  }

  // 根据类型跳转
  if (notification.related_id && notification.related_type) {
    switch (notification.related_type) {
      case 'email':
        router.push(`/emails/${notification.related_id}`)
        break
      case 'draft':
        router.push(`/drafts?id=${notification.related_id}`)
        break
    }
  }
}

// 标记全部已读
async function handleMarkAllRead() {
  try {
    await notificationStore.markAllAsRead()
    ElMessage.success('已全部标记为已读')
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

// 删除通知
async function handleDelete(notification) {
  try {
    await notificationStore.deleteNotification(notification.id)
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

// 清空所有通知
async function handleClearAll() {
  try {
    await ElMessageBox.confirm('确定要清空所有通知吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await notificationStore.clearAll()
    ElMessage.success('已清空所有通知')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
}

// 加载更多
async function loadMore() {
  try {
    const skip = notificationStore.notifications.length
    const response = await notificationStore.loadNotifications({
      skip,
      limit: 20
    })
  } catch (error) {
    ElMessage.error('加载失败')
  }
}

// 组件挂载时加载未读数量
onMounted(async () => {
  await notificationStore.loadUnreadCount()
})
</script>

<style scoped>
.notification-trigger {
  cursor: pointer;
}

.notification-panel {
  display: flex;
  flex-direction: column;
  max-height: 500px;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.notification-header .title {
  font-weight: 600;
  font-size: 14px;
}

.notification-header .actions {
  display: flex;
  gap: 4px;
}

.notification-tabs {
  padding: 12px 0;
}

.notification-list {
  flex: 1;
  overflow-y: auto;
  max-height: 360px;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
  position: relative;
}

.notification-item:hover {
  background-color: var(--el-fill-color-light);
}

.notification-item:hover .delete-btn {
  opacity: 1;
}

.notification-item.unread {
  background-color: rgba(64, 158, 255, 0.05);
}

.notification-item.unread::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  background-color: var(--el-color-primary);
  border-radius: 50%;
}

.notification-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 16px;
}

.notification-icon .icon-email {
  background-color: rgba(64, 158, 255, 0.1);
  color: var(--el-color-primary);
}

.notification-icon .icon-translate {
  background-color: rgba(103, 194, 58, 0.1);
  color: var(--el-color-success);
}

.notification-icon .icon-approval {
  background-color: rgba(230, 162, 60, 0.1);
  color: var(--el-color-warning);
}

.notification-icon .icon-default {
  background-color: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 13px;
  color: var(--el-text-color-primary);
  line-height: 1.4;
  margin-bottom: 2px;
}

.notification-message {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.notification-time {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.notification-footer {
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  text-align: center;
}
</style>
