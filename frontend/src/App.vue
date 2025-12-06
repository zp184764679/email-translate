<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'

onMounted(() => {
  // Listen for update events from Electron
  if (window.electronAPI) {
    window.electronAPI.onUpdateAvailable(() => {
      ElMessage.info('发现新版本，正在下载...')
    })

    window.electronAPI.onUpdateDownloaded(() => {
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
</style>
