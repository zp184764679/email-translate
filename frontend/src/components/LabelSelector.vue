<template>
  <el-dialog
    v-model="visible"
    title="管理标签"
    width="400px"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <div class="label-selector">
      <!-- 快速添加新标签 -->
      <div class="quick-add">
        <el-input
          v-model="newLabelName"
          placeholder="输入标签名称，按回车创建"
          size="small"
          @keyup.enter="createLabel"
        >
          <template #prepend>
            <el-color-picker v-model="newLabelColor" size="small" />
          </template>
          <template #append>
            <el-button @click="createLabel" :loading="creating">
              <el-icon><Plus /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>

      <!-- 标签列表 -->
      <div class="label-list">
        <div v-if="loading" class="loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          加载中...
        </div>
        <div v-else-if="labels.length === 0" class="empty">
          暂无标签，请先创建
        </div>
        <div
          v-else
          v-for="label in labels"
          :key="label.id"
          class="label-item"
          :class="{ selected: selectedIds.includes(label.id) }"
          @click="toggleLabel(label)"
        >
          <el-checkbox
            :model-value="selectedIds.includes(label.id)"
            @change="toggleLabel(label)"
          />
          <el-tag
            :color="label.color"
            :style="{ color: getTextColor(label.color) }"
            size="small"
          >
            {{ label.name }}
          </el-tag>
          <span class="email-count">{{ label.email_count || 0 }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save" :loading="saving">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Plus, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  emailId: {
    type: Number,
    required: true
  },
  currentLabels: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'saved'])

const visible = ref(props.modelValue)
const labels = ref([])
const selectedIds = ref([])
const loading = ref(false)
const saving = ref(false)
const creating = ref(false)

const newLabelName = ref('')
const newLabelColor = ref('#409EFF')

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    loadLabels()
    selectedIds.value = props.currentLabels.map(l => l.id)
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

async function loadLabels() {
  loading.value = true
  try {
    labels.value = await api.getLabels()
  } catch (e) {
    console.error('Failed to load labels:', e)
  } finally {
    loading.value = false
  }
}

function toggleLabel(label) {
  const idx = selectedIds.value.indexOf(label.id)
  if (idx > -1) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(label.id)
  }
}

async function createLabel() {
  if (!newLabelName.value.trim()) return

  creating.value = true
  try {
    const newLabel = await api.createLabel({
      name: newLabelName.value.trim(),
      color: newLabelColor.value
    })
    labels.value.unshift(newLabel)
    selectedIds.value.push(newLabel.id)
    newLabelName.value = ''
    newLabelColor.value = '#409EFF'
    ElMessage.success('标签已创建')
  } catch (e) {
    // Error handled by interceptor
  } finally {
    creating.value = false
  }
}

async function save() {
  saving.value = true
  try {
    // 获取当前邮件的标签
    const currentIds = props.currentLabels.map(l => l.id)

    // 计算需要添加和删除的标签
    const toAdd = selectedIds.value.filter(id => !currentIds.includes(id))
    const toRemove = currentIds.filter(id => !selectedIds.value.includes(id))

    // 添加新标签
    if (toAdd.length > 0) {
      await api.addLabelsToEmail(props.emailId, toAdd)
    }

    // 删除标签
    for (const labelId of toRemove) {
      await api.removeLabelFromEmail(props.emailId, labelId)
    }

    ElMessage.success('标签已更新')
    emit('saved', labels.value.filter(l => selectedIds.value.includes(l.id)))
    visible.value = false
  } catch (e) {
    // Error handled by interceptor
  } finally {
    saving.value = false
  }
}

function onClosed() {
  selectedIds.value = []
}

// 根据背景色计算文字颜色
function getTextColor(bgColor) {
  if (!bgColor) return '#333'
  const hex = bgColor.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)
  const brightness = (r * 299 + g * 587 + b * 114) / 1000
  return brightness > 128 ? '#333' : '#fff'
}
</script>

<style scoped>
.label-selector {
  min-height: 200px;
}

.quick-add {
  margin-bottom: 16px;
}

.label-list {
  max-height: 300px;
  overflow-y: auto;
}

.label-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.label-item:hover {
  background-color: var(--el-fill-color-light);
}

.label-item.selected {
  background-color: var(--el-color-primary-light-9);
}

.email-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.loading,
.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: var(--el-text-color-secondary);
}
</style>
