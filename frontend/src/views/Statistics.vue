<template>
  <div class="statistics-container">
    <!-- 顶部统计卡片 -->
    <el-row :gutter="20" class="stats-cards">
      <el-col :span="6" v-for="card in overviewCards" :key="card.title">
        <el-card shadow="hover" class="stat-card" :style="{ borderTop: `3px solid ${card.color}` }">
          <div class="stat-content">
            <div class="stat-icon" :style="{ backgroundColor: card.color + '20', color: card.color }">
              <el-icon :size="24"><component :is="card.icon" /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ card.value }}</div>
              <div class="stat-label">{{ card.title }}</div>
            </div>
          </div>
          <div class="stat-footer" v-if="card.subtext">
            <span :class="card.trend > 0 ? 'trend-up' : card.trend < 0 ? 'trend-down' : ''">
              {{ card.subtext }}
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-row">
      <!-- 邮件趋势图 -->
      <el-col :span="16">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span>邮件趋势</span>
              <el-radio-group v-model="trendPeriod" size="small" @change="loadEmailTrend">
                <el-radio-button label="daily">日</el-radio-button>
                <el-radio-button label="weekly">周</el-radio-button>
                <el-radio-button label="monthly">月</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <v-chart class="chart" :option="trendChartOption" autoresize />
        </el-card>
      </el-col>

      <!-- 翻译引擎使用分布 -->
      <el-col :span="8">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span>翻译引擎分布</span>
          </template>
          <v-chart class="chart" :option="engineChartOption" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <!-- 供应商排行 -->
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span>供应商邮件量排行</span>
              <el-select v-model="rankingDays" size="small" style="width: 100px" @change="loadSupplierRanking">
                <el-option :value="7" label="近7天" />
                <el-option :value="30" label="近30天" />
                <el-option :value="90" label="近90天" />
              </el-select>
            </div>
          </template>
          <v-chart class="chart" :option="rankingChartOption" autoresize />
        </el-card>
      </el-col>

      <!-- 邮件分类分布 -->
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span>邮件分类分布</span>
          </template>
          <v-chart class="chart" :option="categoryChartOption" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <!-- 响应时间分析 -->
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span>响应时间分析</span>
          </template>
          <div class="response-time-stats" v-if="responseTimeData">
            <div class="time-stat">
              <div class="time-value">{{ formatHours(responseTimeData.avg_response_hours) }}</div>
              <div class="time-label">平均响应</div>
            </div>
            <div class="time-stat">
              <div class="time-value">{{ formatHours(responseTimeData.min_response_hours) }}</div>
              <div class="time-label">最快响应</div>
            </div>
            <div class="time-stat">
              <div class="time-value">{{ formatHours(responseTimeData.max_response_hours) }}</div>
              <div class="time-label">最慢响应</div>
            </div>
          </div>
          <v-chart class="chart chart-small" :option="responseChartOption" autoresize />
        </el-card>
      </el-col>

      <!-- 缓存统计 -->
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span>翻译缓存统计</span>
          </template>
          <div class="cache-stats" v-if="cacheData">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-statistic title="缓存条目" :value="cacheData.total_entries" />
              </el-col>
              <el-col :span="8">
                <el-statistic title="总命中次数" :value="cacheData.total_hits" />
              </el-col>
              <el-col :span="8">
                <el-statistic title="节省API调用" :value="cacheData.api_calls_saved" />
              </el-col>
            </el-row>
            <el-divider />
            <div class="top-cached">
              <div class="section-title">热门缓存</div>
              <el-table :data="cacheData.top_cached" size="small" max-height="200">
                <el-table-column prop="text" label="文本" show-overflow-tooltip />
                <el-table-column prop="hit_count" label="命中" width="80" align="center" />
                <el-table-column prop="target_lang" label="语言" width="60" align="center" />
              </el-table>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 活动热力图 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span>每日活动热力图</span>
          </template>
          <v-chart class="chart heatmap-chart" :option="heatmapChartOption" autoresize />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart, BarChart, HeatmapChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent
} from 'echarts/components'
import VChart from 'vue-echarts'
import {
  Message,
  Document,
  Promotion,
  UserFilled,
  TrendCharts,
  Clock
} from '@element-plus/icons-vue'
import api from '@/api'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  LineChart,
  PieChart,
  BarChart,
  HeatmapChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent
])

// 数据状态
const loading = ref(false)
const overviewData = ref(null)
const trendData = ref([])
const engineData = ref([])
const rankingData = ref([])
const categoryData = ref([])
const responseTimeData = ref(null)
const cacheData = ref(null)
const heatmapData = ref([])

// 筛选条件
const trendPeriod = ref('daily')
const rankingDays = ref(30)

// 概览卡片
const overviewCards = computed(() => {
  const data = overviewData.value || {}
  return [
    {
      title: '总邮件数',
      value: data.total_emails || 0,
      icon: Message,
      color: '#409EFF',
      subtext: `今日 +${data.today_emails || 0}`
    },
    {
      title: '未读邮件',
      value: data.unread_emails || 0,
      icon: Document,
      color: '#E6A23C',
      subtext: `待处理`
    },
    {
      title: '已翻译',
      value: data.translated_emails || 0,
      icon: Promotion,
      color: '#67C23A',
      subtext: `${data.total_emails ? Math.round(data.translated_emails / data.total_emails * 100) : 0}%`
    },
    {
      title: '供应商',
      value: data.total_suppliers || 0,
      icon: UserFilled,
      color: '#909399',
      subtext: `活跃供应商`
    }
  ]
})

// 邮件趋势图配置
const trendChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' }
  },
  legend: {
    data: ['收件', '发件'],
    bottom: 0
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '15%',
    top: '10%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    data: trendData.value.map(d => d.date),
    axisLabel: {
      rotate: 45,
      fontSize: 10
    }
  },
  yAxis: {
    type: 'value',
    minInterval: 1
  },
  series: [
    {
      name: '收件',
      type: 'bar',
      stack: 'total',
      data: trendData.value.map(d => d.received || 0),
      itemStyle: { color: '#409EFF' }
    },
    {
      name: '发件',
      type: 'bar',
      stack: 'total',
      data: trendData.value.map(d => d.sent || 0),
      itemStyle: { color: '#67C23A' }
    }
  ]
}))

// 翻译引擎分布图配置
const engineChartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} ({d}%)'
  },
  legend: {
    orient: 'vertical',
    right: 10,
    top: 'center'
  },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['40%', '50%'],
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
      data: engineData.value.map(d => ({
        name: d.engine === 'vllm' ? 'vLLM' : 'Claude',
        value: d.count,
        itemStyle: {
          color: d.engine === 'vllm' ? '#67C23A' : '#409EFF'
        }
      }))
    }
  ]
}))

// 供应商排行图配置
const rankingChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' }
  },
  grid: {
    left: '3%',
    right: '10%',
    bottom: '3%',
    top: '3%',
    containLabel: true
  },
  xAxis: {
    type: 'value',
    minInterval: 1
  },
  yAxis: {
    type: 'category',
    data: rankingData.value.map(d => d.supplier_name).reverse(),
    axisLabel: {
      width: 100,
      overflow: 'truncate'
    }
  },
  series: [
    {
      type: 'bar',
      data: rankingData.value.map(d => d.email_count).reverse(),
      itemStyle: {
        color: function(params) {
          const colors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399']
          return colors[params.dataIndex % colors.length]
        }
      },
      label: {
        show: true,
        position: 'right',
        formatter: '{c}'
      }
    }
  ]
}))

// 分类分布图配置
const categoryChartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} ({d}%)'
  },
  legend: {
    orient: 'vertical',
    right: 10,
    top: 'center'
  },
  series: [
    {
      type: 'pie',
      radius: '60%',
      center: ['40%', '50%'],
      data: categoryData.value.map(d => ({
        name: getCategoryName(d.category),
        value: d.count
      })),
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }
  ]
}))

// 响应时间图配置
const responseChartOption = computed(() => {
  const data = responseTimeData.value?.by_supplier || []
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: function(params) {
        const d = params[0]
        return `${d.name}<br/>平均响应: ${formatHours(d.value)}`
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'value',
      name: '小时',
      axisLabel: {
        formatter: '{value}h'
      }
    },
    yAxis: {
      type: 'category',
      data: data.slice(0, 5).map(d => d.supplier_name).reverse()
    },
    series: [
      {
        type: 'bar',
        data: data.slice(0, 5).map(d => d.avg_hours).reverse(),
        itemStyle: {
          color: function(params) {
            const value = params.value
            if (value < 2) return '#67C23A'
            if (value < 12) return '#E6A23C'
            return '#F56C6C'
          }
        }
      }
    ]
  }
})

// 热力图配置
const heatmapChartOption = computed(() => {
  const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`)
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

  // 转换数据格式 [day, hour, value]
  const data = []
  heatmapData.value.forEach(item => {
    data.push([item.hour, item.weekday, item.count || 0])
  })

  const maxValue = Math.max(...data.map(d => d[2]), 1)

  return {
    tooltip: {
      position: 'top',
      formatter: function(params) {
        return `${days[params.value[1]]} ${hours[params.value[0]]}<br/>邮件数: ${params.value[2]}`
      }
    },
    grid: {
      left: '80',
      right: '30',
      bottom: '80',
      top: '30'
    },
    xAxis: {
      type: 'category',
      data: hours,
      splitArea: { show: true },
      axisLabel: {
        interval: 2
      }
    },
    yAxis: {
      type: 'category',
      data: days,
      splitArea: { show: true }
    },
    visualMap: {
      min: 0,
      max: maxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0',
      inRange: {
        color: ['#ebeef5', '#409EFF', '#67C23A', '#E6A23C', '#F56C6C']
      }
    },
    series: [
      {
        type: 'heatmap',
        data: data,
        label: {
          show: false
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }
})

// 分类名称映射
function getCategoryName(category) {
  const names = {
    inquiry: '询价',
    order: '订单',
    logistics: '物流',
    payment: '付款',
    quality: '质量',
    urgent: '紧急',
    quotation: '报价',
    technical: '技术',
    other: '其他'
  }
  return names[category] || category
}

// 格式化小时
function formatHours(hours) {
  if (!hours && hours !== 0) return '-'
  if (hours < 1) return `${Math.round(hours * 60)}分钟`
  if (hours < 24) return `${hours.toFixed(1)}小时`
  return `${(hours / 24).toFixed(1)}天`
}

// 加载数据
async function loadOverview() {
  try {
    const res = await api.getStatisticsOverview()
    overviewData.value = res.data
  } catch (e) {
    console.error('Failed to load overview:', e)
  }
}

async function loadEmailTrend() {
  try {
    const days = trendPeriod.value === 'daily' ? 14 : trendPeriod.value === 'weekly' ? 12 : 12
    const res = await api.getEmailTrend(trendPeriod.value, days)
    trendData.value = res.data.trend || []
  } catch (e) {
    console.error('Failed to load trend:', e)
  }
}

async function loadEngineStats() {
  try {
    const res = await api.getTranslationEngineStats(3)
    engineData.value = res.data.engines || []
  } catch (e) {
    console.error('Failed to load engine stats:', e)
  }
}

async function loadSupplierRanking() {
  try {
    const res = await api.getSupplierRanking(10, rankingDays.value)
    rankingData.value = res.data.ranking || []
  } catch (e) {
    console.error('Failed to load ranking:', e)
  }
}

async function loadCategoryDistribution() {
  try {
    const res = await api.getCategoryDistribution(30)
    categoryData.value = res.data.categories || []
  } catch (e) {
    console.error('Failed to load categories:', e)
  }
}

async function loadResponseTime() {
  try {
    const res = await api.getResponseTimeStats(30)
    responseTimeData.value = res.data
  } catch (e) {
    console.error('Failed to load response time:', e)
  }
}

async function loadCacheStats() {
  try {
    const res = await api.getCacheStats()
    cacheData.value = res.data
  } catch (e) {
    console.error('Failed to load cache stats:', e)
  }
}

async function loadDailyActivity() {
  try {
    const res = await api.getDailyActivity(30)
    heatmapData.value = res.data.activity || []
  } catch (e) {
    console.error('Failed to load activity:', e)
  }
}

// 初始化加载所有数据
onMounted(() => {
  loading.value = true
  Promise.all([
    loadOverview(),
    loadEmailTrend(),
    loadEngineStats(),
    loadSupplierRanking(),
    loadCategoryDistribution(),
    loadResponseTime(),
    loadCacheStats(),
    loadDailyActivity()
  ]).finally(() => {
    loading.value = false
  })
})
</script>

<style scoped>
.statistics-container {
  padding: 20px;
  background: #f5f7fa;
  min-height: 100vh;
}

.stats-cards {
  margin-bottom: 20px;
}

.stat-card {
  border-radius: 8px;
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.stat-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
  font-size: 12px;
  color: #909399;
}

.trend-up {
  color: #67C23A;
}

.trend-down {
  color: #F56C6C;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart {
  height: 300px;
  width: 100%;
}

.chart-small {
  height: 180px;
}

.heatmap-chart {
  height: 280px;
}

.response-time-stats {
  display: flex;
  justify-content: space-around;
  padding: 16px 0;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 16px;
}

.time-stat {
  text-align: center;
}

.time-value {
  font-size: 24px;
  font-weight: 600;
  color: #409EFF;
}

.time-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.cache-stats {
  padding: 10px 0;
}

.top-cached {
  margin-top: 10px;
}

.section-title {
  font-size: 14px;
  color: #606266;
  margin-bottom: 10px;
  font-weight: 500;
}

:deep(.el-card__header) {
  padding: 12px 20px;
  border-bottom: 1px solid #ebeef5;
  font-weight: 500;
}

:deep(.el-statistic__head) {
  font-size: 12px;
  color: #909399;
}

:deep(.el-statistic__content) {
  font-size: 20px;
  color: #303133;
}
</style>
