<template>
  <div class="template-manager">
    <!-- Header with search and filters -->
    <div class="manager-header">
      <div class="search-area">
        <el-input
          v-model="searchQuery"
          placeholder="搜索模板名称、描述..."
          :prefix-icon="Search"
          clearable
          style="width: 300px;"
          @input="handleSearch"
        />
        <el-select
          v-model="selectedCategory"
          placeholder="全部分类"
          clearable
          style="width: 150px; margin-left: 10px;"
          @change="loadTemplates"
        >
          <el-option
            v-for="cat in categories"
            :key="cat.code"
            :label="cat.name_cn"
            :value="cat.code"
          />
        </el-select>
        <el-checkbox v-model="includeShared" style="margin-left: 15px;" @change="loadTemplates">
          包含共享模板
        </el-checkbox>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog">
        新建模板
      </el-button>
    </div>

    <!-- Templates Table -->
    <el-table
      v-loading="loading"
      :data="templates"
      stripe
      style="width: 100%;"
      @row-click="handleRowClick"
    >
      <el-table-column prop="name" label="模板名称" min-width="150">
        <template #default="{ row }">
          <div class="template-name">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_shared && !row.is_mine" size="small" type="info">共享</el-tag>
            <el-tag v-if="row.is_shared && row.is_mine" size="small" type="success">已共享</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.category_name" size="small">{{ row.category_name }}</el-tag>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="主题" min-width="200">
        <template #default="{ row }">
          <span class="subject-preview">{{ row.subject_cn || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已翻译" width="150">
        <template #default="{ row }">
          <div class="lang-tags">
            <el-tag
              v-for="lang in row.translated_langs"
              :key="lang"
              size="small"
              type="success"
            >
              {{ getLanguageName(lang) }}
            </el-tag>
            <span v-if="!row.translated_langs?.length" class="text-muted">-</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="使用次数" width="90" align="center">
        <template #default="{ row }">
          <span class="use-count">{{ row.use_count || 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click.stop="viewTemplate(row)">查看</el-button>
          <el-button
            v-if="row.is_mine"
            size="small"
            type="primary"
            @click.stop="editTemplate(row)"
          >
            编辑
          </el-button>
          <el-dropdown v-if="row.is_mine" @command="(cmd) => handleCommand(cmd, row)" trigger="click">
            <el-button size="small" @click.stop>
              更多 <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="translate">翻译</el-dropdown-item>
                <el-dropdown-item v-if="!row.is_shared" command="share">共享</el-dropdown-item>
                <el-dropdown-item v-else command="unshare">取消共享</el-dropdown-item>
                <el-dropdown-item command="delete" divided style="color: #f56c6c;">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div class="pagination-area" v-if="pagination.total > pagination.pageSize">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadTemplates"
        @size-change="loadTemplates"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingTemplate ? '编辑模板' : '新建模板'"
      width="700px"
      destroy-on-close
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item label="模板名称" prop="name">
          <el-input v-model="form.name" placeholder="如：询价模板、订单确认模板" maxlength="100" />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="form.category" placeholder="选择分类" clearable style="width: 100%;">
            <el-option
              v-for="cat in categories"
              :key="cat.code"
              :label="cat.name_cn"
              :value="cat.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="模板用途说明（可选）" maxlength="255" />
        </el-form-item>
        <el-form-item label="中文主题">
          <el-input v-model="form.subject_cn" placeholder="邮件主题（支持变量）" maxlength="255" />
        </el-form-item>
        <el-form-item label="中文正文" prop="body_cn">
          <el-input
            v-model="form.body_cn"
            type="textarea"
            :rows="8"
            placeholder="邮件正文内容（支持变量，如 {supplier_name}、{order_number}）"
          />
        </el-form-item>
        <el-form-item label="可用变量">
          <div class="variables-list">
            <el-tag
              v-for="v in availableVariables"
              :key="v.name"
              size="small"
              type="info"
              class="variable-tag"
              @click="insertVariable(v.name)"
              style="cursor: pointer;"
            >
              {{ `{${v.name}}` }} - {{ v.description }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item label="共享模板">
          <el-switch v-model="form.is_shared" />
          <span class="form-tip">开启后其他同事可以使用此模板</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- View/Translate Dialog -->
    <el-dialog
      v-model="viewDialogVisible"
      :title="viewingTemplate?.name"
      width="800px"
      destroy-on-close
    >
      <div v-if="viewingTemplate" class="template-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="分类">
            {{ viewingTemplate.category_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建者">
            {{ viewingTemplate.author?.email || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="使用次数">
            {{ viewingTemplate.use_count || 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="共享状态">
            <el-tag :type="viewingTemplate.is_shared ? 'success' : 'info'" size="small">
              {{ viewingTemplate.is_shared ? '已共享' : '私有' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-tabs v-model="activeTab" type="card" style="margin-top: 20px;">
          <el-tab-pane label="中文版本" name="zh">
            <div class="content-block">
              <div class="content-label">主题</div>
              <div class="content-text">{{ viewingTemplate.subject_cn || '-' }}</div>
            </div>
            <div class="content-block">
              <div class="content-label">正文</div>
              <div class="content-text body-content">{{ viewingTemplate.body_cn }}</div>
            </div>
          </el-tab-pane>
          <el-tab-pane
            v-for="trans in viewingTemplate.translations"
            :key="trans.target_lang"
            :label="trans.target_lang_name"
            :name="trans.target_lang"
          >
            <div class="content-block">
              <div class="content-label">主题</div>
              <div class="content-text">{{ trans.subject_translated || '-' }}</div>
            </div>
            <div class="content-block">
              <div class="content-label">正文</div>
              <div class="content-text body-content">{{ trans.body_translated }}</div>
            </div>
            <div class="translation-info">
              翻译时间: {{ formatDate(trans.translated_at) }}
            </div>
          </el-tab-pane>
        </el-tabs>

        <!-- Translate Section -->
        <div class="translate-section" v-if="viewingTemplate.is_mine">
          <el-divider>生成翻译版本</el-divider>
          <div class="translate-controls">
            <el-select v-model="translateTargetLang" placeholder="选择目标语言" style="width: 200px;">
              <el-option
                v-for="lang in languages"
                :key="lang.code"
                :label="lang.name"
                :value="lang.code"
                :disabled="hasTranslation(lang.code)"
              />
            </el-select>
            <el-button
              type="primary"
              @click="translateTemplate"
              :loading="translating"
              :disabled="!translateTargetLang"
            >
              翻译
            </el-button>
            <el-checkbox v-model="forceRetranslate" style="margin-left: 15px;">
              强制重新翻译
            </el-checkbox>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="viewDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="handleUseTemplate" :loading="using">
          使用此模板
        </el-button>
      </template>
    </el-dialog>

    <!-- Use Template Dialog -->
    <el-dialog
      v-model="useDialogVisible"
      title="使用模板"
      width="700px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="选择语言">
          <el-radio-group v-model="useTargetLang">
            <el-radio label="">中文原文</el-radio>
            <el-radio
              v-for="trans in viewingTemplate?.translations || []"
              :key="trans.target_lang"
              :label="trans.target_lang"
            >
              {{ trans.target_lang_name }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="填充变量" v-if="viewingTemplate?.variables?.length">
          <div class="variables-input">
            <div v-for="varName in viewingTemplate.variables" :key="varName" class="variable-row">
              <span class="variable-name">{{ `{${varName}}` }}</span>
              <el-input
                v-model="variableValues[varName]"
                :placeholder="getVariableDescription(varName)"
                style="width: 300px;"
              />
            </div>
          </div>
        </el-form-item>
        <el-form-item label="预览结果">
          <div class="preview-box">
            <div class="preview-subject" v-if="previewSubject">
              <strong>主题：</strong>{{ previewSubject }}
            </div>
            <div class="preview-body">{{ previewBody }}</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="useDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmUseTemplate">
          复制到撰写框
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, ArrowDown } from '@element-plus/icons-vue'
import api from '@/api'
import { debounce } from 'lodash-es'

// Props
const props = defineProps({
  // 选择模式：选择模板后触发事件而不是复制
  selectMode: {
    type: Boolean,
    default: false
  }
})

// Emits
const emit = defineEmits(['select', 'use'])

// Data
const loading = ref(false)
const saving = ref(false)
const translating = ref(false)
const using = ref(false)

const templates = ref([])
const categories = ref([])
const languages = ref([])
const availableVariables = ref([])

const searchQuery = ref('')
const selectedCategory = ref('')
const includeShared = ref(true)

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// Dialog states
const dialogVisible = ref(false)
const viewDialogVisible = ref(false)
const useDialogVisible = ref(false)

const editingTemplate = ref(null)
const viewingTemplate = ref(null)

const form = reactive({
  name: '',
  description: '',
  category: '',
  subject_cn: '',
  body_cn: '',
  is_shared: false
})

const formRules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  body_cn: [{ required: true, message: '请输入正文内容', trigger: 'blur' }]
}

const formRef = ref(null)

const activeTab = ref('zh')
const translateTargetLang = ref('')
const forceRetranslate = ref(false)

const useTargetLang = ref('')
const variableValues = reactive({})

// Computed
const previewSubject = computed(() => {
  if (!viewingTemplate.value) return ''
  let subject = viewingTemplate.value.subject_cn
  if (useTargetLang.value) {
    const trans = viewingTemplate.value.translations?.find(t => t.target_lang === useTargetLang.value)
    if (trans?.subject_translated) {
      subject = trans.subject_translated
    }
  }
  return replaceVariables(subject)
})

const previewBody = computed(() => {
  if (!viewingTemplate.value) return ''
  let body = viewingTemplate.value.body_cn
  if (useTargetLang.value) {
    const trans = viewingTemplate.value.translations?.find(t => t.target_lang === useTargetLang.value)
    if (trans?.body_translated) {
      body = trans.body_translated
    }
  }
  return replaceVariables(body)
})

// Methods
const loadTemplates = async () => {
  loading.value = true
  try {
    const result = await api.getTemplates({
      category: selectedCategory.value || undefined,
      include_shared: includeShared.value,
      search: searchQuery.value || undefined,
      page: pagination.page,
      page_size: pagination.pageSize
    })
    templates.value = result.items || []
    pagination.total = result.total || 0
  } catch (error) {
    console.error('Failed to load templates:', error)
    ElMessage.error('加载模板列表失败')
  } finally {
    loading.value = false
  }
}

const loadCategories = async () => {
  try {
    categories.value = await api.getTemplateCategories()
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

const loadLanguages = async () => {
  try {
    languages.value = await api.getTemplateLanguages()
  } catch (error) {
    console.error('Failed to load languages:', error)
  }
}

const loadVariables = async () => {
  try {
    availableVariables.value = await api.getTemplateVariables()
  } catch (error) {
    console.error('Failed to load variables:', error)
  }
}

const handleSearch = debounce(() => {
  pagination.page = 1
  loadTemplates()
}, 300)

const showCreateDialog = () => {
  editingTemplate.value = null
  Object.assign(form, {
    name: '',
    description: '',
    category: '',
    subject_cn: '',
    body_cn: '',
    is_shared: false
  })
  dialogVisible.value = true
}

const editTemplate = (template) => {
  editingTemplate.value = template
  Object.assign(form, {
    name: template.name,
    description: template.description || '',
    category: template.category || '',
    subject_cn: template.subject_cn || '',
    body_cn: template.body_cn || '',
    is_shared: template.is_shared || false
  })
  dialogVisible.value = true
}

const viewTemplate = async (template) => {
  try {
    loading.value = true
    const detail = await api.getTemplate(template.id)
    viewingTemplate.value = detail
    activeTab.value = 'zh'
    translateTargetLang.value = ''
    viewDialogVisible.value = true
  } catch (error) {
    ElMessage.error('获取模板详情失败')
  } finally {
    loading.value = false
  }
}

const saveTemplate = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    if (editingTemplate.value) {
      await api.updateTemplate(editingTemplate.value.id, form)
      ElMessage.success('模板已更新')
    } else {
      await api.createTemplate(form)
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    loadTemplates()
  } catch (error) {
    ElMessage.error('保存模板失败')
  } finally {
    saving.value = false
  }
}

const deleteTemplate = async (template) => {
  try {
    await ElMessageBox.confirm(`确定要删除模板"${template.name}"吗？`, '删除确认', {
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await api.deleteTemplate(template.id)
    ElMessage.success('模板已删除')
    loadTemplates()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const shareTemplate = async (template) => {
  try {
    await api.shareTemplate(template.id)
    ElMessage.success('模板已共享')
    loadTemplates()
  } catch (error) {
    ElMessage.error('共享失败')
  }
}

const unshareTemplate = async (template) => {
  try {
    await api.unshareTemplate(template.id)
    ElMessage.success('已取消共享')
    loadTemplates()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const translateTemplate = async () => {
  if (!translateTargetLang.value || !viewingTemplate.value) return

  translating.value = true
  try {
    const result = await api.translateTemplate(
      viewingTemplate.value.id,
      translateTargetLang.value,
      forceRetranslate.value
    )
    ElMessage.success(result.cached ? '使用缓存的翻译' : '翻译完成')
    // Refresh detail
    const detail = await api.getTemplate(viewingTemplate.value.id)
    viewingTemplate.value = detail
    activeTab.value = translateTargetLang.value
    translateTargetLang.value = ''
  } catch (error) {
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

const handleCommand = (command, template) => {
  switch (command) {
    case 'translate':
      viewTemplate(template)
      break
    case 'share':
      shareTemplate(template)
      break
    case 'unshare':
      unshareTemplate(template)
      break
    case 'delete':
      deleteTemplate(template)
      break
  }
}

const handleRowClick = (row) => {
  if (props.selectMode) {
    emit('select', row)
  }
}

const handleUseTemplate = () => {
  if (!viewingTemplate.value) return
  // Reset values
  useTargetLang.value = ''
  Object.keys(variableValues).forEach(key => delete variableValues[key])
  useDialogVisible.value = true
}

const confirmUseTemplate = () => {
  const result = {
    subject: previewSubject.value,
    body: previewBody.value,
    template_id: viewingTemplate.value?.id,
    target_lang: useTargetLang.value || null
  }

  emit('use', result)

  // Copy to clipboard as fallback
  if (!props.selectMode) {
    const text = previewSubject.value
      ? `主题: ${previewSubject.value}\n\n${previewBody.value}`
      : previewBody.value
    navigator.clipboard.writeText(text).then(() => {
      ElMessage.success('已复制到剪贴板')
    })
  }

  useDialogVisible.value = false
  viewDialogVisible.value = false
}

const insertVariable = (varName) => {
  form.body_cn += `{${varName}}`
}

const hasTranslation = (langCode) => {
  return viewingTemplate.value?.translations?.some(t => t.target_lang === langCode)
}

const replaceVariables = (text) => {
  if (!text) return ''
  let result = text
  for (const [name, value] of Object.entries(variableValues)) {
    if (value) {
      result = result.replace(new RegExp(`\\{${name}\\}`, 'g'), value)
    }
  }
  return result
}

const getLanguageName = (code) => {
  const langMap = {
    zh: '中文',
    en: '英语',
    ja: '日语',
    ko: '韩语',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    it: '意大利语',
    pt: '葡萄牙语',
    ru: '俄语',
    vi: '越南语',
    th: '泰语'
  }
  return langMap[code] || code
}

const getVariableDescription = (varName) => {
  const v = availableVariables.value.find(v => v.name === varName)
  return v ? `${v.description}，如：${v.example}` : varName
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

// Lifecycle
onMounted(() => {
  loadTemplates()
  loadCategories()
  loadLanguages()
  loadVariables()
})
</script>

<style scoped>
.template-manager {
  padding: 0;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.search-area {
  display: flex;
  align-items: center;
}

.template-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.subject-preview {
  color: #606266;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lang-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.use-count {
  color: #909399;
}

.text-muted {
  color: #909399;
}

.pagination-area {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.variables-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.variable-tag {
  cursor: pointer;
}

.variable-tag:hover {
  background-color: #409eff;
  color: white;
}

.form-tip {
  color: #909399;
  font-size: 12px;
  margin-left: 10px;
}

.template-detail .content-block {
  margin-bottom: 15px;
}

.content-label {
  font-weight: 500;
  color: #606266;
  margin-bottom: 5px;
}

.content-text {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

.body-content {
  min-height: 150px;
  max-height: 300px;
  overflow-y: auto;
}

.translation-info {
  text-align: right;
  font-size: 12px;
  color: #909399;
  margin-top: 10px;
}

.translate-section {
  margin-top: 20px;
}

.translate-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.variables-input {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.variable-row {
  display: flex;
  align-items: center;
  gap: 15px;
}

.variable-name {
  width: 150px;
  font-family: monospace;
  color: #409eff;
}

.preview-box {
  padding: 15px;
  background: #f5f7fa;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.preview-subject {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e4e7ed;
}
</style>
</template>
