<template>
  <div class="emails-container" :class="layoutClass">
    <!-- 主要内容区 -->
    <div class="emails-main">
      <!-- 视图切换按钮 -->
      <div class="view-mode-toggle">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="split">双栏</el-radio-button>
          <el-radio-button value="grouped">分组</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 分组视图模式 -->
      <EmailGroupView
        v-if="viewMode === 'grouped'"
        :emails="emails"
        :selected-emails="selectedEmails"
        :active-email-id="activeEmailId"
        @email-click="(email) => handleEmailClick(email, emails.indexOf(email))"
        @toggle-select="toggleSelect"
        @toggle-flag="toggleFlag"
        @mark-read="(ids) => handleBatchMarkRead(ids, true)"
      />

      <!-- Split View 模式：左边原文，右边译文 -->
      <div class="split-panes" v-if="viewMode === 'split'">
      <!-- 左侧原文列表 -->
      <div class="split-pane original-pane">
        <div class="split-pane-header">
          <el-icon><Document /></el-icon>
          <span>原文</span>
          <span class="pane-count">({{ emails.length }})</span>
        </div>
        <div class="email-list" v-loading="loading">
          <el-dropdown
            v-for="(email, index) in emails"
            :key="'orig-' + email.id"
            trigger="contextmenu"
            @command="(cmd) => handleContextMenuCommand(cmd, email)"
            @visible-change="(visible) => visible && (focusedIndex = index)"
          >
          <div
            class="email-item compact"
            :class="{
              'unread': !email.is_read,
              'selected': selectedEmails.includes(email.id),
              'active': activeEmailId === email.id,
              'focused': focusedIndex === index
            }"
            @click="handleEmailClick(email, index)"
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
              </div>
              <div class="email-subject">{{ email.subject_original }}</div>
              <div class="email-preview">{{ getOriginalPreview(email) }}</div>
            </div>
            <div class="email-tags">
              <!-- 邮件标签 -->
              <el-tag
                v-for="label in (email.labels || []).slice(0, 2)"
                :key="label.id"
                :color="label.color"
                :style="{ color: getTextColor(label.color) }"
                size="small"
                class="label-tag"
              >
                {{ label.name }}
              </el-tag>
              <el-tag
                v-if="email.labels && email.labels.length > 2"
                size="small"
                type="info"
                class="more-labels"
              >
                +{{ email.labels.length - 2 }}
              </el-tag>
              <!-- 语言标签 -->
              <el-tag
                v-if="email.language_detected && email.language_detected !== 'unknown'"
                size="small"
                type="info"
              >
                {{ getLanguageName(email.language_detected) }}
              </el-tag>
            </div>
            <!-- 悬停操作按钮 -->
            <div class="hover-actions" @click.stop>
              <el-tooltip content="回复" placement="top" :show-after="500">
                <el-button :icon="Back" size="small" circle @click="handleQuickReply(email)" />
              </el-tooltip>
              <el-tooltip content="删除" placement="top" :show-after="500">
                <el-button :icon="Delete" size="small" circle type="danger" plain @click="handleQuickDelete(email)" />
              </el-tooltip>
              <el-dropdown trigger="click" @command="(cmd) => handleQuickAction(cmd, email)">
                <el-button :icon="MoreFilled" size="small" circle />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="mark-read">
                      {{ email.is_read ? '标记为未读' : '标记为已读' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="toggle-flag">
                      {{ email.is_flagged ? '取消星标' : '添加星标' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="add-label">添加标签</el-dropdown-item>
                    <el-dropdown-item command="translate" :disabled="email.is_translated">翻译</el-dropdown-item>
                    <el-dropdown-item command="forward">转发</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="mark-read">
                  <el-icon><View /></el-icon>
                  {{ email.is_read ? '标记为未读' : '标记为已读' }}
                </el-dropdown-item>
                <el-dropdown-item command="toggle-flag">
                  <el-icon><component :is="email.is_flagged ? Star : StarFilled" /></el-icon>
                  {{ email.is_flagged ? '取消星标' : '添加星标' }}
                </el-dropdown-item>
                <el-dropdown-item divided command="add-label">
                  <el-icon><PriceTag /></el-icon>
                  添加标签...
                </el-dropdown-item>
                <el-dropdown-item command="move-folder">
                  <el-icon><Folder /></el-icon>
                  移至文件夹...
                </el-dropdown-item>
                <el-dropdown-item divided command="reply">
                  <el-icon><Back /></el-icon>
                  回复
                </el-dropdown-item>
                <el-dropdown-item command="forward">
                  <el-icon><Promotion /></el-icon>
                  转发
                </el-dropdown-item>
                <el-dropdown-item divided command="translate" :disabled="email.is_translated">
                  <el-icon><Refresh /></el-icon>
                  翻译
                </el-dropdown-item>
                <el-dropdown-item divided command="delete" style="color: #f56c6c;">
                  <el-icon><Delete /></el-icon>
                  删除
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
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
          <el-dropdown
            v-for="(email, index) in emails"
            :key="'trans-' + email.id"
            trigger="contextmenu"
            @command="(cmd) => handleContextMenuCommand(cmd, email)"
          >
          <div
            class="email-item compact"
            :class="{
              'unread': !email.is_read,
              'selected': selectedEmails.includes(email.id),
              'active': activeEmailId === email.id,
              'focused': focusedIndex === index
            }"
            @click="handleEmailClick(email, index)"
          >
            <!-- 与左侧完全镜像的结构 -->
            <div class="email-actions" style="visibility: hidden;">
              <el-checkbox :model-value="false" />
              <el-icon class="star-icon"><Star /></el-icon>
            </div>
            <div class="email-content">
              <div class="email-top-row">
                <span class="sender-name">{{ email.from_name || extractEmailName(email.from_email) }}</span>
                <!-- 右侧显示时间和翻译状态标签 -->
                <span class="email-time-area">
                  <!-- 翻译中状态 -->
                  <el-tag
                    v-if="email.translation_status === 'translating'"
                    size="small"
                    type="primary"
                    class="translating-tag"
                  >
                    <el-icon class="is-loading"><Loading /></el-icon>
                    翻译中
                  </el-tag>
                  <!-- 翻译失败状态 -->
                  <el-tag
                    v-else-if="email.translation_status === 'failed'"
                    size="small"
                    type="danger"
                    class="failed-tag"
                  >
                    翻译失败
                  </el-tag>
                  <!-- 未翻译状态 -->
                  <el-tag
                    v-else-if="!email.is_translated && email.language_detected && email.language_detected !== 'zh' && email.language_detected !== 'unknown'"
                    size="small"
                    type="warning"
                    class="untranslated-tag"
                  >
                    未翻译
                  </el-tag>
                  <span class="email-time">{{ formatTime(email.received_at) }}</span>
                </span>
              </div>
              <div class="email-subject">{{ email.subject_translated || email.subject_original }}</div>
              <div class="email-preview">{{ getTranslatedPreview(email) }}</div>
            </div>
          </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="mark-read">
                  {{ email.is_read ? '标记为未读' : '标记为已读' }}
                </el-dropdown-item>
                <el-dropdown-item command="toggle-flag">
                  {{ email.is_flagged ? '取消星标' : '添加星标' }}
                </el-dropdown-item>
                <el-dropdown-item divided command="reply">回复</el-dropdown-item>
                <el-dropdown-item command="forward">转发</el-dropdown-item>
                <el-dropdown-item divided command="translate" :disabled="email.is_translated">翻译</el-dropdown-item>
                <el-dropdown-item divided command="delete" style="color: #f56c6c;">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
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

    <!-- 预览窗格（非列表模式时显示） -->
    <div class="preview-pane" v-if="userStore.layoutMode !== 'list'">
      <EmailPreview
        :email-id="previewEmailId"
        @reply="handlePreviewReply"
        @forward="handlePreviewForward"
        @delete="handlePreviewDelete"
        @open="handlePreviewOpen"
        @update="handlePreviewUpdate"
      />
    </div>

    <!-- 标签选择器 -->
    <LabelSelector
      v-model="showLabelSelector"
      :email-id="labelSelectorEmailId"
      :current-labels="labelSelectorCurrentLabels"
      @saved="handleLabelsSaved"
    />


    <!-- 文件夹选择对话框 -->
    <el-dialog
      v-model="showFolderPicker"
      title="移至文件夹"
      width="400px"
      :close-on-click-modal="true"
    >
      <FolderPicker
        v-if="showFolderPicker"
        :email-id="folderPickerEmailId"
        @done="showFolderPicker = false; loadEmails(true)"
        @cancel="showFolderPicker = false"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  Star, StarFilled, Sort, Paperclip, Message, Document, DocumentCopy,
  // 右键菜单图标
  View, Hide, Delete, Folder, PriceTag, EditPen, Promotion, Refresh, Back, DArrowRight,
  // 悬停按钮图标
  MoreFilled,
  // 翻译状态图标
  Loading,
  // 视图切换图标
  Grid
} from '@element-plus/icons-vue'
import api from '@/api'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import EmailPreview from '@/components/EmailPreview.vue'
import LabelSelector from '@/components/LabelSelector.vue'
import FolderPicker from '@/components/FolderPicker.vue'
import EmailGroupView from '@/components/EmailGroupView.vue'

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
const focusedIndex = ref(-1)  // 当前聚焦的邮件索引
const previewEmailId = ref(null)  // 预览的邮件 ID
const showLabelSelector = ref(false)  // 标签选择器可见性
const labelSelectorEmailId = ref(null)  // 当前操作标签的邮件ID
const labelSelectorCurrentLabels = ref([])  // 当前邮件的标签

// 文件夹选择器
const showFolderPicker = ref(false)  // 文件夹选择器
const folderPickerEmailId = ref(null)  // 当前操作的邮件ID

// 操作锁：防止快速双击导致竞态
const pendingFlagOps = ref(new Set())  // 正在进行星标操作的邮件 ID

// 视图模式：split(双栏) / grouped(分组)
const viewMode = ref('split')

// 布局模式类名
const layoutClass = computed(() => {
  const mode = userStore.layoutMode
  return {
    'split-mode': true,
    'layout-list': mode === 'list',
    'layout-right': mode === 'right',
    'layout-bottom': mode === 'bottom'
  }
})

// 当前聚焦的邮件
const focusedEmail = computed(() => {
  if (focusedIndex.value >= 0 && focusedIndex.value < emails.value.length) {
    return emails.value[focusedIndex.value]
  }
  return null
})

// 右键菜单命令处理
async function handleContextMenuCommand(command, email) {
  if (!email) return

  // 获取要操作的邮件ID列表
  const emailIds = selectedEmails.value.length > 0 ? [...selectedEmails.value] : [email.id]

  switch (command) {
    case 'mark-read':
      await handleBatchMarkRead(emailIds, !email.is_read)
      break
    case 'toggle-flag':
      await handleBatchToggleFlag(emailIds, !email.is_flagged)
      break
    case 'add-label':
      openLabelSelector(email)
      break
    case 'move-folder':
      openFolderPicker(email.id)
      break
    case 'reply':
      router.push(`/emails/${email.id}?reply=true`)
      break
    case 'reply-all':
      router.push(`/emails/${email.id}?reply=all`)
      break
    case 'forward':
      router.push(`/emails/${email.id}?forward=true`)
      break
    case 'translate':
      await handleBatchTranslate(emailIds)
      break
    case 'delete':
      await handleBatchDelete(emailIds)
      break
  }
}

// 批量标记已读/未读
async function handleBatchMarkRead(ids, markAsRead) {
  const action = markAsRead ? '标记为已读' : '标记为未读'
  try {
    if (markAsRead) {
      await api.batchMarkAsRead(ids)
      ElMessage.success(`已将 ${ids.length} 封邮件${action}`)
    } else {
      await api.batchMarkAsUnread(ids)
      ElMessage.success(`已将 ${ids.length} 封邮件${action}`)
    }
    // 更新本地状态
    ids.forEach(id => {
      const email = emails.value.find(e => e.id === id)
      if (email) email.is_read = markAsRead
    })
  } catch (e) {
    ElMessage.error(`批量${action}失败，请重试`)
    // 刷新数据获取服务端真实状态
    loadEmails(true)
    console.error('Batch mark read failed:', e)
  }
}

// 批量切换星标
async function handleBatchToggleFlag(ids, flagged) {
  const action = flagged ? '添加星标' : '取消星标'
  try {
    if (flagged) {
      await api.batchFlag(ids)
      ElMessage.success(`已为 ${ids.length} 封邮件${action}`)
    } else {
      await api.batchUnflag(ids)
      ElMessage.success(`已${action} ${ids.length} 封邮件`)
    }
    // 更新本地状态
    ids.forEach(id => {
      const email = emails.value.find(e => e.id === id)
      if (email) email.is_flagged = flagged
    })
  } catch (e) {
    ElMessage.error(`批量${action}失败，请重试`)
    // 刷新数据获取服务端真实状态
    loadEmails(true)
    console.error('Batch toggle flag failed:', e)
  }
}

// 批量删除
async function handleBatchDelete(ids) {
  try {
    await api.batchDelete(ids)
    ElMessage.success(`已删除 ${ids.length} 封邮件`)
    selectedEmails.value = []
    loadEmails()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 批量翻译
async function handleBatchTranslate(ids) {
  try {
    ElMessage.info(`正在翻译 ${ids.length} 封邮件...`)
    for (const id of ids) {
      await api.translateEmail(id)
    }
    ElMessage.success(`${ids.length} 封邮件翻译完成`)
    loadEmails(true)
  } catch (e) {
    ElMessage.error('翻译失败')
  }
}

// 打开文件夹选择器
function openFolderPicker(emailId) {
  folderPickerEmailId.value = emailId
  showFolderPicker.value = true
}

// === 悬停快捷操作 ===

function handleQuickReply(email) {
  router.push(`/emails/${email.id}?reply=true`)
}

async function handleQuickDelete(email) {
  try {
    await api.deleteEmail(email.id)
    ElMessage.success('邮件已删除')
    // 从列表中移除
    const index = emails.value.findIndex(e => e.id === email.id)
    if (index > -1) {
      emails.value.splice(index, 1)
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function handleQuickAction(command, email) {
  switch (command) {
    case 'mark-read':
      await handleBatchMarkRead([email.id], !email.is_read)
      break
    case 'toggle-flag':
      await handleBatchToggleFlag([email.id], !email.is_flagged)
      break
    case 'add-label':
      openLabelSelector(email)
      break
    case 'translate':
      await handleBatchTranslate([email.id])
      break
    case 'forward':
      router.push(`/emails/${email.id}?forward=true`)
      break
  }
}

// 当聚焦索引变化时，更新预览邮件
watch(focusedIndex, (newIndex) => {
  if (userStore.layoutMode !== 'list' && newIndex >= 0 && newIndex < emails.value.length) {
    previewEmailId.value = emails.value[newIndex].id
  }
})

// 邮件列表快捷键
useKeyboardShortcuts([
  {
    key: 'j',
    handler: () => {
      // 下一封
      if (emails.value.length > 0) {
        focusedIndex.value = Math.min(focusedIndex.value + 1, emails.value.length - 1)
        scrollToFocused()
      }
    }
  },
  {
    key: 'k',
    handler: () => {
      // 上一封
      if (emails.value.length > 0) {
        focusedIndex.value = Math.max(focusedIndex.value - 1, 0)
        scrollToFocused()
      }
    }
  },
  {
    key: 'Enter',
    handler: () => {
      // 打开邮件
      if (focusedEmail.value) {
        router.push(`/emails/${focusedEmail.value.id}`)
      }
    }
  },
  {
    key: 'x',
    handler: () => {
      // 选择/取消选择
      if (focusedEmail.value) {
        toggleSelect(focusedEmail.value.id)
      }
    }
  },
  {
    key: 's',
    handler: () => {
      // 切换星标
      if (focusedEmail.value) {
        toggleFlag(focusedEmail.value)
      }
    }
  },
  {
    key: 'd',
    handler: async () => {
      // 删除选中或聚焦的邮件
      const idsToDelete = selectedEmails.value.length > 0
        ? [...selectedEmails.value]
        : (focusedEmail.value ? [focusedEmail.value.id] : [])

      if (idsToDelete.length > 0) {
        try {
          await api.batchDelete(idsToDelete)
          ElMessage.success(`已删除 ${idsToDelete.length} 封邮件`)
          selectedEmails.value = []
          loadEmails()
        } catch (e) {
          ElMessage.error('删除失败')
        }
      }
    }
  },
  {
    key: 'u',
    handler: async () => {
      // 标记未读
      const ids = selectedEmails.value.length > 0
        ? [...selectedEmails.value]
        : (focusedEmail.value ? [focusedEmail.value.id] : [])

      if (ids.length > 0) {
        try {
          await api.batchMarkAsUnread(ids)
          ElMessage.success(`已将 ${ids.length} 封邮件标记为未读`)
          loadEmails()
        } catch (e) {
          ElMessage.error('操作失败')
        }
      }
    }
  },
  {
    key: 'a',
    ctrl: true,
    handler: () => {
      // 全选
      if (selectedEmails.value.length === emails.value.length) {
        selectedEmails.value = []
      } else {
        selectedEmails.value = emails.value.map(e => e.id)
      }
    }
  },
  {
    key: 'l',
    handler: async () => {
      // 打开标签选择器
      if (focusedEmail.value) {
        openLabelSelector(focusedEmail.value)
      }
    }
  },
  {
    key: 'm',
    handler: async () => {
      // 标记已读
      const ids = selectedEmails.value.length > 0
        ? [...selectedEmails.value]
        : (focusedEmail.value ? [focusedEmail.value.id] : [])

      if (ids.length > 0) {
        try {
          await api.batchMarkAsRead(ids)
          ElMessage.success(`已将 ${ids.length} 封邮件标记为已读`)
          loadEmails()
        } catch (e) {
          ElMessage.error('操作失败')
        }
      }
    }
  },
  {
    key: 'r',
    handler: () => {
      // 回复邮件
      if (focusedEmail.value) {
        router.push(`/emails/${focusedEmail.value.id}?reply=true`)
      }
    }
  },
  {
    key: 'f',
    handler: () => {
      // 转发邮件
      if (focusedEmail.value) {
        router.push(`/emails/${focusedEmail.value.id}?forward=true`)
      }
    }
  }
])

// 滚动到聚焦的邮件
function scrollToFocused() {
  const items = document.querySelectorAll('.original-pane .email-item')
  if (items[focusedIndex.value]) {
    items[focusedIndex.value].scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
}

// 初始化
onMounted(async () => {
  // 确保在组件挂载后立即加载邮件
  await loadEmails()

  // 监听 WebSocket 邮件状态变更事件
  window.addEventListener('email-status-changed', handleRemoteStatusChange)
  window.addEventListener('email-deleted', handleRemoteDelete)
  window.addEventListener('ws:reconnected', handleWsReconnected)
  window.addEventListener('email-translated', handleEmailTranslated)
  window.addEventListener('email-translation-failed', handleEmailTranslationFailed)
})

// 清理事件监听器
onUnmounted(() => {
  window.removeEventListener('email-status-changed', handleRemoteStatusChange)
  window.removeEventListener('email-deleted', handleRemoteDelete)
  window.removeEventListener('ws:reconnected', handleWsReconnected)
  window.removeEventListener('email-translated', handleEmailTranslated)
  window.removeEventListener('email-translation-failed', handleEmailTranslationFailed)
})

// 处理翻译完成事件
function handleEmailTranslated(event) {
  const detail = event.detail
  if (!detail?.email_id) return

  const emailIndex = emails.value.findIndex(e => e.id === detail.email_id)
  if (emailIndex === -1) return

  const existingEmail = emails.value[emailIndex]

  // 直接使用 WebSocket 推送的数据（如果有的话）
  if (detail.body_translated !== undefined) {
    existingEmail.subject_translated = detail.subject_translated
    existingEmail.body_translated = detail.body_translated
    existingEmail.is_translated = detail.is_translated
    existingEmail.translation_status = detail.translation_status
    console.log(`[Emails] Updated translation for email ${detail.email_id} from WS data`)
  }
}

// 处理翻译失败事件
function handleEmailTranslationFailed(event) {
  const detail = event.detail
  if (!detail?.email_id) return

  const emailIndex = emails.value.findIndex(e => e.id === detail.email_id)
  if (emailIndex === -1) return

  const existingEmail = emails.value[emailIndex]
  existingEmail.translation_status = 'failed'
  console.log(`[Emails] Translation failed for email ${detail.email_id}`)
}

// 处理远程邮件状态变更（来自其他客户端的 WebSocket 通知）
function handleRemoteStatusChange(event) {
  const { email_ids, changes } = event.detail
  if (!email_ids || !changes) return

  // 更新本地邮件状态
  email_ids.forEach(emailId => {
    const email = emails.value.find(e => e.id === emailId)
    if (email) {
      Object.keys(changes).forEach(key => {
        email[key] = changes[key]
      })
    }
  })
}

// 处理远程邮件删除
function handleRemoteDelete(event) {
  const { email_ids } = event.detail
  if (!email_ids) return

  // 从列表中移除被删除的邮件
  emails.value = emails.value.filter(e => !email_ids.includes(e.id))
  // 从选中列表中移除
  selectedEmails.value = selectedEmails.value.filter(id => !email_ids.includes(id))
}

// 处理 WebSocket 重连后刷新数据
function handleWsReconnected() {
  console.log('[Emails] WebSocket reconnected, refreshing data...')
  loadEmails(true)  // 静默刷新
}

// 监听路由变化（不包括首次加载，因为 onMounted 已经处理）
watch(() => route.query, (newQuery, oldQuery) => {
  // 只有当 query 真正变化时才重新加载
  if (JSON.stringify(newQuery) !== JSON.stringify(oldQuery)) {
    currentPage.value = 1
    loadEmails()
  }
}, { deep: true })

// 监听刷新信号 - 使用静默刷新避免阻塞 UI
watch(() => userStore.emailRefreshKey, () => {
  loadEmails(true)  // 静默刷新，不显示 loading
})

// 暴露选中的邮件ID给父组件（Layout.vue）使用（通过 Pinia store）
watch(selectedEmails, (newVal) => {
  userStore.setSelectedEmailIds(newVal)
}, { immediate: true })

// AbortController 用于取消旧请求，防止竞态条件
let abortController = null

async function loadEmails(silent = false) {
  // 取消之前的请求
  if (abortController) {
    abortController.abort()
  }
  abortController = new AbortController()
  const signal = abortController.signal

  // 非静默模式才显示 loading 状态
  if (!silent) {
    loading.value = true
  }

  try {
    const params = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
      sort_by: sortBy.value
    }

    let result

    // 如果是文件夹视图，调用文件夹API
    if (route.query.folder_id) {
      result = await api.getFolderEmails(route.query.folder_id, params, { signal })
    } else {
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

      result = await api.getEmails(params, { signal })
    }

    // 只有当请求未被取消时才更新数据
    if (!signal.aborted) {
      emails.value = result.emails
      total.value = result.total
    }
  } catch (e) {
    // 忽略取消请求的错误
    if (e.name === 'CanceledError' || e.name === 'AbortError') {
      console.log('[Emails] Request was cancelled')
      return
    }
    console.error('Failed to load emails:', e)
  } finally {
    if (!signal.aborted) {
      loading.value = false
    }
  }
}

function handleEmailClick(email, index) {
  // 更新聚焦索引
  if (typeof index === 'number') {
    focusedIndex.value = index
  }

  // 预览模式：更新预览邮件，不跳转
  if (userStore.layoutMode !== 'list') {
    previewEmailId.value = email.id
    return
  }

  // 列表模式：跳转到详情页
  router.push(`/emails/${email.id}`)
}

// 预览窗格事件处理
function handlePreviewReply() {
  if (previewEmailId.value) {
    router.push(`/emails/${previewEmailId.value}?reply=true`)
  }
}

function handlePreviewForward() {
  ElMessage.info('转发功能开发中')
}

async function handlePreviewDelete() {
  if (!previewEmailId.value) return

  try {
    await api.deleteEmail(previewEmailId.value)
    ElMessage.success('邮件已删除')

    // 从列表中移除
    const index = emails.value.findIndex(e => e.id === previewEmailId.value)
    if (index > -1) {
      emails.value.splice(index, 1)
    }

    // 选中下一封
    if (emails.value.length > 0) {
      const nextIndex = Math.min(index, emails.value.length - 1)
      focusedIndex.value = nextIndex
      previewEmailId.value = emails.value[nextIndex].id
    } else {
      previewEmailId.value = null
      focusedIndex.value = -1
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

function handlePreviewOpen() {
  if (previewEmailId.value) {
    router.push(`/emails/${previewEmailId.value}`)
  }
}

function handlePreviewUpdate(updatedEmail) {
  // 更新列表中的邮件状态
  const emailInList = emails.value.find(e => e.id === updatedEmail.id)
  if (emailInList) {
    Object.assign(emailInList, updatedEmail)
  }
}

// 标签选择器相关
async function openLabelSelector(email) {
  labelSelectorEmailId.value = email.id
  // 获取邮件当前的标签
  try {
    labelSelectorCurrentLabels.value = await api.getEmailLabels(email.id)
  } catch (e) {
    labelSelectorCurrentLabels.value = []
  }
  showLabelSelector.value = true
}

function handleLabelsSaved(labels) {
  // 更新列表中邮件的标签
  const emailInList = emails.value.find(e => e.id === labelSelectorEmailId.value)
  if (emailInList) {
    emailInList.labels = labels
  }
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
  // 防止快速双击：如果该邮件正在操作中，忽略请求
  if (pendingFlagOps.value.has(email.id)) {
    return
  }

  const originalState = email.is_flagged
  const action = !originalState ? '添加星标' : '取消星标'
  email.is_flagged = !email.is_flagged  // 乐观更新
  pendingFlagOps.value.add(email.id)  // 加锁

  try {
    if (email.is_flagged) {
      await api.flagEmail(email.id)
    } else {
      await api.unflagEmail(email.id)
    }
  } catch (e) {
    // 恢复原状态并提示用户
    email.is_flagged = originalState
    ElMessage.error(`${action}失败，请重试`)
    console.error('Failed to toggle flag:', e)
  } finally {
    pendingFlagOps.value.delete(email.id)  // 释放锁
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
  // 防止快速双击：如果该邮件正在操作中，忽略请求
  if (pendingFlagOps.value.has(email.id)) {
    return
  }

  const originalState = email.is_flagged
  const action = !originalState ? '添加星标' : '取消星标'
  email.is_flagged = !email.is_flagged  // 乐观更新
  pendingFlagOps.value.add(email.id)  // 加锁

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
    // 恢复原状态并提示用户
    email.is_flagged = originalState
    ElMessage.error(`${action}失败，请重试`)
    console.error('Failed to toggle flag:', e)
  } finally {
    pendingFlagOps.value.delete(email.id)  // 释放锁
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
  if (!lang || lang === 'unknown') return ''
  const names = {
    en: '🇬🇧 英',
    ja: '🇯🇵 日',
    ko: '🇰🇷 韩',
    de: '🇩🇪 德',
    fr: '🇫🇷 法',
    es: '🇪🇸 西',
    pt: '🇵🇹 葡',
    ru: '🇷🇺 俄',
    it: '🇮🇹 意',
    nl: '🇳🇱 荷',
    vi: '🇻🇳 越',
    th: '🇹🇭 泰',
    ar: '🇸🇦 阿',
    tr: '🇹🇷 土',
    pl: '🇵🇱 波',
    cs: '🇨🇿 捷',
    sv: '🇸🇪 瑞',
    da: '🇩🇰 丹',
    fi: '🇫🇮 芬',
    no: '🇳🇴 挪',
    id: '🇮🇩 印尼',
    ms: '🇲🇾 马',
    zh: '🇨🇳 中'
  }
  return names[lang] || `🌐 ${lang}`
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

// 根据背景色计算文字颜色
function getTextColor(bgColor) {
  if (!bgColor) return '#333'
  const hex = bgColor.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)
  const brightness = (r * 299 + g * 587 + b * 114) / 1000
  return brightness > 128 ? '#333' : '#fff'
}
</script>

<style scoped>
.emails-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 视图模式切换 */
.view-mode-toggle {
  display: flex;
  justify-content: flex-end;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
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

/* 修复 el-dropdown 导致的并排显示问题 */
.email-list :deep(.el-dropdown) {
  display: block;
  width: 100%;
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

.email-item.focused {
  background-color: #f0f7ff;
  outline: 2px solid #409eff;
  outline-offset: -2px;
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
  margin-left: auto;  /* 始终靠右对齐 */
  padding-left: 8px;
}

.email-time-area {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.email-time-area .email-time {
  margin-left: 0;
  padding-left: 0;
}

.untranslated-tag {
  margin-left: auto;  /* 靠右对齐 */
}

.translating-tag {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.translating-tag .el-icon {
  font-size: 12px;
}

.failed-tag {
  margin-left: auto;
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
  min-height: 18px;  /* 固定高度，避免原文/译文内容不同导致行高不一致 */
  line-height: 18px;
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
  min-height: 16px;
  line-height: 16px;
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

/* 悬停操作按钮 */
.hover-actions {
  display: none;
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  gap: 4px;
  background: linear-gradient(to right, transparent, #fff 20%, #fff);
  padding-left: 20px;
}

.email-item {
  position: relative;
}

.email-item:hover .hover-actions {
  display: flex;
}

.email-item:hover .email-tags {
  visibility: hidden;
}

.email-item.selected .hover-actions {
  background: linear-gradient(to right, transparent, #ecf5ff 20%, #ecf5ff);
}

.email-item:hover:not(.selected) .hover-actions {
  background: linear-gradient(to right, transparent, #f5f7fa 20%, #f5f7fa);
}

.hover-actions .el-button.is-circle {
  width: 28px;
  height: 28px;
  padding: 0;
}

.hover-actions .el-button.is-circle .el-icon {
  font-size: 14px;
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

/* ========== 布局模式样式 ========== */

/* 列表模式（默认） */
.emails-container.layout-list {
  flex-direction: column;
}

.emails-container.layout-list .emails-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 右侧预览模式 */
.emails-container.layout-right {
  flex-direction: row;
}

.emails-container.layout-right .emails-main {
  width: 45%;
  min-width: 400px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #e8e8e8;
}

.emails-container.layout-right .preview-pane {
  flex: 1;
  overflow: hidden;
}

/* 底部预览模式 */
.emails-container.layout-bottom {
  flex-direction: column;
}

.emails-container.layout-bottom .emails-main {
  height: 50%;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-bottom: 1px solid #e8e8e8;
}

.emails-container.layout-bottom .preview-pane {
  flex: 1;
  overflow: hidden;
}

/* 预览窗格通用样式 */
.preview-pane {
  background-color: #fff;
}
</style>
