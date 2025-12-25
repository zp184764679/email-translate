<template>
  <el-dialog
    v-model="visible"
    title="从邮件创建任务"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div v-loading="loading" class="create-task-dialog">
      <!-- 步骤指示器 -->
      <el-steps :active="currentStep" simple class="steps-header">
        <el-step title="提取信息" />
        <el-step title="选择项目" />
        <el-step title="确认创建" />
      </el-steps>

      <!-- 步骤1: 提取信息 -->
      <div v-if="currentStep === 0" class="step-content">
        <div v-if="extractionStatus === 'none'" class="extraction-prompt">
          <el-icon :size="48" color="#409eff"><DocumentAdd /></el-icon>
          <p>该邮件尚未提取任务信息</p>
          <el-button type="primary" @click="triggerExtraction" :loading="extracting">
            开始提取
          </el-button>
        </div>

        <div v-else-if="extractionStatus === 'processing'" class="extraction-prompt">
          <el-icon :size="48" color="#e6a23c" class="rotating"><Loading /></el-icon>
          <p>正在提取任务信息，请稍候...</p>
          <el-button @click="checkExtractionStatus">刷新状态</el-button>
        </div>

        <div v-else-if="extractionStatus === 'failed'" class="extraction-prompt">
          <el-icon :size="48" color="#f56c6c"><CircleClose /></el-icon>
          <p>提取失败：{{ extractionError }}</p>
          <el-button type="primary" @click="triggerExtraction" :loading="extracting">
            重新提取
          </el-button>
        </div>

        <div v-else-if="extractionStatus === 'completed'" class="extraction-result">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="任务标题" :span="2">
              {{ extraction.title || '(未提取)' }}
            </el-descriptions-item>
            <el-descriptions-item label="客户名称">
              {{ extraction.customer_name || '(未识别)' }}
            </el-descriptions-item>
            <el-descriptions-item label="订单号">
              {{ extraction.order_no || '(未识别)' }}
            </el-descriptions-item>
            <el-descriptions-item label="品番号">
              {{ extraction.part_number || '(未识别)' }}
            </el-descriptions-item>
            <el-descriptions-item label="优先级">
              <el-tag :type="priorityTagType(extraction.priority)">
                {{ priorityLabel(extraction.priority) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="截止日期">
              {{ extraction.due_date || '(未识别)' }}
            </el-descriptions-item>
            <el-descriptions-item label="负责人">
              {{ extraction.assignee_name || '(未识别)' }}
            </el-descriptions-item>
            <el-descriptions-item label="任务描述" :span="2">
              <div class="description-text">{{ extraction.description || '(无描述)' }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="待办事项" :span="2" v-if="extraction.action_items?.length">
              <ul class="action-items">
                <li v-for="(item, idx) in extraction.action_items" :key="idx">{{ item }}</li>
              </ul>
            </el-descriptions-item>
          </el-descriptions>

          <div class="step-actions">
            <el-button @click="triggerExtraction" :loading="extracting">重新提取</el-button>
            <el-button type="primary" @click="nextStep">下一步：选择项目</el-button>
          </div>
        </div>
      </div>

      <!-- 步骤2: 选择项目 -->
      <div v-if="currentStep === 1" class="step-content">
        <div v-if="matchLoading" class="loading-container">
          <el-icon :size="32" class="rotating"><Loading /></el-icon>
          <p>正在匹配项目...</p>
        </div>

        <div v-else class="project-selection">
          <!-- 匹配结果 -->
          <div v-if="projectMatches.length > 0" class="matches-section">
            <h4>匹配到的项目</h4>
            <el-radio-group v-model="selectedProjectId" class="project-list">
              <el-radio
                v-for="project in projectMatches"
                :key="project.id"
                :value="project.id"
                class="project-item"
              >
                <div class="project-info">
                  <span class="project-name">{{ project.name }}</span>
                  <el-tag size="small" :type="project.score >= 80 ? 'success' : 'warning'">
                    {{ project.match_reason }}
                  </el-tag>
                </div>
              </el-radio>
            </el-radio-group>
          </div>

          <div v-else class="no-matches">
            <el-alert type="info" :closable="false">
              未找到匹配的项目，请选择创建新项目或手动选择
            </el-alert>
          </div>

          <!-- 创建新项目选项 -->
          <div class="create-project-section">
            <el-checkbox v-model="createNewProject" @change="handleCreateProjectChange">
              创建新项目
            </el-checkbox>
            <el-input
              v-if="createNewProject"
              v-model="newProjectName"
              placeholder="输入项目名称"
              class="project-name-input"
            />
          </div>

          <div class="step-actions">
            <el-button @click="prevStep">上一步</el-button>
            <el-button
              type="primary"
              @click="nextStep"
              :disabled="!canProceedToConfirm"
            >
              下一步：确认创建
            </el-button>
          </div>
        </div>
      </div>

      <!-- 步骤3: 确认创建 -->
      <div v-if="currentStep === 2" class="step-content">
        <el-form :model="taskForm" label-width="100px" size="default">
          <el-form-item label="关联项目">
            <el-tag v-if="createNewProject" type="success">
              新建：{{ newProjectName }}
            </el-tag>
            <el-tag v-else>
              {{ selectedProjectName }}
            </el-tag>
          </el-form-item>

          <el-form-item label="任务标题" required>
            <el-input v-model="taskForm.title" placeholder="输入任务标题" />
          </el-form-item>

          <el-form-item label="任务描述">
            <el-input
              v-model="taskForm.description"
              type="textarea"
              :rows="3"
              placeholder="输入任务描述"
            />
          </el-form-item>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="优先级">
                <el-select v-model="taskForm.priority" style="width: 100%">
                  <el-option label="低" value="low" />
                  <el-option label="普通" value="normal" />
                  <el-option label="高" value="high" />
                  <el-option label="紧急" value="urgent" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="任务类型">
                <el-select v-model="taskForm.task_type" style="width: 100%">
                  <el-option label="常规" value="general" />
                  <el-option label="设计" value="design" />
                  <el-option label="开发" value="development" />
                  <el-option label="测试" value="testing" />
                  <el-option label="评审" value="review" />
                  <el-option label="会议" value="meeting" />
                  <el-option label="文档" value="documentation" />
                  <el-option label="其他" value="other" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="开始日期">
                <el-date-picker
                  v-model="taskForm.start_date"
                  type="date"
                  placeholder="选择开始日期"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="截止日期">
                <el-date-picker
                  v-model="taskForm.due_date"
                  type="date"
                  placeholder="选择截止日期"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="待办事项">
            <div class="checklist-editor">
              <div
                v-for="(item, idx) in taskForm.action_items"
                :key="idx"
                class="checklist-item"
              >
                <el-input v-model="taskForm.action_items[idx]" size="small">
                  <template #append>
                    <el-button :icon="Delete" @click="removeActionItem(idx)" />
                  </template>
                </el-input>
              </div>
              <el-button size="small" :icon="Plus" @click="addActionItem">
                添加待办
              </el-button>
            </div>
          </el-form-item>
        </el-form>

        <div class="step-actions">
          <el-button @click="prevStep">上一步</el-button>
          <el-button type="primary" @click="createTask" :loading="creating">
            确认创建任务
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { DocumentAdd, Loading, CircleClose, Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  emailId: {
    type: [Number, String],
    required: true
  },
  emailSubject: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'created'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 状态
const loading = ref(false)
const currentStep = ref(0)
const extracting = ref(false)
const matchLoading = ref(false)
const creating = ref(false)

// 提取数据
const extractionStatus = ref('none')  // none, processing, completed, failed
const extractionError = ref('')
const extraction = ref({})

// 项目匹配
const projectMatches = ref([])
const selectedProjectId = ref(null)
const createNewProject = ref(false)
const newProjectName = ref('')

// 任务表单
const taskForm = ref({
  title: '',
  description: '',
  priority: 'normal',
  task_type: 'general',
  start_date: null,
  due_date: null,
  action_items: []
})

// 计算属性
const selectedProjectName = computed(() => {
  const project = projectMatches.value.find(p => p.id === selectedProjectId.value)
  return project?.name || ''
})

const canProceedToConfirm = computed(() => {
  if (createNewProject.value) {
    return newProjectName.value.trim().length > 0
  }
  return selectedProjectId.value !== null
})

// 监听对话框打开
watch(() => props.modelValue, async (val) => {
  if (val && props.emailId) {
    await checkExtractionStatus()
  }
})

// 方法
async function checkExtractionStatus() {
  loading.value = true
  try {
    const result = await api.getTaskExtraction(props.emailId)
    extractionStatus.value = result.status
    if (result.status === 'completed' && result.data) {
      extraction.value = result.data
      initFormFromExtraction()
    } else if (result.status === 'failed') {
      extractionError.value = result.error_message || '未知错误'
    }
  } catch (e) {
    console.error('检查提取状态失败:', e)
    extractionStatus.value = 'none'
  } finally {
    loading.value = false
  }
}

async function triggerExtraction() {
  extracting.value = true
  try {
    await api.triggerTaskExtraction(props.emailId, true)
    extractionStatus.value = 'processing'
    // 轮询检查状态
    pollExtractionStatus()
  } catch (e) {
    ElMessage.error('触发提取失败')
    console.error(e)
  } finally {
    extracting.value = false
  }
}

async function pollExtractionStatus() {
  const maxAttempts = 30
  let attempts = 0

  const poll = async () => {
    if (attempts >= maxAttempts) {
      extractionStatus.value = 'failed'
      extractionError.value = '提取超时，请重试'
      return
    }

    attempts++
    try {
      const result = await api.getTaskExtraction(props.emailId)
      if (result.status === 'completed') {
        extractionStatus.value = 'completed'
        extraction.value = result.data
        initFormFromExtraction()
      } else if (result.status === 'failed') {
        extractionStatus.value = 'failed'
        extractionError.value = result.error_message || '提取失败'
      } else if (result.status === 'processing') {
        setTimeout(poll, 2000)
      }
    } catch (e) {
      console.error('轮询状态失败:', e)
    }
  }

  setTimeout(poll, 2000)
}

function initFormFromExtraction() {
  const ext = extraction.value
  taskForm.value = {
    title: ext.title || props.emailSubject || '',
    description: ext.description || '',
    priority: ext.priority || 'normal',
    task_type: ext.task_type || 'general',
    start_date: ext.start_date?.split('T')[0] || null,
    due_date: ext.due_date?.split('T')[0] || null,
    action_items: [...(ext.action_items || [])]
  }
  newProjectName.value = ext.suggested_project_name || ext.project_name || ''
}

async function matchProjects() {
  matchLoading.value = true
  try {
    const result = await api.matchProjects(props.emailId)
    if (result.success) {
      projectMatches.value = result.matches || []
      if (result.best_match) {
        selectedProjectId.value = result.best_match.id
      }
      if (result.should_create_project) {
        createNewProject.value = true
        newProjectName.value = result.suggested_project_name || ''
      }
    }
  } catch (e) {
    console.error('匹配项目失败:', e)
    ElMessage.error('匹配项目失败')
  } finally {
    matchLoading.value = false
  }
}

function handleCreateProjectChange(val) {
  if (val) {
    selectedProjectId.value = null
  }
}

function nextStep() {
  if (currentStep.value === 0 && extractionStatus.value === 'completed') {
    currentStep.value = 1
    matchProjects()
  } else if (currentStep.value === 1) {
    currentStep.value = 2
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

function addActionItem() {
  taskForm.value.action_items.push('')
}

function removeActionItem(idx) {
  taskForm.value.action_items.splice(idx, 1)
}

async function createTask() {
  if (!taskForm.value.title?.trim()) {
    ElMessage.warning('请输入任务标题')
    return
  }

  creating.value = true
  try {
    const data = {
      project_id: createNewProject.value ? null : selectedProjectId.value,
      create_project: createNewProject.value,
      project_name: createNewProject.value ? newProjectName.value : null,
      title: taskForm.value.title,
      description: taskForm.value.description,
      priority: taskForm.value.priority,
      task_type: taskForm.value.task_type,
      start_date: taskForm.value.start_date,
      due_date: taskForm.value.due_date,
      action_items: taskForm.value.action_items.filter(item => item.trim()),
      customer_name: extraction.value.customer_name,
      order_no: extraction.value.order_no,
      part_number: extraction.value.part_number
    }

    const result = await api.createTaskFromEmail(props.emailId, data)
    if (result.success) {
      ElMessage.success('任务创建成功')
      emit('created', result)
      handleClose()
    } else {
      ElMessage.error(result.message || '创建失败')
    }
  } catch (e) {
    console.error('创建任务失败:', e)
    ElMessage.error(e.response?.data?.detail || '创建任务失败')
  } finally {
    creating.value = false
  }
}

function handleClose() {
  visible.value = false
  // 重置状态
  currentStep.value = 0
  extractionStatus.value = 'none'
  extraction.value = {}
  projectMatches.value = []
  selectedProjectId.value = null
  createNewProject.value = false
  newProjectName.value = ''
}

function priorityLabel(priority) {
  const labels = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
  return labels[priority] || priority
}

function priorityTagType(priority) {
  const types = { low: 'info', normal: '', high: 'warning', urgent: 'danger' }
  return types[priority] || ''
}
</script>

<style scoped>
.create-task-dialog {
  min-height: 400px;
}

.steps-header {
  margin-bottom: 24px;
}

.step-content {
  padding: 16px 0;
}

.extraction-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.extraction-prompt p {
  margin: 16px 0;
  color: #606266;
}

.rotating {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.extraction-result {
  padding: 0 8px;
}

.description-text {
  max-height: 80px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #606266;
}

.action-items {
  margin: 0;
  padding-left: 20px;
}

.action-items li {
  line-height: 1.6;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
}

.loading-container p {
  margin-top: 12px;
  color: #909399;
}

.project-selection {
  padding: 0 8px;
}

.matches-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #303133;
}

.project-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-item {
  display: block;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  margin-right: 0 !important;
}

.project-item:hover {
  border-color: #409eff;
}

.project-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-name {
  font-weight: 500;
}

.no-matches {
  margin-bottom: 16px;
}

.create-project-section {
  margin-top: 16px;
  padding: 16px;
  background-color: #fafafa;
  border-radius: 4px;
}

.project-name-input {
  margin-top: 12px;
}

.checklist-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checklist-item {
  display: flex;
  align-items: center;
}
</style>
