<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import wsManager from './utils/websocket'
import { useUserStore } from './stores/user'
import { useEmailStore } from './stores/emails'
import api, { getStorageKey } from './api'

const router = useRouter()
const userStore = useUserStore()
const emailStore = useEmailStore()

// 处理认证过期事件
function handleAuthExpired(event) {
  const { message } = event.detail || {}

  // 通过 store 正确清理状态（会停止定时器等）
  userStore.logout()

  // 断开 WebSocket
  wsManager.disconnect()

  // 跳转到登录页
  router.push('/login')

  // 显示消息
  ElMessage.error(message || '登录已过期，请重新登录')
}

// 显示桌面通知（Web Notifications API）
function showDesktopNotification(title, body) {
  if (!('Notification' in window)) return

  if (Notification.permission === 'granted') {
    new Notification(title, { body, icon: '/email/favicon.ico' })
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        new Notification(title, { body, icon: '/email/favicon.ico' })
      }
    })
  }
}

onMounted(() => {
  // 监听认证过期事件
  window.addEventListener('auth:expired', handleAuthExpired)

  // 请求桌面通知权限
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  // 初始化 WebSocket 连接
  initWebSocket()
})

// WebSocket 清理
const wsUnsubscribes = []

function initWebSocket() {
  // 获取账户ID（使用环境前缀避免开发/生产环境冲突）
  const accountId = localStorage.getItem(getStorageKey('accountId'))
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

      // 直接使用 WebSocket 推送的完整数据更新 store（无需再请求 API）
      if (data.success && data.body_translated !== undefined) {
        emailStore.updateEmailTranslation(data.email_id, {
          subject_translated: data.subject_translated,
          body_translated: data.body_translated,
          is_translated: data.is_translated,
          translation_status: data.translation_status
        })
        console.log('[WS] Updated email translation in store from WS data:', data.email_id)
      }

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

      // 更新 store 中的翻译状态为失败
      if (data.email_id) {
        emailStore.updateEmailTranslation(data.email_id, {
          translation_status: 'failed'
        })
      }

      // 触发全局事件供其他组件刷新
      window.dispatchEvent(new CustomEvent('email-translation-failed', { detail: data }))
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
        // 显示桌面通知
        showDesktopNotification('收到新邮件', `您有 ${data.new_count} 封新邮件`)
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

  // 监听邮件状态变更（已读/未读/星标等）
  wsUnsubscribes.push(
    wsManager.on('email_status_changed', (data) => {
      console.log('[WS] Email status changed:', data)
      // 触发全局事件供其他组件更新状态
      window.dispatchEvent(new CustomEvent('email-status-changed', { detail: data }))
    })
  )

  // 监听邮件删除
  wsUnsubscribes.push(
    wsManager.on('email_deleted', (data) => {
      console.log('[WS] Emails deleted:', data)
      // 触发全局事件供其他组件刷新列表
      window.dispatchEvent(new CustomEvent('email-deleted', { detail: data }))
    })
  )

  // 监听日历事件提醒
  wsUnsubscribes.push(
    wsManager.on('calendar_reminder', (data) => {
      console.log('[WS] Calendar reminder:', data)

      // 格式化提醒时间
      const minutesText = data.minutes_until <= 0
        ? '现在开始'
        : data.minutes_until === 1
          ? '1 分钟后开始'
          : `${data.minutes_until} 分钟后开始`

      // 格式化开始时间
      const startTime = new Date(data.start_time)
      const timeStr = startTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

      // 构建消息
      let message = `${timeStr} ${minutesText}`
      if (data.location) {
        message += `\n地点: ${data.location}`
      }

      // 显示应用内通知
      ElNotification.warning({
        title: `📅 ${data.title}`,
        message: message,
        duration: 0,  // 不自动关闭，让用户手动关闭
        onClick: () => {
          // 点击通知跳转到日历页面
          router.push('/calendar')
        }
      })

      // 显示桌面通知（Web Notifications API）
      showDesktopNotification(`📅 ${data.title}`, message)

      // 触发全局事件
      window.dispatchEvent(new CustomEvent('calendar-reminder', { detail: data }))
    })
  )
}

onUnmounted(() => {
  // 清理认证过期事件监听器
  window.removeEventListener('auth:expired', handleAuthExpired)

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
</style>
