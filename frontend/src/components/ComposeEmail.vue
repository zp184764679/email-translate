<template>
  <div class="compose-email">
    <!-- 工具栏 -->
    <div class="compose-toolbar">
      <el-button size="small" :icon="Document" @click="showTemplateSelector = true">
        插入模板
      </el-button>
      <el-divider direction="vertical" />
      <el-checkbox v-model="enableSchedule" size="small">定时发送</el-checkbox>
      <el-date-picker
        v-if="enableSchedule"
        v-model="scheduledTime"
        type="datetime"
        placeholder="选择发送时间"
        size="small"
        :disabled-date="disabledDate"
        :shortcuts="dateShortcuts"
        style="width: 200px; margin-left: 8px"
      />
    </div>

    <!-- 收件人区域 -->
    <div class="compose-field">
      <label>收件人：</label>
      <el-input v-model="form.to" placeholder="请输入收件人邮箱地址" />
    </div>

    <div class="compose-field">
      <label>抄送：</label>
      <el-input v-model="form.cc" placeholder="请输入抄送邮箱地址（可选）" />
    </div>

    <div class="compose-field">
      <label>主题：</label>
      <el-input v-model="form.subject" placeholder="请输入邮件主题" />
    </div>

    <!-- 快速回复短语 -->
    <div class="quick-phrases">
      <span class="quick-phrases-label">快速插入：</span>
      <el-button
        v-for="(phrase, index) in quickPhrases"
        :key="index"
        size="small"
        @click="insertPhrase(phrase)"
      >
        {{ phrase }}
      </el-button>
      <el-popover trigger="click" width="200" placement="bottom">
        <template #reference>
          <el-button size="small" type="info" text>
            <el-icon><Setting /></el-icon>
          </el-button>
        </template>
        <div class="phrase-editor">
          <div class="phrase-editor-title">自定义短语</div>
          <el-input
            v-for="(_, index) in customPhrases"
            :key="index"
            v-model="customPhrases[index]"
            size="small"
            placeholder="输入短语"
            style="margin-bottom: 6px"
          />
          <el-button size="small" type="primary" @click="saveCustomPhrases" style="width: 100%">
            保存
          </el-button>
        </div>
      </el-popover>
    </div>

    <!-- 正文编辑区 -->
    <div class="compose-body">
      <div class="body-section">
        <div class="section-header">
          <span>邮件内容</span>
          <el-select v-model="form.targetLanguage" size="small" style="width: 120px;" placeholder="翻译目标语言">
            <el-option label="英语" value="en" />
            <el-option label="日语" value="ja" />
            <el-option label="韩语" value="ko" />
            <el-option label="德语" value="de" />
            <el-option label="法语" value="fr" />
          </el-select>
        </div>
        <el-input
          v-model="form.bodyChinese"
          type="textarea"
          :rows="10"
          placeholder="输入邮件内容（可直接发送，或点击翻译后发送译文）"
        />
      </div>

      <div class="body-section">
        <div class="section-header">
          <span>翻译预览 ({{ getLanguageName(form.targetLanguage) }})</span>
          <el-button size="small" type="primary" @click="translateContent" :loading="translating">
            翻译
          </el-button>
        </div>
        <el-input
          v-model="form.bodyTranslated"
          type="textarea"
          :rows="10"
          placeholder="点击翻译按钮生成译文，或直接在此编辑..."
        />
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="compose-actions">
      <!-- 自动保存状态提示 -->
      <span class="auto-save-status" :class="autoSaveStatus">
        <template v-if="autoSaveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 正在保存...
        </template>
        <template v-else-if="autoSaveStatus === 'saved'">
          <el-icon><Check /></el-icon> 已保存于 {{ lastSavedTimeStr }}
        </template>
        <template v-else-if="autoSaveStatus === 'failed'">
          <el-icon><Warning /></el-icon>
          <span class="retry-link" @click="saveLocalDraft">保存失败，点击重试</span>
        </template>
      </span>
      <el-popover
        v-if="draftVersions.length > 1"
        trigger="click"
        placement="top"
        width="280"
      >
        <template #reference>
          <el-button size="small" text type="info">
            <el-icon><Clock /></el-icon> 历史版本 ({{ draftVersions.length }})
          </el-button>
        </template>
        <div class="draft-versions">
          <div class="version-title">草稿历史版本</div>
          <div
            v-for="(version, index) in draftVersions"
            :key="index"
            class="version-item"
            @click="restoreVersion(index)"
          >
            <span class="version-time">{{ formatVersionTime(version.savedAt) }}</span>
            <span class="version-preview">{{ version.bodyChinese?.substring(0, 30) || '(空)' }}...</span>
          </div>
        </div>
      </el-popover>
      <span class="send-hint" v-if="!form.bodyTranslated.trim() && form.bodyChinese.trim()">
        将发送左侧内容
      </span>
      <span class="schedule-hint" v-if="enableSchedule && scheduledTime">
        将于 {{ formatScheduleTime(scheduledTime) }} 发送
      </span>
      <el-button @click="$emit('cancel')">取消</el-button>
      <el-button @click="saveDraft">保存草稿</el-button>
      <el-button
        type="primary"
        @click="sendEmail"
        :loading="sending"
        :disabled="!canSend || (enableSchedule && !scheduledTime)"
      >
        {{ enableSchedule ? '定时发送' : '发送' }}
      </el-button>
    </div>

    <!-- 模板选择器对话框 -->
    <el-dialog v-model="showTemplateSelector" title="选择邮件模板" width="700px">
      <div class="template-selector">
        <div class="template-filters">
          <el-select v-model="templateCategory" placeholder="按分类筛选" clearable style="width: 150px">
            <el-option label="全部" value="" />
            <el-option label="询价" value="inquiry" />
            <el-option label="订单" value="order" />
            <el-option label="物流" value="logistics" />
            <el-option label="付款" value="payment" />
            <el-option label="其他" value="other" />
          </el-select>
          <el-input
            v-model="templateSearch"
            placeholder="搜索模板..."
            prefix-icon="Search"
            clearable
            style="width: 200px"
          />
        </div>

        <div class="template-list" v-loading="loadingTemplates">
          <el-empty v-if="filteredTemplates.length === 0" description="暂无模板" />
          <div
            v-else
            v-for="template in filteredTemplates"
            :key="template.id"
            class="template-item"
            :class="{ active: selectedTemplate?.id === template.id }"
            @click="selectTemplate(template)"
          >
            <div class="template-header">
              <span class="template-name">{{ template.name }}</span>
              <el-tag size="small" v-if="template.is_shared" type="success">共享</el-tag>
              <el-tag size="small" v-if="template.category">{{ getCategoryLabel(template.category) }}</el-tag>
            </div>
            <div class="template-subject">{{ template.subject_cn }}</div>
            <div class="template-preview">{{ template.body_cn?.substring(0, 100) }}...</div>
          </div>
        </div>

        <div class="template-preview-section" v-if="selectedTemplate">
          <h4>预览</h4>
          <div class="preview-subject">主题: {{ selectedTemplate.subject_cn }}</div>
          <div class="preview-body">{{ selectedTemplate.body_cn }}</div>
          <div class="preview-variables" v-if="selectedTemplate.variables?.length">
            <span>变量: </span>
            <el-tag v-for="v in selectedTemplate.variables" :key="v" size="small" style="margin-right: 4px">
              {{ '{' + v + '}' }}
            </el-tag>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showTemplateSelector = false">取消</el-button>
        <el-button type="primary" @click="applyTemplate" :disabled="!selectedTemplate">
          使用此模板
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { Document, Loading, Check, Warning, Clock, Setting } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'

// ========== 快速回复短语 ==========
const PHRASES_KEY = 'quick_reply_phrases'
const DEFAULT_PHRASES = ['收到，谢谢', '好的，已确认', '请稍等，正在处理', '已安排，请查收']

const customPhrases = ref([...DEFAULT_PHRASES])

const quickPhrases = computed(() => {
  return customPhrases.value.filter(p => p.trim())
})

function loadCustomPhrases() {
  try {
    const stored = localStorage.getItem(PHRASES_KEY)
    if (stored) {
      customPhrases.value = JSON.parse(stored)
    }
  } catch (e) {
    console.error('Failed to load custom phrases:', e)
  }
}

function saveCustomPhrases() {
  try {
    localStorage.setItem(PHRASES_KEY, JSON.stringify(customPhrases.value))
    ElMessage.success('短语已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

function insertPhrase(phrase) {
  // 插入到中文内容区，光标位置或末尾
  if (form.bodyChinese.trim()) {
    form.bodyChinese += '\n' + phrase
  } else {
    form.bodyChinese = phrase
  }
}

// ========== 草稿自动保存功能 ==========
const DRAFT_KEY = 'compose_draft_versions'
const MAX_VERSIONS = 3
const AUTO_SAVE_INTERVAL = 30000  // 30秒
const CHAR_SAVE_THRESHOLD = 50    // 每输入50字符触发保存

const autoSaveStatus = ref('')  // '', 'saving', 'saved', 'failed'
const lastSavedTime = ref(null)
const draftVersions = ref([])
let autoSaveTimer = null
let charCountSinceLastSave = 0

const lastSavedTimeStr = computed(() => {
  if (!lastSavedTime.value) return ''
  return dayjs(lastSavedTime.value).format('HH:mm')
})

// 加载本地草稿版本
function loadDraftVersions() {
  try {
    const stored = localStorage.getItem(DRAFT_KEY)
    if (stored) {
      draftVersions.value = JSON.parse(stored)
    }
  } catch (e) {
    console.error('Failed to load draft versions:', e)
  }
}

// 保存到本地存储
function saveLocalDraft() {
  try {
    autoSaveStatus.value = 'saving'

    const currentDraft = {
      to: form.to,
      cc: form.cc,
      subject: form.subject,
      bodyChinese: form.bodyChinese,
      bodyTranslated: form.bodyTranslated,
      targetLanguage: form.targetLanguage,
      savedAt: new Date().toISOString()
    }

    // 检查是否有实质内容变化
    const lastVersion = draftVersions.value[0]
    if (lastVersion &&
        lastVersion.bodyChinese === currentDraft.bodyChinese &&
        lastVersion.bodyTranslated === currentDraft.bodyTranslated &&
        lastVersion.subject === currentDraft.subject) {
      autoSaveStatus.value = 'saved'
      return
    }

    // 只有有内容时才保存
    if (!currentDraft.bodyChinese.trim() && !currentDraft.bodyTranslated.trim()) {
      autoSaveStatus.value = ''
      return
    }

    // 添加到版本列表开头
    draftVersions.value.unshift(currentDraft)

    // 只保留最近 N 个版本
    if (draftVersions.value.length > MAX_VERSIONS) {
      draftVersions.value = draftVersions.value.slice(0, MAX_VERSIONS)
    }

    // 保存到 localStorage
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draftVersions.value))

    lastSavedTime.value = new Date()
    autoSaveStatus.value = 'saved'
    charCountSinceLastSave = 0
  } catch (e) {
    console.error('Failed to save local draft:', e)
    autoSaveStatus.value = 'failed'
  }
}

// 恢复指定版本
function restoreVersion(index) {
  const version = draftVersions.value[index]
  if (!version) return

  form.to = version.to || ''
  form.cc = version.cc || ''
  form.subject = version.subject || ''
  form.bodyChinese = version.bodyChinese || ''
  form.bodyTranslated = version.bodyTranslated || ''
  form.targetLanguage = version.targetLanguage || 'en'

  ElMessage.success('已恢复到历史版本')
}

// 格式化版本时间
function formatVersionTime(isoStr) {
  if (!isoStr) return ''
  const d = dayjs(isoStr)
  const today = dayjs()
  if (d.isSame(today, 'day')) {
    return '今天 ' + d.format('HH:mm')
  }
  return d.format('MM-DD HH:mm')
}

// 启动自动保存定时器
function startAutoSaveTimer() {
  if (autoSaveTimer) clearInterval(autoSaveTimer)
  autoSaveTimer = setInterval(() => {
    saveLocalDraft()
  }, AUTO_SAVE_INTERVAL)
}

// 监听内容变化，触发字符计数保存
function onContentChange(newVal, oldVal) {
  if (!oldVal) return
  const diff = Math.abs((newVal?.length || 0) - (oldVal?.length || 0))
  charCountSinceLastSave += diff

  if (charCountSinceLastSave >= CHAR_SAVE_THRESHOLD) {
    saveLocalDraft()
  }
}

// 接收原邮件语言，用于设置默认目标语言
const props = defineProps({
  replyTo: { type: Object, default: null },  // 回复的原邮件
  defaultLanguage: { type: String, default: '' }  // 默认目标语言
})

const emit = defineEmits(['sent', 'cancel'])

const translating = ref(false)
const sending = ref(false)

const form = reactive({
  to: '',
  cc: '',
  subject: '',
  bodyChinese: '',
  bodyTranslated: '',
  targetLanguage: 'en'
})

// 定时发送
const enableSchedule = ref(false)
const scheduledTime = ref(null)

const dateShortcuts = [
  { text: '1小时后', value: () => dayjs().add(1, 'hour').toDate() },
  { text: '2小时后', value: () => dayjs().add(2, 'hour').toDate() },
  { text: '明天此时', value: () => dayjs().add(1, 'day').toDate() },
  { text: '下周一9:00', value: () => {
    const next = dayjs().day(8).hour(9).minute(0).second(0)
    return next.toDate()
  }}
]

function disabledDate(date) {
  return date.getTime() < Date.now() - 60000  // 不能选择过去的时间
}

function formatScheduleTime(date) {
  return dayjs(date).format('MM月DD日 HH:mm')
}

// 模板选择
const showTemplateSelector = ref(false)
const templates = ref([])
const loadingTemplates = ref(false)
const templateCategory = ref('')
const templateSearch = ref('')
const selectedTemplate = ref(null)

const filteredTemplates = computed(() => {
  let result = templates.value
  if (templateCategory.value) {
    result = result.filter(t => t.category === templateCategory.value)
  }
  if (templateSearch.value) {
    const search = templateSearch.value.toLowerCase()
    result = result.filter(t =>
      t.name.toLowerCase().includes(search) ||
      t.subject_cn?.toLowerCase().includes(search)
    )
  }
  return result
})

function getCategoryLabel(category) {
  const labels = {
    inquiry: '询价',
    order: '订单',
    logistics: '物流',
    payment: '付款',
    other: '其他'
  }
  return labels[category] || category
}

async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const res = await api.getTemplates()
    templates.value = res.data || []
  } catch (e) {
    console.error('Failed to load templates:', e)
  } finally {
    loadingTemplates.value = false
  }
}

function selectTemplate(template) {
  selectedTemplate.value = template
}

function applyTemplate() {
  if (!selectedTemplate.value) return

  // 应用模板内容
  if (selectedTemplate.value.subject_cn) {
    form.subject = selectedTemplate.value.subject_cn
  }
  if (selectedTemplate.value.body_cn) {
    form.bodyChinese = selectedTemplate.value.body_cn
  }

  showTemplateSelector.value = false
  selectedTemplate.value = null
  ElMessage.success('模板已应用')
}

// 打开模板选择器时加载模板
watch(showTemplateSelector, (val) => {
  if (val && templates.value.length === 0) {
    loadTemplates()
  }
})

// 初始化时设置默认语言
onMounted(() => {
  if (props.defaultLanguage) {
    form.targetLanguage = props.defaultLanguage
  } else if (props.replyTo?.detected_language) {
    // 根据原邮件语言设置目标语言
    const lang = props.replyTo.detected_language.toLowerCase()
    if (['en', 'ja', 'ko', 'de', 'fr'].includes(lang)) {
      form.targetLanguage = lang
    }
  }
  // 如果是回复，设置收件人和主题
  if (props.replyTo) {
    form.to = props.replyTo.from_email || ''
    form.subject = props.replyTo.subject?.startsWith('Re:')
      ? props.replyTo.subject
      : `Re: ${props.replyTo.subject || ''}`
  }

  // 加载本地草稿版本并启动自动保存
  loadDraftVersions()
  startAutoSaveTimer()

  // 加载自定义快速短语
  loadCustomPhrases()
})

// 组件卸载时清理定时器
onUnmounted(() => {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
  // 最后一次保存
  saveLocalDraft()
})

// 监听内容变化，触发字符计数保存
watch(() => form.bodyChinese, onContentChange)
watch(() => form.bodyTranslated, onContentChange)

// 发送条件：左边或右边有内容即可
const canSend = computed(() => {
  const hasContent = form.bodyChinese.trim() || form.bodyTranslated.trim()
  return form.to.trim() && form.subject.trim() && hasContent
})

function getLanguageName(lang) {
  const names = {
    en: '英语',
    ja: '日语',
    ko: '韩语',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    pt: '葡萄牙语',
    ru: '俄语'
  }
  return names[lang] || lang
}

async function translateContent() {
  if (!form.bodyChinese.trim()) {
    ElMessage.warning('请先输入中文内容')
    return
  }

  translating.value = true
  try {
    const result = await api.translateReply(
      form.bodyChinese,
      form.targetLanguage,
      null,
      null
    )
    form.bodyTranslated = result.translated_text
    ElMessage.success('翻译完成')
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

async function saveDraft() {
  if (!form.bodyChinese.trim()) {
    ElMessage.warning('请输入邮件内容')
    return
  }

  try {
    await api.createDraft({
      body_chinese: form.bodyChinese,
      body_translated: form.bodyTranslated,
      target_language: form.targetLanguage
    })
    ElMessage.success('草稿已保存')
  } catch (e) {
    console.error('Failed to save draft:', e)
    ElMessage.error('保存草稿失败')
  }
}

// 发送前检查清单
async function preSendChecks() {
  const warnings = []

  // 1. 主题为空
  if (!form.subject.trim()) {
    warnings.push({ key: 'no_subject', message: '邮件没有主题，确定发送？' })
  }

  // 2. 正文提到附件但没附件（检查中文和英文关键词）
  const content = (form.bodyChinese + ' ' + form.bodyTranslated).toLowerCase()
  const attachmentKeywords = ['附件', '附上', '附送', 'attachment', 'attached', 'attach', 'enclos']
  const mentionsAttachment = attachmentKeywords.some(kw => content.includes(kw))
  // 目前组件不支持附件功能，所以如果提到了附件就警告
  if (mentionsAttachment) {
    warnings.push({ key: 'missing_attachment', message: '您提到了"附件"，但没有添加附件，确定发送？' })
  }

  // 3. 收件人是自己（获取当前用户邮箱）
  const currentUserEmail = localStorage.getItem('email') || ''
  if (currentUserEmail && form.to.toLowerCase().includes(currentUserEmail.toLowerCase())) {
    warnings.push({ key: 'send_to_self', message: '您将邮件发给了自己，确定发送？' })
  }

  // 4. 有中文内容但没有翻译
  if (form.bodyChinese.trim() && !form.bodyTranslated.trim()) {
    // 检查中文内容是否包含中文字符
    const hasChinese = /[\u4e00-\u9fa5]/.test(form.bodyChinese)
    if (hasChinese) {
      warnings.push({ key: 'not_translated', message: '正文还未翻译，将发送左侧中文内容，确定发送？' })
    }
  }

  // 如果有警告，弹出确认对话框
  if (warnings.length > 0) {
    const warningMessages = warnings.map(w => `• ${w.message}`).join('\n')
    try {
      await ElMessageBox.confirm(
        warningMessages,
        '发送前提醒',
        {
          confirmButtonText: '仍然发送',
          cancelButtonText: '返回修改',
          type: 'warning',
          dangerouslyUseHTMLString: false
        }
      )
      return true  // 用户确认发送
    } catch {
      return false  // 用户取消
    }
  }

  return true  // 没有警告，直接发送
}

async function sendEmail() {
  if (!canSend.value) {
    ElMessage.warning('请填写完整的邮件信息')
    return
  }

  // 检查定时发送
  if (enableSchedule.value && !scheduledTime.value) {
    ElMessage.warning('请选择定时发送时间')
    return
  }

  // 发送前检查清单
  const shouldProceed = await preSendChecks()
  if (!shouldProceed) return

  // 优先发送右边翻译内容，没有则发送左边原始内容
  const bodyToSend = form.bodyTranslated.trim() || form.bodyChinese.trim()

  sending.value = true
  try {
    const emailData = {
      to: form.to,
      cc: form.cc,
      subject: form.subject,
      body: bodyToSend
    }

    // 如果是定时发送，添加 scheduled_at 参数
    if (enableSchedule.value && scheduledTime.value) {
      emailData.scheduled_at = dayjs(scheduledTime.value).toISOString()
      await api.createDraft({
        to_email: form.to,
        cc_email: form.cc,
        subject: form.subject,
        body_chinese: form.bodyChinese,
        body_translated: form.bodyTranslated || bodyToSend,
        target_language: form.targetLanguage,
        scheduled_at: emailData.scheduled_at
      })
      ElMessage.success(`邮件已设置为 ${formatScheduleTime(scheduledTime.value)} 发送`)
    } else {
      await api.sendEmail(emailData)
    }
    emit('sent')
  } catch (e) {
    console.error('Failed to send email:', e)
    ElMessage.error(enableSchedule.value ? '设置定时发送失败' : '发送失败')
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.compose-email {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compose-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compose-field label {
  width: 60px;
  flex-shrink: 0;
  color: #606266;
  font-size: 14px;
}

.compose-field .el-input {
  flex: 1;
}

.compose-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.body-section {
  display: flex;
  flex-direction: column;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  color: #606266;
}

.compose-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #e0e0e0;
}

.send-hint {
  margin-right: auto;
  font-size: 12px;
  color: #909399;
}

.schedule-hint {
  font-size: 12px;
  color: #E6A23C;
  margin-right: 12px;
}

.compose-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

/* 模板选择器样式 */
.template-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.template-filters {
  display: flex;
  gap: 12px;
}

.template-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.template-item {
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
  transition: background-color 0.2s;
}

.template-item:hover {
  background-color: #f5f7fa;
}

.template-item.active {
  background-color: #ecf5ff;
  border-left: 3px solid #409EFF;
}

.template-item:last-child {
  border-bottom: none;
}

.template-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.template-name {
  font-weight: 500;
  color: #303133;
}

.template-subject {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

.template-preview {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-preview-section {
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.template-preview-section h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #303133;
}

.preview-subject {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.preview-body {
  font-size: 13px;
  color: #606266;
  white-space: pre-wrap;
  max-height: 150px;
  overflow-y: auto;
  margin-bottom: 8px;
}

.preview-variables {
  font-size: 12px;
  color: #909399;
}

/* 自动保存状态样式 */
.auto-save-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-right: auto;
}

.auto-save-status.saving {
  color: #409EFF;
}

.auto-save-status.saved {
  color: #67C23A;
}

.auto-save-status.failed {
  color: #F56C6C;
}

.auto-save-status .retry-link {
  cursor: pointer;
  text-decoration: underline;
}

.auto-save-status .retry-link:hover {
  color: #c45656;
}

/* 草稿历史版本样式 */
.draft-versions {
  max-height: 200px;
  overflow-y: auto;
}

.version-title {
  font-weight: 500;
  font-size: 13px;
  color: #303133;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.version-item {
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
  margin-bottom: 4px;
}

.version-item:hover {
  background-color: #ecf5ff;
}

.version-time {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 2px;
}

.version-preview {
  font-size: 12px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
