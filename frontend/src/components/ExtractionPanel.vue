<template>
  <div class="extraction-panel">
    <div class="panel-header">
      <h4>AI 智能提取</h4>
      <div class="header-actions">
        <el-button
          v-if="!extraction && !loading"
          type="primary"
          size="small"
          @click="doExtract"
        >
          <el-icon><MagicStick /></el-icon>
          开始提取
        </el-button>
        <el-button
          v-if="extraction && !loading"
          text
          size="small"
          @click="doExtract(true)"
        >
          <el-icon><Refresh /></el-icon>
          重新提取
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>正在分析邮件内容...</span>
    </div>

    <div v-else-if="extraction" class="extraction-content">
      <!-- 摘要 -->
      <div v-if="extraction.summary" class="section summary-section">
        <div class="section-title">
          <el-icon><Document /></el-icon>
          摘要
        </div>
        <div class="section-content">
          {{ extraction.summary }}
        </div>
      </div>

      <!-- 关键信息点 -->
      <div v-if="extraction.key_points?.length" class="section">
        <div class="section-title">
          <el-icon><Star /></el-icon>
          关键信息
        </div>
        <div class="section-content">
          <ul class="key-points-list">
            <li v-for="(point, i) in extraction.key_points" :key="i">
              {{ point }}
            </li>
          </ul>
        </div>
      </div>

      <!-- 日期/会议 -->
      <div v-if="extraction.dates?.length" class="section">
        <div class="section-title">
          <el-icon><Calendar /></el-icon>
          日期/会议
        </div>
        <div class="section-content">
          <div v-for="(date, i) in extraction.dates" :key="i" class="date-item">
            <el-tag :type="date.is_meeting ? 'danger' : 'info'" size="small">
              {{ date.date }}{{ date.time ? ' ' + date.time : '' }}
            </el-tag>
            <el-tag v-if="date.is_meeting" type="warning" size="small" class="meeting-tag">
              会议
            </el-tag>
            <span v-if="date.context" class="context">{{ date.context }}</span>
            <el-button
              text
              size="small"
              type="primary"
              @click="createEventFromDate(date)"
            >
              <el-icon><Plus /></el-icon>
              创建日程
            </el-button>
          </div>
        </div>
      </div>

      <!-- 公司内部参会人员 -->
      <div v-if="extraction.internal_attendees?.length" class="section">
        <div class="section-title">
          <el-icon><User /></el-icon>
          内部参会人员
        </div>
        <div class="section-content">
          <div class="attendees-list">
            <el-tag
              v-for="(attendee, i) in extraction.internal_attendees"
              :key="i"
              type="success"
              size="small"
              class="attendee-tag"
            >
              {{ attendee.name || attendee.email.split('@')[0] }}
            </el-tag>
          </div>
        </div>
      </div>

      <!-- 金额 -->
      <div v-if="extraction.amounts?.length" class="section">
        <div class="section-title">
          <el-icon><Money /></el-icon>
          金额
        </div>
        <div class="section-content">
          <div v-for="(amount, i) in extraction.amounts" :key="i" class="amount-item">
            <el-tag type="warning" size="small">
              {{ formatAmount(amount.amount, amount.currency) }}
            </el-tag>
            <span v-if="amount.context" class="context">{{ amount.context }}</span>
          </div>
        </div>
      </div>

      <!-- 联系人 -->
      <div v-if="extraction.contacts?.length" class="section">
        <div class="section-title">
          <el-icon><User /></el-icon>
          联系人
        </div>
        <div class="section-content">
          <div v-for="(contact, i) in extraction.contacts" :key="i" class="contact-item">
            <span class="contact-name">{{ contact.name || '未知' }}</span>
            <span v-if="contact.role" class="contact-role">（{{ contact.role }}）</span>
            <div v-if="contact.email || contact.phone" class="contact-details">
              <span v-if="contact.email">
                <el-icon><Message /></el-icon>
                {{ contact.email }}
              </span>
              <span v-if="contact.phone">
                <el-icon><Phone /></el-icon>
                {{ contact.phone }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 待办事项 -->
      <div v-if="extraction.action_items?.length" class="section">
        <div class="section-title">
          <el-icon><List /></el-icon>
          待办事项
        </div>
        <div class="section-content">
          <div v-for="(item, i) in extraction.action_items" :key="i" class="action-item">
            <el-tag
              :type="getPriorityType(item.priority)"
              size="small"
            >
              {{ getPriorityLabel(item.priority) }}
            </el-tag>
            <span class="task-text">{{ item.task }}</span>
            <span v-if="item.deadline" class="deadline">
              截止: {{ item.deadline }}
            </span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="isEmptyExtraction" class="empty-state">
        <el-icon><Warning /></el-icon>
        <span>未能提取到关键信息</span>
      </div>
    </div>

    <div v-else class="empty-state">
      <el-icon><InfoFilled /></el-icon>
      <span>点击"开始提取"分析邮件内容</span>
    </div>

    <!-- 创建日程弹窗 -->
    <el-dialog v-model="showEventDialog" title="创建日程" width="400px">
      <el-form :model="eventForm" label-width="60px">
        <el-form-item label="标题">
          <el-input v-model="eventForm.title" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker
            v-model="eventForm.date"
            type="datetime"
            placeholder="选择日期时间"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEventDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmCreateEvent">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  MagicStick, Refresh, Loading, Document, Star, Calendar,
  Money, User, Message, Phone, List, Warning, InfoFilled, Plus
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  emailId: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['event-created'])

// State
const loading = ref(false)
const extraction = ref(null)
const showEventDialog = ref(false)
const eventForm = ref({
  title: '',
  date: null
})

// Computed
const isEmptyExtraction = computed(() => {
  if (!extraction.value) return true
  return (
    !extraction.value.summary &&
    !extraction.value.key_points?.length &&
    !extraction.value.dates?.length &&
    !extraction.value.amounts?.length &&
    !extraction.value.contacts?.length &&
    !extraction.value.action_items?.length
  )
})

// Watch email change
watch(() => props.emailId, async (newId) => {
  if (newId) {
    await loadExtraction()
  }
}, { immediate: true })

// Load existing extraction
async function loadExtraction() {
  try {
    const result = await api.getExtraction(props.emailId)
    extraction.value = result
  } catch (e) {
    // 404 is expected if no extraction exists
    if (e.response?.status !== 404) {
      console.error('Failed to load extraction:', e)
    }
    extraction.value = null
  }
}

// Do extraction
async function doExtract(force = false) {
  loading.value = true
  try {
    const result = await api.extractEmail(props.emailId, force)
    extraction.value = result
    ElMessage.success('提取完成')
  } catch (e) {
    // 提取失败时清除旧数据，避免显示过期信息
    extraction.value = null
    const errorMsg = e.response?.data?.detail || '提取失败'
    ElMessage.error(errorMsg)
    console.error('Extraction failed:', e)
  } finally {
    loading.value = false
  }
}

// Format amount with validation
function formatAmount(amount, currency) {
  try {
    const numAmount = Number(amount)
    if (!isFinite(numAmount)) {
      return '无效金额'
    }
    const currencySymbols = {
      'USD': '$',
      'EUR': '€',
      'CNY': '¥',
      'RMB': '¥',
      'GBP': '£',
      'JPY': '¥'
    }
    const symbol = currencySymbols[String(currency || '').toUpperCase()] || currency || ''
    return `${symbol}${numAmount.toLocaleString()}`
  } catch (e) {
    console.error('Amount formatting failed:', amount, currency)
    return '金额无效'
  }
}

// Priority helpers
function getPriorityType(priority) {
  const types = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'info'
  }
  return types[priority] || 'info'
}

function getPriorityLabel(priority) {
  const labels = {
    'high': '高',
    'medium': '中',
    'low': '低'
  }
  return labels[priority] || '中'
}

// Create event from date with validation
function createEventFromDate(dateInfo) {
  try {
    // 解析日期和时间
    let dateString = dateInfo.date
    if (dateInfo.time) {
      dateString += 'T' + dateInfo.time + ':00'
    }
    const parsedDate = new Date(dateString)

    // 验证日期有效性
    if (isNaN(parsedDate.getTime())) {
      ElMessage.warning('日期格式不正确，请手动选择时间')
      eventForm.value = {
        title: dateInfo.context || '日程事件',
        date: new Date(), // 使用当前时间作为默认值
        description: ''
      }
    } else {
      // 构建描述，包含参会人员
      let description = ''
      if (extraction.value?.internal_attendees?.length) {
        const attendeeNames = extraction.value.internal_attendees
          .map(a => a.name || a.email.split('@')[0])
          .join('、')
        description = `参会人员：${attendeeNames}`
      }

      eventForm.value = {
        title: dateInfo.is_meeting ? `会议: ${dateInfo.context || '待定'}` : (dateInfo.context || '日程事件'),
        date: parsedDate,
        description: description
      }
    }
    showEventDialog.value = true
  } catch (e) {
    console.error('Invalid date:', dateInfo.date, e)
    ElMessage.error('日期解析失败')
  }
}

// Confirm create event
async function confirmCreateEvent() {
  if (!eventForm.value.title || !eventForm.value.date) {
    ElMessage.warning('请填写标题和时间')
    return
  }

  try {
    const startTime = new Date(eventForm.value.date)
    // 验证日期有效性
    if (isNaN(startTime.getTime())) {
      ElMessage.warning('请选择有效的时间')
      return
    }
    const endTime = new Date(startTime.getTime() + 60 * 60 * 1000) // +1 hour

    await api.createEventFromEmail(props.emailId, {
      title: eventForm.value.title,
      description: eventForm.value.description || '',
      start_time: startTime.toISOString(),
      end_time: endTime.toISOString()
    })

    ElMessage.success('日程已创建')
    showEventDialog.value = false
    emit('event-created')
  } catch (e) {
    const errorMsg = e.response?.data?.detail || '创建失败'
    ElMessage.error(errorMsg)
    console.error('Create event failed:', e)
  }
}
</script>

<style scoped>
.extraction-panel {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #909399;
  font-size: 13px;
}

.loading-state .el-icon {
  font-size: 20px;
}

.extraction-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section {
  background: #fff;
  border-radius: 6px;
  padding: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 8px;
}

.section-content {
  font-size: 13px;
  color: #303133;
}

.summary-section .section-content {
  line-height: 1.6;
}

.key-points-list {
  margin: 0;
  padding-left: 20px;
}

.key-points-list li {
  margin-bottom: 4px;
}

.date-item,
.amount-item,
.action-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.context {
  color: #909399;
  font-size: 12px;
}

.meeting-tag {
  margin-left: -4px;
}

.attendees-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.attendee-tag {
  border-radius: 4px;
}

.contact-item {
  margin-bottom: 8px;
}

.contact-name {
  font-weight: 500;
}

.contact-role {
  color: #909399;
  font-size: 12px;
}

.contact-details {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
}

.contact-details span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-text {
  flex: 1;
}

.deadline {
  font-size: 12px;
  color: #e6a23c;
}
</style>
