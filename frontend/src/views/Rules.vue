<template>
  <div class="rules-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>邮件规则</h2>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        创建规则
      </el-button>
    </div>

    <!-- 规则列表 -->
    <div class="rules-list" v-loading="loading">
      <el-empty v-if="rules.length === 0" description="暂无规则，点击上方按钮创建" />

      <div v-else class="rule-cards">
        <div
          v-for="(rule, index) in rules"
          :key="rule.id"
          class="rule-card"
          :class="{ 'inactive': !rule.is_active }"
        >
          <div class="rule-header">
            <div class="rule-info">
              <span class="rule-priority">{{ index + 1 }}</span>
              <span class="rule-name">{{ rule.name }}</span>
              <el-tag v-if="!rule.is_active" type="info" size="small">已禁用</el-tag>
              <el-tag v-if="rule.stop_processing" type="warning" size="small">停止后续</el-tag>
            </div>
            <div class="rule-actions">
              <el-switch
                v-model="rule.is_active"
                @change="toggleRule(rule)"
                size="small"
              />
              <el-button text size="small" @click="editRule(rule)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text size="small" type="danger" @click="deleteRule(rule)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>

          <div class="rule-body">
            <!-- 条件显示 -->
            <div class="rule-conditions">
              <span class="label">条件：</span>
              <span class="condition-logic">{{ rule.conditions?.logic || 'AND' }}</span>
              <div class="condition-list">
                <el-tag
                  v-for="(cond, idx) in rule.conditions?.rules || []"
                  :key="idx"
                  size="small"
                  type="info"
                >
                  {{ getFieldLabel(cond.field) }} {{ getOperatorLabel(cond.operator) }} "{{ cond.value }}"
                </el-tag>
              </div>
            </div>

            <!-- 动作显示 -->
            <div class="rule-actions-display">
              <span class="label">动作：</span>
              <div class="action-list">
                <el-tag
                  v-for="(action, idx) in rule.actions || []"
                  :key="idx"
                  size="small"
                  type="success"
                >
                  {{ getActionLabel(action) }}
                </el-tag>
              </div>
            </div>

            <!-- 统计 -->
            <div class="rule-stats">
              <span>匹配次数：{{ rule.match_count || 0 }}</span>
              <span v-if="rule.last_match_at">
                最后匹配：{{ formatTime(rule.last_match_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑规则对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingRule ? '编辑规则' : '创建规则'"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="ruleForm" label-width="80px" ref="ruleFormRef">
        <el-form-item label="规则名称" prop="name" required>
          <el-input v-model="ruleForm.name" placeholder="输入规则名称" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="ruleForm.description" placeholder="可选描述" />
        </el-form-item>

        <!-- 条件组 -->
        <el-form-item label="条件">
          <div class="conditions-editor">
            <div class="logic-selector">
              <el-radio-group v-model="ruleForm.conditions.logic" size="small">
                <el-radio-button label="AND">全部满足</el-radio-button>
                <el-radio-button label="OR">任一满足</el-radio-button>
              </el-radio-group>
            </div>

            <div
              v-for="(cond, index) in ruleForm.conditions.rules"
              :key="index"
              class="condition-row"
            >
              <el-select v-model="cond.field" placeholder="字段" style="width: 140px">
                <el-option
                  v-for="field in fieldOptions"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value"
                />
              </el-select>

              <el-select v-model="cond.operator" placeholder="操作符" style="width: 120px">
                <el-option
                  v-for="op in getOperatorsForField(cond.field)"
                  :key="op.value"
                  :label="op.label"
                  :value="op.value"
                />
              </el-select>

              <el-input
                v-if="cond.field !== 'has_attachment'"
                v-model="cond.value"
                placeholder="值"
                style="flex: 1"
              />
              <el-select
                v-else
                v-model="cond.value"
                style="width: 100px"
              >
                <el-option label="有" value="true" />
                <el-option label="无" value="false" />
              </el-select>

              <el-button
                text
                type="danger"
                @click="removeCondition(index)"
                :disabled="ruleForm.conditions.rules.length <= 1"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>

            <el-button text type="primary" @click="addCondition">
              <el-icon><Plus /></el-icon>
              添加条件
            </el-button>
          </div>
        </el-form-item>

        <!-- 动作列表 -->
        <el-form-item label="动作">
          <div class="actions-editor">
            <div
              v-for="(action, index) in ruleForm.actions"
              :key="index"
              class="action-row"
            >
              <el-select v-model="action.type" placeholder="动作类型" style="width: 160px" @change="onActionTypeChange(action)">
                <el-option
                  v-for="act in actionOptions"
                  :key="act.value"
                  :label="act.label"
                  :value="act.value"
                />
              </el-select>

              <!-- 文件夹选择 -->
              <el-select
                v-if="action.type === 'move_to_folder'"
                v-model="action.folder_id"
                placeholder="选择文件夹"
                style="flex: 1"
              >
                <el-option
                  v-for="folder in folders"
                  :key="folder.id"
                  :label="folder.name"
                  :value="folder.id"
                />
              </el-select>

              <!-- 标签选择 -->
              <el-select
                v-if="action.type === 'add_label' || action.type === 'remove_label'"
                v-model="action.label_id"
                placeholder="选择标签"
                style="flex: 1"
              >
                <el-option
                  v-for="label in labels"
                  :key="label.id"
                  :label="label.name"
                  :value="label.id"
                />
              </el-select>

              <el-button
                text
                type="danger"
                @click="removeAction(index)"
                :disabled="ruleForm.actions.length <= 1"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>

            <el-button text type="primary" @click="addAction">
              <el-icon><Plus /></el-icon>
              添加动作
            </el-button>
          </div>
        </el-form-item>

        <!-- 高级选项 -->
        <el-form-item label="高级选项">
          <el-checkbox v-model="ruleForm.stop_processing">
            匹配后停止处理后续规则
          </el-checkbox>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRule" :loading="saving">
          {{ editingRule ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

// 状态
const loading = ref(false)
const saving = ref(false)
const rules = ref([])
const dialogVisible = ref(false)
const editingRule = ref(null)

// 选项
const fieldOptions = ref([])
const operatorOptions = ref([])
const actionOptions = ref([])
const folders = ref([])
const labels = ref([])

// 表单
const ruleFormRef = ref(null)
const ruleForm = ref({
  name: '',
  description: '',
  conditions: {
    logic: 'AND',
    rules: [{ field: 'from_email', operator: 'contains', value: '' }]
  },
  actions: [{ type: 'add_label', label_id: null }],
  stop_processing: false
})

// 加载数据
onMounted(async () => {
  await Promise.all([
    loadRules(),
    loadFieldOptions(),
    loadFolders(),
    loadLabels()
  ])
})

async function loadRules() {
  loading.value = true
  try {
    rules.value = await api.getRules()
  } catch (e) {
    console.error('Load rules failed:', e)
    ElMessage.error('加载规则失败')
  } finally {
    loading.value = false
  }
}

async function loadFieldOptions() {
  try {
    const options = await api.getRuleFieldOptions()
    fieldOptions.value = options.fields || []
    operatorOptions.value = options.operators || []
    actionOptions.value = options.actions || []
  } catch (e) {
    console.error('Load field options failed:', e)
  }
}

async function loadFolders() {
  try {
    folders.value = await api.getFolders()
  } catch (e) {
    console.error('Load folders failed:', e)
  }
}

async function loadLabels() {
  try {
    labels.value = await api.getLabels()
  } catch (e) {
    console.error('Load labels failed:', e)
  }
}

// 获取字段对应的操作符
function getOperatorsForField(field) {
  const fieldDef = fieldOptions.value.find(f => f.value === field)
  if (!fieldDef) return operatorOptions.value

  return operatorOptions.value.filter(op =>
    fieldDef.operators.includes(op.value)
  )
}

// 标签辅助函数
function getFieldLabel(field) {
  const f = fieldOptions.value.find(f => f.value === field)
  return f?.label || field
}

function getOperatorLabel(operator) {
  const op = operatorOptions.value.find(o => o.value === operator)
  return op?.label || operator
}

function getActionLabel(action) {
  const act = actionOptions.value.find(a => a.value === action.type)
  let label = act?.label || action.type

  if (action.type === 'move_to_folder' && action.folder_id) {
    const folder = folders.value.find(f => f.id === action.folder_id)
    label += `: ${folder?.name || action.folder_id}`
  }
  if ((action.type === 'add_label' || action.type === 'remove_label') && action.label_id) {
    const lbl = labels.value.find(l => l.id === action.label_id)
    label += `: ${lbl?.name || action.label_id}`
  }

  return label
}

function formatTime(time) {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN')
}

// 对话框操作
function showCreateDialog() {
  editingRule.value = null
  ruleForm.value = {
    name: '',
    description: '',
    conditions: {
      logic: 'AND',
      rules: [{ field: 'from_email', operator: 'contains', value: '' }]
    },
    actions: [{ type: 'add_label', label_id: null }],
    stop_processing: false
  }
  dialogVisible.value = true
}

function editRule(rule) {
  editingRule.value = rule
  ruleForm.value = {
    name: rule.name,
    description: rule.description || '',
    conditions: JSON.parse(JSON.stringify(rule.conditions)),
    actions: JSON.parse(JSON.stringify(rule.actions)),
    stop_processing: rule.stop_processing
  }
  dialogVisible.value = true
}

// 条件操作
function addCondition() {
  ruleForm.value.conditions.rules.push({
    field: 'from_email',
    operator: 'contains',
    value: ''
  })
}

function removeCondition(index) {
  ruleForm.value.conditions.rules.splice(index, 1)
}

// 动作操作
function addAction() {
  ruleForm.value.actions.push({
    type: 'add_label',
    label_id: null
  })
}

function removeAction(index) {
  ruleForm.value.actions.splice(index, 1)
}

function onActionTypeChange(action) {
  // 清除不相关的参数
  action.folder_id = null
  action.label_id = null
}

// 保存规则
async function saveRule() {
  // 验证
  if (!ruleForm.value.name.trim()) {
    ElMessage.warning('请输入规则名称')
    return
  }

  const hasValidCondition = ruleForm.value.conditions.rules.some(c => c.value?.trim())
  if (!hasValidCondition && ruleForm.value.conditions.rules[0]?.field !== 'has_attachment') {
    ElMessage.warning('请至少填写一个条件')
    return
  }

  const hasValidAction = ruleForm.value.actions.some(a => {
    if (a.type === 'move_to_folder') return a.folder_id
    if (a.type === 'add_label' || a.type === 'remove_label') return a.label_id
    return true
  })
  if (!hasValidAction) {
    ElMessage.warning('请完善动作配置')
    return
  }

  saving.value = true
  try {
    if (editingRule.value) {
      await api.updateRule(editingRule.value.id, ruleForm.value)
      ElMessage.success('规则已更新')
    } else {
      await api.createRule(ruleForm.value)
      ElMessage.success('规则已创建')
    }
    dialogVisible.value = false
    await loadRules()
  } catch (e) {
    console.error('Save rule failed:', e)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 切换启用状态
async function toggleRule(rule) {
  try {
    await api.toggleRule(rule.id)
    ElMessage.success(rule.is_active ? '规则已启用' : '规则已禁用')
  } catch (e) {
    console.error('Toggle rule failed:', e)
    rule.is_active = !rule.is_active // 回滚
    ElMessage.error('操作失败')
  }
}

// 删除规则
async function deleteRule(rule) {
  try {
    await ElMessageBox.confirm(
      `确定要删除规则"${rule.name}"吗？`,
      '删除确认',
      { type: 'warning' }
    )

    await api.deleteRule(rule.id)
    ElMessage.success('规则已删除')
    await loadRules()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Delete rule failed:', e)
      ElMessage.error('删除失败')
    }
  }
}
</script>

<style scoped>
.rules-page {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
}

.rule-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.rule-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.rule-card.inactive {
  opacity: 0.6;
  background: #f5f7fa;
}

.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.rule-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-priority {
  width: 24px;
  height: 24px;
  background: #409eff;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
}

.rule-name {
  font-size: 16px;
  font-weight: 500;
}

.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-body {
  font-size: 13px;
  color: #606266;
}

.rule-conditions,
.rule-actions-display {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.rule-conditions .label,
.rule-actions-display .label {
  color: #909399;
  white-space: nowrap;
}

.condition-logic {
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.condition-list,
.action-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.rule-stats {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

/* 编辑器样式 */
.conditions-editor,
.actions-editor {
  width: 100%;
}

.logic-selector {
  margin-bottom: 12px;
}

.condition-row,
.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
