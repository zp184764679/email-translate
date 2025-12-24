<template>
  <el-drawer
    v-model="visible"
    title="高级搜索"
    direction="rtl"
    size="400px"
    :before-close="handleClose"
  >
    <el-form :model="filters" label-position="top" class="search-form">
      <el-form-item label="发件人">
        <el-input
          v-model="filters.from_email"
          placeholder="搜索发件人邮箱或名称"
          clearable
        />
      </el-form-item>

      <el-form-item label="收件人">
        <el-input
          v-model="filters.to_email"
          placeholder="搜索收件人（含抄送）"
          clearable
        />
      </el-form-item>

      <el-form-item label="日期范围">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          :shortcuts="dateShortcuts"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="附件">
        <el-radio-group v-model="filters.has_attachment">
          <el-radio-button :value="null">全部</el-radio-button>
          <el-radio-button :value="true">有附件</el-radio-button>
          <el-radio-button :value="false">无附件</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="标签">
        <el-select
          v-model="filters.label_ids"
          multiple
          placeholder="选择标签"
          style="width: 100%"
          clearable
        >
          <el-option
            v-for="label in labels"
            :key="label.id"
            :label="label.name"
            :value="label.id"
          >
            <span class="label-option">
              <span class="label-color" :style="{ backgroundColor: label.color }"></span>
              {{ label.name }}
            </span>
          </el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="语言">
        <el-select
          v-model="filters.language"
          placeholder="选择语言"
          style="width: 100%"
          clearable
        >
          <el-option label="中文" value="zh" />
          <el-option label="英语" value="en" />
          <el-option label="日语" value="ja" />
          <el-option label="韩语" value="ko" />
          <el-option label="德语" value="de" />
          <el-option label="法语" value="fr" />
          <el-option label="西班牙语" value="es" />
          <el-option label="俄语" value="ru" />
        </el-select>
      </el-form-item>

      <el-form-item label="翻译状态">
        <el-radio-group v-model="filters.translation_status">
          <el-radio-button :value="null">全部</el-radio-button>
          <el-radio-button value="completed">已翻译</el-radio-button>
          <el-radio-button value="none">未翻译</el-radio-button>
          <el-radio-button value="translating">翻译中</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="已读状态">
        <el-radio-group v-model="filters.is_read">
          <el-radio-button :value="null">全部</el-radio-button>
          <el-radio-button :value="false">未读</el-radio-button>
          <el-radio-button :value="true">已读</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="星标">
        <el-radio-group v-model="filters.is_flagged">
          <el-radio-button :value="null">全部</el-radio-button>
          <el-radio-button :value="true">已星标</el-radio-button>
          <el-radio-button :value="false">无星标</el-radio-button>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="handleReset">重置</el-button>
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import api from '@/api'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'search'])

const router = useRouter()
const route = useRoute()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const filters = ref({
  from_email: '',
  to_email: '',
  has_attachment: null,
  label_ids: [],
  language: null,
  translation_status: null,
  is_read: null,
  is_flagged: null
})

const dateRange = ref(null)
const labels = ref([])

// Date shortcuts
const dateShortcuts = [
  {
    text: '今天',
    value: () => {
      const today = new Date()
      return [today, today]
    }
  },
  {
    text: '最近7天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 7)
      return [start, end]
    }
  },
  {
    text: '最近30天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 30)
      return [start, end]
    }
  },
  {
    text: '本月',
    value: () => {
      const now = new Date()
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [start, now]
    }
  }
]

// Load labels
async function loadLabels() {
  try {
    labels.value = await api.getLabels()
  } catch (e) {
    console.error('Failed to load labels:', e)
  }
}

// Initialize from URL query
function initFromQuery() {
  const query = route.query
  if (query.from_email) filters.value.from_email = query.from_email
  if (query.to_email) filters.value.to_email = query.to_email
  if (query.date_start && query.date_end) {
    dateRange.value = [query.date_start, query.date_end]
  }
  if (query.has_attachment !== undefined) {
    filters.value.has_attachment = query.has_attachment === 'true'
  }
  if (query.label_ids) {
    filters.value.label_ids = query.label_ids.split(',').map(Number)
  }
  if (query.language) filters.value.language = query.language
  if (query.translation_status) filters.value.translation_status = query.translation_status
  if (query.is_read !== undefined) {
    filters.value.is_read = query.is_read === 'true'
  }
  if (query.is_flagged !== undefined) {
    filters.value.is_flagged = query.is_flagged === 'true'
  }
}

function handleClose() {
  visible.value = false
}

function handleReset() {
  filters.value = {
    from_email: '',
    to_email: '',
    has_attachment: null,
    label_ids: [],
    language: null,
    translation_status: null,
    is_read: null,
    is_flagged: null
  }
  dateRange.value = null
}

function handleSearch() {
  // Build query params
  const query = {}

  if (filters.value.from_email) query.from_email = filters.value.from_email
  if (filters.value.to_email) query.to_email = filters.value.to_email
  if (dateRange.value && dateRange.value.length === 2) {
    query.date_start = dateRange.value[0]
    query.date_end = dateRange.value[1]
  }
  if (filters.value.has_attachment !== null) {
    query.has_attachment = filters.value.has_attachment
  }
  if (filters.value.label_ids.length > 0) {
    query.label_ids = filters.value.label_ids.join(',')
  }
  if (filters.value.language) query.language = filters.value.language
  if (filters.value.translation_status) {
    query.translation_status = filters.value.translation_status
  }
  if (filters.value.is_read !== null) query.is_read = filters.value.is_read
  if (filters.value.is_flagged !== null) query.is_flagged = filters.value.is_flagged

  // Navigate with filters
  router.push({ path: '/emails', query })
  emit('search', query)
  visible.value = false
}

onMounted(() => {
  loadLabels()
  initFromQuery()
})

// Watch for route changes
watch(() => route.query, () => {
  if (visible.value) {
    initFromQuery()
  }
}, { deep: true })
</script>

<style scoped>
.search-form {
  padding: 0 4px;
}

.search-form :deep(.el-form-item__label) {
  font-weight: 500;
}

.search-form :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.search-form :deep(.el-radio-button) {
  margin-right: 0;
}

.search-form :deep(.el-radio-button__inner) {
  padding: 8px 12px;
  font-size: 13px;
}

.label-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.label-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
