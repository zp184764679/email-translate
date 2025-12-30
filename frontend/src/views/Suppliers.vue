<template>
  <div class="suppliers-page">
    <!-- Header with stats and actions -->
    <el-card class="header-card" shadow="never">
      <div class="header-content">
        <div class="stats-row">
          <el-statistic title="供应商总数" :value="suppliers.length" />
          <el-statistic title="已分类" :value="classifiedCount" />
          <el-statistic title="未分类" :value="unclassifiedCount" />
        </div>
        <div class="actions-row">
          <el-input
            v-model="searchText"
            placeholder="搜索供应商..."
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
          <el-button type="primary" :icon="Cpu" @click="batchAnalyze" :loading="batchAnalyzing">
            批量 AI 分析
          </el-button>
          <el-button :icon="Setting" @click="showTagManager = true">管理标签</el-button>
        </div>
      </div>
    </el-card>

    <!-- Main table -->
    <el-card shadow="never">
      <el-table
        :data="filteredSuppliers"
        v-loading="loading"
        stripe
        @row-click="showSupplierDetail"
        style="cursor: pointer"
      >
        <el-table-column prop="name" label="供应商名称" min-width="180">
          <template #default="{ row }">
            <div class="supplier-name-cell">
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
        <el-table-column label="AI 分类" width="200">
          <template #default="{ row }">
            <div class="category-cell" v-if="row.category">
              <el-tag :type="getCategoryType(row.category)" size="small">
                {{ getCategoryLabel(row.category) }}
              </el-tag>
              <el-tooltip v-if="row.category_confidence" :content="`置信度: ${(row.category_confidence * 100).toFixed(0)}%`">
                <el-progress
                  :percentage="row.category_confidence * 100"
                  :stroke-width="4"
                  :show-text="false"
                  style="width: 50px; margin-left: 8px"
                />
              </el-tooltip>
              <el-icon v-if="row.category_manual" class="manual-icon" title="人工修改">
                <Edit />
              </el-icon>
            </div>
            <el-button v-else size="small" text type="primary" @click.stop="analyzeOne(row)" :loading="row.analyzing">
              <el-icon><Cpu /></el-icon> 分析
            </el-button>
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
        <el-table-column label="术语表" width="100">
          <template #default="{ row }">
            <el-button size="small" text @click.stop="showGlossary(row)">
              {{ row.glossary_count || 0 }} 条
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-tooltip content="管理标签">
                <el-button size="small" :icon="PriceTag" @click.stop="showTagSelector(row)" />
              </el-tooltip>
              <el-tooltip content="重新分析">
                <el-button size="small" :icon="Refresh" @click.stop="analyzeOne(row)" :loading="row.analyzing" />
              </el-tooltip>
              <el-tooltip content="修改分类">
                <el-button size="small" :icon="Edit" @click.stop="editCategory(row)" />
              </el-tooltip>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && filteredSuppliers.length === 0" description="暂无供应商" />
    </el-card>

    <!-- Supplier Detail Drawer -->
    <el-drawer v-model="detailVisible" :title="currentSupplier?.name" size="50%">
      <template v-if="currentSupplier">
        <el-tabs v-model="detailTab">
          <el-tab-pane label="基本信息" name="info">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="供应商名称">{{ currentSupplier.name }}</el-descriptions-item>
              <el-descriptions-item label="主邮箱域名">{{ currentSupplier.email_domain }}</el-descriptions-item>
              <el-descriptions-item label="联系邮箱">{{ currentSupplier.contact_email || '-' }}</el-descriptions-item>
              <el-descriptions-item label="AI 分类">
                <el-tag v-if="currentSupplier.category" :type="getCategoryType(currentSupplier.category)">
                  {{ getCategoryLabel(currentSupplier.category) }}
                </el-tag>
                <span v-else>未分类</span>
              </el-descriptions-item>
              <el-descriptions-item label="分类置信度" v-if="currentSupplier.category_confidence">
                {{ (currentSupplier.category_confidence * 100).toFixed(0) }}%
              </el-descriptions-item>
              <el-descriptions-item label="分类依据" v-if="currentSupplier.category_reason">
                {{ currentSupplier.category_reason }}
              </el-descriptions-item>
              <el-descriptions-item label="标签">
                <div v-if="currentSupplier.tags && currentSupplier.tags.length">
                  <el-tag
                    v-for="tag in currentSupplier.tags"
                    :key="tag.id"
                    :color="tag.color"
                    size="small"
                    effect="dark"
                    closable
                    @close="removeTag(currentSupplier, tag)"
                    style="margin-right: 4px; border: none;"
                  >
                    {{ tag.name }}
                  </el-tag>
                </div>
                <span v-else>无标签</span>
                <el-button size="small" text type="primary" @click="showTagSelector(currentSupplier)" style="margin-left: 8px">
                  添加标签
                </el-button>
              </el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane label="联系人" name="contacts">
            <div class="tab-header">
              <el-button type="primary" size="small" :icon="Plus" @click="showAddContact">添加联系人</el-button>
            </div>
            <el-table :data="supplierContacts" stripe v-loading="contactsLoading">
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
            <el-empty v-if="!contactsLoading && supplierContacts.length === 0" description="暂无联系人" />
          </el-tab-pane>

          <el-tab-pane label="域名" name="domains">
            <div class="tab-header">
              <el-button type="primary" size="small" :icon="Plus" @click="showAddDomain">添加域名</el-button>
            </div>
            <el-table :data="supplierDomains" stripe v-loading="domainsLoading">
              <el-table-column prop="email_domain" label="邮箱域名" min-width="200" />
              <el-table-column prop="description" label="说明" min-width="150" />
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

          <el-tab-pane label="术语表" name="glossary">
            <div class="tab-header">
              <el-button type="primary" size="small" :icon="Plus" @click="showAddTerm">添加术语</el-button>
            </div>
            <el-table :data="glossaryTerms" stripe>
              <el-table-column prop="term_source" label="原文" min-width="150" />
              <el-table-column prop="term_target" label="译文" min-width="150" />
              <el-table-column prop="source_lang" label="原语言" width="80" />
              <el-table-column prop="target_lang" label="目标语言" width="80" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button size="small" text type="danger" @click="deleteTerm(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="glossaryTerms.length === 0" description="暂无术语" />
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>

    <!-- Add Term Dialog -->
    <el-dialog v-model="addTermVisible" title="添加术语" width="400px">
      <el-form :model="termForm" label-width="80px">
        <el-form-item label="原文">
          <el-input v-model="termForm.term_source" placeholder="例如: MOQ" />
        </el-form-item>
        <el-form-item label="译文">
          <el-input v-model="termForm.term_target" placeholder="例如: 最小起订量" />
        </el-form-item>
        <el-form-item label="原语言">
          <el-select v-model="termForm.source_lang">
            <el-option label="英语" value="en" />
            <el-option label="日语" value="ja" />
            <el-option label="中文" value="zh" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标语言">
          <el-select v-model="termForm.target_lang">
            <el-option label="中文" value="zh" />
            <el-option label="英语" value="en" />
            <el-option label="日语" value="ja" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addTermVisible = false">取消</el-button>
        <el-button type="primary" @click="addTerm">添加</el-button>
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
            <el-option label="销售" value="sales" />
            <el-option label="技术" value="tech" />
            <el-option label="财务" value="finance" />
            <el-option label="物流" value="logistics" />
            <el-option label="管理" value="manager" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="contactForm.department" placeholder="所属部门" />
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
          <el-input v-model="domainForm.email_domain" placeholder="例如: sales.company.com" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="domainForm.description" placeholder="例如: 销售部" />
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
          <el-table-column prop="description" label="描述" />
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
import { Plus, Search, Cpu, Setting, Edit, Refresh, PriceTag } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// Category options
const categoryOptions = [
  { value: 'raw_material', label: '原材料' },
  { value: 'machining', label: '机加工' },
  { value: 'electronics', label: '电子元器件' },
  { value: 'packaging', label: '包装材料' },
  { value: 'logistics', label: '物流服务' },
  { value: 'service', label: '服务商' },
  { value: 'other', label: '其他' }
]

const getCategoryLabel = (value) => {
  const cat = categoryOptions.find(c => c.value === value)
  return cat ? cat.label : value
}

const getCategoryType = (category) => {
  const types = {
    raw_material: 'success',
    machining: 'primary',
    electronics: 'warning',
    packaging: 'info',
    logistics: '',
    service: 'danger',
    other: 'info'
  }
  return types[category] || 'info'
}

const getRoleLabel = (role) => {
  const roles = {
    sales: '销售',
    tech: '技术',
    finance: '财务',
    logistics: '物流',
    manager: '管理',
    other: '其他'
  }
  return roles[role] || role
}

// State
const suppliers = ref([])
const tags = ref([])
const loading = ref(false)
const searchText = ref('')
const filterCategory = ref('')
const filterTag = ref('')
const batchAnalyzing = ref(false)

// Detail drawer
const detailVisible = ref(false)
const detailTab = ref('info')
const currentSupplier = ref(null)

// Contacts
const supplierContacts = ref([])
const contactsLoading = ref(false)
const addContactVisible = ref(false)
const editingContact = ref(null)
const savingContact = ref(false)
const contactForm = reactive({
  name: '',
  email: '',
  phone: '',
  role: '',
  department: '',
  is_primary: false,
  notes: ''
})

// Domains
const supplierDomains = ref([])
const domainsLoading = ref(false)
const addDomainVisible = ref(false)
const savingDomain = ref(false)
const domainForm = reactive({
  email_domain: '',
  description: ''
})

// Glossary
const glossaryTerms = ref([])
const addTermVisible = ref(false)
const termForm = reactive({
  term_source: '',
  term_target: '',
  source_lang: 'en',
  target_lang: 'zh'
})

// Category editing
const editCategoryVisible = ref(false)
const editCategoryValue = ref('')
const editingSupplier = ref(null)
const savingCategory = ref(false)

// Tag management
const tagSelectorVisible = ref(false)
const selectedTagIds = ref([])
const tagTargetSupplier = ref(null)
const savingTags = ref(false)
const showTagManager = ref(false)
const newTagName = ref('')
const newTagColor = ref('#409EFF')
const creatingTag = ref(false)

// Computed
const filteredSuppliers = computed(() => {
  let result = suppliers.value

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    result = result.filter(s =>
      s.name.toLowerCase().includes(search) ||
      s.email_domain.toLowerCase().includes(search)
    )
  }

  if (filterCategory.value) {
    result = result.filter(s => s.category === filterCategory.value)
  }

  if (filterTag.value) {
    result = result.filter(s =>
      s.tags && s.tags.some(t => t.id === filterTag.value)
    )
  }

  return result
})

const classifiedCount = computed(() => {
  return suppliers.value.filter(s => s.category).length
})

const unclassifiedCount = computed(() => {
  return suppliers.value.filter(s => !s.category).length
})

// Methods
onMounted(() => {
  loadSuppliers()
  loadTags()
})

async function loadSuppliers() {
  loading.value = true
  try {
    suppliers.value = await api.getSuppliers()
  } catch (e) {
    console.error('Failed to load suppliers:', e)
  } finally {
    loading.value = false
  }
}

async function loadTags() {
  try {
    tags.value = await api.getSupplierTags()
  } catch (e) {
    console.error('Failed to load tags:', e)
  }
}

function showSupplierDetail(supplier) {
  currentSupplier.value = supplier
  detailTab.value = 'info'
  detailVisible.value = true
  loadSupplierContacts(supplier.id)
  loadSupplierDomains(supplier.id)
  loadGlossary(supplier)
}

// Contacts
async function loadSupplierContacts(supplierId) {
  contactsLoading.value = true
  try {
    supplierContacts.value = await api.getSupplierContacts(supplierId)
  } catch (e) {
    console.error('Failed to load contacts:', e)
    supplierContacts.value = []
  } finally {
    contactsLoading.value = false
  }
}

function showContacts(supplier) {
  currentSupplier.value = supplier
  detailTab.value = 'contacts'
  detailVisible.value = true
  loadSupplierContacts(supplier.id)
}

function showAddContact() {
  editingContact.value = null
  Object.assign(contactForm, {
    name: '',
    email: '',
    phone: '',
    role: '',
    department: '',
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
      await api.updateSupplierContact(currentSupplier.value.id, editingContact.value.id, contactForm)
      ElMessage.success('联系人已更新')
    } else {
      await api.addSupplierContact(currentSupplier.value.id, contactForm)
      ElMessage.success('联系人已添加')
    }
    addContactVisible.value = false
    loadSupplierContacts(currentSupplier.value.id)
  } catch (e) {
    console.error('Failed to save contact:', e)
  } finally {
    savingContact.value = false
  }
}

async function deleteContact(contact) {
  try {
    await ElMessageBox.confirm('确定删除此联系人？', '确认删除', { type: 'warning' })
    await api.deleteSupplierContact(currentSupplier.value.id, contact.id)
    ElMessage.success('联系人已删除')
    loadSupplierContacts(currentSupplier.value.id)
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete contact:', e)
    }
  }
}

// Domains
async function loadSupplierDomains(supplierId) {
  domainsLoading.value = true
  try {
    supplierDomains.value = await api.getSupplierDomains(supplierId)
  } catch (e) {
    console.error('Failed to load domains:', e)
    supplierDomains.value = []
  } finally {
    domainsLoading.value = false
  }
}

function showDomains(supplier) {
  currentSupplier.value = supplier
  detailTab.value = 'domains'
  detailVisible.value = true
  loadSupplierDomains(supplier.id)
}

function showAddDomain() {
  Object.assign(domainForm, {
    email_domain: '',
    description: ''
  })
  addDomainVisible.value = true
}

async function addDomain() {
  if (!domainForm.email_domain) {
    ElMessage.warning('请填写域名')
    return
  }

  savingDomain.value = true
  try {
    await api.addSupplierDomain(currentSupplier.value.id, domainForm)
    ElMessage.success('域名已添加')
    addDomainVisible.value = false
    loadSupplierDomains(currentSupplier.value.id)
    loadSuppliers() // Refresh to update domain count
  } catch (e) {
    console.error('Failed to add domain:', e)
  } finally {
    savingDomain.value = false
  }
}

async function deleteDomain(domain) {
  try {
    await ElMessageBox.confirm('确定删除此域名？', '确认删除', { type: 'warning' })
    await api.deleteSupplierDomain(currentSupplier.value.id, domain.id)
    ElMessage.success('域名已删除')
    loadSupplierDomains(currentSupplier.value.id)
    loadSuppliers()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('Failed to delete domain:', e)
    }
  }
}

// Glossary
async function loadGlossary(supplier) {
  try {
    glossaryTerms.value = await api.getGlossary(supplier.id)
  } catch (e) {
    console.error('Failed to load glossary:', e)
    glossaryTerms.value = []
  }
}

function showGlossary(supplier) {
  currentSupplier.value = supplier
  detailTab.value = 'glossary'
  detailVisible.value = true
  loadGlossary(supplier)
}

function showAddTerm() {
  Object.assign(termForm, {
    term_source: '',
    term_target: '',
    source_lang: 'en',
    target_lang: 'zh'
  })
  addTermVisible.value = true
}

async function addTerm() {
  if (!termForm.term_source || !termForm.term_target) {
    ElMessage.warning('请填写完整')
    return
  }

  try {
    await api.addGlossaryTerm({
      supplier_id: currentSupplier.value.id,
      ...termForm
    })
    ElMessage.success('术语已添加')
    addTermVisible.value = false
    loadGlossary(currentSupplier.value)
  } catch (e) {
    console.error('Failed to add term:', e)
  }
}

async function deleteTerm(term) {
  try {
    await api.deleteGlossaryTerm(term.id)
    ElMessage.success('术语已删除')
    glossaryTerms.value = glossaryTerms.value.filter(t => t.id !== term.id)
  } catch (e) {
    console.error('Failed to delete term:', e)
  }
}

// AI Analysis
async function analyzeOne(supplier) {
  supplier.analyzing = true
  try {
    const result = await api.analyzeSupplierCategory(supplier.id)
    Object.assign(supplier, result)
    ElMessage.success(`分类完成: ${getCategoryLabel(result.category)}`)
  } catch (e) {
    console.error('Failed to analyze:', e)
    ElMessage.error('分析失败')
  } finally {
    supplier.analyzing = false
  }
}

async function batchAnalyze() {
  const unclassified = suppliers.value.filter(s => !s.category)
  if (unclassified.length === 0) {
    ElMessage.info('所有供应商都已分类')
    return
  }

  batchAnalyzing.value = true
  try {
    const result = await api.batchAnalyzeSuppliers()
    ElMessage.success(`批量分析完成，成功 ${result.success} 个，失败 ${result.failed} 个`)
    loadSuppliers()
  } catch (e) {
    console.error('Failed to batch analyze:', e)
    ElMessage.error('批量分析失败')
  } finally {
    batchAnalyzing.value = false
  }
}

function editCategory(supplier) {
  editingSupplier.value = supplier
  editCategoryValue.value = supplier.category || ''
  editCategoryVisible.value = true
}

async function saveCategory() {
  if (!editCategoryValue.value) {
    ElMessage.warning('请选择分类')
    return
  }

  savingCategory.value = true
  try {
    await api.updateSupplierCategory(editingSupplier.value.id, editCategoryValue.value)
    editingSupplier.value.category = editCategoryValue.value
    editingSupplier.value.category_manual = true
    ElMessage.success('分类已更新')
    editCategoryVisible.value = false
  } catch (e) {
    console.error('Failed to update category:', e)
  } finally {
    savingCategory.value = false
  }
}

// Tags
function showTagSelector(supplier) {
  tagTargetSupplier.value = supplier
  selectedTagIds.value = supplier.tags ? supplier.tags.map(t => t.id) : []
  tagSelectorVisible.value = true
}

async function saveTags() {
  savingTags.value = true
  try {
    const currentTags = tagTargetSupplier.value.tags || []
    const currentTagIds = currentTags.map(t => t.id)

    // Add new tags
    for (const tagId of selectedTagIds.value) {
      if (!currentTagIds.includes(tagId)) {
        await api.addTagToSupplier(tagTargetSupplier.value.id, tagId)
      }
    }

    // Remove old tags
    for (const tagId of currentTagIds) {
      if (!selectedTagIds.value.includes(tagId)) {
        await api.removeTagFromSupplier(tagTargetSupplier.value.id, tagId)
      }
    }

    // Update local state
    tagTargetSupplier.value.tags = tags.value.filter(t => selectedTagIds.value.includes(t.id))
    ElMessage.success('标签已更新')
    tagSelectorVisible.value = false
  } catch (e) {
    console.error('Failed to save tags:', e)
  } finally {
    savingTags.value = false
  }
}

async function removeTag(supplier, tag) {
  try {
    await api.removeTagFromSupplier(supplier.id, tag.id)
    supplier.tags = supplier.tags.filter(t => t.id !== tag.id)
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
    const tag = await api.createSupplierTag({
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
    await ElMessageBox.confirm('确定删除此标签？删除后将从所有供应商移除。', '确认删除', { type: 'warning' })
    await api.deleteSupplierTag(tag.id)
    tags.value = tags.value.filter(t => t.id !== tag.id)
    // Also remove from suppliers
    suppliers.value.forEach(s => {
      if (s.tags) {
        s.tags = s.tags.filter(t => t.id !== tag.id)
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
.suppliers-page {
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

.supplier-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.supplier-name-cell .name {
  font-weight: 500;
}

.supplier-name-cell .tags {
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
