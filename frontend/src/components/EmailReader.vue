<template>
  <div class="email-reader">
    <!-- 邮件头部 -->
    <div class="reader-header">
      <div class="header-actions">
        <el-button-group>
          <el-button :icon="Back" size="small" @click="handleReply">回复</el-button>
          <el-button :icon="Right" size="small" @click="handleForward">转发</el-button>
        </el-button-group>

        <el-button-group>
          <el-button :icon="Delete" size="small" @click="handleDelete">删除</el-button>
          <el-button :icon="Star" size="small" @click="handleFlag">
            {{ email.is_flagged ? '取消标记' : '标记' }}
          </el-button>
        </el-button-group>
      </div>
    </div>

    <!-- 邮件主题 -->
    <div class="reader-subject">
      <h1>{{ email.subject_translated || email.subject_original }}</h1>
      <div class="subject-labels">
        <el-tag
          v-if="email.language_detected && email.language_detected !== 'zh'"
          :type="email.is_translated ? 'success' : 'warning'"
          size="small"
        >
          {{ email.is_translated ? '已翻译' : getLanguageName(email.language_detected) }}
        </el-tag>
      </div>
    </div>

    <!-- 发件人信息 -->
    <div class="reader-sender">
      <el-avatar :size="40" :style="{ backgroundColor: getAvatarColor(email.from_email) }">
        {{ getInitials(email.from_name || email.from_email) }}
      </el-avatar>
      <div class="sender-details">
        <div class="sender-name">{{ email.from_name || email.from_email }}</div>
        <div class="sender-email" v-if="email.from_name">{{ email.from_email }}</div>
        <div class="email-meta">
          <span class="meta-item">
            <strong>收件人：</strong>{{ formatAddressList(email.to_email) }}
          </span>
        </div>
      </div>
      <div class="email-time">
        {{ formatDateTime(email.received_at) }}
      </div>
    </div>

    <!-- 附件 -->
    <div class="reader-attachments" v-if="email.attachments && email.attachments.length > 0">
      <div class="attachments-header">
        <el-icon><Paperclip /></el-icon>
        <span>附件 ({{ email.attachments.length }})</span>
      </div>
      <div class="attachments-list">
        <div class="attachment-item" v-for="att in email.attachments" :key="att.id">
          <el-icon><Document /></el-icon>
          <span class="filename">{{ att.filename }}</span>
          <span class="filesize">({{ formatFileSize(att.file_size) }})</span>
        </div>
      </div>
    </div>

    <!-- 邮件正文 - Split View -->
    <div class="reader-body split-view" v-if="email.language_detected && email.language_detected !== 'zh'">
      <!-- Split View 头部 -->
      <div class="split-header">
        <div class="split-header-left">
          <span>原文 ({{ getLanguageName(email.language_detected) }})</span>
        </div>
        <div class="split-header-right">
          <span>翻译 (中文)</span>
          <el-button
            v-if="!email.is_translated"
            type="primary"
            size="small"
            @click="handleTranslate"
            :loading="translating"
          >
            翻译
          </el-button>
        </div>
      </div>

      <!-- Split View 内容 -->
      <div class="split-body">
        <!-- 左侧原文 -->
        <div
          class="split-pane original-pane"
          ref="originalPane"
          @scroll="handleOriginalScroll"
        >
          <div class="pane-content">{{ email.body_original || '(无文本内容)' }}</div>
        </div>

        <!-- 分隔线 -->
        <div class="split-divider"></div>

        <!-- 右侧翻译 -->
        <div
          class="split-pane translated-pane"
          ref="translatedPane"
          @scroll="handleTranslatedScroll"
        >
          <div class="pane-content" v-if="email.body_translated">
            {{ email.body_translated }}
          </div>
          <div class="pane-placeholder" v-else>
            <el-icon :size="28"><DocumentCopy /></el-icon>
            <p>尚未翻译</p>
            <el-button type="primary" size="small" @click="handleTranslate" :loading="translating">
              立即翻译
            </el-button>
          </div>
        </div>
      </div>

      <!-- HTML 查看按钮 -->
      <div class="html-toggle" v-if="email.body_html">
        <el-button text size="small" @click="showHtmlDialog = true">
          <el-icon><View /></el-icon>
          查看 HTML 原文
        </el-button>
      </div>
    </div>

    <!-- 中文邮件：单栏显示 -->
    <div class="reader-body single-view" v-else>
      <div class="body-content">{{ email.body_original || '(无文本内容)' }}</div>
      <div class="html-toggle" v-if="email.body_html">
        <el-button text size="small" @click="showHtmlDialog = true">
          <el-icon><View /></el-icon>
          查看 HTML 原文
        </el-button>
      </div>
    </div>

    <!-- HTML 对话框 -->
    <el-dialog v-model="showHtmlDialog" title="HTML 原文" width="80%" top="5vh">
      <div class="body-html" v-html="sanitizeHtml(email.body_html)"></div>
    </el-dialog>

    <!-- 快速回复区域 -->
    <div class="reader-quick-reply">
      <el-input
        v-model="quickReply"
        type="textarea"
        :rows="2"
        placeholder="输入回复内容..."
      />
      <div class="quick-reply-actions">
        <el-button type="primary" size="small" @click="sendQuickReply">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Back, Right, Delete, Star, Paperclip, Document, DocumentCopy, View } from '@element-plus/icons-vue'
import DOMPurify from 'dompurify'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const props = defineProps({
  email: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['reply', 'replyAll', 'forward', 'delete', 'flag', 'refresh'])

const quickReply = ref('')
const translating = ref(false)
const showHtmlDialog = ref(false)

// Split View 滚动同步
const originalPane = ref(null)
const translatedPane = ref(null)
let isScrollingSynced = false

function handleOriginalScroll(e) {
  if (isScrollingSynced) return
  if (!translatedPane.value) return

  isScrollingSynced = true
  const sourceEl = e.target
  const targetEl = translatedPane.value

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

  const scrollPercentage = sourceEl.scrollTop / (sourceEl.scrollHeight - sourceEl.clientHeight)
  targetEl.scrollTop = scrollPercentage * (targetEl.scrollHeight - targetEl.clientHeight)

  setTimeout(() => { isScrollingSynced = false }, 50)
}

// 当邮件变化时重置
watch(() => props.email?.id, () => {
  quickReply.value = ''
  showHtmlDialog.value = false
})

function handleReply() {
  emit('reply', props.email)
}

function handleReplyAll() {
  emit('replyAll', props.email)
}

function handleForward() {
  emit('forward', props.email)
}

function handleDelete() {
  emit('delete', props.email)
}

function handleFlag() {
  emit('flag', props.email)
}

async function handleTranslate() {
  translating.value = true
  try {
    await api.translateEmail(props.email.id)
    ElMessage.success('翻译完成')
    emit('refresh')
    // 触发全局邮件列表刷新
    userStore.triggerEmailRefresh()
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

function sendQuickReply() {
  if (!quickReply.value.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }
  emit('reply', { ...props.email, quickReplyText: quickReply.value })
}

function formatDateTime(date) {
  if (!date) return ''
  return dayjs(date).format('YYYY年MM月DD日 HH:mm')
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
  const names = {
    en: '英语',
    ja: '日语',
    ko: '韩语',
    zh: '中文',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    pt: '葡萄牙语',
    ru: '俄语'
  }
  return names[lang] || lang
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
.email-reader {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.reader-header {
  padding: 8px 16px;
  border-bottom: 1px solid #e8e8e8;
  background-color: #fafafa;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.reader-subject {
  padding: 12px 16px 8px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-shrink: 0;
}

.reader-subject h1 {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
  line-height: 1.4;
  flex: 1;
}

.subject-labels {
  flex-shrink: 0;
  margin-left: 8px;
}

.reader-sender {
  display: flex;
  align-items: flex-start;
  padding: 10px 16px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.sender-details {
  flex: 1;
  margin-left: 10px;
  min-width: 0;
}

.sender-name {
  font-weight: 600;
  font-size: 13px;
  color: #1a1a1a;
}

.sender-email {
  font-size: 11px;
  color: #909399;
  margin-top: 1px;
}

.email-meta {
  margin-top: 2px;
  font-size: 11px;
  color: #606266;
}

.meta-item {
  display: block;
}

.meta-item strong {
  color: #909399;
  font-weight: normal;
}

.email-time {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

.reader-attachments {
  padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0;
  background-color: #fafafa;
  flex-shrink: 0;
}

.attachments-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}

.attachments-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 11px;
  color: #606266;
  cursor: pointer;
}

.attachment-item:hover {
  background-color: #e6f7ff;
  border-color: #91d5ff;
}

.attachment-item .filesize {
  color: #909399;
}

/* Split View 样式 */
.reader-body.split-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-top: 1px solid #e8e8e8;
}

.split-header {
  display: flex;
  background-color: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.split-header-left,
.split-header-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
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
  overflow: hidden;
}

.split-pane {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.original-pane {
  background-color: #fffef0;
}

.translated-pane {
  background-color: #f0f9ff;
}

.split-divider {
  width: 3px;
  background: linear-gradient(to bottom, #e8e8e8 0%, #d0d0d0 50%, #e8e8e8 100%);
  cursor: col-resize;
  flex-shrink: 0;
}

.split-divider:hover {
  background: linear-gradient(to bottom, #409eff 0%, #79bbff 50%, #409eff 100%);
}

.pane-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  font-size: 13px;
  color: #303133;
}

.pane-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 8px;
}

.pane-placeholder p {
  margin: 0;
  font-size: 13px;
}

.html-toggle {
  padding: 6px 12px;
  border-top: 1px solid #e8e8e8;
  background-color: #fafafa;
  text-align: center;
  flex-shrink: 0;
}

/* 单栏视图样式 */
.reader-body.single-view {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.single-view .body-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  font-size: 13px;
  color: #303133;
}

.single-view .html-toggle {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e8e8e8;
  text-align: center;
}

/* HTML 对话框内容 */
.body-html {
  padding: 16px;
  background-color: #fafafa;
  border-radius: 4px;
  overflow: auto;
  max-height: 500px;
}

.body-html :deep(img) {
  max-width: 100%;
  height: auto;
}

.body-html :deep(a) {
  color: #409eff;
}

.body-html :deep(table) {
  border-collapse: collapse;
  max-width: 100%;
}

.body-html :deep(td),
.body-html :deep(th) {
  border: 1px solid #ddd;
  padding: 6px;
}

/* 快速回复 */
.reader-quick-reply {
  padding: 8px 16px;
  border-top: 1px solid #e8e8e8;
  background-color: #fafafa;
  flex-shrink: 0;
}

.quick-reply-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}
</style>
