<template>
  <div class="drafts-page">
    <!-- 列表头部 -->
    <div class="page-header">
      <div class="header-left">
        <h2>草稿箱</h2>
        <span class="draft-count">({{ drafts.length }})</span>
      </div>
      <div class="header-right">
        <el-button type="primary" :icon="EditPen" @click="showNewDraft">
          新建草稿
        </el-button>
      </div>
    </div>

    <!-- 草稿列表 -->
    <div class="drafts-list" v-loading="loading">
      <div
        v-for="draft in drafts"
        :key="draft.id"
        class="draft-item"
        @click="editDraft(draft)"
      >
        <div class="draft-left">
          <el-checkbox
            :model-value="selectedDrafts.includes(draft.id)"
            @change="toggleSelect(draft.id)"
            @click.stop
          />
        </div>

        <div class="draft-content">
          <div class="draft-header">
            <span class="draft-recipient">
              {{ draft.reply_to_email?.from_name || draft.reply_to_email?.from_email || '新邮件' }}
            </span>
            <span class="draft-time">{{ formatTime(draft.updated_at || draft.created_at) }}</span>
          </div>
          <div class="draft-subject">
            回复: {{ draft.reply_to_email?.subject_original || '(无主题)' }}
          </div>
          <div class="draft-preview">
            {{ getPreview(draft) }}
          </div>
        </div>

        <div class="draft-actions">
          <el-tag :type="getStatusType(draft.status)" size="small">
            {{ getStatusText(draft.status) }}
          </el-tag>
          <el-button
            v-if="draft.status === 'draft'"
            type="primary"
            size="small"
            @click.stop="submitDraftFromList(draft)"
          >
            发送
          </el-button>
          <el-button
            type="danger"
            size="small"
            plain
            @click.stop="deleteDraft(draft)"
          >
            删除
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <el-empty v-if="!loading && drafts.length === 0" description="暂无草稿" />
    </div>

    <!-- 编辑草稿对话框 -->
    <el-dialog
      v-model="showEditDialog"
      :title="editingDraft?.id ? '编辑草稿' : '新建草稿'"
      width="75%"
      top="5vh"
      :close-on-click-modal="false"
    >
      <div class="edit-dialog-content" v-if="editingDraft">
        <div class="edit-header" v-if="editingDraft.reply_to_email">
          <span>回复给：</span>
          <strong>{{ editingDraft.reply_to_email.from_name || editingDraft.reply_to_email.from_email }}</strong>
        </div>

        <div class="edit-body-grid">
          <div class="edit-input">
            <div class="section-label">
              中文内容
              <el-select v-model="editingDraft.target_language" size="small" style="margin-left: 12px; width: 100px;">
                <el-option label="英语" value="en" />
                <el-option label="日语" value="ja" />
                <el-option label="韩语" value="ko" />
                <el-option label="德语" value="de" />
                <el-option label="法语" value="fr" />
              </el-select>
            </div>
            <el-input
              v-model="editingDraft.body_chinese"
              type="textarea"
              :rows="12"
              placeholder="请输入中文内容..."
            />
          </div>

          <div class="edit-preview">
            <div class="section-label">
              翻译预览 ({{ getLanguageName(editingDraft.target_language) }})
              <el-button size="small" type="primary" @click="translateDraft" :loading="translating">
                翻译
              </el-button>
            </div>
            <el-input
              v-model="editingDraft.body_translated"
              type="textarea"
              :rows="12"
              placeholder="点击翻译按钮生成译文..."
            />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button @click="saveDraft">保存草稿</el-button>
        <el-button type="primary" @click="showApproverDialog" :loading="sending">
          提交审批
        </el-button>
      </template>
    </el-dialog>

    <!-- 选择审批人对话框 -->
    <el-dialog
      v-model="showApproverSelector"
      title="选择审批人"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px">
        <el-form-item label="审批人" required>
          <el-select
            v-model="selectedApproverId"
            placeholder="请选择审批人"
            style="width: 100%"
          >
            <el-option
              v-for="approver in approvers"
              :key="approver.id"
              :label="approver.email"
              :value="approver.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="saveAsDefaultApprover">设为默认审批人</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showApproverSelector = false">取消</el-button>
        <el-button type="primary" @click="confirmSendWithApprover" :loading="sending">
          确认提交
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { EditPen } from '@element-plus/icons-vue'
import api from '@/api'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'

const drafts = ref([])
const loading = ref(false)
const selectedDrafts = ref([])
const showEditDialog = ref(false)
const editingDraft = ref(null)
const translating = ref(false)
const sending = ref(false)

// 审批人相关
const showApproverSelector = ref(false)
const approvers = ref([])
const selectedApproverId = ref(null)
const saveAsDefaultApprover = ref(false)
const defaultApproverId = ref(null)
const pendingDraftForSend = ref(null)  // 待发送的草稿

onMounted(async () => {
  await loadDrafts()
  await loadApprovers()
  await loadUserInfo()
})

async function loadDrafts() {
  loading.value = true
  try {
    drafts.value = await api.getMyDrafts()
  } catch (e) {
    console.error('Failed to load drafts:', e)
  } finally {
    loading.value = false
  }
}

function toggleSelect(id) {
  const index = selectedDrafts.value.indexOf(id)
  if (index > -1) {
    selectedDrafts.value.splice(index, 1)
  } else {
    selectedDrafts.value.push(id)
  }
}

function showNewDraft() {
  editingDraft.value = {
    body_chinese: '',
    body_translated: '',
    target_language: 'en'
  }
  showEditDialog.value = true
}

function editDraft(draft) {
  editingDraft.value = { ...draft }
  showEditDialog.value = true
}

async function translateDraft() {
  if (!editingDraft.value.body_chinese.trim()) {
    ElMessage.warning('请先输入中文内容')
    return
  }

  translating.value = true
  try {
    const result = await api.translateReply(
      editingDraft.value.body_chinese,
      editingDraft.value.target_language,
      null,
      null
    )
    editingDraft.value.body_translated = result.translated_text
    ElMessage.success('翻译完成')
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

async function saveDraft() {
  if (!editingDraft.value.body_chinese.trim()) {
    ElMessage.warning('请输入内容')
    return
  }

  try {
    if (editingDraft.value.id) {
      await api.updateDraft(editingDraft.value.id, editingDraft.value)
    } else {
      await api.createDraft(editingDraft.value)
    }
    ElMessage.success('草稿已保存')
    showEditDialog.value = false
    loadDrafts()
  } catch (e) {
    console.error('Failed to save draft:', e)
    ElMessage.error('保存失败')
  }
}

async function sendDraft() {
  if (!editingDraft.value.body_chinese.trim()) {
    ElMessage.warning('请输入内容')
    return
  }

  if (!editingDraft.value.body_translated.trim()) {
    ElMessage.warning('请先翻译内容')
    return
  }

  sending.value = true
  try {
    let draft = editingDraft.value
    if (!draft.id) {
      draft = await api.createDraft(draft)
    }

    const result = await api.submitDraft(draft.id)

    if (result.status === 'sent') {
      ElMessage.success('邮件已发送')
    } else if (result.status === 'pending') {
      ElMessage.info(`邮件已提交审批 (触发规则: ${result.rule})`)
    }

    showEditDialog.value = false
    loadDrafts()
  } catch (e) {
    console.error('Failed to send draft:', e)
    ElMessage.error('发送失败')
  } finally {
    sending.value = false
  }
}

async function submitDraft(draft) {
  try {
    const result = await api.submitDraft(draft.id)

    if (result.status === 'sent') {
      ElMessage.success('邮件已发送')
    } else if (result.status === 'pending') {
      ElMessage.info(`邮件已提交审批 (触发规则: ${result.rule})`)
    }

    loadDrafts()
  } catch (e) {
    console.error('Failed to submit draft:', e)
    ElMessage.error('发送失败')
  }
}

async function deleteDraft(draft) {
  try {
    await ElMessageBox.confirm('确定要删除这个草稿吗？', '确认删除', {
      type: 'warning'
    })

    await api.deleteDraft(draft.id)
    ElMessage.success('已删除')
    loadDrafts()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete draft:', e)
      ElMessage.error('删除失败')
    }
  }
}

function formatTime(date) {
  if (!date) return ''
  const d = dayjs(date)
  const today = dayjs()

  if (d.isSame(today, 'day')) {
    return d.format('HH:mm')
  } else if (d.isSame(today, 'year')) {
    return d.format('MM/DD HH:mm')
  }
  return d.format('YYYY/MM/DD')
}

function getPreview(draft) {
  const body = draft.body_chinese || draft.body_translated || ''
  return body.substring(0, 80).replace(/\n/g, ' ').trim()
}

function getStatusType(status) {
  const types = {
    draft: 'info',
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    sent: 'success'
  }
  return types[status] || 'info'
}

function getStatusText(status) {
  const texts = {
    draft: '草稿',
    pending: '待审批',
    approved: '已批准',
    rejected: '已拒绝',
    sent: '已发送'
  }
  return texts[status] || status
}

function getLanguageName(lang) {
  const names = {
    en: '英语',
    ja: '日语',
    ko: '韩语',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    pt: '葡萄牙语',
    ru: '俄语'
  }
  return names[lang] || lang
}

// ============ 审批人相关函数 ============
async function loadApprovers() {
  try {
    approvers.value = await api.getApprovers()
  } catch (e) {
    console.error('Failed to load approvers:', e)
  }
}

async function loadUserInfo() {
  try {
    const userInfo = await api.getCurrentAccount()
    defaultApproverId.value = userInfo.default_approver_id
  } catch (e) {
    console.error('Failed to load user info:', e)
  }
}

function showApproverDialog() {
  // 验证草稿内容
  if (!editingDraft.value.body_chinese.trim()) {
    ElMessage.warning('请输入内容')
    return
  }

  if (!editingDraft.value.body_translated.trim()) {
    ElMessage.warning('请先翻译内容')
    return
  }

  // 设置默认审批人
  if (defaultApproverId.value) {
    selectedApproverId.value = defaultApproverId.value
  } else if (approvers.value.length > 0) {
    selectedApproverId.value = approvers.value[0].id
  }

  // 保存待发送的草稿引用
  pendingDraftForSend.value = editingDraft.value

  // 显示审批人选择对话框
  showApproverSelector.value = true
}

async function confirmSendWithApprover() {
  if (!selectedApproverId.value) {
    ElMessage.warning('请选择审批人')
    return
  }

  sending.value = true
  try {
    let draft = pendingDraftForSend.value

    // 如果是新草稿，先保存
    if (!draft.id) {
      draft = await api.createDraft(draft)
    } else {
      // 更新现有草稿
      await api.updateDraft(draft.id, draft)
    }

    // 提交审批
    const result = await api.submitDraft(
      draft.id,
      selectedApproverId.value,
      saveAsDefaultApprover.value
    )

    ElMessage.success(`邮件已提交审批，审批人: ${result.approver}`)

    // 如果设置为默认审批人，更新本地状态
    if (saveAsDefaultApprover.value) {
      defaultApproverId.value = selectedApproverId.value
    }

    // 关闭对话框
    showApproverSelector.value = false
    showEditDialog.value = false

    // 重置状态
    saveAsDefaultApprover.value = false
    pendingDraftForSend.value = null

    // 刷新草稿列表
    loadDrafts()
  } catch (e) {
    console.error('Failed to submit for approval:', e)
    ElMessage.error('提交审批失败')
  } finally {
    sending.value = false
  }
}

// 草稿列表中直接发送（也需要选择审批人）
async function submitDraftFromList(draft) {
  // 设置默认审批人
  if (defaultApproverId.value) {
    selectedApproverId.value = defaultApproverId.value
  } else if (approvers.value.length > 0) {
    selectedApproverId.value = approvers.value[0].id
  }

  // 保存待发送的草稿
  pendingDraftForSend.value = draft

  // 显示审批人选择对话框
  showApproverSelector.value = true
}
</script>

<style scoped>
.drafts-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  background-color: #fafafa;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1a1a1a;
}

.draft-count {
  font-size: 14px;
  color: #909399;
}

.drafts-list {
  flex: 1;
  overflow-y: auto;
}

.draft-item {
  display: flex;
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.draft-item:hover {
  background-color: #f5f7fa;
}

.draft-left {
  margin-right: 12px;
}

.draft-content {
  flex: 1;
  min-width: 0;
}

.draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.draft-recipient {
  font-weight: 600;
  font-size: 14px;
  color: #1a1a1a;
}

.draft-time {
  font-size: 12px;
  color: #909399;
}

.draft-subject {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.draft-preview {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.draft-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 16px;
}

/* 编辑对话框 */
.edit-dialog-content {
  padding: 0 10px;
}

.edit-header {
  margin-bottom: 16px;
  font-size: 14px;
  color: #606266;
}

.edit-body-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 8px;
}
</style>
