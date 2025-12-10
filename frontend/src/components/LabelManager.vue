<template>
  <div class="label-manager">
    <div class="header">
      <h3>标签管理</h3>
      <el-button type="primary" size="small" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        新建标签
      </el-button>
    </div>

    <el-table :data="labels" v-loading="loading" style="width: 100%">
      <el-table-column label="标签" min-width="150">
        <template #default="{ row }">
          <el-tag
            :color="row.color"
            :style="{ color: getTextColor(row.color) }"
          >
            {{ row.name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200">
        <template #default="{ row }">
          <span class="description">{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="email_count" label="邮件数" width="100" align="center" />
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="editLabel(row)">
            编辑
          </el-button>
          <el-popconfirm
            title="确定删除此标签吗？"
            @confirm="deleteLabel(row.id)"
          >
            <template #reference>
              <el-button type="danger" link size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingLabel ? '编辑标签' : '新建标签'"
      width="400px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="请输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <div class="color-picker-row">
            <el-color-picker v-model="form.color" />
            <div class="preset-colors">
              <span
                v-for="color in presetColors"
                :key="color"
                class="preset-color"
                :style="{ backgroundColor: color }"
                :class="{ active: form.color === color }"
                @click="form.color = color"
              />
            </div>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="可选的标签描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveLabel" :loading="saving">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const labels = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingLabel = ref(null)
const saving = ref(false)

const form = ref({
  name: '',
  color: '#409EFF',
  description: ''
})

const presetColors = [
  '#409EFF', '#67C23A', '#E6A23C', '#F56C6C',
  '#909399', '#00BCD4', '#9C27B0', '#FF5722'
]

onMounted(() => {
  loadLabels()
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

function showCreateDialog() {
  editingLabel.value = null
  form.value = {
    name: '',
    color: '#409EFF',
    description: ''
  }
  dialogVisible.value = true
}

function editLabel(label) {
  editingLabel.value = label
  form.value = {
    name: label.name,
    color: label.color,
    description: label.description || ''
  }
  dialogVisible.value = true
}

async function saveLabel() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }

  saving.value = true
  try {
    if (editingLabel.value) {
      await api.updateLabel(editingLabel.value.id, form.value)
      ElMessage.success('标签已更新')
    } else {
      await api.createLabel(form.value)
      ElMessage.success('标签已创建')
    }
    dialogVisible.value = false
    loadLabels()
  } catch (e) {
    // Error handled by interceptor
  } finally {
    saving.value = false
  }
}

async function deleteLabel(id) {
  try {
    await api.deleteLabel(id)
    ElMessage.success('标签已删除')
    loadLabels()
  } catch (e) {
    // Error handled by interceptor
  }
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
.label-manager {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h3 {
  margin: 0;
}

.description {
  color: var(--el-text-color-secondary);
}

.color-picker-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.preset-colors {
  display: flex;
  gap: 8px;
}

.preset-color {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}

.preset-color:hover {
  transform: scale(1.1);
}

.preset-color.active {
  border-color: var(--el-color-primary);
}
</style>
