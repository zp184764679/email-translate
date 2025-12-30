<template>
  <el-dialog
    v-model="visible"
    :title="currentAttachment?.filename || '附件预览'"
    width="80%"
    top="5vh"
    class="attachment-preview-dialog"
    :close-on-click-modal="true"
    @close="handleClose"
  >
    <div class="preview-container" v-loading="loading">
      <!-- 图片预览 -->
      <div v-if="isImage" class="image-preview">
        <img
          :src="previewUrl"
          :alt="currentAttachment?.filename"
          @load="loading = false"
          @error="handleLoadError"
        />
      </div>

      <!-- PDF 预览 -->
      <div v-else-if="isPdf" class="pdf-preview">
        <iframe
          :src="previewUrl"
          @load="loading = false"
        ></iframe>
      </div>

      <!-- 文本/代码预览 -->
      <div v-else-if="isText" class="text-preview">
        <pre>{{ textContent }}</pre>
      </div>

      <!-- 不支持预览 -->
      <div v-else class="no-preview">
        <el-icon :size="64" color="#909399"><Document /></el-icon>
        <p>此文件类型不支持预览</p>
        <p class="file-info">
          {{ currentAttachment?.filename }}
          <span v-if="currentAttachment?.file_size">
            ({{ formatFileSize(currentAttachment.file_size) }})
          </span>
        </p>
      </div>
    </div>

    <!-- 底部工具栏 -->
    <template #footer>
      <div class="preview-footer">
        <div class="nav-buttons" v-if="attachments.length > 1">
          <el-button :disabled="currentIndex <= 0" @click="prevAttachment">
            <el-icon><ArrowLeft /></el-icon>
            上一个
          </el-button>
          <span class="nav-info">{{ currentIndex + 1 }} / {{ attachments.length }}</span>
          <el-button :disabled="currentIndex >= attachments.length - 1" @click="nextAttachment">
            下一个
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
        <div class="action-buttons">
          <el-button type="primary" @click="downloadCurrent">
            <el-icon><Download /></el-icon>
            下载
          </el-button>
          <el-button @click="visible = false">关闭</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Document, ArrowLeft, ArrowRight, Download } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  emailId: {
    type: [Number, String],
    required: true
  },
  attachments: {
    type: Array,
    default: () => []
  },
  initialIndex: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const loading = ref(false)
const currentIndex = ref(0)
const previewUrl = ref('')
const textContent = ref('')

// 当前附件
const currentAttachment = computed(() => {
  return props.attachments[currentIndex.value] || null
})

// 文件类型判断
const fileExtension = computed(() => {
  if (!currentAttachment.value?.filename) return ''
  const parts = currentAttachment.value.filename.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
})

const isImage = computed(() => {
  return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(fileExtension.value)
})

const isPdf = computed(() => {
  return fileExtension.value === 'pdf'
})

const isText = computed(() => {
  return ['txt', 'log', 'md', 'json', 'xml', 'csv', 'html', 'css', 'js', 'ts', 'py', 'java', 'c', 'cpp', 'h'].includes(fileExtension.value)
})

const canPreview = computed(() => {
  return isImage.value || isPdf.value || isText.value
})

// 格式化文件大小
function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 加载预览
async function loadPreview() {
  if (!currentAttachment.value || !props.emailId) return

  // 清理之前的 URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  textContent.value = ''

  if (!canPreview.value) {
    loading.value = false
    return
  }

  loading.value = true

  try {
    const url = await api.previewAttachment(props.emailId, currentAttachment.value.id)

    if (isText.value) {
      // 文本文件需要读取内容
      const response = await fetch(url)
      textContent.value = await response.text()
      URL.revokeObjectURL(url)
      loading.value = false
    } else {
      previewUrl.value = url
      // 图片和 PDF 通过 onload 事件设置 loading = false
    }
  } catch (e) {
    console.error('Failed to load preview:', e)
    ElMessage.error('加载预览失败')
    loading.value = false
  }
}

function handleLoadError() {
  loading.value = false
  ElMessage.error('加载预览失败')
}

function handleClose() {
  // 清理 URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  textContent.value = ''
}

function prevAttachment() {
  if (currentIndex.value > 0) {
    currentIndex.value--
  }
}

function nextAttachment() {
  if (currentIndex.value < props.attachments.length - 1) {
    currentIndex.value++
  }
}

async function downloadCurrent() {
  if (!currentAttachment.value) return
  try {
    await api.downloadAttachment(
      props.emailId,
      currentAttachment.value.id,
      currentAttachment.value.filename
    )
  } catch (e) {
    console.error('Download failed:', e)
    ElMessage.error('下载失败')
  }
}

// 监听对话框打开
watch(visible, (val) => {
  if (val) {
    currentIndex.value = props.initialIndex
    loadPreview()
  }
})

// 监听当前索引变化
watch(currentIndex, () => {
  loadPreview()
})

// 监听初始索引变化
watch(() => props.initialIndex, (val) => {
  if (visible.value) {
    currentIndex.value = val
  }
})
</script>

<style scoped>
.attachment-preview-dialog :deep(.el-dialog__body) {
  padding: 0;
  height: 70vh;
  overflow: hidden;
}

.preview-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f5f5;
}

.image-preview {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: 20px;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  background-color: #fff;
}

.pdf-preview {
  width: 100%;
  height: 100%;
}

.pdf-preview iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.text-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 20px;
  background-color: #1e1e1e;
}

.text-preview pre {
  margin: 0;
  padding: 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.no-preview {
  text-align: center;
  color: #909399;
}

.no-preview p {
  margin: 16px 0 8px;
  font-size: 16px;
}

.no-preview .file-info {
  font-size: 14px;
  color: #c0c4cc;
}

.preview-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.nav-buttons {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-info {
  font-size: 14px;
  color: #606266;
  min-width: 60px;
  text-align: center;
}

.action-buttons {
  display: flex;
  gap: 8px;
}
</style>
