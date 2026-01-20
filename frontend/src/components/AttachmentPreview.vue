<template>
  <el-dialog
    v-model="visible"
    :title="currentAttachment?.filename || '附件预览'"
    width="80%"
    top="5vh"
    class="attachment-preview-dialog"
    :class="{ 'fullscreen-mode': isFullscreen }"
    :close-on-click-modal="true"
    :fullscreen="isFullscreen"
    @close="handleClose"
    @keydown="handleKeydown"
  >
    <div class="preview-container" v-loading="loading" tabindex="0" ref="containerRef">
      <!-- 图片预览（画廊模式） -->
      <div v-if="isImage" class="image-preview" :class="{ zoomed: isZoomed }">
        <img
          ref="imageRef"
          :src="previewUrl"
          :alt="currentAttachment?.filename"
          :style="imageStyle"
          @load="loading = false"
          @error="handleLoadError"
          @click="toggleZoom"
          @wheel="handleWheel"
        />
        <!-- 图片工具栏 -->
        <div class="image-toolbar">
          <el-button circle size="small" @click="zoomOut" :disabled="zoomLevel <= 0.5">
            <el-icon><ZoomOut /></el-icon>
          </el-button>
          <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
          <el-button circle size="small" @click="zoomIn" :disabled="zoomLevel >= 3">
            <el-icon><ZoomIn /></el-icon>
          </el-button>
          <el-button circle size="small" @click="resetZoom">
            <el-icon><RefreshRight /></el-icon>
          </el-button>
          <el-button circle size="small" @click="toggleFullscreen">
            <el-icon><FullScreen /></el-icon>
          </el-button>
        </div>
        <!-- 缩略图导航 -->
        <div v-if="imageAttachments.length > 1" class="thumbnail-strip">
          <div
            v-for="(att, idx) in imageAttachments"
            :key="att.id"
            class="thumbnail-item"
            :class="{ active: attachments[currentIndex]?.id === att.id }"
            @click="jumpToAttachment(att)"
          >
            <img
              :src="thumbnailUrls[att.id] || ''"
              :alt="att.filename"
              @error="(e) => e.target.style.display = 'none'"
            />
            <div class="thumbnail-index">{{ idx + 1 }}</div>
          </div>
        </div>
        <!-- 左右导航箭头 -->
        <div v-if="attachments.length > 1" class="image-nav prev" @click="prevAttachment">
          <el-icon :size="32"><ArrowLeft /></el-icon>
        </div>
        <div v-if="attachments.length > 1" class="image-nav next" @click="nextAttachment">
          <el-icon :size="32"><ArrowRight /></el-icon>
        </div>
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

      <!-- Excel 预览 -->
      <div v-else-if="isExcel && excelData" class="excel-preview">
        <div class="sheet-tabs" v-if="excelData.sheets.length > 1">
          <el-radio-group v-model="excelData.activeSheet" size="small">
            <el-radio-button
              v-for="sheet in excelData.sheets"
              :key="sheet.name"
              :value="sheet.name"
            >
              {{ sheet.name }}
            </el-radio-button>
          </el-radio-group>
        </div>
        <div class="excel-table-wrapper">
          <table class="excel-table">
            <tbody>
              <tr v-for="(row, rowIdx) in activeSheetData" :key="rowIdx">
                <td
                  v-for="(cell, colIdx) in row"
                  :key="colIdx"
                  :class="{ 'header-cell': rowIdx === 0 }"
                >
                  {{ cell }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Word 预览 -->
      <div v-else-if="isWord && wordHtml" class="word-preview">
        <div class="word-content" v-html="wordHtml"></div>
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Document, ArrowLeft, ArrowRight, Download, ZoomIn, ZoomOut, RefreshRight, FullScreen } from '@element-plus/icons-vue'
import api from '@/api'
import { ElMessage } from 'element-plus'
import * as XLSX from 'xlsx'
import mammoth from 'mammoth'

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
const excelData = ref(null)      // Excel 表格数据 { sheets, activeSheet }
const wordHtml = ref('')          // Word 文档 HTML
const containerRef = ref(null)
const imageRef = ref(null)

// 图片画廊模式状态
const isFullscreen = ref(false)
const zoomLevel = ref(1)
const isZoomed = computed(() => zoomLevel.value !== 1)
const thumbnailUrls = ref({})  // 缩略图 URL 缓存

// 只过滤图片附件（用于缩略图条）
const imageAttachments = computed(() => {
  const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']
  return props.attachments.filter(att => {
    const ext = att.filename?.split('.').pop()?.toLowerCase() || ''
    return imageExts.includes(ext)
  })
})

// 图片样式（缩放）
const imageStyle = computed(() => ({
  transform: `scale(${zoomLevel.value})`,
  cursor: isZoomed.value ? 'zoom-out' : 'zoom-in'
}))

// 缩放控制
function zoomIn() {
  if (zoomLevel.value < 3) {
    zoomLevel.value = Math.min(3, zoomLevel.value + 0.25)
  }
}

function zoomOut() {
  if (zoomLevel.value > 0.5) {
    zoomLevel.value = Math.max(0.5, zoomLevel.value - 0.25)
  }
}

function resetZoom() {
  zoomLevel.value = 1
}

function toggleZoom() {
  if (zoomLevel.value === 1) {
    zoomLevel.value = 2
  } else {
    zoomLevel.value = 1
  }
}

function handleWheel(e) {
  if (!isImage.value) return
  e.preventDefault()
  if (e.deltaY < 0) {
    zoomIn()
  } else {
    zoomOut()
  }
}

// 全屏切换
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

// 键盘导航
function handleKeydown(e) {
  switch (e.key) {
    case 'ArrowLeft':
      prevAttachment()
      e.preventDefault()
      break
    case 'ArrowRight':
      nextAttachment()
      e.preventDefault()
      break
    case 'Escape':
      if (isFullscreen.value) {
        isFullscreen.value = false
        e.preventDefault()
      }
      break
    case '+':
    case '=':
      zoomIn()
      e.preventDefault()
      break
    case '-':
      zoomOut()
      e.preventDefault()
      break
    case '0':
      resetZoom()
      e.preventDefault()
      break
  }
}

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

const isExcel = computed(() => {
  return ['xls', 'xlsx', 'xlsm', 'xlsb'].includes(fileExtension.value)
})

const isWord = computed(() => {
  return ['doc', 'docx'].includes(fileExtension.value)
})

// 当前激活的 Excel 工作表数据
const activeSheetData = computed(() => {
  if (!excelData.value?.sheets?.length) return []
  const sheet = excelData.value.sheets.find(s => s.name === excelData.value.activeSheet)
  return sheet?.data || []
})

const canPreview = computed(() => {
  return isImage.value || isPdf.value || isText.value || isExcel.value || isWord.value
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

  // 清理之前的 URL 和内容
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  textContent.value = ''
  excelData.value = null
  wordHtml.value = ''

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
    } else if (isExcel.value) {
      // Excel 文件解析
      const response = await fetch(url)
      const arrayBuffer = await response.arrayBuffer()
      URL.revokeObjectURL(url)

      const workbook = XLSX.read(arrayBuffer, { type: 'array' })
      const sheets = workbook.SheetNames.map(name => {
        const sheet = workbook.Sheets[name]
        const data = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' })
        return { name, data }
      })

      excelData.value = {
        sheets,
        activeSheet: sheets[0]?.name || ''
      }
      loading.value = false
    } else if (isWord.value) {
      // Word 文件解析（仅支持 .docx）
      if (fileExtension.value === 'docx') {
        const response = await fetch(url)
        const arrayBuffer = await response.arrayBuffer()
        URL.revokeObjectURL(url)

        const result = await mammoth.convertToHtml({ arrayBuffer })
        wordHtml.value = result.value
        if (result.messages.length > 0) {
          console.warn('Word conversion warnings:', result.messages)
        }
      } else {
        // .doc 格式不支持
        wordHtml.value = '<p style="text-align:center;color:#909399;padding:40px;">旧版 .doc 格式不支持预览，请下载后使用 WPS 或 Office 打开</p>'
      }
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
  // 清理预览 URL
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  textContent.value = ''
  excelData.value = null
  wordHtml.value = ''

  // 清理缩略图 URL
  Object.values(thumbnailUrls.value).forEach(url => {
    if (url) URL.revokeObjectURL(url)
  })
  thumbnailUrls.value = {}
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

// 跳转到指定附件
function jumpToAttachment(att) {
  const idx = props.attachments.findIndex(a => a.id === att.id)
  if (idx !== -1) {
    currentIndex.value = idx
  }
}

// 加载所有图片的缩略图
async function loadThumbnails() {
  for (const att of imageAttachments.value) {
    if (thumbnailUrls.value[att.id]) continue  // 已加载过
    try {
      const url = await api.previewAttachment(props.emailId, att.id)
      thumbnailUrls.value[att.id] = url
    } catch (e) {
      console.warn('Failed to load thumbnail for', att.filename)
    }
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
    loadThumbnails()  // 加载缩略图
  }
})

// 监听当前索引变化
watch(currentIndex, () => {
  zoomLevel.value = 1  // 切换图片时重置缩放
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
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: 20px;
  background-color: #1a1a1a;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  background-color: #fff;
  transition: transform 0.2s ease;
  user-select: none;
}

.image-preview.zoomed img {
  max-width: none;
  max-height: none;
}

/* 图片工具栏 */
.image-toolbar {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 20px;
  z-index: 10;
}

.image-toolbar .el-button {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: #fff;
}

.image-toolbar .el-button:hover {
  background: rgba(255, 255, 255, 0.3);
}

.image-toolbar .el-button:disabled {
  opacity: 0.5;
}

.image-toolbar .zoom-level {
  color: #fff;
  font-size: 12px;
  min-width: 40px;
  text-align: center;
}

/* 图片导航箭头 */
.image-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 50px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
  transition: all 0.2s;
  z-index: 10;
}

.image-nav:hover {
  background: rgba(0, 0, 0, 0.7);
}

.image-nav.prev {
  left: 0;
  border-radius: 0 8px 8px 0;
}

.image-nav.next {
  right: 0;
  border-radius: 8px 0 0 8px;
}

/* 缩略图导航条 */
.thumbnail-strip {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 8px;
  z-index: 10;
  max-width: 80%;
  overflow-x: auto;
}

.thumbnail-strip::-webkit-scrollbar {
  height: 4px;
}

.thumbnail-strip::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}

.thumbnail-item {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
  flex-shrink: 0;
}

.thumbnail-item:hover {
  border-color: rgba(255, 255, 255, 0.5);
}

.thumbnail-item.active {
  border-color: #409EFF;
  box-shadow: 0 0 8px rgba(64, 158, 255, 0.5);
}

.thumbnail-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail-index {
  position: absolute;
  bottom: 2px;
  right: 2px;
  font-size: 10px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  padding: 1px 4px;
  border-radius: 2px;
  line-height: 1;
}

/* 全屏模式 */
.fullscreen-mode :deep(.el-dialog__body) {
  height: calc(100vh - 120px) !important;
}

.fullscreen-mode .preview-container {
  height: 100%;
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

/* Excel 预览 */
.excel-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
}

.sheet-tabs {
  padding: 8px 16px;
  background-color: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.excel-table-wrapper {
  flex: 1;
  overflow: auto;
  padding: 16px;
}

.excel-table {
  border-collapse: collapse;
  background-color: #fff;
  font-size: 13px;
  min-width: 100%;
}

.excel-table td {
  border: 1px solid #e4e7ed;
  padding: 8px 12px;
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.excel-table td.header-cell {
  background-color: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

.excel-table tr:hover td {
  background-color: #f5f7fa;
}

.excel-table tr:hover td.header-cell {
  background-color: #ebeef5;
}

/* Word 预览 */
.word-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: #f5f5f5;
  padding: 20px;
}

.word-content {
  max-width: 800px;
  margin: 0 auto;
  background-color: #fff;
  padding: 40px 60px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  min-height: 100%;
  line-height: 1.8;
  color: #303133;
}

.word-content h1,
.word-content h2,
.word-content h3 {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  color: #1f2329;
}

.word-content p {
  margin: 0.8em 0;
}

.word-content table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
}

.word-content table td,
.word-content table th {
  border: 1px solid #dcdfe6;
  padding: 8px 12px;
}

.word-content img {
  max-width: 100%;
  height: auto;
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
