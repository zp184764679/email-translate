<template>
  <div class="archive-container">
    <!-- 左侧：归档文件夹树 -->
    <div class="archive-sidebar">
      <div class="sidebar-header">
        <h3>归档文件夹</h3>
        <el-button type="primary" size="small" :icon="Plus" @click="showCreateFolder">
          新建
        </el-button>
      </div>

      <!-- 统计信息 -->
      <div class="archive-stats" v-if="stats">
        <div class="stat-item">
          <span class="stat-value">{{ stats.total_archived }}</span>
          <span class="stat-label">已归档</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ stats.total_folders }}</span>
          <span class="stat-label">文件夹</span>
        </div>
      </div>

      <!-- 文件夹树 -->
      <div class="folder-tree">
        <div
          class="folder-item all-archived"
          :class="{ active: !selectedFolderId }"
          @click="selectFolder(null)"
        >
          <el-icon><Folder /></el-icon>
          <span>全部归档</span>
          <span class="count">{{ stats?.total_archived || 0 }}</span>
        </div>

        <el-tree
          :data="folderTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :expand-on-click-node="false"
          @node-click="handleNodeClick"
          default-expand-all
        >
          <template #default="{ node, data }">
            <div class="tree-node" :class="{ active: selectedFolderId === data.id }">
              <el-icon :color="data.color || '#909399'"><FolderOpened /></el-icon>
              <span class="node-label">{{ data.name }}</span>
              <span class="node-count">{{ data.email_count || 0 }}</span>
              <el-dropdown trigger="click" @command="handleFolderCommand($event, data)" @click.stop>
                <el-icon class="node-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit"><el-icon><Edit /></el-icon>编辑</el-dropdown-item>
                    <el-dropdown-item command="delete" divided><el-icon><Delete /></el-icon>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-tree>
      </div>
    </div>

    <!-- 右侧：归档邮件列表 -->
    <div class="archive-content">
      <div class="content-header">
        <div class="header-left">
          <h2>{{ selectedFolderName }}</h2>
          <span class="email-count">{{ archivedEmails.length }} 封邮件</span>
        </div>
        <div class="header-right">
          <el-input
            v-model="searchQuery"
            placeholder="搜索归档邮件..."
            prefix-icon="Search"
            clearable
            style="width: 240px"
            @clear="loadArchivedEmails"
            @keyup.enter="loadArchivedEmails"
          />
        </div>
      </div>

      <!-- 邮件列表 -->
      <div class="email-list" v-loading="loading">
        <el-empty v-if="archivedEmails.length === 0" description="暂无归档邮件" />

        <div
          v-else
          class="email-item"
          v-for="email in archivedEmails"
          :key="email.id"
          @click="viewEmail(email)"
        >
          <div class="email-checkbox" @click.stop>
            <el-checkbox v-model="email.selected" />
          </div>
          <div class="email-sender">
            <el-avatar :size="32" :style="{ backgroundColor: getAvatarColor(email.from_email) }">
              {{ getInitials(email.from_name || email.from_email) }}
            </el-avatar>
            <div class="sender-info">
              <div class="sender-name">{{ email.from_name || email.from_email }}</div>
              <div class="sender-email" v-if="email.from_name">{{ email.from_email }}</div>
            </div>
          </div>
          <div class="email-content">
            <div class="email-subject">{{ email.subject_translated || email.subject_original }}</div>
            <div class="email-preview">{{ getPreviewText(email) }}</div>
          </div>
          <div class="email-meta">
            <div class="email-date">{{ formatDate(email.received_at) }}</div>
            <div class="email-folder" v-if="email.archive_folder">
              <el-tag size="small" :color="email.archive_folder.color">
                {{ email.archive_folder.name }}
              </el-tag>
            </div>
          </div>
          <div class="email-actions" @click.stop>
            <el-button text size="small" @click="unarchiveEmail(email)">
              <el-icon><RefreshLeft /></el-icon>
              恢复
            </el-button>
          </div>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <div class="batch-actions" v-if="selectedEmails.length > 0">
        <span>已选择 {{ selectedEmails.length }} 封邮件</span>
        <el-button size="small" @click="batchUnarchive">批量恢复</el-button>
        <el-button size="small" @click="batchMoveToFolder">移动到...</el-button>
      </div>
    </div>

    <!-- 创建/编辑文件夹对话框 -->
    <el-dialog
      v-model="showFolderDialog"
      :title="editingFolder ? '编辑文件夹' : '新建归档文件夹'"
      width="450px"
    >
      <el-form :model="folderForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="folderForm.name" placeholder="请输入文件夹名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="folderForm.folder_type" style="width: 100%">
            <el-option label="按年份" value="year" />
            <el-option label="按项目" value="project" />
            <el-option label="按供应商" value="supplier" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="folderForm.color" />
        </el-form-item>
        <el-form-item label="父文件夹">
          <el-tree-select
            v-model="folderForm.parent_id"
            :data="folderTree"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            placeholder="无（顶级文件夹）"
            clearable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="folderForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFolderDialog = false">取消</el-button>
        <el-button type="primary" @click="saveFolder" :loading="savingFolder">保存</el-button>
      </template>
    </el-dialog>

    <!-- 移动到文件夹对话框 -->
    <el-dialog v-model="showMoveDialog" title="移动到文件夹" width="400px">
      <el-tree-select
        v-model="moveTargetFolder"
        :data="folderTree"
        :props="{ label: 'name', value: 'id', children: 'children' }"
        placeholder="选择目标文件夹"
        check-strictly
        style="width: 100%"
      />
      <template #footer>
        <el-button @click="showMoveDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmMove" :loading="moving">移动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus, Folder, FolderOpened, MoreFilled, Edit, Delete, RefreshLeft
} from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'

const router = useRouter()

// 状态
const loading = ref(false)
const stats = ref(null)
const folderTree = ref([])
const archivedEmails = ref([])
const selectedFolderId = ref(null)
const searchQuery = ref('')

// 文件夹表单
const showFolderDialog = ref(false)
const editingFolder = ref(null)
const savingFolder = ref(false)
const folderForm = ref({
  name: '',
  folder_type: 'custom',
  color: '#409EFF',
  parent_id: null,
  description: ''
})

// 移动对话框
const showMoveDialog = ref(false)
const moveTargetFolder = ref(null)
const moving = ref(false)

// 计算属性
const selectedFolderName = computed(() => {
  if (!selectedFolderId.value) return '全部归档'
  const folder = findFolderById(folderTree.value, selectedFolderId.value)
  return folder?.name || '归档邮件'
})

const selectedEmails = computed(() => {
  return archivedEmails.value.filter(e => e.selected)
})

// 初始化
onMounted(() => {
  loadStats()
  loadFolders()
  loadArchivedEmails()
})

// 加载统计
async function loadStats() {
  try {
    const res = await api.getArchiveStats()
    stats.value = res.data
  } catch (e) {
    console.error('Failed to load stats:', e)
  }
}

// 加载文件夹
async function loadFolders() {
  try {
    const res = await api.getArchiveFolders()
    folderTree.value = res.data || []
  } catch (e) {
    console.error('Failed to load folders:', e)
  }
}

// 加载归档邮件
async function loadArchivedEmails() {
  loading.value = true
  try {
    const params = {}
    if (selectedFolderId.value) {
      params.folder_id = selectedFolderId.value
    }
    if (searchQuery.value) {
      params.search = searchQuery.value
    }
    const res = await api.getArchivedEmails(params)
    archivedEmails.value = (res.data || []).map(e => ({ ...e, selected: false }))
  } catch (e) {
    console.error('Failed to load emails:', e)
  } finally {
    loading.value = false
  }
}

// 选择文件夹
function selectFolder(folderId) {
  selectedFolderId.value = folderId
  loadArchivedEmails()
}

function handleNodeClick(data) {
  selectFolder(data.id)
}

// 文件夹操作
function showCreateFolder() {
  editingFolder.value = null
  folderForm.value = {
    name: '',
    folder_type: 'custom',
    color: '#409EFF',
    parent_id: null,
    description: ''
  }
  showFolderDialog.value = true
}

function handleFolderCommand(command, folder) {
  if (command === 'edit') {
    editingFolder.value = folder
    folderForm.value = {
      name: folder.name,
      folder_type: folder.folder_type || 'custom',
      color: folder.color || '#409EFF',
      parent_id: folder.parent_id,
      description: folder.description || ''
    }
    showFolderDialog.value = true
  } else if (command === 'delete') {
    deleteFolder(folder)
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
      await api.updateArchiveFolder(editingFolder.value.id, folderForm.value)
      ElMessage.success('文件夹已更新')
    } else {
      await api.createArchiveFolder(folderForm.value)
      ElMessage.success('文件夹已创建')
    }
    showFolderDialog.value = false
    loadFolders()
    loadStats()
  } catch (e) {
    console.error('Save folder failed:', e)
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingFolder.value = false
  }
}

async function deleteFolder(folder) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件夹"${folder.name}"吗？文件夹中的邮件将被恢复到收件箱。`,
      '删除确认',
      { type: 'warning' }
    )
    await api.deleteArchiveFolder(folder.id)
    ElMessage.success('文件夹已删除')
    if (selectedFolderId.value === folder.id) {
      selectedFolderId.value = null
    }
    loadFolders()
    loadArchivedEmails()
    loadStats()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Delete folder failed:', e)
      ElMessage.error('删除失败')
    }
  }
}

// 邮件操作
function viewEmail(email) {
  router.push(`/emails/${email.id}`)
}

async function unarchiveEmail(email) {
  try {
    await api.unarchiveEmail(email.id)
    ElMessage.success('邮件已恢复')
    loadArchivedEmails()
    loadStats()
  } catch (e) {
    console.error('Unarchive failed:', e)
    ElMessage.error('恢复失败')
  }
}

async function batchUnarchive() {
  if (selectedEmails.value.length === 0) return
  try {
    const ids = selectedEmails.value.map(e => e.id)
    await api.batchUnarchiveEmails(ids)
    ElMessage.success(`已恢复 ${ids.length} 封邮件`)
    loadArchivedEmails()
    loadStats()
  } catch (e) {
    console.error('Batch unarchive failed:', e)
    ElMessage.error('批量恢复失败')
  }
}

function batchMoveToFolder() {
  if (selectedEmails.value.length === 0) return
  moveTargetFolder.value = null
  showMoveDialog.value = true
}

async function confirmMove() {
  if (!moveTargetFolder.value) {
    ElMessage.warning('请选择目标文件夹')
    return
  }
  moving.value = true
  try {
    const ids = selectedEmails.value.map(e => e.id)
    await api.batchArchiveEmails(ids, moveTargetFolder.value)
    ElMessage.success(`已移动 ${ids.length} 封邮件`)
    showMoveDialog.value = false
    loadArchivedEmails()
    loadFolders()
  } catch (e) {
    console.error('Move failed:', e)
    ElMessage.error('移动失败')
  } finally {
    moving.value = false
  }
}

// 工具函数
function findFolderById(folders, id) {
  for (const folder of folders) {
    if (folder.id === id) return folder
    if (folder.children) {
      const found = findFolderById(folder.children, id)
      if (found) return found
    }
  }
  return null
}

function getAvatarColor(email) {
  const colors = ['#f56c6c', '#e6a23c', '#67c23a', '#409eff', '#909399']
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

function getInitials(name) {
  if (!name) return '?'
  const parts = name.split(/[@\s]+/)
  return parts[0]?.charAt(0)?.toUpperCase() || '?'
}

function getPreviewText(email) {
  const text = email.body_translated || email.body_original || ''
  return text.substring(0, 100).replace(/\s+/g, ' ')
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return dayjs(dateStr).format('MM-DD HH:mm')
}
</script>

<style scoped>
.archive-container {
  display: flex;
  height: 100%;
  background: #f5f7fa;
}

.archive-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.archive-stats {
  display: flex;
  padding: 16px;
  gap: 24px;
  border-bottom: 1px solid #e4e7ed;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #409EFF;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.folder-tree {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.folder-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.folder-item:hover {
  background-color: #f5f7fa;
}

.folder-item.active {
  background-color: #ecf5ff;
  color: #409EFF;
}

.folder-item .count {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding: 4px 8px;
  border-radius: 4px;
}

.tree-node:hover {
  background-color: #f5f7fa;
}

.tree-node.active {
  background-color: #ecf5ff;
}

.node-label {
  flex: 1;
}

.node-count {
  font-size: 12px;
  color: #909399;
}

.node-more {
  opacity: 0;
  transition: opacity 0.2s;
}

.tree-node:hover .node-more {
  opacity: 1;
}

.archive-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.header-left h2 {
  margin: 0;
  font-size: 18px;
  color: #303133;
}

.email-count {
  font-size: 13px;
  color: #909399;
  margin-left: 8px;
}

.email-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.email-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.email-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.email-sender {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}

.sender-info {
  overflow: hidden;
}

.sender-name {
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sender-email {
  font-size: 12px;
  color: #909399;
}

.email-content {
  flex: 1;
  min-width: 0;
}

.email-subject {
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-preview {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  min-width: 100px;
}

.email-date {
  font-size: 12px;
  color: #909399;
}

.email-actions {
  opacity: 0;
  transition: opacity 0.2s;
}

.email-item:hover .email-actions {
  opacity: 1;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #409EFF;
  color: #fff;
}

.batch-actions .el-button {
  color: #fff;
  border-color: rgba(255, 255, 255, 0.5);
}
</style>
