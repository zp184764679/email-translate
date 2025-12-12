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

        <!-- 自定义文件夹 -->
        <div class="custom-folders-section">
          <div class="section-header">
            <span>文件夹</span>
            <el-button text size="small" @click="showFolderDialog = true">
              <el-icon><Plus /></el-icon>
            </el-button>
          </div>
          <div
            v-for="folder in customFolders"
            :key="folder.id"
            class="folder-item custom-folder"
            :class="{ active: currentFolder === `folder-${folder.id}` }"
            @click="navigateTo(`/emails?folder_id=${folder.id}`, `folder-${folder.id}`)"
            @contextmenu.prevent="showFolderContextMenu($event, folder)"
          >
            <el-icon :style="{ color: folder.color }"><Folder /></el-icon>
            <span class="folder-name">{{ folder.name }}</span>
            <el-badge v-if="folder.email_count > 0" :value="folder.email_count" class="folder-badge" type="info" />
          </div>
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

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'calendar' }"
          @click="navigateTo('/calendar', 'calendar')"
        >
          <el-icon><Calendar /></el-icon>
          <span class="folder-name">日历</span>
        </div>

        <div
          class="folder-item"
          :class="{ active: currentFolder === 'rules' }"
          @click="navigateTo('/rules', 'rules')"
        >
          <el-icon><Operation /></el-icon>
          <span class="folder-name">规则</span>
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

          <el-divider direction="vertical" v-if="isEmailView" />

          <!-- 批量翻译 -->
          <el-button
            v-if="isEmailView"
            :icon="DocumentCopy"
            :loading="batchTranslating"
            @click="batchTranslateAll"
          >
            批量翻译
          </el-button>
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
          <!-- 布局切换 -->
          <el-dropdown @command="handleLayoutChange" v-if="isEmailView">
            <el-button>
              <el-icon><Grid /></el-icon>
              布局
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="list" :class="{ 'is-active': userStore.layoutMode === 'list' }">
                  <el-icon><List /></el-icon>
                  列表模式
                </el-dropdown-item>
                <el-dropdown-item command="right" :class="{ 'is-active': userStore.layoutMode === 'right' }">
                  <el-icon><Operation /></el-icon>
                  右侧预览
                </el-dropdown-item>
                <el-dropdown-item command="bottom" :class="{ 'is-active': userStore.layoutMode === 'bottom' }">
                  <el-icon><Histogram /></el-icon>
                  底部预览
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 双语对比模式提示 -->
          <span class="view-mode-hint">
            <el-icon><Reading /></el-icon>
            双语对比
          </span>
        </div>
      </header>

      <!-- 内容区域 -->
      <div class="content-area">
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

    <!-- 快捷键帮助弹窗 -->
    <KeyboardShortcutsHelp ref="shortcutsHelpRef" />

    <!-- 文件夹创建/编辑对话框 -->
    <el-dialog
      v-model="showFolderDialog"
      :title="editingFolder ? '编辑文件夹' : '新建文件夹'"
      width="400px"
    >
      <el-form :model="folderForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="folderForm.name" placeholder="请输入文件夹名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="folderForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFolderDialog = false">取消</el-button>
        <el-button type="primary" @click="saveFolder" :loading="savingFolder">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 文件夹右键菜单 -->
    <div
      v-show="folderContextMenu.visible"
      class="context-menu"
      :style="{ left: folderContextMenu.x + 'px', top: folderContextMenu.y + 'px' }"
    >
      <div class="context-menu-item" @click="editFolder">
        <el-icon><Edit /></el-icon>
        <span>编辑</span>
      </div>
      <div class="context-menu-item danger" @click="deleteFolderConfirm">
        <el-icon><Delete /></el-icon>
        <span>删除</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  Refresh, RefreshRight, Message, EditPen, Document, Delete,
  OfficeBuilding, Setting, Promotion, Star, ChatDotSquare,
  SwitchButton, Checked, Reading, DocumentCopy, Grid, List,
  Operation, Histogram, ArrowDown, Plus, Folder, Edit, Calendar
} from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import ComposeEmail from '@/components/ComposeEmail.vue'
import KeyboardShortcutsHelp from '@/components/KeyboardShortcutsHelp.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// 状态
const fetching = ref(false)
const batchTranslating = ref(false)
const currentFolder = ref('inbox')
const searchQuery = ref('')
const showComposeDialog = ref(false)
const unreadCount = ref(0)
const draftCount = ref(0)

// 文件夹管理
const customFolders = ref([])
const showFolderDialog = ref(false)
const editingFolder = ref(null)
const savingFolder = ref(false)
const folderForm = ref({
  name: '',
  color: '#409EFF'
})
const folderContextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  folder: null
})

// 组件 refs
const shortcutsHelpRef = ref(null)
const searchInputRef = ref(null)

// 全局快捷键
useKeyboardShortcuts([
  {
    key: 'n',
    handler: () => {
      showComposeDialog.value = true
    }
  },
  {
    key: '/',
    handler: () => {
      // 聚焦搜索框
      const searchEl = document.querySelector('.search-input input')
      if (searchEl) searchEl.focus()
    }
  }
])

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
  loadFolders()
  updateCurrentFolder()

  // 请求通知权限
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  // 启动自动收件
  userStore.startAutoFetch()

  // 点击其他区域关闭右键菜单
  document.addEventListener('click', closeFolderContextMenu)
})

// 组件卸载时清理
onUnmounted(() => {
  userStore.stopAutoFetch()
  document.removeEventListener('click', closeFolderContextMenu)
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
    } else if (route.query.folder_id) {
      currentFolder.value = `folder-${route.query.folder_id}`
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
  } else if (path.startsWith('/calendar')) {
    currentFolder.value = 'calendar'
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

async function batchTranslateAll() {
  batchTranslating.value = true
  try {
    ElMessage.info('正在批量翻译所有未翻译邮件，请稍候...')
    const result = await api.batchTranslateAll()
    ElMessage.success(result.message || '批量翻译完成')
    userStore.triggerEmailRefresh()
  } catch (e) {
    console.error('Batch translate failed:', e)
    ElMessage.error('批量翻译失败')
  } finally {
    batchTranslating.value = false
  }
}

function handleSearch() {
  if (searchQuery.value.trim()) {
    router.push(`/emails?search=${encodeURIComponent(searchQuery.value)}`)
  }
}

function handleLayoutChange(mode) {
  userStore.setLayoutMode(mode)
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

// ============ 文件夹管理函数 ============
async function loadFolders() {
  try {
    customFolders.value = await api.getFolders()
  } catch (e) {
    console.error('Failed to load folders:', e)
  }
}

async function saveFolder() {
  if (!folderForm.value.name.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }

  savingFolder.value = true
  try {
    if (editingFolder.value) {
      // 更新文件夹
      await api.updateFolder(editingFolder.value.id, {
        name: folderForm.value.name,
        color: folderForm.value.color
      })
      ElMessage.success('文件夹已更新')
    } else {
      // 创建文件夹
      await api.createFolder({
        name: folderForm.value.name,
        color: folderForm.value.color
      })
      ElMessage.success('文件夹已创建')
    }

    showFolderDialog.value = false
    editingFolder.value = null
    folderForm.value = { name: '', color: '#409EFF' }
    loadFolders()
  } catch (e) {
    console.error('Failed to save folder:', e)
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingFolder.value = false
  }
}

function showFolderContextMenu(event, folder) {
  event.preventDefault()
  folderContextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    folder: folder
  }
}

function closeFolderContextMenu() {
  folderContextMenu.value.visible = false
}

function editFolder() {
  const folder = folderContextMenu.value.folder
  if (folder) {
    editingFolder.value = folder
    folderForm.value = {
      name: folder.name,
      color: folder.color
    }
    showFolderDialog.value = true
  }
  closeFolderContextMenu()
}

async function deleteFolderConfirm() {
  const folder = folderContextMenu.value.folder
  closeFolderContextMenu()

  if (!folder) return

  if (folder.is_system) {
    ElMessage.warning('系统文件夹不可删除')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除文件夹"${folder.name}"吗？文件夹中的邮件不会被删除。`,
      '删除文件夹',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await api.deleteFolder(folder.id)
    ElMessage.success('文件夹已删除')
    loadFolders()

    // 如果当前在该文件夹，跳转到收件箱
    if (currentFolder.value === `folder-${folder.id}`) {
      navigateTo('/emails', 'inbox')
    }
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete folder:', e)
      ElMessage.error('删除失败')
    }
  }
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

/* 自定义文件夹区域 */
.custom-folders-section {
  margin: 4px 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 16px;
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}

.section-header .el-button {
  padding: 2px;
  height: auto;
}

.custom-folder {
  padding-left: 24px;
}

/* 右键菜单 */
.context-menu {
  position: fixed;
  z-index: 3000;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 120px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 14px;
  color: #303133;
  cursor: pointer;
  transition: background-color 0.15s;
}

.context-menu-item:hover {
  background-color: #f5f7fa;
}

.context-menu-item.danger {
  color: #f56c6c;
}

.context-menu-item.danger:hover {
  background-color: #fef0f0;
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
