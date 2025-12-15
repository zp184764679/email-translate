<template>
  <div class="calendar-container">
    <div class="calendar-header">
      <h2>日历</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索事件..."
          clearable
          prefix-icon="Search"
          class="search-input"
          @keyup.enter="handleSearch"
          @clear="handleClearSearch"
        />
        <el-button type="primary" @click="openEventDialog()">
          <el-icon><Plus /></el-icon>
          新建事件
        </el-button>
      </div>
    </div>

    <div class="calendar-content">
      <FullCalendar
        ref="calendarRef"
        :options="calendarOptions"
      />
    </div>

    <!-- 事件编辑弹窗 -->
    <el-dialog
      v-model="showEventDialog"
      :title="editingEvent ? '编辑事件' : '新建事件'"
      width="500px"
      @close="resetEventForm"
    >
      <el-form :model="eventForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="eventForm.title" placeholder="请输入事件标题" />
        </el-form-item>

        <el-form-item label="时间">
          <el-date-picker
            v-model="eventForm.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>

        <el-form-item label="全天事件">
          <el-switch v-model="eventForm.allDay" />
        </el-form-item>

        <el-form-item label="地点">
          <el-input v-model="eventForm.location" placeholder="可选" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input
            v-model="eventForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选"
          />
        </el-form-item>

        <el-form-item label="颜色">
          <el-color-picker v-model="eventForm.color" />
        </el-form-item>

        <el-form-item label="提醒">
          <el-select v-model="eventForm.reminderMinutes" placeholder="提前提醒">
            <el-option label="不提醒" :value="0" />
            <el-option label="5 分钟前" :value="5" />
            <el-option label="15 分钟前" :value="15" />
            <el-option label="30 分钟前" :value="30" />
            <el-option label="1 小时前" :value="60" />
            <el-option label="1 天前" :value="1440" />
          </el-select>
        </el-form-item>

        <el-form-item label="重复">
          <el-select v-model="eventForm.recurrenceType" placeholder="不重复" @change="handleRecurrenceTypeChange">
            <el-option label="不重复" value="" />
            <el-option label="每天" value="DAILY" />
            <el-option label="每周" value="WEEKLY" />
            <el-option label="每月" value="MONTHLY" />
            <el-option label="每年" value="YEARLY" />
          </el-select>
        </el-form-item>

        <!-- 每周重复的星期选择 -->
        <el-form-item v-if="eventForm.recurrenceType === 'WEEKLY'" label="重复日">
          <el-checkbox-group v-model="eventForm.recurrenceWeekdays">
            <el-checkbox label="MO">周一</el-checkbox>
            <el-checkbox label="TU">周二</el-checkbox>
            <el-checkbox label="WE">周三</el-checkbox>
            <el-checkbox label="TH">周四</el-checkbox>
            <el-checkbox label="FR">周五</el-checkbox>
            <el-checkbox label="SA">周六</el-checkbox>
            <el-checkbox label="SU">周日</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <!-- 重复结束日期 -->
        <el-form-item v-if="eventForm.recurrenceType" label="结束日期">
          <el-date-picker
            v-model="eventForm.recurrenceEnd"
            type="date"
            placeholder="永不结束"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DDT23:59:59"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button v-if="editingEvent" type="danger" @click="deleteEvent" :loading="deleting">
            删除
          </el-button>
          <div style="flex: 1"></div>
          <el-button @click="showEventDialog = false">取消</el-button>
          <el-button type="primary" @click="saveEvent" :loading="saving">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import api from '@/api'

// Calendar ref
const calendarRef = ref(null)

// State
const events = ref([])
const showEventDialog = ref(false)
const editingEvent = ref(null)
const saving = ref(false)
const deleting = ref(false)
const conflictWarning = ref(null)  // 冲突警告信息
const searchKeyword = ref('')  // 搜索关键词

// Event form
const eventForm = ref({
  title: '',
  dateRange: [],
  allDay: false,
  location: '',
  description: '',
  color: '#409EFF',
  reminderMinutes: 15,
  // 重复事件字段
  recurrenceType: '',  // '', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'
  recurrenceWeekdays: [],  // ['MO', 'TU', 'WE', 'TH', 'FR']
  recurrenceEnd: null
})

// 处理重复类型变化
function handleRecurrenceTypeChange(type) {
  if (type === 'WEEKLY' && eventForm.value.recurrenceWeekdays.length === 0) {
    // 默认选择当前日期的星期
    const dayMap = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA']
    if (eventForm.value.dateRange && eventForm.value.dateRange[0]) {
      const startDay = new Date(eventForm.value.dateRange[0]).getDay()
      eventForm.value.recurrenceWeekdays = [dayMap[startDay]]
    }
  }
}

// 生成 RRULE 字符串
function buildRecurrenceRule() {
  if (!eventForm.value.recurrenceType) return null

  let rule = `FREQ=${eventForm.value.recurrenceType}`

  // 每周重复需要指定星期
  if (eventForm.value.recurrenceType === 'WEEKLY' && eventForm.value.recurrenceWeekdays.length > 0) {
    rule += `;BYDAY=${eventForm.value.recurrenceWeekdays.join(',')}`
  }

  return rule
}

// 解析 RRULE 字符串
function parseRecurrenceRule(rule) {
  if (!rule) {
    return { type: '', weekdays: [], end: null }
  }

  const parts = rule.split(';')
  let type = ''
  let weekdays = []

  for (const part of parts) {
    if (part.startsWith('FREQ=')) {
      type = part.replace('FREQ=', '')
    } else if (part.startsWith('BYDAY=')) {
      weekdays = part.replace('BYDAY=', '').split(',')
    }
  }

  return { type, weekdays }
}

// Calendar options
const calendarOptions = reactive({
  plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
  initialView: 'dayGridMonth',
  locale: 'zh-cn',
  headerToolbar: {
    left: 'prev,today,next',
    center: 'title',
    right: 'dayGridMonth,timeGridWeek,timeGridDay'
  },
  buttonText: {
    today: '今天',
    month: '月',
    week: '周',
    day: '日'
  },
  events: [],
  editable: true,
  selectable: true,
  selectMirror: true,
  dayMaxEvents: true,
  weekends: true,
  height: 'auto',

  // Event handlers
  select: handleDateSelect,
  eventClick: handleEventClick,
  eventDrop: handleEventDrop,
  eventResize: handleEventResize,
  datesSet: handleDatesSet
})

// Load events
async function loadEvents(start, end) {
  try {
    const params = {}
    if (start) params.start = start
    if (end) params.end = end
    if (searchKeyword.value.trim()) params.search = searchKeyword.value.trim()

    const result = await api.getCalendarEvents(params)
    events.value = result

    // Update calendar events
    calendarOptions.events = result.map(event => ({
      id: event.is_recurring ? `${event.id}-${event.start_time}` : event.id,  // 重复实例使用组合ID
      title: event.is_recurring ? `🔄 ${event.title}` : event.title,  // 重复事件添加图标
      start: event.start_time,
      end: event.end_time,
      allDay: event.all_day,
      backgroundColor: event.color,
      borderColor: event.color,
      extendedProps: {
        description: event.description,
        location: event.location,
        reminderMinutes: event.reminder_minutes,
        emailId: event.email_id,
        recurrenceRule: event.recurrence_rule,
        recurrenceEnd: event.recurrence_end,
        isRecurring: event.is_recurring,
        parentEventId: event.parent_event_id,
        originalId: event.id  // 保存原始ID用于编辑
      }
    }))
  } catch (e) {
    console.error('Failed to load events:', e)
  }
}

// Search handlers
function handleSearch() {
  const calendarApi = calendarRef.value?.getApi()
  if (calendarApi) {
    const view = calendarApi.view
    loadEvents(view.activeStart.toISOString(), view.activeEnd.toISOString())
  }
}

function handleClearSearch() {
  searchKeyword.value = ''
  handleSearch()
}

// Handle date range change
function handleDatesSet(info) {
  loadEvents(info.startStr, info.endStr)
}

// Handle date selection (create new event)
function handleDateSelect(selectInfo) {
  openEventDialog(null, selectInfo.start, selectInfo.end, selectInfo.allDay)
}

// Handle event click (edit event)
function handleEventClick(clickInfo) {
  const event = clickInfo.event
  const originalId = event.extendedProps.originalId || event.id

  editingEvent.value = {
    id: originalId,  // 使用原始ID进行编辑
    title: event.title.replace('🔄 ', ''),  // 移除重复图标
    start: event.start,
    end: event.end,
    allDay: event.allDay,
    ...event.extendedProps
  }

  // 解析重复规则
  const recurrence = parseRecurrenceRule(event.extendedProps.recurrenceRule)

  eventForm.value = {
    title: event.title.replace('🔄 ', ''),
    dateRange: [event.start, event.end || event.start],
    allDay: event.allDay,
    location: event.extendedProps.location || '',
    description: event.extendedProps.description || '',
    color: event.backgroundColor || '#409EFF',
    reminderMinutes: event.extendedProps.reminderMinutes || 15,
    recurrenceType: recurrence.type,
    recurrenceWeekdays: recurrence.weekdays,
    recurrenceEnd: event.extendedProps.recurrenceEnd || null
  }

  showEventDialog.value = true
}

// Handle event drag & drop
async function handleEventDrop(info) {
  try {
    const newStartTime = info.event.start.toISOString()
    const newEndTime = (info.event.end || info.event.start).toISOString()

    await api.updateCalendarEvent(info.event.id, {
      start_time: newStartTime,
      end_time: newEndTime
    })

    // 同步本地状态
    const eventIndex = events.value.findIndex(e => e.id == info.event.id)
    if (eventIndex > -1) {
      events.value[eventIndex].start_time = newStartTime
      events.value[eventIndex].end_time = newEndTime
    }

    ElMessage.success('事件已更新')
  } catch (e) {
    info.revert()
    const errorMsg = e.response?.data?.detail || '更新失败'
    ElMessage.error(errorMsg)
    console.error('Event drop failed:', e)
  }
}

// Handle event resize
async function handleEventResize(info) {
  try {
    const newStartTime = info.event.start.toISOString()
    const newEndTime = info.event.end.toISOString()

    await api.updateCalendarEvent(info.event.id, {
      start_time: newStartTime,
      end_time: newEndTime
    })

    // 同步本地状态
    const eventIndex = events.value.findIndex(e => e.id == info.event.id)
    if (eventIndex > -1) {
      events.value[eventIndex].start_time = newStartTime
      events.value[eventIndex].end_time = newEndTime
    }

    ElMessage.success('事件已更新')
  } catch (e) {
    info.revert()
    const errorMsg = e.response?.data?.detail || '更新失败'
    ElMessage.error(errorMsg)
    console.error('Event resize failed:', e)
  }
}

// Open event dialog
function openEventDialog(event = null, start = null, end = null, allDay = false) {
  if (event) {
    // 解析重复规则
    const recurrence = parseRecurrenceRule(event.recurrenceRule)

    editingEvent.value = event
    eventForm.value = {
      title: event.title,
      dateRange: [event.start, event.end || event.start],
      allDay: event.allDay,
      location: event.location || '',
      description: event.description || '',
      color: event.color || '#409EFF',
      reminderMinutes: event.reminderMinutes || 15,
      recurrenceType: recurrence.type,
      recurrenceWeekdays: recurrence.weekdays,
      recurrenceEnd: event.recurrenceEnd || null
    }
  } else {
    editingEvent.value = null
    const now = start || new Date()
    const endTime = end || new Date(now.getTime() + 60 * 60 * 1000)
    eventForm.value = {
      title: '',
      dateRange: [now, endTime],
      allDay: allDay,
      location: '',
      description: '',
      color: '#409EFF',
      reminderMinutes: 15,
      recurrenceType: '',
      recurrenceWeekdays: [],
      recurrenceEnd: null
    }
  }

  showEventDialog.value = true
}

// Reset form
function resetEventForm() {
  editingEvent.value = null
  conflictWarning.value = null
  eventForm.value = {
    title: '',
    dateRange: [],
    allDay: false,
    location: '',
    description: '',
    color: '#409EFF',
    reminderMinutes: 15,
    recurrenceType: '',
    recurrenceWeekdays: [],
    recurrenceEnd: null
  }
}

// Check for conflicts
async function checkConflicts() {
  if (!eventForm.value.dateRange || eventForm.value.dateRange.length < 2) {
    conflictWarning.value = null
    return
  }

  try {
    const result = await api.checkEventConflicts(
      eventForm.value.dateRange[0],
      eventForm.value.dateRange[1],
      editingEvent.value?.id || null
    )

    if (result.has_conflict) {
      conflictWarning.value = result.conflicts
    } else {
      conflictWarning.value = null
    }
  } catch (e) {
    console.error('Failed to check conflicts:', e)
    conflictWarning.value = null
  }
}

// Save event
async function saveEvent(forceIgnoreConflict = false) {
  if (!eventForm.value.title.trim()) {
    ElMessage.warning('请输入事件标题')
    return
  }

  if (!eventForm.value.dateRange || eventForm.value.dateRange.length < 2 ||
      !eventForm.value.dateRange[0] || !eventForm.value.dateRange[1]) {
    ElMessage.warning('请选择完整的事件时间')
    return
  }

  // 验证时间顺序
  const startTime = new Date(eventForm.value.dateRange[0])
  const endTime = new Date(eventForm.value.dateRange[1])
  if (startTime > endTime) {
    ElMessage.warning('结束时间不能早于开始时间')
    return
  }

  // 验证每周重复必须选择至少一天
  if (eventForm.value.recurrenceType === 'WEEKLY' && eventForm.value.recurrenceWeekdays.length === 0) {
    ElMessage.warning('每周重复请至少选择一天')
    return
  }

  // 检查冲突（如果没有强制忽略）
  if (!forceIgnoreConflict) {
    await checkConflicts()
    if (conflictWarning.value && conflictWarning.value.length > 0) {
      // 有冲突，询问用户是否继续
      try {
        const conflictTitles = conflictWarning.value.map(c => c.title).join('、')
        await ElMessageBox.confirm(
          `与以下事件时间冲突：${conflictTitles}。是否仍然创建？`,
          '时间冲突',
          {
            confirmButtonText: '仍然创建',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
      } catch {
        return  // 用户取消
      }
    }
  }

  saving.value = true
  try {
    const data = {
      title: eventForm.value.title,
      start_time: eventForm.value.dateRange[0],
      end_time: eventForm.value.dateRange[1],
      all_day: eventForm.value.allDay,
      location: eventForm.value.location || null,
      description: eventForm.value.description || null,
      color: eventForm.value.color,
      reminder_minutes: eventForm.value.reminderMinutes,
      recurrence_rule: buildRecurrenceRule(),
      recurrence_end: eventForm.value.recurrenceEnd || null
    }

    if (editingEvent.value) {
      await api.updateCalendarEvent(editingEvent.value.id, data)
      ElMessage.success('事件已更新')
    } else {
      await api.createCalendarEvent(data)
      ElMessage.success('事件已创建')
    }

    showEventDialog.value = false
    conflictWarning.value = null
    // Refresh calendar
    const calendarApi = calendarRef.value.getApi()
    calendarApi.refetchEvents()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Delete event
async function deleteEvent() {
  if (!editingEvent.value) return

  try {
    await ElMessageBox.confirm(
      '确定要删除这个事件吗？',
      '删除事件',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    deleting.value = true
    await api.deleteCalendarEvent(editingEvent.value.id)
    ElMessage.success('事件已删除')
    showEventDialog.value = false

    // Refresh calendar
    const calendarApi = calendarRef.value.getApi()
    calendarApi.refetchEvents()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  } finally {
    deleting.value = false
  }
}

// Initialize
onMounted(() => {
  // Events will be loaded by datesSet callback
})
</script>

<style scoped>
.calendar-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  background-color: #fff;
  overflow: auto;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.calendar-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  width: 220px;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.calendar-content {
  flex: 1;
}

.dialog-footer {
  display: flex;
  align-items: center;
}

/* FullCalendar custom styles */
:deep(.fc) {
  font-family: inherit;
}

:deep(.fc-toolbar-title) {
  font-size: 18px !important;
  font-weight: 600;
}

:deep(.fc-button) {
  font-size: 13px !important;
}

:deep(.fc-event) {
  cursor: pointer;
  border-radius: 4px;
  padding: 2px 4px;
}

:deep(.fc-daygrid-event) {
  font-size: 12px;
}

:deep(.fc-timegrid-event) {
  font-size: 12px;
}

:deep(.fc-day-today) {
  background-color: #f0f9ff !important;
}

:deep(.fc-highlight) {
  background-color: #e6f7ff !important;
}
</style>
