<template>
  <div class="email-preview" v-if="email" v-loading="loading">
    <!-- 预览头部 -->
    <div class="preview-header">
      <div class="preview-subject">
        <h2>{{ email.subject_translated || email.subject_original }}</h2>
        <div class="preview-tags">
          <el-tag
            v-if="email.language_detected && email.language_detected !== 'zh'"
            :type="email.is_translated ? 'success' : 'warning'"
            size="small"
          >
            {{ email.is_translated ? '已翻译' : getLanguageName(email.language_detected) }}
          </el-tag>
        </div>
      </div>

      <!-- 快速操作 -->
      <div class="preview-actions">
        <el-button-group size="small">
          <el-button :icon="Back" @click="$emit('reply')">回复</el-button>
          <el-button :icon="Right" @click="$emit('forward')">转发</el-button>
        </el-button-group>
        <el-button
          size="small"
          :icon="Star"
          :type="email.is_flagged ? 'warning' : 'default'"
          @click="toggleFlag"
        >
          {{ email.is_flagged ? '取消星标' : '星标' }}
        </el-button>
        <el-button size="small" :icon="Delete" type="danger" plain @click="$emit('delete')">
          删除
        </el-button>
        <el-button size="small" type="primary" @click="$emit('open')">
          查看完整邮件
        </el-button>
      </div>
    </div>

    <!-- 发件人信息 -->
    <div class="preview-sender">
      <el-avatar :size="36" :style="{ backgroundColor: getAvatarColor(email.from_email) }">
        {{ getInitials(email.from_name || email.from_email) }}
      </el-avatar>
      <div class="sender-details">
        <div class="sender-name">{{ email.from_name || email.from_email }}</div>
        <div class="sender-time">{{ formatDateTime(email.received_at) }}</div>
      </div>
    </div>

    <!-- 收件人 -->
    <div class="preview-recipients" v-if="email.to_email">
      <span class="label">收件人：</span>
      <span class="value">{{ formatRecipients(email.to_email) }}</span>
    </div>

    <!-- 附件提示 -->
    <div class="preview-attachments" v-if="email.attachments && email.attachments.length > 0">
      <el-icon><Paperclip /></el-icon>
      <span>{{ email.attachments.length }} 个附件</span>
    </div>

    <!-- 翻译按钮（如果未翻译） -->
    <div class="preview-translate" v-if="!email.is_translated && email.language_detected !== 'zh'">
      <el-button type="primary" size="small" @click="translateEmail" :loading="translating">
        翻译此邮件
      </el-button>
    </div>

    <!-- 邮件正文 -->
    <div class="preview-body">
      <!-- 显示切换 -->
      <div class="body-tabs" v-if="email.is_translated">
        <el-radio-group v-model="showMode" size="small">
          <el-radio-button value="translated">翻译</el-radio-button>
          <el-radio-button value="original">原文</el-radio-button>
          <el-radio-button value="split">对比</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 单独显示 -->
      <div class="body-content" v-if="showMode !== 'split'">
        <div class="body-text" v-if="showMode === 'translated' && email.body_translated">
          {{ email.body_translated }}
        </div>
        <div class="body-text" v-else>
          {{ email.body_original || '(无文本内容)' }}
        </div>
      </div>

      <!-- 对比显示 -->
      <div class="body-split" v-else>
        <div class="split-pane">
          <div class="split-label">原文</div>
          <div class="split-text">{{ email.body_original || '(无文本内容)' }}</div>
        </div>
        <div class="split-divider"></div>
        <div class="split-pane">
          <div class="split-label">{{ (!email.language_detected || email.language_detected === 'zh') ? '内容预览' : '翻译' }}</div>
          <div class="split-text">{{ (!email.language_detected || email.language_detected === 'zh') ? (email.body_original || '(无文本内容)') : (email.body_translated || '(未翻译)') }}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 无选中邮件 -->
  <div class="preview-empty" v-else>
    <el-icon :size="48"><Message /></el-icon>
    <p>选择邮件以预览内容</p>
    <p class="hint">使用 J/K 键快速浏览邮件列表</p>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { Back, Right, Star, Delete, Paperclip, Message } from '@element-plus/icons-vue'
import api from '@/api'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'

const props = defineProps({
  emailId: {
    type: [Number, String],
    default: null
  }
})

const emit = defineEmits(['reply', 'forward', 'delete', 'open', 'flag', 'update'])

const email = ref(null)
const loading = ref(false)
const translating = ref(false)
const showMode = ref('translated')  // translated, original, split
let isUnmounted = false  // 组件卸载状态标志

// 组件卸载时标记状态，让翻译请求在后台继续运行
onUnmounted(() => {
  isUnmounted = true  // 标记已卸载，防止异步回调修改状态
  // 注意：不取消翻译请求，让它在后台继续运行
})

// 监听 emailId 变化
watch(() => props.emailId, async (newId) => {
  if (newId) {
    await loadEmail(newId)
  } else {
    email.value = null
  }
}, { immediate: true })

async function loadEmail(id) {
  loading.value = true
  try {
    email.value = await api.getEmail(id)

    // 标记已读
    if (!email.value.is_read) {
      try {
        await api.markAsRead(id)
        email.value.is_read = true
        emit('update', { ...email.value })
      } catch (e) {
        console.error('Failed to mark as read:', e)
      }
    }

    // 根据翻译状态设置默认显示模式
    showMode.value = email.value.is_translated ? 'translated' : 'original'
  } catch (e) {
    console.error('Failed to load email:', e)
    email.value = null
  } finally {
    loading.value = false
  }
}

async function toggleFlag() {
  if (!email.value) return

  const originalState = email.value.is_flagged
  email.value.is_flagged = !email.value.is_flagged

  try {
    if (email.value.is_flagged) {
      await api.flagEmail(email.value.id)
    } else {
      await api.unflagEmail(email.value.id)
    }
    emit('flag', email.value)
    emit('update', { ...email.value })
  } catch (e) {
    email.value.is_flagged = originalState
    ElMessage.error('操作失败')
  }
}

async function translateEmail() {
  if (!email.value) return

  translating.value = true
  try {
    // 不使用 AbortController，让请求在后台继续运行
    const result = await api.translateEmail(email.value.id)
    // 组件卸载后不更新状态，但翻译已保存到后端
    if (isUnmounted) {
      console.log('Translation completed in background')
      return
    }
    email.value = result
    showMode.value = 'translated'
    ElMessage.success('翻译完成')
    emit('update', { ...email.value })
  } catch (e) {
    // 组件卸载后不显示错误
    if (isUnmounted) return
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    // 只在组件未卸载时修改状态
    if (!isUnmounted) {
      translating.value = false
    }
  }
}

function formatDateTime(date) {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

function formatRecipients(str) {
  if (!str) return ''
  return str.split(',').map(s => s.trim()).slice(0, 3).join('; ') +
    (str.split(',').length > 3 ? ` 等${str.split(',').length}人` : '')
}

function getLanguageName(lang) {
  const names = {
    en: '英语', ja: '日语', ko: '韩语', zh: '中文',
    de: '德语', fr: '法语', es: '西班牙语', pt: '葡萄牙语', ru: '俄语'
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
  const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#00bcd4', '#9c27b0', '#ff5722']
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}
</script>

<style scoped>
.email-preview {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

/* 预览头部 */
.preview-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.preview-subject {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}

.preview-subject h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.4;
  flex: 1;
}

.preview-tags {
  margin-left: 12px;
  flex-shrink: 0;
}

.preview-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 发件人信息 */
.preview-sender {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.sender-details {
  margin-left: 10px;
}

.sender-name {
  font-weight: 500;
  font-size: 14px;
  color: #303133;
}

.sender-time {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

/* 收件人 */
.preview-recipients {
  padding: 8px 16px;
  font-size: 13px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.preview-recipients .label {
  color: #909399;
}

.preview-recipients .value {
  color: #606266;
}

/* 附件提示 */
.preview-attachments {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  color: #909399;
  background-color: #fafafa;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

/* 翻译按钮 */
.preview-translate {
  padding: 10px 16px;
  background-color: #fdf6ec;
  border-bottom: 1px solid #faecd8;
  flex-shrink: 0;
}

/* 正文区域 */
.preview-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.body-tabs {
  padding: 10px 16px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.body-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.body-text {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 对比显示 */
.body-split {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.body-split .split-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.body-split .split-label {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.body-split .split-pane:first-child .split-label {
  background-color: #fff9e6;
}

.body-split .split-pane:last-child .split-label {
  background-color: #e6f7ff;
}

.body-split .split-text {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.body-split .split-divider {
  width: 1px;
  background-color: #e8e8e8;
  flex-shrink: 0;
}

/* 空状态 */
.preview-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  background-color: #fafafa;
}

.preview-empty .el-icon {
  color: #c0c4cc;
  margin-bottom: 16px;
}

.preview-empty p {
  margin: 0;
  font-size: 14px;
}

.preview-empty .hint {
  margin-top: 8px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
