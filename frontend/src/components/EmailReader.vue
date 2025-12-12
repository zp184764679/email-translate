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

    <!-- 邮件正文 - 段落配对视图（所有邮件统一双栏显示）-->
    <div class="reader-body split-view">
      <!-- Split View 头部 -->
      <div class="split-header">
        <div class="split-header-left">
          <span>原文 ({{ getLanguageName(email.language_detected) || '中文' }})</span>
        </div>
        <div class="split-header-right">
          <span v-if="email.language_detected && email.language_detected !== 'zh'">翻译 (中文)</span>
          <span v-else>内容预览</span>
          <el-button
            v-if="!email.is_translated && email.language_detected && email.language_detected !== 'zh'"
            type="primary"
            size="small"
            @click="handleTranslate"
            :loading="translating"
          >
            翻译
          </el-button>
        </div>
      </div>

      <!-- 段落配对内容 -->
      <div class="paragraph-container" ref="paragraphContainer">
        <!-- 中文邮件：左右都显示原文 -->
        <template v-if="!email.language_detected || email.language_detected === 'zh'">
          <div class="paragraph-pair" v-for="(para, index) in chineseParagraphs" :key="index">
            <div class="pair-cell original-cell">
              <div class="cell-content">{{ para }}</div>
            </div>
            <div class="pair-cell translated-cell">
              <div class="cell-content">{{ para }}</div>
            </div>
          </div>
        </template>
        <!-- 非中文邮件：显示原文和翻译 -->
        <template v-else-if="email.body_translated">
          <div class="paragraph-pair" v-for="(pair, index) in paragraphPairs" :key="index">
            <div class="pair-cell original-cell">
              <div class="cell-content">{{ pair.original }}</div>
            </div>
            <div class="pair-cell translated-cell">
              <div class="cell-content">{{ pair.translated }}</div>
            </div>
          </div>
        </template>
        <template v-else>
          <!-- 未翻译时显示原文和占位符 -->
          <div class="split-body-fallback">
            <div class="split-pane original-pane">
              <div class="pane-content">{{ displayOriginalBody }}</div>
            </div>
            <div class="split-divider"></div>
            <div class="split-pane translated-pane">
              <div class="pane-placeholder">
                <el-icon :size="28"><DocumentCopy /></el-icon>
                <p>尚未翻译</p>
                <el-button type="primary" size="small" @click="handleTranslate" :loading="translating">
                  立即翻译
                </el-button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- HTML 查看按钮 -->
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
import { ref, watch, computed } from 'vue'
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

// 计算属性：显示原文（优先纯文本，其次从 HTML 提取）
const displayOriginalBody = computed(() => {
  if (props.email.body_original) {
    return normalizeLineBreaks(props.email.body_original)
  }
  if (props.email.body_html) {
    return htmlToTextWithFormat(props.email.body_html)
  }
  return '(无文本内容)'
})

// 计算属性：显示翻译结果（合并连续空行）
const displayTranslatedBody = computed(() => {
  if (!props.email.body_translated) return ''
  return normalizeLineBreaks(props.email.body_translated)
})

// 段落配对：将原文和翻译按段落配对显示
const paragraphPairs = computed(() => {
  const originalText = displayOriginalBody.value
  const translatedText = displayTranslatedBody.value

  // 按空行分割成段落
  const originalParagraphs = splitIntoParagraphs(originalText)
  const translatedParagraphs = splitIntoParagraphs(translatedText)

  // 配对段落
  const pairs = []
  const maxLen = Math.max(originalParagraphs.length, translatedParagraphs.length)

  for (let i = 0; i < maxLen; i++) {
    pairs.push({
      original: originalParagraphs[i] || '',
      translated: translatedParagraphs[i] || ''
    })
  }

  return pairs
})

// 中文邮件段落：用于中文邮件左右双栏显示
const chineseParagraphs = computed(() => {
  const text = displayOriginalBody.value
  return splitIntoParagraphs(text)
})

// 将文本按段落分割（以空行为分隔符）
function splitIntoParagraphs(text) {
  if (!text) return []

  // 先按换行分割
  const lines = text.split('\n')
  const paragraphs = []
  let currentParagraph = []

  for (const line of lines) {
    const trimmedLine = line.trim()
    if (trimmedLine === '') {
      // 遇到空行，保存当前段落
      if (currentParagraph.length > 0) {
        paragraphs.push(currentParagraph.join('\n'))
        currentParagraph = []
      }
    } else {
      currentParagraph.push(trimmedLine)
    }
  }

  // 处理最后一个段落
  if (currentParagraph.length > 0) {
    paragraphs.push(currentParagraph.join('\n'))
  }

  return paragraphs
}

// 规范化换行：合并连续空行，删除邮件头字段后的空行
function normalizeLineBreaks(text) {
  if (!text) return ''
  const lines = text.split('\n').map(line => line.trim())
  let result = []
  let lastWasEmpty = false
  const headerPattern = /^(发件人|时\s*间|收件人|抄送人|主\s*题)：/

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line === '') {
      // 如果前一行是邮件头字段，跳过这个空行
      if (result.length > 0 && headerPattern.test(result[result.length - 1])) {
        continue
      }
      if (!lastWasEmpty) {
        result.push(line)
        lastWasEmpty = true
      }
    } else {
      result.push(line)
      lastWasEmpty = false
    }
  }
  return result.join('\n').trim()
}

// 从 HTML 提取文本，保留段落格式
function htmlToTextWithFormat(html) {
  if (!html) return ''
  let text = html
  // 先保留原始换行符
  text = text.replace(/\r\n/g, '\n')
  // <br> -> 换行
  text = text.replace(/<br\s*\/?>/gi, '\n')
  // </p>, </div>, </li>, </tr>, </h1-6> -> 换行
  text = text.replace(/<\/(?:p|div|li|tr|h[1-6])>/gi, '\n')
  // 移除其他 HTML 标签（不影响换行）
  text = text.replace(/<[^>]+>/g, '')
  // 处理 HTML 实体
  text = text.replace(/&nbsp;/g, ' ')
  text = text.replace(/&lt;/g, '<')
  text = text.replace(/&gt;/g, '>')
  text = text.replace(/&amp;/g, '&')
  text = text.replace(/&quot;/g, '"')
  text = text.replace(/&#\d+;/g, '')
  text = text.replace(/&[a-z]+;/gi, '')
  // 清理但保留换行：只压缩水平空白（空格、制表符等，不包括换行）
  text = text.replace(/[ \t]+/g, ' ')
  // 每行首尾空格清理
  const lines = text.split('\n').map(line => line.trim())
  // 合并连续空行为1个
  let result = []
  let lastWasEmpty = false
  for (const line of lines) {
    if (line === '') {
      if (!lastWasEmpty) {
        result.push(line)
        lastWasEmpty = true
      }
    } else {
      result.push(line)
      lastWasEmpty = false
    }
  }
  return result.join('\n').trim()
}

// 段落配对容器引用
const paragraphContainer = ref(null)

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
    ElMessage.error('翻译失败: ' + (e.response?.data?.detail || e.message))
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

/* 段落配对容器 */
.paragraph-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.paragraph-pair {
  display: flex;
  border-bottom: 1px solid #e8e8e8;
}

.paragraph-pair:last-child {
  border-bottom: none;
}

.pair-cell {
  flex: 1;
  padding: 10px 12px;
  min-width: 0;
}

.original-cell {
  background-color: #fffef0;
  border-right: 2px solid #e8e8e8;
}

.translated-cell {
  background-color: #f0f9ff;
}

.cell-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  font-size: 13px;
  color: #303133;
}

/* 未翻译时的回退布局 */
.split-body-fallback {
  display: flex;
  flex: 1;
  height: 100%;
}

.split-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.split-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 12px;
  min-width: 0;
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
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  font-size: 13px;
  color: #303133;
}

.pane-placeholder {
  flex: 1;
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
/* Updated: paragraph pairing view applied v2 */
</style>
