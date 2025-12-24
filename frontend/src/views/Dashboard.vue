<template>
  <div class="dashboard-container">
    <div class="dashboard-header">
      <h1>仪表盘</h1>
      <el-button :icon="Refresh" :loading="loading" @click="loadData">
        刷新
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <el-card class="stat-card" shadow="hover" @click="goToEmails('today')">
        <div class="stat-icon today">
          <el-icon><Calendar /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.today_count }}</div>
          <div class="stat-label">今日新邮件</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover" @click="goToEmails('unread')">
        <div class="stat-icon unread">
          <el-icon><Message /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.unread_count }}</div>
          <div class="stat-label">未读邮件</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover" @click="goToEmails('untranslated')">
        <div class="stat-icon pending">
          <el-icon><DocumentCopy /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.pending_translation }}</div>
          <div class="stat-label">待翻译</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover" @click="goToApprovals">
        <div class="stat-icon approval">
          <el-icon><Checked /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.pending_approval }}</div>
          <div class="stat-label">待审批</div>
        </div>
      </el-card>
    </div>

    <!-- 图表区域 -->
    <div class="chart-row">
      <el-card class="chart-card">
        <template #header>
          <span>翻译进度</span>
        </template>
        <div class="chart-container">
          <v-chart :option="translationChartOption" autoresize />
        </div>
      </el-card>

      <el-card class="chart-card">
        <template #header>
          <span>近7天邮件趋势</span>
        </template>
        <div class="chart-container">
          <v-chart :option="trendChartOption" autoresize />
        </div>
      </el-card>
    </div>

    <!-- 底部区域 -->
    <div class="bottom-row">
      <el-card class="recent-card">
        <template #header>
          <div class="card-header">
            <span>最近邮件</span>
            <el-button text @click="goToEmails()">查看全部</el-button>
          </div>
        </template>
        <div class="recent-emails">
          <div
            v-for="email in recentEmails"
            :key="email.id"
            class="email-item"
            @click="goToEmail(email.id)"
          >
            <div class="email-status">
              <span v-if="!email.is_read" class="unread-dot"></span>
            </div>
            <div class="email-content">
              <div class="email-subject">{{ email.subject }}</div>
              <div class="email-meta">
                <span class="email-from">{{ email.from_email }}</span>
                <span class="email-time">{{ formatTime(email.received_at) }}</span>
              </div>
            </div>
            <el-tag v-if="email.is_translated" type="success" size="small">已翻译</el-tag>
            <el-tag v-else type="warning" size="small">未翻译</el-tag>
          </div>
          <el-empty v-if="recentEmails.length === 0" description="暂无邮件" :image-size="60" />
        </div>
      </el-card>

      <el-card class="agenda-card">
        <template #header>
          <div class="card-header">
            <span>今日日程</span>
            <el-button text @click="goToCalendar">查看全部</el-button>
          </div>
        </template>
        <div class="today-events">
          <div
            v-for="event in todayEvents"
            :key="event.id"
            class="event-item"
            @click="goToCalendar"
          >
            <div class="event-time">
              <span v-if="event.is_all_day">全天</span>
              <span v-else>{{ formatEventTime(event.start_time) }}</span>
            </div>
            <div class="event-content">
              <div class="event-title">{{ event.title }}</div>
              <div v-if="event.location" class="event-location">
                <el-icon><Location /></el-icon>
                {{ event.location }}
              </div>
            </div>
          </div>
          <el-empty v-if="todayEvents.length === 0" description="今日无日程" :image-size="60" />
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Calendar, Message, DocumentCopy, Checked, Location } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import api from '@/api'
import { ElMessage } from 'element-plus'

// Register ECharts components
use([
  CanvasRenderer,
  PieChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const router = useRouter()

// State
const loading = ref(false)
const stats = ref({
  today_count: 0,
  unread_count: 0,
  pending_translation: 0,
  pending_approval: 0
})
const translationStats = ref({
  translated: 0,
  untranslated: 0,
  translating: 0,
  failed: 0
})
const weeklyTrend = ref([])
const recentEmails = ref([])
const todayEvents = ref([])

// Chart options
const translationChartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} ({d}%)'
  },
  legend: {
    orient: 'horizontal',
    bottom: 10
  },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: false
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      data: [
        { value: translationStats.value.translated, name: '已翻译', itemStyle: { color: '#67c23a' } },
        { value: translationStats.value.untranslated, name: '未翻译', itemStyle: { color: '#e6a23c' } },
        { value: translationStats.value.translating, name: '翻译中', itemStyle: { color: '#409eff' } },
        { value: translationStats.value.failed, name: '失败', itemStyle: { color: '#f56c6c' } }
      ].filter(item => item.value > 0)
    }
  ]
}))

const trendChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis'
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: weeklyTrend.value.map(item => item.date)
  },
  yAxis: {
    type: 'value',
    minInterval: 1
  },
  series: [
    {
      name: '邮件数量',
      type: 'line',
      smooth: true,
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
          ]
        }
      },
      lineStyle: {
        color: '#409eff',
        width: 2
      },
      itemStyle: {
        color: '#409eff'
      },
      data: weeklyTrend.value.map(item => item.count)
    }
  ]
}))

// Load data
async function loadData() {
  loading.value = true
  try {
    const data = await api.getDashboardStats()
    stats.value = data.stats
    translationStats.value = data.translation_stats
    weeklyTrend.value = data.weekly_trend
    recentEmails.value = data.recent_emails
    todayEvents.value = data.today_events
  } catch (e) {
    console.error('Failed to load dashboard data:', e)
    ElMessage.error('加载仪表盘数据失败')
  } finally {
    loading.value = false
  }
}

// Navigation
function goToEmails(filter) {
  if (filter === 'today') {
    router.push('/emails?date=today')
  } else if (filter === 'unread') {
    router.push('/emails?is_read=false')
  } else if (filter === 'untranslated') {
    router.push('/emails?is_translated=false')
  } else {
    router.push('/emails')
  }
}

function goToEmail(id) {
  router.push(`/emails/${id}`)
}

function goToApprovals() {
  router.push('/approvals')
}

function goToCalendar() {
  router.push('/calendar')
}

// Formatters
function formatTime(dateStr) {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`

  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function formatEventTime(dateStr) {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.dashboard-container {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.dashboard-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}

/* Stat Cards */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-icon.today {
  background-color: #e6f4ff;
  color: #1677ff;
}

.stat-icon.unread {
  background-color: #fff7e6;
  color: #fa8c16;
}

.stat-icon.pending {
  background-color: #f6ffed;
  color: #52c41a;
}

.stat-icon.approval {
  background-color: #fff1f0;
  color: #ff4d4f;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-top: 4px;
}

/* Chart Row */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.chart-card :deep(.el-card__header) {
  font-weight: 600;
  padding: 16px 20px;
}

.chart-container {
  height: 280px;
}

/* Bottom Row */
.bottom-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.recent-card :deep(.el-card__body),
.agenda-card :deep(.el-card__body) {
  padding: 0;
  max-height: 320px;
  overflow-y: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Email Items */
.email-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.email-item:last-child {
  border-bottom: none;
}

.email-item:hover {
  background-color: #f5f7fa;
}

.email-status {
  width: 8px;
}

.unread-dot {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #409eff;
}

.email-content {
  flex: 1;
  min-width: 0;
}

.email-subject {
  font-size: 14px;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.email-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.email-from {
  max-width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Event Items */
.event-item {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.event-item:last-child {
  border-bottom: none;
}

.event-item:hover {
  background-color: #f5f7fa;
}

.event-time {
  min-width: 50px;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}

.event-content {
  flex: 1;
}

.event-title {
  font-size: 14px;
  color: #1a1a1a;
}

.event-location {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

/* Responsive */
@media (max-width: 1200px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .chart-row,
  .bottom-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stat-cards {
    grid-template-columns: 1fr;
  }
}
</style>
