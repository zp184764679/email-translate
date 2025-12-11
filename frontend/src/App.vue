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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import wsManager from './utils/websocket'

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

  // 初始化 WebSocket 连接
  initWebSocket()
})

// WebSocket 清理
const wsUnsubscribes = []

function initWebSocket() {
  // 获取账户ID
  const accountId = localStorage.getItem('accountId')
  if (!accountId) {
    console.log('[App] No accountId, WebSocket not connected')
    return
  }

  // 连接 WebSocket
  wsManager.connect(parseInt(accountId))

  // 监听翻译完成事件
  wsUnsubscribes.push(
    wsManager.on('translation_complete', (data) => {
      console.log('[WS] Translation complete:', data)
      ElNotification.success({
        title: '翻译完成',
        message: `邮件 #${data.email_id} 翻译完成`,
        duration: 3000
      })
      // 触发全局事件供其他组件刷新
      window.dispatchEvent(new CustomEvent('email-translated', { detail: data }))
    })
  )

  // 监听翻译失败事件
  wsUnsubscribes.push(
    wsManager.on('translation_failed', (data) => {
      console.log('[WS] Translation failed:', data)
      ElNotification.error({
        title: '翻译失败',
        message: data.error || '翻译过程中发生错误',
        duration: 5000
      })
    })
  )

  // 监听邮件发送完成
  wsUnsubscribes.push(
    wsManager.on('email_sent', (data) => {
      console.log('[WS] Email sent:', data)
      ElNotification.success({
        title: '邮件已发送',
        message: `发送至 ${data.to}`,
        duration: 3000
      })
      window.dispatchEvent(new CustomEvent('email-sent', { detail: data }))
    })
  )

  // 监听邮件拉取进度
  wsUnsubscribes.push(
    wsManager.on('fetch_progress', (data) => {
      console.log('[WS] Fetch progress:', data)
      // 可以更新全局状态显示进度
      window.dispatchEvent(new CustomEvent('fetch-progress', { detail: data }))
    })
  )

  // 监听邮件拉取完成
  wsUnsubscribes.push(
    wsManager.on('fetch_complete', (data) => {
      console.log('[WS] Fetch complete:', data)
      if (data.new_count > 0) {
        ElNotification.success({
          title: '同步完成',
          message: `收到 ${data.new_count} 封新邮件`,
          duration: 3000
        })
      } else {
        ElMessage.info('没有新邮件')
      }
      window.dispatchEvent(new CustomEvent('fetch-complete', { detail: data }))
    })
  )

  // 监听 AI 提取完成
  wsUnsubscribes.push(
    wsManager.on('extraction_complete', (data) => {
      console.log('[WS] Extraction complete:', data)
      ElNotification.success({
        title: 'AI 提取完成',
        message: `邮件 #${data.email_id} 信息提取完成`,
        duration: 3000
      })
      window.dispatchEvent(new CustomEvent('extraction-complete', { detail: data }))
    })
  )

  // 监听导出完成
  wsUnsubscribes.push(
    wsManager.on('export_ready', (data) => {
      console.log('[WS] Export ready:', data)
      ElNotification.success({
        title: '导出完成',
        message: `${data.email_count} 封邮件已准备好下载`,
        duration: 0,  // 不自动关闭
        onClick: () => {
          // 点击通知打开下载链接
          window.open(data.download_url, '_blank')
        }
      })
    })
  )

  // 监听批量操作完成
  wsUnsubscribes.push(
    wsManager.on('batch_translation_complete', (data) => {
      console.log('[WS] Batch translation complete:', data)
      ElNotification.success({
        title: '批量翻译完成',
        message: `成功 ${data.completed}/${data.total}`,
        duration: 5000
      })
      window.dispatchEvent(new CustomEvent('batch-complete', { detail: data }))
    })
  )
}

onUnmounted(() => {
  // 清理 WebSocket 监听器
  wsUnsubscribes.forEach(unsub => unsub())
  wsManager.disconnect()
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
