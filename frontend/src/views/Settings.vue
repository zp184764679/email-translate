<template>
  <div class="settings-page">
    <!-- 邮件签名 -->
    <el-card style="margin-bottom: 20px;">
      <template #header>
        <div class="card-header">
          <span>邮件签名</span>
          <el-button type="primary" :icon="Plus" @click="showAddSignature">新建签名</el-button>
        </div>
      </template>

      <el-table :data="signatures" stripe>
        <el-table-column prop="name" label="签名名称" width="150" />
        <el-table-column label="中文内容" min-width="200">
          <template #default="{ row }">
            <div class="signature-preview">{{ row.content_chinese || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="翻译内容" min-width="200">
          <template #default="{ row }">
            <div class="signature-preview">{{ row.content_translated || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="目标语言" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ getLanguageName(row.target_language) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="editSignature(row)">编辑</el-button>
            <el-button size="small" type="primary" @click="setDefaultSignature(row)" :disabled="row.is_default">设为默认</el-button>
            <el-button size="small" type="danger" @click="deleteSignature(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="signatures.length === 0" description="暂无签名，点击上方按钮创建" />
    </el-card>

    <!-- 审批设置 -->
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>默认审批人</span>
          </template>
          <el-select
            v-model="defaultApproverId"
            placeholder="选择默认审批人"
            clearable
            style="width: 100%;"
            @change="saveDefaultApprover"
          >
            <el-option
              v-for="approver in approvers"
              :key="approver.id"
              :label="approver.email"
              :value="approver.id"
            />
          </el-select>
          <div class="form-tip">提交审批时将自动选择此人</div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>审批人组</span>
              <el-button type="primary" size="small" :icon="Plus" @click="showAddGroup">新建组</el-button>
            </div>
          </template>

          <el-table :data="approvalGroups" stripe max-height="300">
            <el-table-column prop="name" label="组名" width="120" />
            <el-table-column prop="description" label="描述" width="150">
              <template #default="{ row }">
                <span class="text-muted">{{ row.description || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="成员" min-width="250">
              <template #default="{ row }">
                <div class="member-tags">
                  <el-tag
                    v-for="member in row.members"
                    :key="member.id"
                    size="small"
                    closable
                    @close="removeGroupMember(row.id, member.id)"
                  >
                    {{ member.email.split('@')[0] }}
                  </el-tag>
                  <el-button size="small" :icon="Plus" circle @click="showAddMember(row)" title="添加成员" />
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="editGroup(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="deleteGroup(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="approvalGroups.length === 0" description="暂无审批人组，点击上方按钮创建" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Signature Dialog -->
    <el-dialog v-model="signatureDialogVisible" :title="signatureForm.id ? '编辑签名' : '新建签名'" width="600px">
      <el-form :model="signatureForm" label-width="100px">
        <el-form-item label="签名名称" required>
          <el-input v-model="signatureForm.name" placeholder="例如: 默认签名、正式签名" />
        </el-form-item>
        <el-form-item label="目标语言">
          <el-select v-model="signatureForm.target_language">
            <el-option label="英语" value="en" />
            <el-option label="日语" value="ja" />
            <el-option label="韩语" value="ko" />
            <el-option label="德语" value="de" />
            <el-option label="法语" value="fr" />
            <el-option label="西班牙语" value="es" />
          </el-select>
        </el-form-item>
        <el-form-item label="中文签名">
          <el-input
            v-model="signatureForm.content_chinese"
            type="textarea"
            :rows="4"
            placeholder="输入中文签名内容，例如：&#10;此致&#10;敬礼&#10;&#10;张三&#10;采购部&#10;电话: 123-456-7890"
          />
        </el-form-item>
        <el-form-item label="翻译签名">
          <el-input
            v-model="signatureForm.content_translated"
            type="textarea"
            :rows="4"
            placeholder="输入翻译后的签名内容，或点击下方按钮自动翻译"
          />
          <el-button
            style="margin-top: 8px;"
            size="small"
            :loading="translatingSignature"
            @click="translateSignature"
            :disabled="!signatureForm.content_chinese"
          >
            自动翻译
          </el-button>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="signatureForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="signatureDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSignature" :loading="savingSignature">保存</el-button>
      </template>
    </el-dialog>

    <!-- Approval Group Dialog -->
    <el-dialog v-model="groupDialogVisible" :title="groupForm.id ? '编辑审批人组' : '新建审批人组'" width="500px">
      <el-form :model="groupForm" label-width="80px">
        <el-form-item label="组名" required>
          <el-input v-model="groupForm.name" placeholder="例如: 采购组、销售组" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="groupForm.description" type="textarea" :rows="2" placeholder="可选：组的用途说明" />
        </el-form-item>
        <el-form-item label="成员" v-if="!groupForm.id">
          <el-select
            v-model="groupForm.member_ids"
            multiple
            filterable
            placeholder="选择组成员"
            style="width: 100%;"
          >
            <el-option
              v-for="approver in approvers"
              :key="approver.id"
              :label="approver.email"
              :value="approver.id"
            />
          </el-select>
          <div class="form-tip">可以先创建组，之后再添加成员</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveGroup" :loading="savingGroup">保存</el-button>
      </template>
    </el-dialog>

    <!-- Add Member Dialog -->
    <el-dialog v-model="memberDialogVisible" title="添加组成员" width="400px">
      <el-select
        v-model="selectedMemberId"
        filterable
        placeholder="选择要添加的成员"
        style="width: 100%;"
      >
        <el-option
          v-for="approver in availableMembers"
          :key="approver.id"
          :label="approver.email"
          :value="approver.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addMemberToGroup" :disabled="!selectedMemberId">添加</el-button>
      </template>
    </el-dialog>

    <!-- 关于 -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <span>关于</span>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="应用名称">供应商邮件翻译系统</el-descriptions-item>
        <el-descriptions-item label="当前版本">
          <el-tag type="primary">v{{ appVersion }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="运行环境">
          <el-tag :type="isElectron ? 'success' : 'info'">{{ isElectron ? 'Electron 桌面端' : '浏览器' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="服务器地址">
          <span class="text-muted">{{ apiBaseUrl }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 16px; display: flex; gap: 10px;">
        <el-button type="primary" @click="checkForUpdates" :loading="checkingUpdate">
          检查更新
        </el-button>
        <el-button @click="openGitHub">
          GitHub 仓库
        </el-button>
      </div>
      <div v-if="updateStatus" style="margin-top: 12px;">
        <el-alert :title="updateStatus" :type="updateStatusType" show-icon :closable="false" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import api, { API_BASE_URL } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// 关于信息
const appVersion = ref('unknown')
const isElectron = ref(false)
const apiBaseUrl = ref(API_BASE_URL)
const checkingUpdate = ref(false)
const updateStatus = ref('')
const updateStatusType = ref('info')

// 初始化应用信息
function initAppInfo() {
  // 检测是否在 Electron 环境
  isElectron.value = !!(window.electronAPI)

  // 获取版本号
  if (window.electronAPI?.getAppVersion) {
    window.electronAPI.getAppVersion().then(version => {
      appVersion.value = version
    }).catch(() => {
      appVersion.value = import.meta.env.VITE_APP_VERSION || '1.0.37'
    })
  } else {
    appVersion.value = import.meta.env.VITE_APP_VERSION || '1.0.37'
  }
}

// 检查更新
async function checkForUpdates() {
  checkingUpdate.value = true
  updateStatus.value = ''

  try {
    if (window.electronAPI?.checkForUpdates) {
      await window.electronAPI.checkForUpdates()
      updateStatus.value = '正在检查更新...'
      updateStatusType.value = 'info'
    } else {
      updateStatus.value = '请在桌面端应用中检查更新'
      updateStatusType.value = 'warning'
    }
  } catch (e) {
    updateStatus.value = '检查更新失败: ' + (e.message || '未知错误')
    updateStatusType.value = 'error'
  } finally {
    checkingUpdate.value = false
  }
}

// 打开 GitHub
function openGitHub() {
  const url = 'https://github.com/zp184764679/email-translate'
  if (window.electronAPI?.openExternal) {
    window.electronAPI.openExternal(url)
  } else {
    window.open(url, '_blank')
  }
}

const signatures = ref([])
const approvers = ref([])
const approvalGroups = ref([])
const defaultApproverId = ref(null)
const signatureDialogVisible = ref(false)
const groupDialogVisible = ref(false)
const memberDialogVisible = ref(false)
const translatingSignature = ref(false)
const savingSignature = ref(false)
const savingGroup = ref(false)
const selectedMemberId = ref(null)
const currentGroupId = ref(null)

const signatureForm = reactive({
  id: null,
  name: '',
  content_chinese: '',
  content_translated: '',
  target_language: 'en',
  is_default: false
})

const groupForm = reactive({
  id: null,
  name: '',
  description: '',
  member_ids: []
})

// 计算可添加的成员（排除已在组中的成员）
const availableMembers = computed(() => {
  if (!currentGroupId.value) return approvers.value
  const group = approvalGroups.value.find(g => g.id === currentGroupId.value)
  if (!group) return approvers.value
  const existingIds = new Set(group.members.map(m => m.id))
  return approvers.value.filter(a => !existingIds.has(a.id))
})

const languageMap = {
  en: '英语',
  ja: '日语',
  ko: '韩语',
  de: '德语',
  fr: '法语',
  es: '西班牙语',
  zh: '中文'
}

function getLanguageName(code) {
  return languageMap[code] || code
}

onMounted(() => {
  initAppInfo()
  loadSignatures()
  loadApprovers()
  loadApprovalGroups()
})

async function loadApprovers() {
  try {
    // 获取可选审批人列表
    approvers.value = await api.getApprovers()
    // 获取当前账户信息
    const me = await api.getCurrentAccount()
    defaultApproverId.value = me.default_approver_id
  } catch (e) {
    console.error('Failed to load approvers:', e)
  }
}

async function saveDefaultApprover() {
  try {
    await api.setDefaultApprover(defaultApproverId.value)
    ElMessage.success('默认审批人已保存')
  } catch (e) {
    console.error('Failed to save default approver:', e)
    ElMessage.error('保存失败')
  }
}

// ========== 审批人组管理 ==========
async function loadApprovalGroups() {
  try {
    approvalGroups.value = await api.getApprovalGroups()
  } catch (e) {
    console.error('Failed to load approval groups:', e)
  }
}

function showAddGroup() {
  Object.assign(groupForm, {
    id: null,
    name: '',
    description: '',
    member_ids: []
  })
  groupDialogVisible.value = true
}

function editGroup(group) {
  Object.assign(groupForm, {
    id: group.id,
    name: group.name,
    description: group.description || '',
    member_ids: []
  })
  groupDialogVisible.value = true
}

async function saveGroup() {
  if (!groupForm.name) {
    ElMessage.warning('请输入组名')
    return
  }

  savingGroup.value = true
  try {
    if (groupForm.id) {
      await api.updateApprovalGroup(groupForm.id, {
        name: groupForm.name,
        description: groupForm.description
      })
      ElMessage.success('审批人组已更新')
    } else {
      await api.createApprovalGroup({
        name: groupForm.name,
        description: groupForm.description,
        member_ids: groupForm.member_ids
      })
      ElMessage.success('审批人组已创建')
    }
    groupDialogVisible.value = false
    loadApprovalGroups()
  } catch (e) {
    console.error('Failed to save group:', e)
    ElMessage.error('保存失败')
  } finally {
    savingGroup.value = false
  }
}

async function deleteGroup(group) {
  try {
    await ElMessageBox.confirm(`确定要删除审批人组 "${group.name}" 吗？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await api.deleteApprovalGroup(group.id)
    ElMessage.success('审批人组已删除')
    loadApprovalGroups()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete group:', e)
      ElMessage.error('删除失败')
    }
  }
}

function showAddMember(group) {
  currentGroupId.value = group.id
  selectedMemberId.value = null
  memberDialogVisible.value = true
}

async function addMemberToGroup() {
  if (!selectedMemberId.value || !currentGroupId.value) return

  try {
    await api.addGroupMember(currentGroupId.value, selectedMemberId.value)
    ElMessage.success('成员已添加')
    memberDialogVisible.value = false
    loadApprovalGroups()
  } catch (e) {
    console.error('Failed to add member:', e)
    ElMessage.error('添加失败')
  }
}

async function removeGroupMember(groupId, memberId) {
  try {
    await api.removeGroupMember(groupId, memberId)
    ElMessage.success('成员已移除')
    loadApprovalGroups()
  } catch (e) {
    console.error('Failed to remove member:', e)
    ElMessage.error('移除失败')
  }
}

// Signature functions
async function loadSignatures() {
  try {
    signatures.value = await api.getSignatures()
  } catch (e) {
    console.error('Failed to load signatures:', e)
  }
}

function showAddSignature() {
  Object.assign(signatureForm, {
    id: null,
    name: '',
    content_chinese: '',
    content_translated: '',
    target_language: 'en',
    is_default: false
  })
  signatureDialogVisible.value = true
}

function editSignature(signature) {
  Object.assign(signatureForm, {
    id: signature.id,
    name: signature.name,
    content_chinese: signature.content_chinese || '',
    content_translated: signature.content_translated || '',
    target_language: signature.target_language || 'en',
    is_default: signature.is_default
  })
  signatureDialogVisible.value = true
}

async function translateSignature() {
  if (!signatureForm.content_chinese) {
    ElMessage.warning('请先输入中文签名内容')
    return
  }

  translatingSignature.value = true
  try {
    const result = await api.translateReply(
      signatureForm.content_chinese,
      signatureForm.target_language
    )
    signatureForm.content_translated = result.translated_text
    ElMessage.success('翻译完成')
  } catch (e) {
    console.error('Failed to translate signature:', e)
    ElMessage.error('翻译失败')
  } finally {
    translatingSignature.value = false
  }
}

async function saveSignature() {
  if (!signatureForm.name) {
    ElMessage.warning('请输入签名名称')
    return
  }

  savingSignature.value = true
  try {
    const data = {
      name: signatureForm.name,
      content_chinese: signatureForm.content_chinese,
      content_translated: signatureForm.content_translated,
      target_language: signatureForm.target_language,
      is_default: signatureForm.is_default
    }

    if (signatureForm.id) {
      await api.updateSignature(signatureForm.id, data)
      ElMessage.success('签名已更新')
    } else {
      await api.createSignature(data)
      ElMessage.success('签名已创建')
    }

    signatureDialogVisible.value = false
    loadSignatures()
  } catch (e) {
    console.error('Failed to save signature:', e)
    ElMessage.error('保存失败')
  } finally {
    savingSignature.value = false
  }
}

async function setDefaultSignature(signature) {
  try {
    await api.setDefaultSignature(signature.id)
    ElMessage.success('已设为默认签名')
    loadSignatures()
  } catch (e) {
    console.error('Failed to set default signature:', e)
    ElMessage.error('设置失败')
  }
}

async function deleteSignature(signature) {
  try {
    await ElMessageBox.confirm('确定要删除此签名吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await api.deleteSignature(signature.id)
    ElMessage.success('签名已删除')
    loadSignatures()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete signature:', e)
      ElMessage.error('删除失败')
    }
  }
}
</script>

<style scoped>
.settings-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.signature-preview {
  max-height: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: pre-wrap;
  font-size: 12px;
  color: #666;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.text-muted {
  color: #909399;
  font-size: 12px;
}

.member-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.member-tags .el-tag {
  margin: 0;
}
</style>
