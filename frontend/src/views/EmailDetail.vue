<template>
  <div class="email-detail-page" v-loading="loading">
    <!-- 顶部操作栏 -->
    <div class="detail-toolbar">
      <div class="toolbar-left">
        <el-button :icon="ArrowLeft" @click="$router.push('/emails')">返回</el-button>
        <el-divider direction="vertical" />
        <el-button-group>
          <el-button :icon="Back" @click="handleReply">回复</el-button>
          <el-button :icon="ChatLineSquare" @click="handleReplyAll">全部回复</el-button>
          <el-button :icon="Right" @click="handleForward">转发</el-button>
        </el-button-group>
        <el-divider direction="vertical" />
        <el-button-group>
          <el-button :icon="Delete" type="danger" plain @click="handleDelete">删除</el-button>
          <el-button :icon="Star" @click="handleFlag">
            {{ email?.is_flagged ? '取消标记' : '标记' }}
          </el-button>
          <el-button :icon="CollectionTag" @click="openLabelSelector">标签</el-button>
        </el-button-group>
      </div>
      <div class="toolbar-right">
        <el-dropdown @command="handleExport">
          <el-button>
            导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="eml">导出为 EML</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button :icon="Printer" @click="handlePrint">打印</el-button>
      </div>
    </div>

    <!-- 邮件内容区 -->
    <div class="detail-content" v-if="email">
      <!-- 主题 -->
      <div class="email-subject-section">
        <h1 class="email-subject">{{ email.subject_translated || email.subject_original }}</h1>
        <div class="email-labels">
          <el-tag v-if="email.direction === 'inbound'" type="primary" size="small">收件</el-tag>
          <el-tag v-else type="success" size="small">发件</el-tag>
          <!-- 外语标签：显示翻译状态 -->
          <el-tag
            v-if="email.translation_status === 'translating'"
            type="primary"
            size="small"
            class="translating-status-tag"
          >
            <el-icon class="is-loading"><Loading /></el-icon>
            翻译中
          </el-tag>
          <el-tag
            v-else-if="email.translation_status === 'failed'"
            type="danger"
            size="small"
          >
            翻译失败
          </el-tag>
          <el-tag
            v-else-if="email.language_detected && email.language_detected !== 'zh' && email.language_detected !== 'unknown'"
            :type="email.is_translated ? 'success' : 'warning'"
            size="small"
          >
            {{ email.is_translated ? '已翻译' : getLanguageName(email.language_detected) }}
          </el-tag>
          <!-- 中文标签：直接显示语言 -->
          <el-tag
            v-else-if="email.language_detected === 'zh'"
            type="info"
            size="small"
          >
            {{ getLanguageName(email.language_detected) }}
          </el-tag>
          <!-- 自定义标签 -->
          <el-tag
            v-for="label in (email.labels || [])"
            :key="label.id"
            :color="label.color"
            :style="{ color: getTextColor(label.color) }"
            size="small"
            closable
            @close="removeLabel(label.id)"
          >
            {{ label.name }}
          </el-tag>
        </div>
      </div>

      <!-- 发件人信息 -->
      <div class="sender-section">
        <el-avatar :size="48" :style="{ backgroundColor: getAvatarColor(email.from_email) }">
          {{ getInitials(email.from_name || email.from_email) }}
        </el-avatar>
        <div class="sender-info">
          <div class="sender-primary">
            <span
              class="sender-name clickable"
              @contextmenu.prevent="handleSenderContextMenu($event, email.from_email)"
            >
              {{ email.from_name || email.from_email }}
            </span>
            <span
              class="sender-email clickable"
              v-if="email.from_name"
              @contextmenu.prevent="handleSenderContextMenu($event, email.from_email)"
            >
              &lt;{{ email.from_email }}&gt;
            </span>
          </div>
          <div class="recipient-info">
            <div class="recipient-row">
              <span class="label">收件人：</span>
              <span class="value">{{ formatAddressList(email.to_email) }}</span>
            </div>
            <div class="recipient-row" v-if="email.cc_email">
              <span class="label">抄送：</span>
              <span class="value cc">{{ formatAddressList(email.cc_email) }}</span>
            </div>
            <div class="recipient-row" v-if="email.bcc_email">
              <span class="label">密送：</span>
              <span class="value bcc">{{ formatAddressList(email.bcc_email) }}</span>
            </div>
            <div class="recipient-row" v-if="email.reply_to && email.reply_to !== email.from_email">
              <span class="label">回复至：</span>
              <span class="value">{{ email.reply_to }}</span>
            </div>
          </div>
        </div>
        <div class="email-datetime">
          <div class="date-primary">{{ formatDate(email.received_at) }}</div>
          <div class="date-secondary">{{ formatTime(email.received_at) }}</div>
        </div>
      </div>

      <!-- 翻译提示条 -->
      <!-- 翻译中状态 -->
      <div class="translation-notice translating" v-if="email.translation_status === 'translating'">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在翻译此邮件，请稍候...</span>
      </div>
      <!-- 翻译失败状态 -->
      <div class="translation-notice failed" v-else-if="email.translation_status === 'failed'">
        <el-icon><InfoFilled /></el-icon>
        <span>翻译失败，请重试</span>
        <el-button type="primary" size="small" @click="translateEmail" :loading="translating">
          重试翻译
        </el-button>
      </div>
      <!-- 未翻译状态（仅非中文时显示）-->
      <div class="translation-notice" v-else-if="!email.is_translated && email.language_detected && email.language_detected !== 'zh' && email.language_detected !== 'unknown'">
        <el-icon><InfoFilled /></el-icon>
        <span>此邮件为 {{ getLanguageName(email.language_detected) }}，尚未翻译</span>
        <el-button type="primary" size="small" @click="translateEmail" :loading="translating">
          立即翻译
        </el-button>
      </div>

      <!-- 附件区域 -->
      <div class="attachments-section" v-if="email.attachments && email.attachments.length > 0">
        <div class="section-header">
          <el-icon><Paperclip /></el-icon>
          <span>附件 ({{ email.attachments.length }})</span>
          <el-button text size="small" @click="downloadAllAttachments">全部下载</el-button>
        </div>
        <div class="attachments-grid">
          <div
            class="attachment-card"
            v-for="att in email.attachments"
            :key="att.id"
            @contextmenu.prevent="handleAttachmentContextMenu($event, att)"
          >
            <div class="attachment-icon">
              <el-icon :size="24"><Document /></el-icon>
            </div>
            <div class="attachment-info">
              <div class="attachment-name">{{ att.filename }}</div>
              <div class="attachment-size">{{ formatFileSize(att.file_size) }}</div>
            </div>
            <div class="attachment-actions">
              <el-button
                text
                size="small"
                :icon="Download"
                :loading="downloadingAttachments[att.id]"
                @click="downloadAttachment(att)"
              >
                下载
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 邮件正文 - Split View（所有邮件统一双栏显示）-->
      <div class="body-section split-view">
        <div class="split-header">
          <div class="split-header-left">
            <el-icon><Document /></el-icon>
            <span>原文 ({{ getLanguageName(email.language_detected) || '中文' }})</span>
            <el-tag v-if="!email.body_original || !email.body_original.trim()" type="info" size="small">HTML</el-tag>
          </div>
          <div class="split-header-right">
            <el-icon><Document /></el-icon>
            <span v-if="email.language_detected && email.language_detected !== 'zh' && email.language_detected !== 'unknown'">翻译 (中文)</span>
            <span v-else>内容预览</span>
            <el-tag v-if="!email.is_translated && email.language_detected && email.language_detected !== 'zh' && email.language_detected !== 'unknown'" type="warning" size="small">未翻译</el-tag>
          </div>
        </div>

        <div class="split-body">
          <!-- 左侧原文 -->
          <div
            class="split-pane original-pane"
            ref="originalPane"
            @scroll="handleOriginalScroll"
            @contextmenu.prevent="handleBodyContextMenu"
          >
            <!-- 优先显示纯文本，否则显示 HTML 渲染 -->
            <div class="pane-content" v-if="email.body_original && email.body_original.trim()">
              {{ email.body_original }}
            </div>
            <div class="pane-content html-content" v-else-if="email.body_html" v-html="sanitizeHtml(email.body_html)">
            </div>
            <div class="pane-content empty-content" v-else>
              (无文本内容)
            </div>
          </div>

          <!-- 分隔线 -->
          <div class="split-divider"></div>

          <!-- 右侧翻译/预览 -->
          <div
            class="split-pane translated-pane"
            ref="translatedPane"
            @scroll="handleTranslatedScroll"
            @contextmenu.prevent="handleBodyContextMenu"
          >
            <!-- 中文邮件或未识别语言：右侧显示原文 -->
            <div class="pane-content" v-if="!email.language_detected || email.language_detected === 'zh' || email.language_detected === 'unknown'">
              <template v-if="email.body_original && email.body_original.trim()">
                {{ email.body_original }}
              </template>
              <div class="html-content" v-else-if="email.body_html" v-html="sanitizeHtml(email.body_html)"></div>
              <template v-else>(无文本内容)</template>
            </div>
            <!-- 非中文邮件：显示翻译 -->
            <div class="pane-content" v-else-if="email.body_translated">
              {{ email.body_translated }}
              <div class="retranslate-hint">
                <el-button
                  type="primary"
                  text
                  size="small"
                  @click="retranslateEmail"
                  :loading="translating"
                >
                  <el-icon><RefreshRight /></el-icon>
                  重新翻译
                </el-button>
              </div>
            </div>
            <div class="pane-placeholder" v-else>
              <el-icon :size="32"><DocumentCopy /></el-icon>
              <p>尚未翻译</p>
              <el-button type="primary" @click="translateEmail" :loading="translating">
                立即翻译
              </el-button>
            </div>
          </div>
        </div>

        <!-- HTML 原文切换（可选） -->
        <div class="html-toggle" v-if="email.body_html">
          <el-button text size="small" @click="showHtmlDialog = true">
            <el-icon><View /></el-icon>
            查看 HTML 原文
          </el-button>
        </div>
      </div>

      <!-- HTML 原文对话框 -->
      <el-dialog v-model="showHtmlDialog" title="HTML 原文" width="80%" top="5vh">
        <div class="body-html" v-html="sanitizeHtml(email.body_html)"></div>
      </el-dialog>

      <!-- AI 智能提取面板 -->
      <ExtractionPanel
        v-if="email.id"
        :email-id="email.id"
        @event-created="handleEventCreated"
      />

      <!-- 邮件线程区域 -->
      <div class="thread-section" v-if="threadEmails.length > 1">
        <div class="section-header">
          <el-icon><ChatLineSquare /></el-icon>
          <span>对话线程 ({{ threadEmails.length }} 封)</span>
        </div>
        <div class="thread-list">
          <div
            v-for="threadEmail in threadEmails"
            :key="threadEmail.id"
            class="thread-item"
            :class="{ 'current': threadEmail.id === email.id }"
            @click="navigateToEmail(threadEmail.id)"
          >
            <div class="thread-avatar">
              <el-avatar :size="32" :style="{ backgroundColor: getAvatarColor(threadEmail.from_email) }">
                {{ getInitials(threadEmail.from_name || threadEmail.from_email) }}
              </el-avatar>
            </div>
            <div class="thread-content">
              <div class="thread-header">
                <span class="thread-sender">{{ threadEmail.from_name || threadEmail.from_email }}</span>
                <span class="thread-time">{{ formatDateTime(threadEmail.received_at) }}</span>
              </div>
              <div class="thread-subject">{{ threadEmail.subject_translated || threadEmail.subject_original }}</div>
              <div class="thread-preview">{{ getBodyPreview(threadEmail) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 回复区域 -->
      <div class="reply-section">
        <div class="reply-header">
          <h3>回复邮件</h3>
          <el-button type="primary" @click="showReplyDialog = true">
            撰写回复
          </el-button>
        </div>
      </div>
    </div>

    <!-- 回复对话框 -->
    <el-dialog
      v-model="showReplyDialog"
      title="回复邮件"
      width="75%"
      top="5vh"
      :close-on-click-modal="false"
    >
      <div class="reply-dialog-content">
        <!-- 收件人和抄送 - 标签式 -->
        <div class="reply-recipients-tags">
          <!-- 收件人 -->
          <div class="recipient-row">
            <label>收件人：</label>
            <div class="tags-container">
              <el-tag
                v-for="(addr, index) in toList"
                :key="'to-' + index"
                closable
                size="small"
                @close="removeToAddress(index)"
              >
                {{ addr }}
              </el-tag>
              <el-autocomplete
                v-model="toInput"
                :fetch-suggestions="queryContacts"
                placeholder="输入邮箱，回车添加"
                size="small"
                class="tag-input"
                @keyup.enter="addToAddress"
                @select="handleToSelect"
                clearable
              />
            </div>
          </div>

          <!-- 抄送 -->
          <div class="recipient-row">
            <label>抄送：</label>
            <div class="tags-container">
              <el-tag
                v-for="(addr, index) in ccList"
                :key="'cc-' + index"
                closable
                type="info"
                size="small"
                @close="removeCcAddress(index)"
              >
                {{ addr }}
              </el-tag>
              <el-autocomplete
                v-model="ccInput"
                :fetch-suggestions="queryContacts"
                placeholder="输入邮箱，回车添加"
                size="small"
                class="tag-input"
                @keyup.enter="addCcAddress"
                @select="handleCcSelect"
                clearable
              />
            </div>
          </div>

          <!-- 主题 -->
          <div class="recipient-row subject-row">
            <label>主题：</label>
            <el-input v-model="replyForm.subject" placeholder="邮件主题" size="small" />
          </div>
        </div>

        <div class="reply-body-grid">
          <div class="reply-input">
            <div class="section-label">
              中文内容
              <el-select v-model="replyForm.target_language" size="small" style="margin-left: 12px; width: 100px;">
                <el-option label="英语" value="en" />
                <el-option label="日语" value="ja" />
                <el-option label="韩语" value="ko" />
                <el-option label="德语" value="de" />
                <el-option label="法语" value="fr" />
              </el-select>
            </div>
            <el-input
              v-model="replyForm.body_chinese"
              type="textarea"
              :rows="10"
              placeholder="请输入中文回复内容..."
            />
            <div class="signature-selector">
              <span class="signature-label">签名：</span>
              <el-select
                v-model="replyForm.signature_id"
                size="small"
                placeholder="选择签名"
                clearable
                style="width: 150px;"
              >
                <el-option label="不使用签名" value="" />
                <el-option
                  v-for="sig in signatures"
                  :key="sig.id"
                  :label="sig.name"
                  :value="sig.id"
                />
              </el-select>
              <el-button
                v-if="replyForm.signature_id"
                text
                size="small"
                @click="previewSignature"
              >
                预览
              </el-button>
            </div>
          </div>

          <div class="reply-preview">
            <div class="section-label">
              翻译预览 ({{ getLanguageName(replyForm.target_language) }})
              <el-button size="small" type="primary" @click="translateReply" :loading="translating">
                翻译
              </el-button>
            </div>
            <el-input
              v-model="replyForm.body_translated"
              type="textarea"
              :rows="10"
              placeholder="点击翻译按钮生成译文..."
            />
            <div class="signature-preview-box" v-if="selectedSignature">
              <div class="signature-preview-label">签名预览：</div>
              <div class="signature-preview-content">{{ selectedSignature.content_translated || selectedSignature.content_chinese }}</div>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showReplyDialog = false">取消</el-button>
        <el-button @click="saveDraft">保存草稿</el-button>
        <el-button type="primary" @click="submitReply" :loading="submitting">
          发送
        </el-button>
      </template>
    </el-dialog>

    <!-- 标签选择器 -->
    <LabelSelector
      v-model="showLabelSelector"
      :email-id="email?.id"
      :current-labels="email?.labels || []"
      @saved="handleLabelsSaved"
    />

    <!-- 邮件正文右键菜单 -->
    <ContextMenu
      :visible="bodyContextMenu.state.visible"
      :x="bodyContextMenu.state.x"
      :y="bodyContextMenu.state.y"
      :items="bodyContextMenuItems"
      @select="handleBodyMenuSelect"
      @close="bodyContextMenu.hide()"
    />

    <!-- 附件右键菜单 -->
    <ContextMenu
      :visible="attachmentContextMenu.state.visible"
      :x="attachmentContextMenu.state.x"
      :y="attachmentContextMenu.state.y"
      :items="attachmentContextMenuItems"
      @select="handleAttachmentMenuSelect"
      @close="attachmentContextMenu.hide()"
    />

    <!-- 发件人右键菜单 -->
    <ContextMenu
      :visible="senderContextMenu.state.visible"
      :x="senderContextMenu.state.x"
      :y="senderContextMenu.state.y"
      :items="senderContextMenuItems"
      @select="handleSenderMenuSelect"
      @close="senderContextMenu.hide()"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Back, ChatLineSquare, Right, Delete, Star,
  Printer, Paperclip, Document, Download, InfoFilled, DocumentCopy, View, ArrowDown, CollectionTag,
  CopyDocument, Refresh, RefreshRight, Search, Link, Message, Loading
} from '@element-plus/icons-vue'
import LabelSelector from '@/components/LabelSelector.vue'
import ExtractionPanel from '@/components/ExtractionPanel.vue'
import ContextMenu from '@/components/ContextMenu.vue'
import api, { getStorageKey } from '@/api'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import DOMPurify from 'dompurify'
import { useUserStore } from '@/stores/user'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useContextMenu } from '@/composables/useContextMenu'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const email = ref(null)
const loading = ref(false)
const showReplyDialog = ref(false)
const showHtmlDialog = ref(false)
const translating = ref(false)
const submitting = ref(false)
const downloadingAttachments = ref({})  // 跟踪每个附件的下载状态
const threadEmails = ref([])  // 邮件线程
const signatures = ref([])  // 签名列表

// 右键菜单
const bodyContextMenu = useContextMenu()
const attachmentContextMenu = useContextMenu()
const senderContextMenu = useContextMenu()
const selectedText = ref('')  // 选中的文本
const translatedSelection = ref('')  // 选中文本的翻译
const translatingSelection = ref(false)  // 是否正在翻译选中文本
const showLabelSelector = ref(false)  // 标签选择器可见性
let isUnmounted = false  // 组件卸载状态标志

// 组件卸载时标记状态，让翻译请求在后台继续运行
onUnmounted(() => {
  isUnmounted = true  // 标记已卸载，防止异步回调修改状态
  // 注意：不取消翻译请求，让它在后台继续运行
  // 翻译完成后数据会保存到后端，下次查看时直接显示结果
  // 移除翻译事件监听
  window.removeEventListener('email-translated', handleEmailTranslated)
  window.removeEventListener('email-translation-failed', handleEmailTranslationFailed)
})

// 邮件详情快捷键
const { setEnabled: setShortcutsEnabled } = useKeyboardShortcuts([
  {
    key: 'r',
    handler: () => {
      if (!showReplyDialog.value) {
        handleReply()
      }
    }
  },
  {
    key: 'a',
    handler: () => {
      if (!showReplyDialog.value) {
        handleReplyAll()
      }
    }
  },
  {
    key: 'f',
    handler: () => {
      if (!showReplyDialog.value) {
        handleForward()
      }
    }
  },
  {
    key: 's',
    handler: () => {
      if (!showReplyDialog.value) {
        handleFlag()
      }
    }
  },
  {
    key: 'd',
    handler: () => {
      if (!showReplyDialog.value) {
        handleDelete()
      }
    }
  },
  {
    key: 'u',
    handler: async () => {
      if (!showReplyDialog.value && email.value) {
        try {
          await api.markAsUnread(email.value.id)
          email.value.is_read = false
          ElMessage.success('已标记为未读')
        } catch (e) {
          ElMessage.error('操作失败')
        }
      }
    }
  },
  {
    key: 'm',
    handler: async () => {
      if (!showReplyDialog.value && email.value) {
        try {
          await api.markAsRead(email.value.id)
          email.value.is_read = true
          ElMessage.success('已标记为已读')
        } catch (e) {
          ElMessage.error('操作失败')
        }
      }
    }
  },
  {
    key: 'Escape',
    handler: () => {
      if (showReplyDialog.value) {
        showReplyDialog.value = false
      } else if (showHtmlDialog.value) {
        showHtmlDialog.value = false
      } else {
        router.push('/emails')
      }
    }
  },
  {
    key: 'j',
    handler: () => {
      // 下一封（线程中）
      if (!showReplyDialog.value && threadEmails.value.length > 1) {
        const currentIndex = threadEmails.value.findIndex(e => e.id === email.value?.id)
        if (currentIndex < threadEmails.value.length - 1) {
          navigateToEmail(threadEmails.value[currentIndex + 1].id)
        }
      }
    }
  },
  {
    key: 'k',
    handler: () => {
      // 上一封（线程中）
      if (!showReplyDialog.value && threadEmails.value.length > 1) {
        const currentIndex = threadEmails.value.findIndex(e => e.id === email.value?.id)
        if (currentIndex > 0) {
          navigateToEmail(threadEmails.value[currentIndex - 1].id)
        }
      }
    }
  },
  {
    key: 'Enter',
    ctrl: true,
    handler: () => {
      // Ctrl+Enter 发送回复
      if (showReplyDialog.value && !submitting.value) {
        submitReply()
      }
    }
  },
  {
    key: 'l',
    handler: () => {
      // 打开标签选择器
      if (!showReplyDialog.value && email.value) {
        openLabelSelector()
      }
    }
  }
])

// 对话框打开时禁用部分快捷键
watch(showReplyDialog, (val) => {
  // 不完全禁用，只是在 handler 中检查状态
})

// === 右键菜单 ===

// 邮件正文右键菜单项
const bodyContextMenuItems = computed(() => {
  const hasSelection = selectedText.value.length > 0
  return [
    {
      key: 'copy',
      icon: CopyDocument,
      label: '复制',
      disabled: !hasSelection
    },
    {
      key: 'translate-selection',
      icon: Refresh,
      label: translatingSelection.value ? '翻译中...' : '翻译选中文本',
      disabled: !hasSelection || translatingSelection.value
    },
    { divider: true },
    {
      key: 'search',
      icon: Search,
      label: '搜索',
      disabled: !hasSelection
    }
  ]
})

// 附件右键菜单项
const attachmentContextMenuItems = computed(() => {
  const attachment = attachmentContextMenu.state.data
  if (!attachment) return []

  return [
    {
      key: 'download',
      icon: Download,
      label: '下载'
    },
    {
      key: 'preview',
      icon: View,
      label: '预览',
      disabled: !canPreviewAttachment(attachment)
    }
  ]
})

// 发件人右键菜单项
const senderContextMenuItems = computed(() => {
  const emailAddr = senderContextMenu.state.data
  if (!emailAddr) return []

  return [
    {
      key: 'send-email',
      icon: Message,
      label: '发送邮件'
    },
    {
      key: 'copy-email',
      icon: CopyDocument,
      label: '复制邮箱地址'
    }
  ]
})

// 检查附件是否可预览
function canPreviewAttachment(attachment) {
  if (!attachment) return false
  const previewableTypes = ['image/', 'text/', 'application/pdf']
  return previewableTypes.some(type => attachment.content_type?.startsWith(type))
}

// 邮件正文右键菜单处理
function handleBodyContextMenu(event) {
  // 获取选中的文本
  const selection = window.getSelection()
  selectedText.value = selection ? selection.toString().trim() : ''
  translatedSelection.value = ''
  bodyContextMenu.show(event)
}

// 邮件正文右键菜单选项处理
async function handleBodyMenuSelect(key) {
  switch (key) {
    case 'copy':
      await copyToClipboard(selectedText.value)
      break
    case 'translate-selection':
      await translateSelectedText()
      break
    case 'search':
      searchSelectedText()
      break
  }
}

// 复制到剪贴板
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (e) {
    console.error('Copy failed:', e)
    ElMessage.error('复制失败')
  }
}

// 翻译选中文本
async function translateSelectedText() {
  if (!selectedText.value) return

  translatingSelection.value = true
  try {
    const result = await api.translate(
      selectedText.value,
      'zh',  // 翻译为中文
      email.value?.supplier_id
    )
    translatedSelection.value = result.translated_text

    // 显示翻译结果
    ElMessageBox.alert(
      `<div style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">
        <p style="color: #909399; margin-bottom: 8px;">原文：</p>
        <p style="margin-bottom: 16px;">${selectedText.value}</p>
        <p style="color: #909399; margin-bottom: 8px;">翻译：</p>
        <p>${result.translated_text}</p>
      </div>`,
      '翻译结果',
      {
        dangerouslyUseHTMLString: true,
        confirmButtonText: '复制翻译',
        showCancelButton: true,
        cancelButtonText: '关闭',
        callback: (action) => {
          if (action === 'confirm') {
            copyToClipboard(result.translated_text)
          }
        }
      }
    )
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translatingSelection.value = false
  }
}

// 搜索选中文本
function searchSelectedText() {
  if (!selectedText.value) return
  // 在新标签页打开搜索
  window.open(`https://www.google.com/search?q=${encodeURIComponent(selectedText.value)}`, '_blank')
}

// 附件右键菜单处理
function handleAttachmentContextMenu(event, attachment) {
  attachmentContextMenu.show(event, attachment)
}

// 附件右键菜单选项处理
async function handleAttachmentMenuSelect(key) {
  const attachment = attachmentContextMenu.state.data
  if (!attachment) return

  switch (key) {
    case 'download':
      downloadAttachment(attachment)
      break
    case 'preview':
      previewAttachment(attachment)
      break
  }
}

// 预览附件
function previewAttachment(attachment) {
  const url = api.getAttachmentUrl(email.value.id, attachment.id)
  window.open(url, '_blank')
}

// 发件人右键菜单处理
function handleSenderContextMenu(event, emailAddr) {
  senderContextMenu.show(event, emailAddr)
}

// 发件人右键菜单选项处理
async function handleSenderMenuSelect(key) {
  const emailAddr = senderContextMenu.state.data
  if (!emailAddr) return

  switch (key) {
    case 'send-email':
      // TODO: 打开撰写邮件，收件人为该地址
      ElMessage.info('功能开发中')
      break
    case 'copy-email':
      await copyToClipboard(emailAddr)
      break
  }
}

// Split View 滚动同步
const originalPane = ref(null)
const translatedPane = ref(null)
let isScrollingSynced = false  // 防止无限循环

function handleOriginalScroll(e) {
  if (isScrollingSynced) return
  if (!translatedPane.value) return

  isScrollingSynced = true
  const sourceEl = e.target
  const targetEl = translatedPane.value

  // 按比例同步滚动
  const scrollPercentage = sourceEl.scrollTop / (sourceEl.scrollHeight - sourceEl.clientHeight)
  targetEl.scrollTop = scrollPercentage * (targetEl.scrollHeight - targetEl.clientHeight)

  setTimeout(() => { isScrollingSynced = false }, 50)
}

function handleTranslatedScroll(e) {
  if (isScrollingSynced) return
  if (!originalPane.value) return

  isScrollingSynced = true
  const sourceEl = e.target
  const targetEl = originalPane.value

  // 按比例同步滚动
  const scrollPercentage = sourceEl.scrollTop / (sourceEl.scrollHeight - sourceEl.clientHeight)
  targetEl.scrollTop = scrollPercentage * (targetEl.scrollHeight - targetEl.clientHeight)

  setTimeout(() => { isScrollingSynced = false }, 50)
}

const replyForm = reactive({
  to: '',
  cc: '',
  subject: '',
  body_chinese: '',
  body_translated: '',
  target_language: 'en',
  signature_id: ''
})

// 标签式邮箱输入
const toList = ref([])      // 收件人列表
const ccList = ref([])      // 抄送列表
const toInput = ref('')     // 收件人输入框
const ccInput = ref('')     // 抄送输入框
const contactHistory = ref([])  // 历史联系人

// 加载历史联系人（带缓存和失败降级）
async function loadContactHistory() {
  // 先尝试从缓存读取
  const cacheKey = 'contactHistory'
  try {
    const cached = localStorage.getItem(cacheKey)
    if (cached) {
      contactHistory.value = JSON.parse(cached)
    }
  } catch (e) {
    // 缓存读取失败，忽略
  }

  try {
    const result = await api.getContacts()
    contactHistory.value = result.contacts || []
    // 成功后更新缓存
    try {
      localStorage.setItem(cacheKey, JSON.stringify(contactHistory.value))
    } catch (e) {
      // 缓存写入失败，忽略
    }
  } catch (e) {
    console.error('Failed to load contacts:', e)
    // 如果没有缓存数据，显示提示
    if (contactHistory.value.length === 0) {
      ElMessage.info('联系人加载失败，可手动输入邮箱')
    }
  }
}

// 查询联系人（自动补全）
function queryContacts(query, cb) {
  const results = query
    ? contactHistory.value.filter(c =>
        c.email.toLowerCase().includes(query.toLowerCase()) ||
        (c.name && c.name.toLowerCase().includes(query.toLowerCase()))
      )
    : contactHistory.value.slice(0, 10)

  cb(results.map(c => ({
    value: c.email,
    label: c.name ? `${c.name} <${c.email}>` : c.email
  })))
}

// 检查邮箱是否已存在于列表中（不区分大小写）
function emailExistsIn(email, list) {
  return list.some(e => e.toLowerCase() === email.toLowerCase())
}

// 添加收件人
function addToAddress() {
  const addr = toInput.value.trim()
  if (!addr) return

  if (!isValidEmail(addr)) {
    ElMessage.warning('邮箱格式不正确')
    return
  }
  if (emailExistsIn(addr, toList.value)) {
    ElMessage.warning('该邮箱已在收件人列表中')
    return
  }
  toList.value.push(addr)
  toInput.value = ''
}

// 选择收件人（从自动补全）
function handleToSelect(item) {
  if (!item.value) return

  if (emailExistsIn(item.value, toList.value)) {
    ElMessage.warning('该邮箱已在收件人列表中')
  } else {
    toList.value.push(item.value)
  }
  toInput.value = ''
}

// 移除收件人
function removeToAddress(index) {
  toList.value.splice(index, 1)
}

// 添加抄送
function addCcAddress() {
  const addr = ccInput.value.trim()
  if (!addr) return

  if (!isValidEmail(addr)) {
    ElMessage.warning('邮箱格式不正确')
    return
  }
  // 检查是否已在收件人中
  if (emailExistsIn(addr, toList.value)) {
    ElMessage.warning('该邮箱已在收件人列表中')
    return
  }
  if (emailExistsIn(addr, ccList.value)) {
    ElMessage.warning('该邮箱已在抄送列表中')
    return
  }
  ccList.value.push(addr)
  ccInput.value = ''
}

// 选择抄送（从自动补全）
function handleCcSelect(item) {
  if (!item.value) return

  if (emailExistsIn(item.value, toList.value)) {
    ElMessage.warning('该邮箱已在收件人列表中')
  } else if (emailExistsIn(item.value, ccList.value)) {
    ElMessage.warning('该邮箱已在抄送列表中')
  } else {
    ccList.value.push(item.value)
  }
  ccInput.value = ''
}

// 移除抄送
function removeCcAddress(index) {
  ccList.value.splice(index, 1)
}

// 验证邮箱格式（更严格的RFC 5322兼容验证）
function isValidEmail(email) {
  // 要求：本地部分 @ 域名部分，域名至少有一个点且结尾至少2字符
  const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/
  return emailRegex.test(email)
}

// 选中的签名
const selectedSignature = computed(() => {
  if (!replyForm.signature_id) return null
  return signatures.value.find(s => s.id === replyForm.signature_id)
})

// 加载签名列表
async function loadSignatures() {
  try {
    signatures.value = await api.getSignatures()
    // 自动选择默认签名
    const defaultSig = signatures.value.find(s => s.is_default)
    if (defaultSig) {
      replyForm.signature_id = defaultSig.id
    }
  } catch (e) {
    console.error('Failed to load signatures:', e)
  }
}

function previewSignature() {
  if (!selectedSignature.value) return
  ElMessageBox.alert(
    `<div style="white-space: pre-wrap;">
      <div style="margin-bottom: 12px;">
        <strong>中文：</strong><br/>
        ${selectedSignature.value.content_chinese || '(无)'}
      </div>
      <div>
        <strong>翻译 (${getLanguageName(selectedSignature.value.target_language)})：</strong><br/>
        ${selectedSignature.value.content_translated || '(无)'}
      </div>
    </div>`,
    '签名预览',
    {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '确定'
    }
  )
}

// 处理翻译完成事件
function handleEmailTranslated(event) {
  const detail = event.detail
  if (!detail?.email_id || !email.value || email.value.id !== detail.email_id) return

  // 直接使用 WebSocket 推送的数据（如果有的话）
  if (detail.body_translated !== undefined) {
    email.value.subject_translated = detail.subject_translated
    email.value.body_translated = detail.body_translated
    email.value.is_translated = detail.is_translated
    email.value.translation_status = detail.translation_status
    console.log(`[EmailDetail] Updated translation for email ${detail.email_id} from WS data`)
  }
}

function handleEmailTranslationFailed(event) {
  const detail = event.detail
  if (!detail?.email_id || !email.value || email.value.id !== detail.email_id) return

  email.value.translation_status = 'failed'
  console.log(`[EmailDetail] Translation failed for email ${detail.email_id}`)
}

onMounted(() => {
  loadEmail()
  loadSignatures()
  loadContactHistory()
  // 监听翻译事件
  window.addEventListener('email-translated', handleEmailTranslated)
  window.addEventListener('email-translation-failed', handleEmailTranslationFailed)
})

async function loadEmail() {
  const id = route.params.id
  loading.value = true

  try {
    email.value = await api.getEmail(id)

    // 自动标记为已读
    if (!email.value.is_read) {
      try {
        await api.markAsRead(id)
        email.value.is_read = true
      } catch (e) {
        console.error('Failed to mark as read:', e)
      }
    }

    // 设置目标语言
    if (email.value.language_detected && email.value.language_detected !== 'zh') {
      replyForm.target_language = email.value.language_detected
    }

    // 如果URL带有reply参数，自动打开回复对话框
    if (route.query.reply === 'true') {
      initReplyForm(false)
      showReplyDialog.value = true
    } else if (route.query.reply === 'all') {
      initReplyForm(true)
      showReplyDialog.value = true
    } else if (route.query.forward === 'true') {
      handleForward()
    }

    // 加载邮件线程
    if (email.value.thread_id) {
      loadThread(email.value.thread_id)
    }
  } catch (e) {
    console.error('Failed to load email:', e)
    ElMessage.error('加载邮件失败')
  } finally {
    loading.value = false
  }
}

async function loadThread(threadId) {
  try {
    const result = await api.getEmailThread(threadId)
    threadEmails.value = result.emails || []
  } catch (e) {
    console.error('Failed to load thread:', e)
    threadEmails.value = []
  }
}

function navigateToEmail(emailId) {
  if (emailId !== email.value.id) {
    router.push(`/emails/${emailId}`)
  }
}

function formatDateTime(date) {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

function getBodyPreview(email) {
  const body = email.body_translated || email.body_original || ''
  return body.substring(0, 100).replace(/\n/g, ' ').trim() + (body.length > 100 ? '...' : '')
}

function handleReply() {
  initReplyForm(false)
  showReplyDialog.value = true
}

function handleReplyAll() {
  initReplyForm(true)
  showReplyDialog.value = true
}

// 初始化回复表单
function initReplyForm(isReplyAll = false) {
  if (!email.value) return

  const currentUserEmail = localStorage.getItem(getStorageKey('email')) || ''

  // 收件人：原邮件发件人（优先使用 reply_to）
  const toAddr = email.value.reply_to || email.value.from_email || ''
  toList.value = toAddr ? [toAddr] : []
  toInput.value = ''

  // 主题
  const originalSubject = email.value.subject_original || ''
  replyForm.subject = originalSubject.startsWith('Re:') ? originalSubject : `Re: ${originalSubject}`

  if (isReplyAll) {
    // 全部回复：抄送包含原邮件的其他收件人和原抄送人（排除自己和发件人）
    const ccAddrs = []

    // 添加原邮件的其他收件人（排除自己）
    if (email.value.to_email) {
      const toAddresses = email.value.to_email.split(',').map(e => e.trim()).filter(e => e)
      for (const addr of toAddresses) {
        const emailAddr = extractEmail(addr)
        if (emailAddr &&
            emailAddr.toLowerCase() !== currentUserEmail.toLowerCase() &&
            emailAddr.toLowerCase() !== toAddr.toLowerCase()) {
          ccAddrs.push(emailAddr)
        }
      }
    }

    // 添加原邮件的抄送人（排除自己）
    if (email.value.cc_email) {
      const ccAddresses = email.value.cc_email.split(',').map(e => e.trim()).filter(e => e)
      for (const addr of ccAddresses) {
        const emailAddr = extractEmail(addr)
        if (emailAddr &&
            emailAddr.toLowerCase() !== currentUserEmail.toLowerCase() &&
            !ccAddrs.some(cc => cc.toLowerCase() === emailAddr.toLowerCase())) {
          ccAddrs.push(emailAddr)
        }
      }
    }

    ccList.value = ccAddrs
  } else {
    // 普通回复：不抄送
    ccList.value = []
  }
  ccInput.value = ''

  // 清空正文
  replyForm.body_chinese = ''
  replyForm.body_translated = ''
}

// 从地址字符串中提取邮箱（支持多种格式）
// 支持: "Name" <email>, Name <email>, <email>, email
function extractEmail(addr) {
  if (!addr) return null
  const trimmed = addr.trim()

  // 尝试匹配 <email> 格式（包括带引号的名字）
  const match = trimmed.match(/<([^>]+)>/)
  if (match) {
    const email = match[1].trim()
    return isValidEmail(email) ? email : null
  }

  // 如果没有 <> 格式，检查是否是纯邮箱
  if (isValidEmail(trimmed)) {
    return trimmed
  }

  return null
}

function handleForward() {
  if (!email.value) return

  // 清空收件人和抄送人（用户自行添加）
  toList.value = []
  toInput.value = ''
  ccList.value = []
  ccInput.value = ''

  // 主题
  const originalSubject = email.value.subject_original || ''
  replyForm.subject = originalSubject.startsWith('Fwd:') ? originalSubject : `Fwd: ${originalSubject}`

  // 构建转发正文 - 使用中文版本（如果有翻译）
  const forwardHeader = `\n\n---------- 转发的邮件 ----------\n发件人: ${email.value.from_name || ''} <${email.value.from_email || ''}>\n日期: ${formatDateTime(email.value.received_at)}\n主题: ${email.value.subject_translated || email.value.subject_original || ''}\n收件人: ${email.value.to_email || ''}\n`

  // 使用翻译后的正文（如果有）
  const body = email.value.body_translated || email.value.body_original || ''
  replyForm.body_chinese = forwardHeader + '\n' + body

  // 清空翻译内容（用户需要重新翻译）
  replyForm.body_translated = ''

  showReplyDialog.value = true
}

// AI 提取 - 日程创建成功回调
function handleEventCreated() {
  ElMessage.success('日程已创建，可在日历中查看')
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除这封邮件吗？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await api.deleteEmail(email.value.id)
    ElMessage.success('邮件已删除')
    router.push('/emails')
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete email:', e)
      ElMessage.error('删除失败')
    }
  }
}

async function handleFlag() {
  if (!email.value) return

  const originalState = email.value.is_flagged
  email.value.is_flagged = !email.value.is_flagged

  try {
    if (email.value.is_flagged) {
      await api.flagEmail(email.value.id)
      ElMessage.success('已标记')
    } else {
      await api.unflagEmail(email.value.id)
      ElMessage.success('已取消标记')
    }
  } catch (e) {
    email.value.is_flagged = originalState
    console.error('Failed to toggle flag:', e)
    ElMessage.error('操作失败')
  }
}

// 标签相关函数
function openLabelSelector() {
  showLabelSelector.value = true
}

function handleLabelsSaved(labels) {
  if (email.value) {
    email.value.labels = labels
  }
}

async function removeLabel(labelId) {
  if (!email.value) return

  try {
    await api.removeLabelFromEmail(email.value.id, labelId)
    email.value.labels = (email.value.labels || []).filter(l => l.id !== labelId)
    ElMessage.success('标签已移除')
  } catch (e) {
    ElMessage.error('移除标签失败')
  }
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

function handlePrint() {
  window.print()
}

async function handleExport(command) {
  if (command === 'eml') {
    try {
      const subject = email.value.subject_original || 'email'
      const filename = `${subject.substring(0, 50).replace(/[/\\:*?"<>|]/g, '_')}.eml`
      await api.exportEmail(email.value.id, filename)
      ElMessage.success('邮件导出成功')
    } catch (e) {
      console.error('Export failed:', e)
      ElMessage.error('导出失败')
    }
  }
}

async function downloadAttachment(att) {
  downloadingAttachments.value[att.id] = true
  try {
    await api.downloadAttachment(email.value.id, att.id, att.filename)
    ElMessage.success(`附件 "${att.filename}" 下载成功`)
  } catch (e) {
    console.error('Download attachment failed:', e)
    ElMessage.error('下载附件失败')
  } finally {
    downloadingAttachments.value[att.id] = false
  }
}

async function downloadAllAttachments() {
  if (!email.value?.attachments?.length) return

  for (const att of email.value.attachments) {
    await downloadAttachment(att)
  }
}

async function translateEmail(force = false) {
  // 立即显示提交状态
  translating.value = true

  // 保存当前邮件 ID，用于后续验证
  const currentEmailId = email.value.id

  // 发起翻译请求（不等待完成）
  api.translateEmail(currentEmailId, { force })
    .then(translatedEmail => {
      // 翻译完成后更新（如果用户还在此页面且是同一封邮件）
      if (!isUnmounted && email.value.id === currentEmailId) {
        // 只更新翻译相关字段，避免覆盖用户可能正在编辑的其他状态
        email.value.subject_translated = translatedEmail.subject_translated
        email.value.body_translated = translatedEmail.body_translated
        email.value.is_translated = translatedEmail.is_translated
        email.value.translation_status = translatedEmail.translation_status
        ElMessage.success(force ? '重新翻译完成' : '翻译完成')
      } else {
        console.log('Translation completed in background, data saved to server')
      }
      // 触发刷新信号（更新列表中该邮件的状态）
      userStore.triggerEmailRefresh()
    })
    .catch(e => {
      // 组件卸载后不显示错误
      if (isUnmounted) return
      console.error('Translation failed:', e)
      ElMessage.error('翻译失败: ' + (e.response?.data?.detail || e.message))
    })

  // 立即提示用户并释放 UI
  ElMessage.info(force ? '重新翻译任务已提交，可继续操作' : '翻译任务已提交，可继续操作')
  translating.value = false
}

// 强制重新翻译（清除缓存后重新翻译）
async function retranslateEmail() {
  await ElMessageBox.confirm(
    '确定要重新翻译吗？这将清除已有翻译并重新生成。',
    '确认重新翻译',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    translateEmail(true)
  }).catch(() => {
    // 用户取消
  })
}

async function translateReply() {
  if (!replyForm.body_chinese.trim()) {
    ElMessage.warning('请先输入中文内容')
    return
  }

  translating.value = true
  try {
    const result = await api.translateReply(
      replyForm.body_chinese,
      replyForm.target_language,
      email.value.supplier_id,
      email.value.body_original?.substring(0, 500)
    )
    replyForm.body_translated = result.translated_text
    ElMessage.success('翻译完成')
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

// 获取带签名的内容
function getContentWithSignature(content, isTranslated = false) {
  if (!selectedSignature.value) return content
  const signatureContent = isTranslated
    ? (selectedSignature.value.content_translated || selectedSignature.value.content_chinese)
    : selectedSignature.value.content_chinese
  if (!signatureContent) return content
  return content + '\n\n--\n' + signatureContent
}

async function saveDraft() {
  if (!replyForm.body_chinese.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }

  try {
    await api.createDraft({
      reply_to_email_id: email.value.id,
      to: toList.value.join(', '),
      cc: ccList.value.length > 0 ? ccList.value.join(', ') : null,
      subject: replyForm.subject.trim(),
      body_chinese: getContentWithSignature(replyForm.body_chinese, false),
      body_translated: getContentWithSignature(replyForm.body_translated, true),
      target_language: replyForm.target_language
    })
    ElMessage.success('草稿已保存')
    showReplyDialog.value = false
  } catch (e) {
    console.error('Failed to save draft:', e)
    ElMessage.error('保存草稿失败')
  }
}

async function submitReply() {
  if (toList.value.length === 0) {
    ElMessage.warning('请输入收件人')
    return
  }

  if (!replyForm.body_chinese.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }

  if (!replyForm.body_translated.trim()) {
    ElMessage.warning('请先翻译内容')
    return
  }

  submitting.value = true
  try {
    const draft = await api.createDraft({
      reply_to_email_id: email.value.id,
      to: toList.value.join(', '),
      cc: ccList.value.length > 0 ? ccList.value.join(', ') : null,
      subject: replyForm.subject.trim(),
      body_chinese: getContentWithSignature(replyForm.body_chinese, false),
      body_translated: getContentWithSignature(replyForm.body_translated, true),
      target_language: replyForm.target_language
    })

    const result = await api.submitDraft(draft.id)

    if (result.status === 'sent') {
      ElMessage.success('邮件已发送')
    } else if (result.status === 'pending') {
      ElMessage.info(`邮件已提交审批 (触发规则: ${result.rule})`)
    }

    showReplyDialog.value = false
    replyForm.body_chinese = ''
    replyForm.body_translated = ''
  } catch (e) {
    console.error('Failed to submit reply:', e)
    ElMessage.error('发送失败')
  } finally {
    submitting.value = false
  }
}

function formatDate(date) {
  return dayjs(date).format('YYYY年MM月DD日')
}

function formatTime(date) {
  return dayjs(date).format('HH:mm')
}

function formatAddressList(addressStr) {
  if (!addressStr) return ''
  return addressStr
    .replace(/\r\n/g, ' ')
    .replace(/\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(',')
    .map(addr => addr.trim())
    .filter(addr => addr)
    .join('; ')
}

function getLanguageName(lang) {
  if (!lang || lang === 'unknown') return '🇨🇳 中文'
  const names = {
    en: '🇬🇧 英语',
    ja: '🇯🇵 日语',
    ko: '🇰🇷 韩语',
    zh: '🇨🇳 中文',
    de: '🇩🇪 德语',
    fr: '🇫🇷 法语',
    es: '🇪🇸 西班牙语',
    pt: '🇵🇹 葡萄牙语',
    ru: '🇷🇺 俄语',
    it: '🇮🇹 意大利语',
    nl: '🇳🇱 荷兰语',
    vi: '🇻🇳 越南语',
    th: '🇹🇭 泰语',
    ar: '🇸🇦 阿拉伯语',
    tr: '🇹🇷 土耳其语',
    pl: '🇵🇱 波兰语',
    cs: '🇨🇿 捷克语',
    sv: '🇸🇪 瑞典语',
    da: '🇩🇰 丹麦语',
    fi: '🇫🇮 芬兰语',
    no: '🇳🇴 挪威语',
    id: '🇮🇩 印尼语',
    ms: '🇲🇾 马来语'
  }
  return names[lang] || `🌐 ${lang}`
}

function getInitials(name) {
  if (!name) return '?'
  const parts = name.split(/[@\s]+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.substring(0, 2).toUpperCase()
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

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i]
}

function sanitizeHtml(html) {
  if (!html) return ''

  // 先处理 cid: 图片，替换为占位符提示
  let processedHtml = html.replace(
    /<img[^>]*src=["']cid:[^"']+["'][^>]*>/gi,
    '<span style="display:inline-block;padding:4px 8px;background:#f5f5f5;border:1px solid #ddd;border-radius:4px;color:#999;font-size:12px;">[嵌入图片]</span>'
  )

  return DOMPurify.sanitize(processedHtml, {
    ALLOWED_TAGS: ['p', 'br', 'div', 'span', 'b', 'i', 'u', 'strong', 'em',
                   'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
                   'table', 'tr', 'td', 'th', 'thead', 'tbody', 'a', 'img',
                   'blockquote', 'pre', 'code', 'hr', 'font', 'center'],
    ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'style', 'class', 'color', 'size', 'face'],
    ALLOW_DATA_ATTR: false
  })
}
</script>

<style scoped>
.email-detail-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

/* 工具栏 */
.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #e8e8e8;
  background-color: #fafafa;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 内容区 */
.detail-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px 20px;
}

/* 主题区域 */
.email-subject-section {
  padding: 20px 0 12px;
  border-bottom: 1px solid #f0f0f0;
}

.email-subject {
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px;
  line-height: 1.4;
}

.email-labels {
  display: flex;
  gap: 8px;
}

/* 发件人区域 */
.sender-section {
  display: flex;
  align-items: flex-start;
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
}

.sender-info {
  flex: 1;
  margin-left: 12px;
}

.sender-primary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.sender-name {
  font-weight: 600;
  font-size: 15px;
  color: #1a1a1a;
}

.sender-email {
  font-size: 13px;
  color: #909399;
}

.clickable {
  cursor: pointer;
}

.clickable:hover {
  text-decoration: underline;
}

.recipient-info {
  font-size: 13px;
  color: #606266;
}

.recipient-row {
  margin-top: 4px;
}

.recipient-row .label {
  color: #909399;
  margin-right: 4px;
}

.recipient-row .value.cc,
.recipient-row .value.bcc {
  color: #909399;
}

.email-datetime {
  text-align: right;
  flex-shrink: 0;
}

.date-primary {
  font-size: 14px;
  color: #303133;
}

.date-secondary {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

/* 翻译提示 */
.translation-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin: 12px 0;
  background-color: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  font-size: 13px;
  color: #e6a23c;
}

.translation-notice.translating {
  background-color: #ecf5ff;
  border-color: #d9ecff;
  color: #409eff;
}

.translation-notice.failed {
  background-color: #fef0f0;
  border-color: #fde2e2;
  color: #f56c6c;
}

.translating-status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.translating-status-tag .el-icon {
  font-size: 12px;
}

/* 附件区域 */
.attachments-section {
  margin: 16px 0;
  padding: 12px 16px;
  background-color: #fafafa;
  border-radius: 4px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
  margin-bottom: 12px;
}

.attachments-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.attachment-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  min-width: 200px;
}

.attachment-card:hover {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.attachment-icon {
  color: #909399;
}

.attachment-info {
  flex: 1;
}

.attachment-name {
  font-size: 13px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}

.attachment-size {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

/* Split View 正文区域 */
.body-section.split-view {
  margin-top: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 400px;
}

.split-header {
  display: flex;
  background-color: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.split-header-left,
.split-header-right {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.split-header-left {
  border-right: 1px solid #e8e8e8;
  background-color: #fff9e6;
}

.split-header-right {
  background-color: #e6f7ff;
}

.split-body {
  display: flex;
  flex: 1;
  min-height: 300px;
}

.split-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 16px;
  min-width: 0;
}

.original-pane {
  background-color: #fffef0;
  border-right: none;
}

.translated-pane {
  background-color: #f0f9ff;
}

.split-divider {
  width: 4px;
  background: linear-gradient(to bottom, #e8e8e8 0%, #d0d0d0 50%, #e8e8e8 100%);
  cursor: col-resize;
  flex-shrink: 0;
}

.split-divider:hover {
  background: linear-gradient(to bottom, #409eff 0%, #79bbff 50%, #409eff 100%);
}

.pane-content {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  font-size: 14px;
  color: #303133;
}

.pane-content.html-content {
  white-space: normal;
}

.pane-content.html-content :deep(img) {
  max-width: 100%;
  height: auto;
}

.pane-content.html-content :deep(table) {
  border-collapse: collapse;
  max-width: 100%;
}

.pane-content.html-content :deep(td),
.pane-content.html-content :deep(th) {
  border: 1px solid #ddd;
  padding: 6px;
}

.pane-content.html-content :deep(a) {
  color: #409eff;
}

.pane-content.html-content :deep(blockquote) {
  border-left: 3px solid #ddd;
  padding-left: 12px;
  margin-left: 0;
  color: #666;
}

.pane-content.empty-content {
  color: #909399;
  font-style: italic;
}

.retranslate-hint {
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px dashed #dcdfe6;
  text-align: center;
}

.pane-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 12px;
}

.pane-placeholder p {
  margin: 0;
  font-size: 14px;
}

.html-toggle {
  padding: 8px 16px;
  border-top: 1px solid #e8e8e8;
  background-color: #fafafa;
  text-align: center;
}

.body-html {
  padding: 16px;
  background-color: #fafafa;
  border-radius: 4px;
  overflow: auto;
  max-height: 600px;
}

.body-html :deep(img) {
  max-width: 100%;
  height: auto;
}

.body-html :deep(table) {
  border-collapse: collapse;
  max-width: 100%;
}

.body-html :deep(td),
.body-html :deep(th) {
  border: 1px solid #ddd;
  padding: 8px;
}

.body-html :deep(a) {
  color: #409eff;
}

.body-html :deep(blockquote) {
  border-left: 3px solid #ddd;
  padding-left: 12px;
  margin-left: 0;
  color: #666;
}

/* 回复区域 */
.reply-section {
  margin-top: 24px;
  padding: 16px;
  background-color: #fafafa;
  border-radius: 4px;
}

.reply-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reply-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

/* 回复对话框 */
.reply-dialog-content {
  padding: 0 10px;
}

/* 标签式收件人输入 */
.reply-recipients-tags {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recipient-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.recipient-row label {
  width: 55px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
  text-align: right;
  padding-top: 5px;
}

.tags-container {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 6px;
  min-height: 32px;
  max-height: 120px;
  overflow-y: auto;
  padding: 4px 8px;
  background-color: var(--el-fill-color-light, #f5f7fa);
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 4px;
}

.tags-container:focus-within {
  border-color: #409eff;
}

.tags-container .el-tag {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-input {
  flex: 1;
  min-width: 150px;
}

.tag-input :deep(.el-input__wrapper) {
  box-shadow: none !important;
  background: transparent;
  padding: 0;
}

.tag-input :deep(.el-input__inner) {
  height: 24px;
  line-height: 24px;
}

.subject-row {
  align-items: center;
}

.subject-row .el-input {
  flex: 1;
}

.reply-body-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 8px;
}

.signature-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.signature-label {
  font-size: 13px;
  color: #606266;
}

.signature-preview-box {
  margin-top: 10px;
  padding: 10px 12px;
  background-color: #f0f9ff;
  border: 1px dashed #79bbff;
  border-radius: 4px;
}

.signature-preview-label {
  font-size: 12px;
  color: #409eff;
  margin-bottom: 6px;
}

.signature-preview-content {
  font-size: 12px;
  color: #606266;
  white-space: pre-wrap;
  max-height: 60px;
  overflow-y: auto;
}

/* 邮件线程区域 */
.thread-section {
  margin-top: 24px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.thread-section .section-header {
  background-color: #f5f7fa;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #606266;
}

.thread-list {
  max-height: 300px;
  overflow-y: auto;
}

.thread-item {
  display: flex;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.thread-item:last-child {
  border-bottom: none;
}

.thread-item:hover {
  background-color: #f5f7fa;
}

.thread-item.current {
  background-color: #e1efff;
  border-left: 3px solid #409eff;
}

.thread-avatar {
  margin-right: 12px;
  flex-shrink: 0;
}

.thread-content {
  flex: 1;
  min-width: 0;
}

.thread-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.thread-sender {
  font-weight: 500;
  font-size: 13px;
  color: #303133;
}

.thread-time {
  font-size: 12px;
  color: #909399;
}

.thread-subject {
  font-size: 12px;
  color: #606266;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thread-preview {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 响应式设计 - 小屏幕适配 */
@media (max-width: 600px) {
  .tag-input {
    min-width: 100px;
  }

  .tags-container .el-tag {
    max-width: 150px;
  }

  .recipient-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .recipient-row label {
    width: auto;
    text-align: left;
    padding-top: 0;
    margin-bottom: 4px;
  }

  .reply-body-grid {
    grid-template-columns: 1fr;
  }
}
</style>
