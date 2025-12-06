<template>
  <div class="suppliers-page">
    <el-card>
      <template #header>
        <span>供应商列表</span>
      </template>

      <el-table :data="suppliers" v-loading="loading" stripe>
        <el-table-column prop="name" label="供应商名称" min-width="150" />
        <el-table-column prop="email_domain" label="邮箱域名" width="200" />
        <el-table-column prop="contact_email" label="联系邮箱" width="200" />
        <el-table-column label="术语表" width="100">
          <template #default="{ row }">
            <el-button size="small" @click="showGlossary(row)">
              管理 ({{ row.glossary_count || 0 }})
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && suppliers.length === 0" description="暂无供应商" />
    </el-card>

    <!-- Glossary Dialog -->
    <el-dialog v-model="glossaryVisible" :title="`术语表 - ${currentSupplier?.name}`" width="60%">
      <el-button type="primary" :icon="Plus" @click="showAddTerm" style="margin-bottom: 16px;">
        添加术语
      </el-button>

      <el-table :data="glossaryTerms" stripe>
        <el-table-column prop="term_source" label="原文" />
        <el-table-column prop="term_target" label="译文" />
        <el-table-column prop="source_lang" label="原语言" width="100" />
        <el-table-column prop="target_lang" label="目标语言" width="100" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="deleteTerm(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const suppliers = ref([])
const loading = ref(false)
const glossaryVisible = ref(false)
const addTermVisible = ref(false)
const currentSupplier = ref(null)
const glossaryTerms = ref([])

const termForm = reactive({
  term_source: '',
  term_target: '',
  source_lang: 'en',
  target_lang: 'zh'
})

onMounted(() => {
  loadSuppliers()
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

async function showGlossary(supplier) {
  currentSupplier.value = supplier
  glossaryVisible.value = true

  try {
    glossaryTerms.value = await api.getGlossary(supplier.id)
  } catch (e) {
    console.error('Failed to load glossary:', e)
    glossaryTerms.value = []
  }
}

function showAddTerm() {
  termForm.term_source = ''
  termForm.term_target = ''
  termForm.source_lang = 'en'
  termForm.target_lang = 'zh'
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

    // Reload glossary
    glossaryTerms.value = await api.getGlossary(currentSupplier.value.id)
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
</script>
