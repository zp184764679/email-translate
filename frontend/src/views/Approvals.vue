<template>
  <div class="approvals-page">
    <el-card>
      <template #header>
        <span>待审批邮件</span>
      </template>

      <el-table :data="drafts" v-loading="loading" stripe>
        <el-table-column label="作者" prop="author_id" width="120" />
        <el-table-column label="原邮件主题" min-width="200">
          <template #default="{ row }">
            {{ row.reply_to_email?.subject_original || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="中文内容" min-width="200">
          <template #default="{ row }">
            {{ row.body_chinese?.substring(0, 50) }}...
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.submitted_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDraft(row)">查看</el-button>
            <el-button size="small" type="success" @click="approveDraft(row)">通过</el-button>
            <el-button size="small" type="danger" @click="rejectDraft(row)">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && drafts.length === 0" description="暂无待审批邮件" />
    </el-card>

    <!-- View Dialog -->
    <el-dialog v-model="viewDialogVisible" title="审批详情" width="70%">
      <div v-if="currentDraft">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="提交人">{{ currentDraft.author_id }}</el-descriptions-item>
          <el-descriptions-item label="目标语言">{{ currentDraft.target_language }}</el-descriptions-item>
          <el-descriptions-item label="提交时间" :span="2">{{ formatDate(currentDraft.submitted_at) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <div class="content-compare">
          <div class="content-section">
            <h4>中文原文</h4>
            <div class="content-box">{{ currentDraft.body_chinese }}</div>
          </div>
          <div class="content-section">
            <h4>翻译内容</h4>
            <el-input
              v-model="editableTranslation"
              type="textarea"
              :rows="10"
            />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="viewDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject">驳回</el-button>
        <el-button type="warning" @click="modifyAndApprove">修改后通过</el-button>
        <el-button type="success" @click="confirmApprove">直接通过</el-button>
      </template>
    </el-dialog>

    <!-- Reject Dialog -->
    <el-dialog v-model="rejectDialogVisible" title="驳回原因" width="400px">
      <el-input
        v-model="rejectReason"
        type="textarea"
        :rows="4"
        placeholder="请输入驳回原因..."
      />
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReject">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'

const drafts = ref([])
const loading = ref(false)
const viewDialogVisible = ref(false)
const rejectDialogVisible = ref(false)
const currentDraft = ref(null)
const editableTranslation = ref('')
const rejectReason = ref('')

onMounted(() => {
  loadDrafts()
})

async function loadDrafts() {
  loading.value = true
  try {
    drafts.value = await api.getPendingApprovals()
  } catch (e) {
    console.error('Failed to load drafts:', e)
  } finally {
    loading.value = false
  }
}

function viewDraft(draft) {
  currentDraft.value = draft
  editableTranslation.value = draft.body_translated
  viewDialogVisible.value = true
}

function approveDraft(draft) {
  currentDraft.value = draft
  editableTranslation.value = draft.body_translated
  viewDialogVisible.value = true
}

function rejectDraft(draft) {
  currentDraft.value = draft
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function confirmApprove() {
  try {
    await api.approveDraft(currentDraft.value.id)
    ElMessage.success('已通过并发送')
    viewDialogVisible.value = false
    loadDrafts()
  } catch (e) {
    console.error('Failed to approve:', e)
  }
}

async function confirmReject() {
  rejectDialogVisible.value = true
  viewDialogVisible.value = false
}

async function submitReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请输入驳回原因')
    return
  }

  try {
    await api.rejectDraft(currentDraft.value.id, rejectReason.value)
    ElMessage.success('已驳回')
    rejectDialogVisible.value = false
    loadDrafts()
  } catch (e) {
    console.error('Failed to reject:', e)
  }
}

async function modifyAndApprove() {
  if (!editableTranslation.value.trim()) {
    ElMessage.warning('翻译内容不能为空')
    return
  }

  try {
    await api.modifyAndApprove(currentDraft.value.id, editableTranslation.value)
    ElMessage.success('已修改并发送')
    viewDialogVisible.value = false
    loadDrafts()
  } catch (e) {
    console.error('Failed to modify and approve:', e)
  }
}

function formatDate(date) {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}
</script>

<style scoped>
.content-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.content-section h4 {
  margin-bottom: 8px;
  color: #606266;
}

.content-box {
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
  white-space: pre-wrap;
  min-height: 200px;
}
</style>
