<template>
  <div class="outlook-layout">
    <!-- 左侧文件夹导航栏 -->
    <aside class="folder-pane">
      <!-- 账户头像区域 -->
      <div class="account-section">
        <el-avatar :size="40" icon="UserFilled" />
        <div class="account-info">
          <div class="account-name">{{ displayName }}</div>
          <div class="account-email">{{ userStore.email }}</div>
        </div>
      </div>

      <!-- 新邮件按钮 -->
      <div class="new-mail-section">
        <el-button type="primary" class="new-mail-btn" @click="showComposeDialog = true">
          <el-icon><EditPen /></el-icon>
          <span>新邮件</span>
        </el-button>
      </div>

      <!-- 文件夹列表 -->
      <div class="folder-list">
        <div
          class="folder-item"
          :class="{ active: currentFolder === 'inbox' }"
          @click="navigateTo('/emails', 'inbox')"
        >
          <el-icon><Message /></el-icon>
          <span class="folder-name">收件箱</span>
          <el-badge v-if="unreadCount > 0" :value="unreadCount" class="folder-badge" />
        </div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'sent' }"
          @click="navigateTo('/emails?direction=outbound', 'sent')"
        >
          <el-icon><Promotion /></el-icon>
          <span class="folder-name">已发送</span>
        </div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'drafts' }"
          @click="navigateTo('/drafts', 'drafts')"
        >
          <el-icon><Document /></el-icon>
          <span class="folder-name">草稿箱</span>
          <el-badge v-if="draftCount > 0" :value="draftCount" class="folder-badge" type="info" />
        </div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'deleted' }"
          @click="navigateTo('/deleted', 'deleted')"
        >
          <el-icon><Delete /></el-icon>
          <span class="folder-name">已删除</span>
        </div>

        <div class="folder-divider"></div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'suppliers' }"
          @click="navigateTo('/suppliers', 'suppliers')"
        >
          <el-icon><OfficeBuilding /></el-icon>
          <span class="folder-name">供应商</span>
        </div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'approvals' }"
          @click="navigateTo('/approvals', 'approvals')"
        >
          <el-icon><Checked /></el-icon>
          <span class="folder-name">审批</span>
        </div>

        <div class="folder-divider"></div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'settings' }"
          @click="navigateTo('/settings', 'settings')"
        >
          <el-icon><Setting /></el-icon>
          <span class="folder-name">设置</span>
        </div>
      </div>

      <!-- 底部操作区 -->
      <div class="folder-footer">
        <el-button text @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          <span>退出登录</span>
        </el-button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main-area">
      <!-- 顶部工具栏 -->
      <header class="toolbar">
        <div class="toolbar-left">
          <!-- 邮件操作按钮组 -->
          <el-button-group class="action-group">
            <el-button :icon="Refresh" :loading="fetching" @click="fetchEmails">
              同步
            </el-button>
            <el-button :icon="RefreshRight" @click="refreshList">
              刷新
            </el-button>
          </el-button-group>

          <el-divider direction="vertical" />

          <!-- 邮件操作 -->
          <el-button-group class="action-group" v-if="isEmailView">
            <el-button :icon="Message" @click="markAsRead">已读</el-button>
            <el-button :icon="ChatDotSquare" @click="markAsUnread">未读</el-button>
            <el-button :icon="Star" @click="toggleFlag">标记</el-button>
            <el-button :icon="Delete" type="danger" plain @click="deleteSelected">删除</el-button>
          </el-button-group>
        </div>

        <div class="toolbar-center">
          <!-- 搜索框 -->
          <el-input
            v-model="searchQuery"
            placeholder="搜索邮件..."
            prefix-icon="Search"
            clearable
            class="search-input"
            @keyup.enter="handleSearch"
          />
        </div>

        <div class="toolbar-right">
          <!-- 双语对比模式提示 -->
          <span class="view-mode-hint">
            <el-icon><Reading /></el-icon>
            双语对比
          </span>
        </div>
      </header>

      <!-- 内容区域 -->
      <div class="content-area split-view">
        <router-view />
      </div>
    </div>

    <!-- 新邮件撰写对话框 -->
    <el-dialog
      v-model="showComposeDialog"
      title="撰写新邮件"
      width="70%"
      top="5vh"
      :close-on-click-modal="false"
    >
      <ComposeEmail
        v-if="showComposeDialog"
        @sent="onEmailSent"
        @cancel="showComposeDialog = false"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  Refresh, RefreshRight, Message, EditPen, Document, Delete,
  OfficeBuilding, Setting, Promotion, Star, ChatDotSquare,
  SwitchButton, Checked, Reading
} from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage } from 'element-plus'
import ComposeEmail from '@/components/ComposeEmail.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// 状态
const fetching = ref(false)
const currentFolder = ref('inbox')
const searchQuery = ref('')
const showComposeDialog = ref(false)
const unreadCount = ref(0)
const draftCount = ref(0)

// 计算属性
const displayName = computed(() => {
  const email = userStore.email || ''
  return email.split('@')[0] || '用户'
})

const isEmailView = computed(() => {
  return route.path.startsWith('/emails')
})

// 初始化
onMounted(() => {
  loadCounts()
  updateCurrentFolder()

  // 请求通知权限
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  // 启动自动收件
  userStore.startAutoFetch()
})

// 组件卸载时停止自动收件
onUnmounted(() => {
  userStore.stopAutoFetch()
})

// 监听路由变化
watch(() => route.path, () => {
  updateCurrentFolder()
})

function updateCurrentFolder() {
  const path = route.path
  if (path.startsWith('/emails')) {
    if (route.query.direction === 'outbound') {
      currentFolder.value = 'sent'
    } else {
      currentFolder.value = 'inbox'
    }
  } else if (path.startsWith('/drafts')) {
    currentFolder.value = 'drafts'
  } else if (path.startsWith('/deleted')) {
    currentFolder.value = 'deleted'
  } else if (path.startsWith('/suppliers')) {
    currentFolder.value = 'suppliers'
  } else if (path.startsWith('/approvals')) {
    currentFolder.value = 'approvals'
  } else if (path.startsWith('/settings')) {
    currentFolder.value = 'settings'
  }
}

async function loadCounts() {
  try {
    const stats = await api.getEmailStats()
    // 使用真正的未读数（unread）而非未翻译数（untranslated）
    unreadCount.value = stats.unread || 0

    // 获取草稿数量
    try {
      const drafts = await api.getDrafts()
      draftCount.value = drafts.length || 0
    } catch (e) {
      draftCount.value = 0
    }
  } catch (e) {
    console.error('Failed to load counts:', e)
  }
}

function navigateTo(path, folder) {
  currentFolder.value = folder
  router.push(path)
}

async function fetchEmails() {
  fetching.value = true
  try {
    ElMessage.info('正在同步邮件...')
    await api.fetchEmails(30)
    ElMessage.success('邮件同步完成')
    userStore.triggerEmailRefresh()
    loadCounts()
  } catch (e) {
    console.error('Failed to fetch emails:', e)
    ElMessage.error('同步邮件失败')
  } finally {
    fetching.value = false
  }
}

function refreshList() {
  userStore.triggerEmailRefresh()
  loadCounts()
}

function handleSearch() {
  if (searchQuery.value.trim()) {
    router.push(`/emails?search=${encodeURIComponent(searchQuery.value)}`)
  }
}

async function markAsRead() {
  const selectedIds = getSelectedEmailIds()
  if (selectedIds.length === 0) {
    ElMessage.warning('请先选择邮件')
    return
  }
  try {
    await api.batchMarkAsRead(selectedIds)
    ElMessage.success(`已将 ${selectedIds.length} 封邮件标记为已读`)
    userStore.triggerEmailRefresh()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function markAsUnread() {
  const selectedIds = getSelectedEmailIds()
  if (selectedIds.length === 0) {
    ElMessage.warning('请先选择邮件')
    return
  }
  try {
    await api.batchMarkAsUnread(selectedIds)
    ElMessage.success(`已将 ${selectedIds.length} 封邮件标记为未读`)
    userStore.triggerEmailRefresh()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function toggleFlag() {
  const selectedIds = getSelectedEmailIds()
  if (selectedIds.length === 0) {
    ElMessage.warning('请先选择邮件')
    return
  }
  try {
    await api.batchFlag(selectedIds)
    ElMessage.success(`已为 ${selectedIds.length} 封邮件添加星标`)
    userStore.triggerEmailRefresh()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function deleteSelected() {
  const selectedIds = getSelectedEmailIds()
  if (selectedIds.length === 0) {
    ElMessage.warning('请先选择邮件')
    return
  }
  try {
    await api.batchDelete(selectedIds)
    ElMessage.success(`已删除 ${selectedIds.length} 封邮件`)
    userStore.triggerEmailRefresh()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 获取选中的邮件ID（由 Emails.vue 通过 provide/inject 提供）
function getSelectedEmailIds() {
  // 通过事件总线或 store 获取选中的邮件
  // 暂时返回空数组，需要在 Emails.vue 中实现选中状态共享
  return window.__selectedEmailIds || []
}

function onEmailSent() {
  showComposeDialog.value = false
  ElMessage.success('邮件已发送')
  fetchEmails()
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.outlook-layout {
  display: flex;
  height: 100vh;
  background-color: #f3f3f3;
}

/* 左侧文件夹栏 */
.folder-pane {
  width: 240px;
  background-color: #f8f9fa;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.account-section {
  display: flex;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  background-color: #fff;
}

.account-info {
  margin-left: 12px;
  overflow: hidden;
}

.account-name {
  font-weight: 600;
  font-size: 14px;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-email {
  font-size: 12px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.new-mail-section {
  padding: 12px 16px;
}

.new-mail-btn {
  width: 100%;
  height: 40px;
  font-size: 14px;
  font-weight: 500;
}

.folder-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.folder-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: background-color 0.15s;
  color: #1a1a1a;
  font-size: 14px;
}

.folder-item:hover {
  background-color: #e8e8e8;
}

.folder-item.active {
  background-color: #e1efff;
  color: #0078d4;
}

.folder-item .el-icon {
  font-size: 18px;
  margin-right: 12px;
  color: inherit;
}

.folder-name {
  flex: 1;
}

.folder-badge {
  margin-left: 8px;
}

.folder-divider {
  height: 1px;
  background-color: #e0e0e0;
  margin: 8px 16px;
}

.folder-footer {
  padding: 12px 16px;
  border-top: 1px solid #e0e0e0;
}

.folder-footer .el-button {
  width: 100%;
  justify-content: flex-start;
  color: #666;
}

/* 主内容区 */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

/* 顶部工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background-color: #fff;
  border-bottom: 1px solid #e0e0e0;
  min-height: 52px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-center {
  flex: 1;
  max-width: 400px;
  margin: 0 24px;
}

.search-input {
  width: 100%;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-mode-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #909399;
  padding: 4px 8px;
  background-color: #f0f9ff;
  border-radius: 4px;
}

.action-group {
  display: flex;
}

/* 内容区域 */
.content-area {
  flex: 1;
  overflow: hidden;
}

.content-area.split-view {
  display: flex;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .folder-pane {
    width: 200px;
  }

  .toolbar-center {
    max-width: 300px;
  }
}

@media (max-width: 900px) {
  .folder-pane {
    width: 60px;
  }

  .account-info,
  .folder-name,
  .new-mail-btn span,
  .folder-footer span {
    display: none;
  }

  .new-mail-btn {
    padding: 0;
    justify-content: center;
  }

  .folder-item {
    justify-content: center;
    padding: 12px;
  }

  .folder-item .el-icon {
    margin-right: 0;
  }

  .account-section {
    justify-content: center;
    padding: 12px;
  }
}
</style>
