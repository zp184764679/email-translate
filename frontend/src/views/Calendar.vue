<template>
  <div class="calendar-container">
    <div class="calendar-header">
      <h2>日历</h2>
      <el-button type="primary" @click="openEventDialog()">
        <el-icon><Plus /></el-icon>
        新建事件
      </el-button>
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
import { Plus } from '@element-plus/icons-vue'
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

// Event form
const eventForm = ref({
  title: '',
  dateRange: [],
  allDay: false,
  location: '',
  description: '',
  color: '#409EFF',
  reminderMinutes: 15
})

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

    const result = await api.getCalendarEvents(params)
    events.value = result

    // Update calendar events
    calendarOptions.events = result.map(event => ({
      id: event.id,
      title: event.title,
      start: event.start_time,
      end: event.end_time,
      allDay: event.all_day,
      backgroundColor: event.color,
      borderColor: event.color,
      extendedProps: {
        description: event.description,
        location: event.location,
        reminderMinutes: event.reminder_minutes,
        emailId: event.email_id
      }
    }))
  } catch (e) {
    console.error('Failed to load events:', e)
  }
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
  editingEvent.value = {
    id: event.id,
    title: event.title,
    start: event.start,
    end: event.end,
    allDay: event.allDay,
    ...event.extendedProps
  }

  eventForm.value = {
    title: event.title,
    dateRange: [event.start, event.end || event.start],
    allDay: event.allDay,
    location: event.extendedProps.location || '',
    description: event.extendedProps.description || '',
    color: event.backgroundColor || '#409EFF',
    reminderMinutes: event.extendedProps.reminderMinutes || 15
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
    editingEvent.value = event
    eventForm.value = {
      title: event.title,
      dateRange: [event.start, event.end || event.start],
      allDay: event.allDay,
      location: event.location || '',
      description: event.description || '',
      color: event.color || '#409EFF',
      reminderMinutes: event.reminderMinutes || 15
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
      reminderMinutes: 15
    }
  }

  showEventDialog.value = true
}

// Reset form
function resetEventForm() {
  editingEvent.value = null
  eventForm.value = {
    title: '',
    dateRange: [],
    allDay: false,
    location: '',
    description: '',
    color: '#409EFF',
    reminderMinutes: 15
  }
}

// Save event
async function saveEvent() {
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
      reminder_minutes: eventForm.value.reminderMinutes
    }

    if (editingEvent.value) {
      await api.updateCalendarEvent(editingEvent.value.id, data)
      ElMessage.success('事件已更新')
    } else {
      await api.createCalendarEvent(data)
      ElMessage.success('事件已创建')
    }

    showEventDialog.value = false
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
