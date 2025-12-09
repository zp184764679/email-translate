<template>
  <div class="emails-container split-mode">
    <!-- Split View 模式：左边原文，右边译文 -->
    <div class="split-panes">
      <!-- 左侧原文列表 -->
      <div class="split-pane original-pane">
        <div class="split-pane-header">
          <el-icon><Document /></el-icon>
          <span>原文</span>
          <span class="pane-count">({{ emails.length }})</span>
        </div>
        <div class="email-list" v-loading="loading">
          <div
            v-for="email in emails"
            :key="'orig-' + email.id"
            class="email-item compact"
            :class="{
              'unread': !email.is_read,
              'selected': selectedEmails.includes(email.id),
              'active': activeEmailId === email.id
            }"
            @click="handleEmailClick(email)"
          >
            <div class="email-actions">
              <el-checkbox
                :model-value="selectedEmails.includes(email.id)"
                @change="toggleSelect(email.id)"
                @click.stop
              />
              <el-icon
                class="star-icon"
                :class="{ 'starred': email.is_flagged }"
                @click.stop="toggleFlag(email)"
              >
                <component :is="email.is_flagged ? StarFilled : Star" />
              </el-icon>
            </div>
            <div class="email-content">
              <div class="email-top-row">
                <span class="sender-name">{{ email.from_name || extractEmailName(email.from_email) }}</span>
                <span class="email-time">{{ formatTime(email.received_at) }}</span>
                <!-- 左侧也保留"未翻译"标签占位符，保持与右侧结构一致 -->
                <el-tag
                  v-if="!email.is_translated && email.language_detected !== 'zh'"
                  size="small"
                  type="warning"
                  style="visibility: hidden;"
                >
                  未翻译
                </el-tag>
              </div>
              <div class="email-subject">{{ email.subject_original }}</div>
              <div class="email-preview">{{ getOriginalPreview(email) }}</div>
            </div>
            <div class="email-tags">
              <el-tag
                v-if="email.language_detected && email.language_detected !== 'zh'"
                size="small"
                type="info"
              >
                {{ getLanguageName(email.language_detected) }}
              </el-tag>
            </div>
          </div>
          <el-empty v-if="!loading && emails.length === 0" description="暂无邮件" />
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="split-divider"></div>

      <!-- 右侧翻译列表 -->
      <div class="split-pane translated-pane">
        <div class="split-pane-header">
          <el-icon><DocumentCopy /></el-icon>
          <span>中文翻译</span>
          <span class="pane-count" style="visibility: hidden;">({{ emails.length }})</span>
        </div>
        <div class="email-list">
          <div
            v-for="email in emails"
            :key="'trans-' + email.id"
            class="email-item compact"
            :class="{
              'unread': !email.is_read,
              'selected': selectedEmails.includes(email.id),
              'active': activeEmailId === email.id
            }"
            @click="handleEmailClick(email)"
          >
            <!-- 与左侧完全镜像的结构 -->
            <div class="email-actions" style="visibility: hidden;">
              <el-checkbox :model-value="false" />
              <el-icon class="star-icon"><Star /></el-icon>
            </div>
            <div class="email-content">
              <div class="email-top-row">
                <span class="sender-name">{{ email.from_name || extractEmailName(email.from_email) }}</span>
                <span class="email-time" style="visibility: hidden;">{{ formatTime(email.received_at) }}</span>
                <!-- 右侧显示"未翻译"标签 -->
                <el-tag
                  v-if="!email.is_translated && email.language_detected !== 'zh'"
                  size="small"
                  type="warning"
                >
                  未翻译
                </el-tag>
              </div>
              <div class="email-subject">{{ email.subject_translated || email.subject_original }}</div>
              <div class="email-preview">{{ getTranslatedPreview(email) }}</div>
            </div>
            <div class="email-tags">
              <!-- 与左侧一样的语言标签结构，但隐藏 -->
              <el-tag
                v-if="email.language_detected && email.language_detected !== 'zh'"
                size="small"
                type="info"
                style="visibility: hidden;"
              >
                {{ getLanguageName(email.language_detected) }}
              </el-tag>
            </div>
          </div>
          <el-empty v-if="!loading && emails.length === 0" description="暂无邮件" />
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="split-footer" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          @current-change="loadEmails"
        />
      </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Star, StarFilled, Sort, Paperclip, Message, Document, DocumentCopy } from '@element-plus/icons-vue'
import api from '@/api'
import dayjs from 'dayjs'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// 状态
const emails = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)
const selectedEmails = ref([])
const activeEmailId = ref(null)
const activeEmail = ref(null)
const sortBy = ref('date_desc')

// 初始化
onMounted(async () => {
  // 确保在组件挂载后立即加载邮件
  await loadEmails()
})

// 监听路由变化（不包括首次加载，因为 onMounted 已经处理）
watch(() => route.query, (newQuery, oldQuery) => {
  // 只有当 query 真正变化时才重新加载
  if (JSON.stringify(newQuery) !== JSON.stringify(oldQuery)) {
    currentPage.value = 1
    loadEmails()
  }
}, { deep: true })

// 监听刷新信号
watch(() => userStore.emailRefreshKey, () => {
  loadEmails()
})

// 暴露选中的邮件ID给父组件（Layout.vue）使用
watch(selectedEmails, (newVal) => {
  window.__selectedEmailIds = newVal
}, { immediate: true })

async function loadEmails() {
  loading.value = true
  try {
    const params = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
      sort_by: sortBy.value
    }

    // 默认显示收件箱（inbound），除非明确指定了其他方向
    if (route.query.direction) {
      params.direction = route.query.direction
    } else {
      // 收件箱默认只显示收到的邮件
      params.direction = 'inbound'
    }

    if (route.query.search) {
      params.search = route.query.search
    }

    if (route.query.supplier_id) {
      params.supplier_id = route.query.supplier_id
    }

    const result = await api.getEmails(params)
    emails.value = result.emails
    total.value = result.total
  } catch (e) {
    console.error('Failed to load emails:', e)
  } finally {
    loading.value = false
  }
}

function handleEmailClick(email) {
  // 点击邮件跳转到详情页
  router.push(`/emails/${email.id}`)
}

async function loadEmailDetail(id) {
  try {
    activeEmail.value = await api.getEmail(id)
  } catch (e) {
    console.error('Failed to load email:', e)
  }
}

function handleSelectAll(val) {
  if (val) {
    selectedEmails.value = emails.value.map(e => e.id)
  } else {
    selectedEmails.value = []
  }
}

function toggleSelect(id) {
  const index = selectedEmails.value.indexOf(id)
  if (index > -1) {
    selectedEmails.value.splice(index, 1)
  } else {
    selectedEmails.value.push(id)
  }
}

async function toggleFlag(email) {
  const originalState = email.is_flagged
  email.is_flagged = !email.is_flagged

  try {
    if (email.is_flagged) {
      await api.flagEmail(email.id)
    } else {
      await api.unflagEmail(email.id)
    }
  } catch (e) {
    // 恢复原状态
    email.is_flagged = originalState
    console.error('Failed to toggle flag:', e)
  }
}

function handleSort(command) {
  sortBy.value = command
  currentPage.value = 1
  loadEmails()
}

function handleReply(email) {
  router.push(`/emails/${email.id}?reply=true`)
}

async function handleEmailRefresh() {
  // 翻译完成后重新加载邮件详情
  if (activeEmailId.value) {
    await loadEmailDetail(activeEmailId.value)
    // 同时更新列表中的状态
    const emailInList = emails.value.find(e => e.id === activeEmailId.value)
    if (emailInList && activeEmail.value) {
      emailInList.is_translated = activeEmail.value.is_translated
      emailInList.subject_translated = activeEmail.value.subject_translated
      emailInList.body_translated = activeEmail.value.body_translated
    }
  }
}

async function handleEmailDelete(email) {
  try {
    await api.deleteEmail(email.id)
    // 从列表中移除
    const index = emails.value.findIndex(e => e.id === email.id)
    if (index > -1) {
      emails.value.splice(index, 1)
    }
    activeEmail.value = null
    activeEmailId.value = null
    // 选中下一封
    if (emails.value.length > 0) {
      handleEmailClick(emails.value[Math.min(index, emails.value.length - 1)])
    }
  } catch (e) {
    console.error('Failed to delete email:', e)
  }
}

async function handleEmailFlag(email) {
  const originalState = email.is_flagged
  email.is_flagged = !email.is_flagged

  try {
    if (email.is_flagged) {
      await api.flagEmail(email.id)
    } else {
      await api.unflagEmail(email.id)
    }
    // 同步列表中的状态
    const emailInList = emails.value.find(e => e.id === email.id)
    if (emailInList) {
      emailInList.is_flagged = email.is_flagged
    }
  } catch (e) {
    email.is_flagged = originalState
    console.error('Failed to toggle flag:', e)
  }
}

function formatTime(date) {
  if (!date) return ''
  const d = dayjs(date)
  const today = dayjs()

  if (d.isSame(today, 'day')) {
    return d.format('HH:mm')
  } else if (d.isSame(today, 'year')) {
    return d.format('MM/DD HH:mm')
  }
  return d.format('YYYY/MM/DD HH:mm')
}

function getLanguageName(lang) {
  const names = {
    en: '英',
    ja: '日',
    ko: '韩',
    de: '德',
    fr: '法',
    es: '西',
    pt: '葡',
    ru: '俄'
  }
  return names[lang] || lang
}

function getPreview(email) {
  const body = email.body_translated || email.body_original || ''
  return body.substring(0, 80).replace(/\n/g, ' ').trim()
}

function getOriginalPreview(email) {
  const body = email.body_original || ''
  return body.substring(0, 80).replace(/\n/g, ' ').trim()
}

function getTranslatedPreview(email) {
  const body = email.body_translated || email.body_original || ''
  return body.substring(0, 80).replace(/\n/g, ' ').trim()
}

function getInitials(name) {
  if (!name) return '?'
  const parts = name.split(/[@\s]+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.substring(0, 2).toUpperCase()
}

function extractEmailName(email) {
  if (!email) return ''
  return email.split('@')[0]
}

function getAvatarColor(email) {
  if (!email) return '#409eff'
  const colors = [
    '#409eff', '#67c23a', '#e6a23c', '#f56c6c',
    '#909399', '#00bcd4', '#9c27b0', '#ff5722'
  ]
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

function hasAttachments(email) {
  return email.attachments && email.attachments.length > 0
}
</script>

<style scoped>
.emails-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 列表头部 */
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  background-color: #fafafa;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title {
  font-weight: 600;
  font-size: 14px;
  color: #1a1a1a;
}

.email-count {
  font-size: 13px;
  color: #909399;
}

.sort-trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
}

.sort-trigger:hover {
  color: #409eff;
}

/* 邮件列表 */
.email-list {
  /* 不设置 overflow，让父容器统一滚动 */
}

.email-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.email-item:hover {
  background-color: #f5f7fa;
}

.email-item.selected {
  background-color: #ecf5ff;
}

.email-item.active {
  background-color: #e1efff;
  border-left: 3px solid #0078d4;
  padding-left: 13px;
}

.email-item.unread {
  background-color: #fff;
}

.email-item.unread .sender-name,
.email-item.unread .email-subject {
  font-weight: 600;
}

.email-item.unread::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: #0078d4;
}

/* 左侧操作区 */
.email-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-right: 12px;
}

.star-icon {
  cursor: pointer;
  color: #c0c4cc;
  font-size: 16px;
  transition: color 0.15s;
}

.star-icon:hover {
  color: #e6a23c;
}

.star-icon.starred {
  color: #e6a23c;
}

/* 发件人头像 */
.sender-avatar {
  margin-right: 12px;
  flex-shrink: 0;
}

/* 邮件内容 */
.email-content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.email-top-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.sender-name {
  font-size: 14px;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-time {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
  margin-left: 8px;
}

.email-subject {
  font-size: 13px;
  color: #303133;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-preview {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 右侧标签区 */
.email-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  flex-shrink: 0;
}

.attachment-icon {
  color: #909399;
  font-size: 14px;
}

/* 列表底部 */
.list-footer {
  padding: 8px 16px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: center;
}

/* 阅读窗格 */
.reading-pane {
  flex: 1;
  overflow: hidden;
  background-color: #fff;
}

.no-selection {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
}

.no-selection .el-icon {
  margin-bottom: 16px;
  color: #c0c4cc;
}

.no-selection p {
  font-size: 14px;
}

/* ========== Split View 模式样式 ========== */
.split-panes {
  display: flex;
  flex-direction: row;
  flex: 1;
  overflow-y: auto;  /* 整体滚动 */
  overflow-x: hidden;
}

.split-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  /* 不设置 overflow，让内容自然撑开高度 */
}

.original-pane {
  border-right: none;
}

.translated-pane {
  border-left: none;
}

.split-divider {
  width: 1px;
  background: linear-gradient(to bottom, #e0e0e0, #d0d0d0);
  flex-shrink: 0;
}

.split-pane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: linear-gradient(to bottom, #fafbfc, #f5f6f7);
  border-bottom: 1px solid #e8e8e8;
  font-weight: 600;
  font-size: 13px;
  color: #606266;
}

.split-pane-header .el-icon {
  font-size: 16px;
  color: #909399;
}

.original-pane .split-pane-header {
  color: #606266;
}

.translated-pane .split-pane-header {
  color: #409eff;
}

.translated-pane .split-pane-header .el-icon {
  color: #409eff;
}

.pane-count {
  font-weight: normal;
  color: #909399;
  font-size: 12px;
}

/* Split View 紧凑型邮件项 */
.email-item.compact {
  padding: 10px 12px;
}

.email-item.compact .email-actions {
  flex-direction: row;
  gap: 6px;
  margin-right: 10px;
}

.email-item.compact .email-content {
  flex: 1;
}

.email-item.compact .email-top-row {
  margin-bottom: 3px;
}

.email-item.compact .sender-name {
  font-size: 13px;
  max-width: 150px;
}

.email-item.compact .email-time {
  font-size: 11px;
}

.email-item.compact .email-subject {
  font-size: 12px;
  margin-bottom: 2px;
}

.email-item.compact .email-preview {
  font-size: 11px;
  color: #a0a0a0;
}

.email-item.compact .email-tags {
  margin-left: 6px;
}

.email-item.compact .email-tags .el-tag {
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
  line-height: 18px;
}

/* 翻译列表右侧简化样式（无复选框和星标） */
.translated-pane .email-item.compact {
  padding-left: 16px;
}

.translated-pane .email-item.compact .email-top-row {
  gap: 8px;
}

/* Split View 底部分页 */
.split-footer {
  width: 100%;
  padding: 8px 16px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: center;
  background-color: #fafafa;
}
</style>
