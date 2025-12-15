<template>
  <div class="folder-picker">
    <div class="folder-list">
      <div
        v-for="folder in folders"
        :key="folder.id"
        class="folder-item"
        :class="{ 'is-selected': selectedFolderId === folder.id }"
        @click="selectedFolderId = folder.id"
      >
        <el-icon><Folder /></el-icon>
        <span>{{ folder.name }}</span>
      </div>
      <el-empty v-if="folders.length === 0" description="暂无文件夹" :image-size="60" />
    </div>
    <div class="picker-footer">
      <el-button @click="$emit('cancel')">取消</el-button>
      <el-button type="primary" :disabled="!selectedFolderId" :loading="moving" @click="moveToFolder">
        移动
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Folder } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const props = defineProps({
  emailId: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['done', 'cancel'])

const folders = ref([])
const selectedFolderId = ref(null)
const moving = ref(false)

onMounted(async () => {
  try {
    folders.value = await api.getFolders()
  } catch (e) {
    console.error('Failed to load folders:', e)
  }
})

async function moveToFolder() {
  if (!selectedFolderId.value) return

  moving.value = true
  try {
    await api.addEmailsToFolder(selectedFolderId.value, [props.emailId])
    ElMessage.success('已移至文件夹')
    emit('done')
  } catch (e) {
    ElMessage.error('移动失败')
  } finally {
    moving.value = false
  }
}
</script>

<style scoped>
.folder-picker {
  min-height: 200px;
}

.folder-list {
  max-height: 300px;
  overflow-y: auto;
}

.folder-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.15s;
}

.folder-item:hover {
  background-color: #f5f7fa;
}

.folder-item.is-selected {
  background-color: #ecf5ff;
  color: #409eff;
}

.picker-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>
