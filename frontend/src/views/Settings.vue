<template>
  <div class="settings-page">
    <el-row :gutter="20">
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()

const accounts = ref([])
const rules = ref([])
const accountDialogVisible = ref(false)
const ruleDialogVisible = ref(false)

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

onMounted(() => {
  loadAccounts()
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
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
