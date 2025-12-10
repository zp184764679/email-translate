<template>
  <div id="app">
    <router-view />

    <!-- 下载进度弹窗 -->
    <el-dialog
      v-model="showDownloadProgress"
      title="正在下载更新"
      width="400px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      center
    >
      <div class="download-progress">
        <div class="version-info">新版本: {{ downloadVersion }}</div>
        <el-progress
          :percentage="downloadPercent"
          :stroke-width="20"
          :format="() => `${downloadPercent}%`"
        />
        <div class="download-details">
          <span>{{ formatBytes(downloadTransferred) }} / {{ formatBytes(downloadTotal) }}</span>
          <span>{{ formatBytes(downloadSpeed) }}/s</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const showDownloadProgress = ref(false)
const downloadVersion = ref('')
const downloadPercent = ref(0)
const downloadTransferred = ref(0)
const downloadTotal = ref(0)
const downloadSpeed = ref(0)

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

onMounted(() => {
  // Listen for update events from Electron
  if (window.electronAPI) {
    window.electronAPI.onUpdateAvailable((version) => {
      ElMessage.info(`发现新版本 ${version}，正在下载...`)
    })

    window.electronAPI.onDownloadStarted((version) => {
      downloadVersion.value = version
      downloadPercent.value = 0
      downloadTransferred.value = 0
      downloadTotal.value = 0
      showDownloadProgress.value = true
    })

    window.electronAPI.onDownloadProgress((progress) => {
      downloadPercent.value = progress.percent
      downloadTransferred.value = progress.transferred
      downloadTotal.value = progress.total
      downloadSpeed.value = progress.bytesPerSecond
    })

    window.electronAPI.onDownloadComplete((version) => {
      showDownloadProgress.value = false
      ElMessage.success(`版本 ${version} 下载完成！`)
    })

    window.electronAPI.onUpdateDownloaded(() => {
      showDownloadProgress.value = false
      ElMessage.success({
        message: '新版本已下载完成，重启后生效',
        duration: 0,
        showClose: true
      })
    })
  }
})
</script>

<style>
#app {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.download-progress {
  text-align: center;
}

.download-progress .version-info {
  font-size: 16px;
  color: #409eff;
  margin-bottom: 20px;
}

.download-progress .download-details {
  display: flex;
  justify-content: space-between;
  margin-top: 15px;
  color: #909399;
  font-size: 13px;
}
</style>
