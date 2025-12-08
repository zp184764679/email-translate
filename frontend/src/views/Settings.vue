<template>
  <div class="settings-page">
    <el-row :gutter="20">
      <!-- Email Signatures -->
      <el-col :span="24" style="margin-bottom: 20px;">
        <el-card>
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
      </el-col>

      <!-- Email Accounts -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>邮箱账户</span>
              <el-button type="primary" :icon="Plus" @click="showAddAccount">添加</el-button>
            </div>
          </template>

          <el-table :data="accounts" stripe>
            <el-table-column prop="email" label="邮箱" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- Approval Rules -->
      <el-col :span="12" v-if="userStore.isAdmin">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>审批规则</span>
              <el-button type="primary" :icon="Plus" @click="showAddRule">添加</el-button>
            </div>
          </template>

          <el-table :data="rules" stripe>
            <el-table-column prop="name" label="规则名称" />
            <el-table-column label="关键词" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="kw in row.keywords" :key="kw" size="small" style="margin-right: 4px;">
                  {{ kw }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="deleteRule(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- Add Account Dialog -->
    <el-dialog v-model="accountDialogVisible" title="添加邮箱账户" width="500px">
      <el-form :model="accountForm" label-width="100px">
        <el-form-item label="邮箱地址">
          <el-input v-model="accountForm.email" placeholder="example@company.com" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="accountForm.password" type="password" placeholder="邮箱密码或授权码" />
        </el-form-item>
        <el-form-item label="IMAP服务器">
          <el-input v-model="accountForm.imap_server" placeholder="imap.company.com" />
        </el-form-item>
        <el-form-item label="IMAP端口">
          <el-input-number v-model="accountForm.imap_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="SMTP服务器">
          <el-input v-model="accountForm.smtp_server" placeholder="smtp.company.com" />
        </el-form-item>
        <el-form-item label="SMTP端口">
          <el-input-number v-model="accountForm.smtp_port" :min="1" :max="65535" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addAccount">添加</el-button>
      </template>
    </el-dialog>

    <!-- Add Rule Dialog -->
    <el-dialog v-model="ruleDialogVisible" title="添加审批规则" width="500px">
      <el-form :model="ruleForm" label-width="100px">
        <el-form-item label="规则名称">
          <el-input v-model="ruleForm.name" placeholder="例如: 价格相关" />
        </el-form-item>
        <el-form-item label="触发关键词">
          <el-select
            v-model="ruleForm.keywords"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入关键词后按回车"
          />
        </el-form-item>
        <el-form-item label="审批角色">
          <el-select v-model="ruleForm.approver_role">
            <el-option label="主管" value="manager" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addRule">添加</el-button>
      </template>
    </el-dialog>

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const userStore = useUserStore()

const accounts = ref([])
const rules = ref([])
const signatures = ref([])
const accountDialogVisible = ref(false)
const ruleDialogVisible = ref(false)
const signatureDialogVisible = ref(false)
const translatingSignature = ref(false)
const savingSignature = ref(false)

const accountForm = reactive({
  email: '',
  password: '',
  imap_server: '',
  imap_port: 993,
  smtp_server: '',
  smtp_port: 465
})

const ruleForm = reactive({
  name: '',
  keywords: [],
  approver_role: 'manager'
})

const signatureForm = reactive({
  id: null,
  name: '',
  content_chinese: '',
  content_translated: '',
  target_language: 'en',
  is_default: false
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
  loadAccounts()
  loadSignatures()
  if (userStore.isAdmin) {
    loadRules()
  }
})

async function loadAccounts() {
  try {
    const result = await api.getEmailAccounts()
    accounts.value = result.accounts
  } catch (e) {
    console.error('Failed to load accounts:', e)
  }
}

async function loadRules() {
  try {
    rules.value = await api.getApprovalRules()
  } catch (e) {
    console.error('Failed to load rules:', e)
  }
}

function showAddAccount() {
  Object.assign(accountForm, {
    email: '',
    password: '',
    imap_server: '',
    imap_port: 993,
    smtp_server: '',
    smtp_port: 465
  })
  accountDialogVisible.value = true
}

function showAddRule() {
  Object.assign(ruleForm, {
    name: '',
    keywords: [],
    approver_role: 'manager'
  })
  ruleDialogVisible.value = true
}

async function addAccount() {
  if (!accountForm.email || !accountForm.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }

  try {
    await api.createEmailAccount(accountForm)
    ElMessage.success('邮箱账户已添加')
    accountDialogVisible.value = false
    loadAccounts()
  } catch (e) {
    console.error('Failed to add account:', e)
  }
}

async function addRule() {
  if (!ruleForm.name || ruleForm.keywords.length === 0) {
    ElMessage.warning('请填写规则名称和关键词')
    return
  }

  try {
    await api.createApprovalRule(ruleForm)
    ElMessage.success('审批规则已添加')
    ruleDialogVisible.value = false
    loadRules()
  } catch (e) {
    console.error('Failed to add rule:', e)
  }
}

async function deleteRule(rule) {
  try {
    await api.deleteApprovalRule(rule.id)
    ElMessage.success('规则已删除')
    loadRules()
  } catch (e) {
    console.error('Failed to delete rule:', e)
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
</style>
