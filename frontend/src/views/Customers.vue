<template>
  <div class="customers-page">
    <!-- Header with stats and actions -->
    <el-card class="header-card" shadow="never">
      <div class="header-content">
        <div class="stats-row">
          <el-statistic title="客户总数" :value="customers.length" />
          <el-statistic title="已分类" :value="classifiedCount" />
          <el-statistic title="未分类" :value="unclassifiedCount" />
        </div>
        <div class="actions-row">
          <el-input
            v-model="searchText"
            placeholder="搜索客户..."
            :prefix-icon="Search"
            clearable
            style="width: 240px"
          />
          <el-select v-model="filterCategory" placeholder="按分类筛选" clearable style="width: 150px">
            <el-option label="全部" value="" />
            <el-option v-for="cat in categoryOptions" :key="cat.value" :label="cat.label" :value="cat.value" />
          </el-select>
          <el-select v-model="filterTag" placeholder="按标签筛选" clearable style="width: 150px">
            <el-option label="全部" value="" />
            <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id">
              <span :style="{ color: tag.color }">●</span> {{ tag.name }}
            </el-option>
          </el-select>
          <el-button type="primary" :icon="Plus" @click="showAddCustomer">
            添加客户
          </el-button>
          <el-button :icon="Setting" @click="showTagManager = true">管理标签</el-button>
        </div>
      </div>
    </el-card>

    <!-- Main table -->
    <el-card shadow="never">
      <el-table
        :data="filteredCustomers"
        v-loading="loading"
        stripe
        @row-click="showCustomerDetail"
        style="cursor: pointer"
      >
        <el-table-column prop="name" label="客户名称" min-width="180">
          <template #default="{ row }">
            <div class="customer-name-cell">
              <span class="name">{{ row.name }}</span>
              <div class="tags" v-if="row.tags && row.tags.length">
                <el-tag
                  v-for="tag in row.tags"
                  :key="tag.id"
                  :color="tag.color"
                  size="small"
                  effect="dark"
                  style="margin-right: 4px; border: none;"
                >
                  {{ tag.name }}
                </el-tag>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email_domain" label="主域名" width="180" />
        <el-table-column prop="country" label="国家/地区" width="120" />
        <el-table-column label="分类" width="150">
          <template #default="{ row }">
            <div class="category-cell" v-if="row.category">
              <el-tag :type="getCategoryType(row.category)" size="small">
                {{ getCategoryLabel(row.category) }}
              </el-tag>
              <el-icon v-if="row.category_manual" class="manual-icon" title="人工修改">
                <Edit />
              </el-icon>
            </div>
            <span v-else class="text-gray">未分类</span>
          </template>
        </el-table-column>
        <el-table-column label="联系人" width="100">
          <template #default="{ row }">
            <el-button size="small" text @click.stop="showContacts(row)">
              {{ row.contact_count || 0 }} 人
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="域名" width="100">
          <template #default="{ row }">
            <el-button size="small" text @click.stop="showDomains(row)">
              {{ row.domain_count || 1 }} 个
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-tooltip content="管理标签">
                <el-button size="small" :icon="PriceTag" @click.stop="showTagSelector(row)" />
              </el-tooltip>
              <el-tooltip content="修改分类">
                <el-button size="small" :icon="Edit" @click.stop="editCategory(row)" />
              </el-tooltip>
              <el-tooltip content="删除客户">
                <el-button size="small" :icon="Delete" type="danger" @click.stop="deleteCustomer(row)" />
              </el-tooltip>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && filteredCustomers.length === 0" description="暂无客户" />
    </el-card>

    <!-- Customer Detail Drawer -->
    <el-drawer v-model="detailVisible" :title="currentCustomer?.name" size="50%">
      <template v-if="currentCustomer">
        <el-tabs v-model="detailTab">
          <el-tab-pane label="基本信息" name="info">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="客户名称">{{ currentCustomer.name }}</el-descriptions-item>
              <el-descriptions-item label="主邮箱域名">{{ currentCustomer.email_domain }}</el-descriptions-item>
              <el-descriptions-item label="国家/地区">{{ currentCustomer.country || '-' }}</el-descriptions-item>
              <el-descriptions-item label="分类">
                <el-tag v-if="currentCustomer.category" :type="getCategoryType(currentCustomer.category)">
                  {{ getCategoryLabel(currentCustomer.category) }}
                </el-tag>
                <span v-else>未分类</span>
              </el-descriptions-item>
              <el-descriptions-item label="备注" v-if="currentCustomer.notes">
                {{ currentCustomer.notes }}
              </el-descriptions-item>
              <el-descriptions-item label="标签">
                <div v-if="currentCustomer.tags && currentCustomer.tags.length">
                  <el-tag
                    v-for="tag in currentCustomer.tags"
                    :key="tag.id"
                    :color="tag.color"
                    size="small"
                    effect="dark"
                    closable
                    @close="removeTag(currentCustomer, tag)"
                    style="margin-right: 4px; border: none;"
                  >
                    {{ tag.name }}
                  </el-tag>
                </div>
                <span v-else>无标签</span>
                <el-button size="small" text type="primary" @click="showTagSelector(currentCustomer)" style="margin-left: 8px">
                  添加标签
                </el-button>
              </el-descriptions-item>
            </el-descriptions>
            <div style="margin-top: 16px;">
              <el-button type="primary" @click="showEditCustomer">编辑信息</el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="联系人" name="contacts">
            <div class="tab-header">
              <el-button type="primary" size="small" :icon="Plus" @click="showAddContact">添加联系人</el-button>
            </div>
            <el-table :data="customerContacts" stripe v-loading="contactsLoading">
              <el-table-column prop="name" label="姓名" width="120" />
              <el-table-column prop="email" label="邮箱" min-width="180" />
              <el-table-column prop="phone" label="电话" width="140" />
              <el-table-column prop="role" label="角色" width="100">
                <template #default="{ row }">
                  {{ getRoleLabel(row.role) }}
                </template>
              </el-table-column>
              <el-table-column prop="is_primary" label="主联系人" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.is_primary" type="success" size="small">是</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click="editContact(row)">编辑</el-button>
                  <el-button size="small" text type="danger" @click="deleteContact(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!contactsLoading && customerContacts.length === 0" description="暂无联系人" />
          </el-tab-pane>

          <el-tab-pane label="域名" name="domains">
            <div class="tab-header">
              <el-button type="primary" size="small" :icon="Plus" @click="showAddDomain">添加域名</el-button>
            </div>
            <el-table :data="customerDomains" stripe v-loading="domainsLoading">
              <el-table-column prop="domain" label="邮箱域名" min-width="200" />
              <el-table-column prop="is_primary" label="主域名" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.is_primary" type="success" size="small">是</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    text
                    type="danger"
                    @click="deleteDomain(row)"
                    :disabled="row.is_primary"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>

    <!-- Add/Edit Customer Dialog -->
    <el-dialog v-model="customerDialogVisible" :title="editingCustomer ? '编辑客户' : '添加客户'" width="500px">
      <el-form :model="customerForm" label-width="100px">
        <el-form-item label="客户名称" required>
          <el-input v-model="customerForm.name" placeholder="客户名称" />
        </el-form-item>
        <el-form-item label="邮箱域名" required>
          <el-input v-model="customerForm.email_domain" placeholder="例如: customer.com" />
        </el-form-item>
        <el-form-item label="国家/地区">
          <el-input v-model="customerForm.country" placeholder="例如: 美国" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="customerForm.category" placeholder="选择分类" clearable style="width: 100%">
            <el-option v-for="cat in categoryOptions" :key="cat.value" :label="cat.label" :value="cat.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="customerForm.notes" type="textarea" :rows="3" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="customerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCustomer" :loading="savingCustomer">
          {{ editingCustomer ? '保存' : '添加' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Add Contact Dialog -->
    <el-dialog v-model="addContactVisible" :title="editingContact ? '编辑联系人' : '添加联系人'" width="500px">
      <el-form :model="contactForm" label-width="80px">
        <el-form-item label="姓名" required>
          <el-input v-model="contactForm.name" placeholder="联系人姓名" />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="contactForm.email" placeholder="联系人邮箱" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="contactForm.phone" placeholder="电话号码" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="contactForm.role" placeholder="选择角色">
            <el-option label="采购" value="purchasing" />
            <el-option label="技术" value="tech" />
            <el-option label="财务" value="finance" />
            <el-option label="销售" value="sales" />
            <el-option label="管理" value="manager" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="主联系人">
          <el-switch v-model="contactForm.is_primary" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="contactForm.notes" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addContactVisible = false">取消</el-button>
        <el-button type="primary" @click="saveContact" :loading="savingContact">
          {{ editingContact ? '保存' : '添加' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Add Domain Dialog -->
    <el-dialog v-model="addDomainVisible" title="添加域名" width="400px">
      <el-form :model="domainForm" label-width="80px">
        <el-form-item label="域名" required>
          <el-input v-model="domainForm.domain" placeholder="例如: sales.customer.com" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDomainVisible = false">取消</el-button>
        <el-button type="primary" @click="addDomain" :loading="savingDomain">添加</el-button>
      </template>
    </el-dialog>

    <!-- Edit Category Dialog -->
    <el-dialog v-model="editCategoryVisible" title="修改分类" width="400px">
      <el-form label-width="80px">
        <el-form-item label="分类">
          <el-select v-model="editCategoryValue" placeholder="选择分类" style="width: 100%">
            <el-option v-for="cat in categoryOptions" :key="cat.value" :label="cat.label" :value="cat.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editCategoryVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCategory" :loading="savingCategory">保存</el-button>
      </template>
    </el-dialog>

    <!-- Tag Selector Dialog -->
    <el-dialog v-model="tagSelectorVisible" title="选择标签" width="400px">
      <div class="tag-selector">
        <el-checkbox-group v-model="selectedTagIds">
          <div v-for="tag in tags" :key="tag.id" class="tag-option">
            <el-checkbox :value="tag.id">
              <span :style="{ color: tag.color }">●</span> {{ tag.name }}
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="tagSelectorVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTags" :loading="savingTags">保存</el-button>
      </template>
    </el-dialog>

    <!-- Tag Manager Dialog -->
    <el-dialog v-model="showTagManager" title="管理标签" width="500px">
      <div class="tag-manager">
        <div class="add-tag-form">
          <el-input v-model="newTagName" placeholder="新标签名称" style="width: 200px" />
          <el-color-picker v-model="newTagColor" />
          <el-button type="primary" :icon="Plus" @click="createTag" :loading="creatingTag">添加</el-button>
        </div>
        <el-divider />
        <el-table :data="tags" stripe>
          <el-table-column label="颜色" width="60">
            <template #default="{ row }">
              <span :style="{ color: row.color, fontSize: '20px' }">●</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="deleteTag(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Setting, Edit, PriceTag, Delete } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// Category options for customers
const categoryOptions = [
  { value: 'oem', label: 'OEM客户' },
  { value: 'distributor', label: '分销商' },
  { value: 'retailer', label: '零售商' },
  { value: 'trading', label: '贸易商' },
  { value: 'end_user', label: '终端用户' },
  { value: 'agent', label: '代理商' },
  { value: 'other', label: '其他' }
]

const getCategoryLabel = (value) => {
  const cat = categoryOptions.find(c => c.value === value)
  return cat ? cat.label : value
}

const getCategoryType = (category) => {
  const types = {
    oem: 'success',
    distributor: 'primary',
    retailer: 'warning',
    trading: 'info',
    end_user: '',
    agent: 'danger',
    other: 'info'
  }
  return types[category] || 'info'
}

const getRoleLabel = (role) => {
  const roles = {
    purchasing: '采购',
    tech: '技术',
    finance: '财务',
    sales: '销售',
    manager: '管理',
    other: '其他'
  }
  return roles[role] || role
}

// State
const customers = ref([])
const tags = ref([])
const loading = ref(false)
const searchText = ref('')
const filterCategory = ref('')
const filterTag = ref('')

// Detail drawer
const detailVisible = ref(false)
const detailTab = ref('info')
const currentCustomer = ref(null)

// Customer dialog
const customerDialogVisible = ref(false)
const editingCustomer = ref(null)
const savingCustomer = ref(false)
const customerForm = reactive({
  name: '',
  email_domain: '',
  country: '',
  category: '',
  notes: ''
})

// Contacts
const customerContacts = ref([])
const contactsLoading = ref(false)
const addContactVisible = ref(false)
const editingContact = ref(null)
const savingContact = ref(false)
const contactForm = reactive({
  name: '',
  email: '',
  phone: '',
  role: '',
  is_primary: false,
  notes: ''
})

// Domains
const customerDomains = ref([])
const domainsLoading = ref(false)
const addDomainVisible = ref(false)
const savingDomain = ref(false)
const domainForm = reactive({
  domain: ''
})

// Category editing
const editCategoryVisible = ref(false)
const editCategoryValue = ref('')
const editingCategoryCustomer = ref(null)
const savingCategory = ref(false)

// Tag management
const tagSelectorVisible = ref(false)
const selectedTagIds = ref([])
const tagTargetCustomer = ref(null)
const savingTags = ref(false)
const showTagManager = ref(false)
const newTagName = ref('')
const newTagColor = ref('#409EFF')
const creatingTag = ref(false)

// Computed
const filteredCustomers = computed(() => {
  let result = customers.value

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    result = result.filter(c =>
      c.name.toLowerCase().includes(search) ||
      (c.email_domain && c.email_domain.toLowerCase().includes(search))
    )
  }

  if (filterCategory.value) {
    result = result.filter(c => c.category === filterCategory.value)
  }

  if (filterTag.value) {
    result = result.filter(c =>
      c.tags && c.tags.some(t => t.id === filterTag.value)
    )
  }

  return result
})

const classifiedCount = computed(() => {
  return customers.value.filter(c => c.category).length
})

const unclassifiedCount = computed(() => {
  return customers.value.filter(c => !c.category).length
})

// Methods
onMounted(() => {
  loadCustomers()
  loadTags()
})

async function loadCustomers() {
  loading.value = true
  try {
    customers.value = await api.getCustomers()
  } catch (e) {
    console.error('Failed to load customers:', e)
  } finally {
    loading.value = false
  }
}

async function loadTags() {
  try {
    tags.value = await api.getCustomerTags()
  } catch (e) {
    console.error('Failed to load tags:', e)
  }
}

function showCustomerDetail(customer) {
  currentCustomer.value = customer
  detailTab.value = 'info'
  detailVisible.value = true
  loadCustomerContacts(customer.id)
  loadCustomerDomains(customer.id)
}

// Customer CRUD
function showAddCustomer() {
  editingCustomer.value = null
  Object.assign(customerForm, {
    name: '',
    email_domain: '',
    country: '',
    category: '',
    notes: ''
  })
  customerDialogVisible.value = true
}

function showEditCustomer() {
  editingCustomer.value = currentCustomer.value
  Object.assign(customerForm, {
    name: currentCustomer.value.name,
    email_domain: currentCustomer.value.email_domain,
    country: currentCustomer.value.country || '',
    category: currentCustomer.value.category || '',
    notes: currentCustomer.value.notes || ''
  })
  customerDialogVisible.value = true
}

async function saveCustomer() {
  if (!customerForm.name || !customerForm.email_domain) {
    ElMessage.warning('请填写客户名称和邮箱域名')
    return
  }

  savingCustomer.value = true
  try {
    if (editingCustomer.value) {
      const updated = await api.updateCustomer(editingCustomer.value.id, customerForm)
      Object.assign(currentCustomer.value, updated)
      ElMessage.success('客户信息已更新')
    } else {
      await api.createCustomer(customerForm)
      ElMessage.success('客户已添加')
    }
    customerDialogVisible.value = false
    loadCustomers()
  } catch (e) {
    console.error('Failed to save customer:', e)
    ElMessage.error('保存失败')
  } finally {
    savingCustomer.value = false
  }
}

async function deleteCustomer(customer) {
  try {
    await ElMessageBox.confirm(`确定删除客户 "${customer.name}"？`, '确认删除', { type: 'warning' })
    await api.deleteCustomer(customer.id)
    ElMessage.success('客户已删除')
    loadCustomers()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete customer:', e)
    }
  }
}

// Contacts
async function loadCustomerContacts(customerId) {
  contactsLoading.value = true
  try {
    customerContacts.value = await api.getCustomerContacts(customerId)
  } catch (e) {
    console.error('Failed to load contacts:', e)
    customerContacts.value = []
  } finally {
    contactsLoading.value = false
  }
}

function showContacts(customer) {
  currentCustomer.value = customer
  detailTab.value = 'contacts'
  detailVisible.value = true
  loadCustomerContacts(customer.id)
}

function showAddContact() {
  editingContact.value = null
  Object.assign(contactForm, {
    name: '',
    email: '',
    phone: '',
    role: '',
    is_primary: false,
    notes: ''
  })
  addContactVisible.value = true
}

function editContact(contact) {
  editingContact.value = contact
  Object.assign(contactForm, contact)
  addContactVisible.value = true
}

async function saveContact() {
  if (!contactForm.name || !contactForm.email) {
    ElMessage.warning('请填写姓名和邮箱')
    return
  }

  savingContact.value = true
  try {
    if (editingContact.value) {
      await api.updateCustomerContact(currentCustomer.value.id, editingContact.value.id, contactForm)
      ElMessage.success('联系人已更新')
    } else {
      await api.addCustomerContact(currentCustomer.value.id, contactForm)
      ElMessage.success('联系人已添加')
    }
    addContactVisible.value = false
    loadCustomerContacts(currentCustomer.value.id)
  } catch (e) {
    console.error('Failed to save contact:', e)
  } finally {
    savingContact.value = false
  }
}

async function deleteContact(contact) {
  try {
    await ElMessageBox.confirm('确定删除此联系人？', '确认删除', { type: 'warning' })
    await api.deleteCustomerContact(currentCustomer.value.id, contact.id)
    ElMessage.success('联系人已删除')
    loadCustomerContacts(currentCustomer.value.id)
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete contact:', e)
    }
  }
}

// Domains
async function loadCustomerDomains(customerId) {
  domainsLoading.value = true
  try {
    customerDomains.value = await api.getCustomerDomains(customerId)
  } catch (e) {
    console.error('Failed to load domains:', e)
    customerDomains.value = []
  } finally {
    domainsLoading.value = false
  }
}

function showDomains(customer) {
  currentCustomer.value = customer
  detailTab.value = 'domains'
  detailVisible.value = true
  loadCustomerDomains(customer.id)
}

function showAddDomain() {
  Object.assign(domainForm, {
    domain: ''
  })
  addDomainVisible.value = true
}

async function addDomain() {
  if (!domainForm.domain) {
    ElMessage.warning('请填写域名')
    return
  }

  savingDomain.value = true
  try {
    await api.addCustomerDomain(currentCustomer.value.id, domainForm)
    ElMessage.success('域名已添加')
    addDomainVisible.value = false
    loadCustomerDomains(currentCustomer.value.id)
    loadCustomers() // Refresh to update domain count
  } catch (e) {
    console.error('Failed to add domain:', e)
  } finally {
    savingDomain.value = false
  }
}

async function deleteDomain(domain) {
  try {
    await ElMessageBox.confirm('确定删除此域名？', '确认删除', { type: 'warning' })
    await api.deleteCustomerDomain(currentCustomer.value.id, domain.id)
    ElMessage.success('域名已删除')
    loadCustomerDomains(currentCustomer.value.id)
    loadCustomers()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete domain:', e)
    }
  }
}

// Category editing
function editCategory(customer) {
  editingCategoryCustomer.value = customer
  editCategoryValue.value = customer.category || ''
  editCategoryVisible.value = true
}

async function saveCategory() {
  if (!editCategoryValue.value) {
    ElMessage.warning('请选择分类')
    return
  }

  savingCategory.value = true
  try {
    await api.updateCustomerCategory(editingCategoryCustomer.value.id, editCategoryValue.value)
    editingCategoryCustomer.value.category = editCategoryValue.value
    editingCategoryCustomer.value.category_manual = true
    ElMessage.success('分类已更新')
    editCategoryVisible.value = false
  } catch (e) {
    console.error('Failed to update category:', e)
  } finally {
    savingCategory.value = false
  }
}

// Tags
function showTagSelector(customer) {
  tagTargetCustomer.value = customer
  selectedTagIds.value = customer.tags ? customer.tags.map(t => t.id) : []
  tagSelectorVisible.value = true
}

async function saveTags() {
  savingTags.value = true
  try {
    const currentTags = tagTargetCustomer.value.tags || []
    const currentTagIds = currentTags.map(t => t.id)

    // Add new tags
    for (const tagId of selectedTagIds.value) {
      if (!currentTagIds.includes(tagId)) {
        await api.addTagToCustomer(tagTargetCustomer.value.id, tagId)
      }
    }

    // Remove old tags
    for (const tagId of currentTagIds) {
      if (!selectedTagIds.value.includes(tagId)) {
        await api.removeTagFromCustomer(tagTargetCustomer.value.id, tagId)
      }
    }

    // Update local state
    tagTargetCustomer.value.tags = tags.value.filter(t => selectedTagIds.value.includes(t.id))
    ElMessage.success('标签已更新')
    tagSelectorVisible.value = false
  } catch (e) {
    console.error('Failed to save tags:', e)
  } finally {
    savingTags.value = false
  }
}

async function removeTag(customer, tag) {
  try {
    await api.removeTagFromCustomer(customer.id, tag.id)
    customer.tags = customer.tags.filter(t => t.id !== tag.id)
    ElMessage.success('标签已移除')
  } catch (e) {
    console.error('Failed to remove tag:', e)
  }
}

async function createTag() {
  if (!newTagName.value) {
    ElMessage.warning('请输入标签名称')
    return
  }

  creatingTag.value = true
  try {
    const tag = await api.createCustomerTag({
      name: newTagName.value,
      color: newTagColor.value
    })
    tags.value.push(tag)
    newTagName.value = ''
    newTagColor.value = '#409EFF'
    ElMessage.success('标签已创建')
  } catch (e) {
    console.error('Failed to create tag:', e)
  } finally {
    creatingTag.value = false
  }
}

async function deleteTag(tag) {
  try {
    await ElMessageBox.confirm('确定删除此标签？删除后将从所有客户移除。', '确认删除', { type: 'warning' })
    await api.deleteCustomerTag(tag.id)
    tags.value = tags.value.filter(t => t.id !== tag.id)
    // Also remove from customers
    customers.value.forEach(c => {
      if (c.tags) {
        c.tags = c.tags.filter(t => t.id !== tag.id)
      }
    })
    ElMessage.success('标签已删除')
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete tag:', e)
    }
  }
}
</script>

<style scoped>
.customers-page {
  padding: 20px;
}

.header-card {
  margin-bottom: 16px;
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-row {
  display: flex;
  gap: 40px;
}

.actions-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.customer-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.customer-name-cell .name {
  font-weight: 500;
}

.customer-name-cell .tags {
  display: flex;
  flex-wrap: wrap;
}

.category-cell {
  display: flex;
  align-items: center;
}

.manual-icon {
  margin-left: 8px;
  color: #909399;
}

.text-gray {
  color: #909399;
}

.tab-header {
  margin-bottom: 16px;
}

.tag-selector {
  max-height: 300px;
  overflow-y: auto;
}

.tag-option {
  padding: 8px 0;
}

.tag-manager .add-tag-form {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
</style>
