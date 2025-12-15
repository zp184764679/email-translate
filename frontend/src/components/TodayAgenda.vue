<template>
  <div class="today-agenda" :class="{ collapsed: isCollapsed }">
    <div class="agenda-header" @click="toggleCollapse">
      <div class="header-left">
        <el-icon><Calendar /></el-icon>
        <span class="header-title">今日日程</span>
        <el-badge v-if="todayEvents.length > 0" :value="todayEvents.length" class="event-count" />
      </div>
      <el-icon class="collapse-icon" :class="{ rotated: isCollapsed }">
        <ArrowDown />
      </el-icon>
    </div>

    <transition name="slide">
      <div v-show="!isCollapsed" class="agenda-content">
        <div v-if="loading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载中...</span>
        </div>

        <div v-else-if="todayEvents.length === 0" class="empty-state">
          <el-icon><Calendar /></el-icon>
          <span>今日暂无日程</span>
        </div>

        <div v-else class="event-list">
          <div
            v-for="event in todayEvents"
            :key="event.id"
            class="event-item"
            :style="{ borderLeftColor: event.color }"
            @click="goToCalendar(event)"
          >
            <div class="event-time">
              {{ formatTime(event.start_time) }}
            </div>
            <div class="event-info">
              <div class="event-title">
                <span v-if="event.is_recurring" class="recurring-icon">🔄</span>
                {{ event.title }}
              </div>
              <div v-if="event.location" class="event-location">
                <el-icon><Location /></el-icon>
                {{ event.location }}
              </div>
            </div>
            <el-icon v-if="event.email_id" class="email-link-icon" title="关联邮件">
              <Message />
            </el-icon>
          </div>
        </div>

        <div class="agenda-footer">
          <el-button text size="small" @click="goToCalendar()">
            查看完整日历
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Calendar, ArrowDown, ArrowRight, Loading, Location, Message } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()

// State
const todayEvents = ref([])
const loading = ref(false)
const isCollapsed = ref(false)

// Toggle collapse
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

// Format time
function formatTime(dateStr) {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// Load today's events
async function loadTodayEvents() {
  loading.value = true
  try {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const tomorrow = new Date(today)
    tomorrow.setDate(tomorrow.getDate() + 1)

    const result = await api.getCalendarEvents({
      start: today.toISOString(),
      end: tomorrow.toISOString()
    })

    // Sort by start time
    todayEvents.value = result.sort((a, b) =>
      new Date(a.start_time) - new Date(b.start_time)
    )
  } catch (e) {
    console.error('Failed to load today events:', e)
    todayEvents.value = []
  } finally {
    loading.value = false
  }
}

// Go to calendar page
function goToCalendar(event = null) {
  router.push('/calendar')
}

// Listen for calendar reminder events
function handleCalendarReminder(e) {
  // Refresh when a reminder is received
  loadTodayEvents()
}

// Auto refresh every 5 minutes
let refreshTimer = null

onMounted(() => {
  loadTodayEvents()

  // Auto refresh
  refreshTimer = setInterval(loadTodayEvents, 5 * 60 * 1000)

  // Listen for calendar events
  window.addEventListener('calendar-reminder', handleCalendarReminder)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
  window.removeEventListener('calendar-reminder', handleCalendarReminder)
})
</script>

<style scoped>
.today-agenda {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin: 16px;
  overflow: hidden;
}

.agenda-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
  color: #fff;
  cursor: pointer;
  user-select: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-weight: 600;
  font-size: 14px;
}

.event-count {
  margin-left: 4px;
}

.event-count :deep(.el-badge__content) {
  background-color: #fff;
  color: #409eff;
}

.collapse-icon {
  transition: transform 0.3s;
}

.collapse-icon.rotated {
  transform: rotate(-90deg);
}

.agenda-content {
  max-height: 300px;
  overflow-y: auto;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: #909399;
  font-size: 13px;
}

.event-list {
  padding: 8px;
}

.event-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  border-left: 3px solid #409eff;
  background: #f9fafc;
  cursor: pointer;
  transition: background-color 0.2s;
}

.event-item:hover {
  background: #f0f5ff;
}

.event-item:last-child {
  margin-bottom: 0;
}

.event-time {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  min-width: 45px;
}

.event-info {
  flex: 1;
  min-width: 0;
}

.event-title {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recurring-icon {
  font-size: 11px;
  margin-right: 2px;
}

.event-location {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.email-link-icon {
  flex-shrink: 0;
  color: #409eff;
  font-size: 14px;
}

.agenda-footer {
  padding: 8px 12px;
  border-top: 1px solid #ebeef5;
  text-align: center;
}

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: max-height 0.3s ease, opacity 0.3s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
