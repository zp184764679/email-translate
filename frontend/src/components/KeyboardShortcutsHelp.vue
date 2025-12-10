<template>
  <el-dialog
    v-model="visible"
    title="键盘快捷键"
    width="600px"
    :append-to-body="true"
    class="shortcuts-dialog"
  >
    <div class="shortcuts-content">
      <!-- 邮件列表快捷键 -->
      <div class="shortcut-section">
        <h4>邮件列表</h4>
        <div class="shortcut-grid">
          <div class="shortcut-item" v-for="s in listShortcuts" :key="s.key">
            <kbd>{{ formatKey(s) }}</kbd>
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>

      <!-- 邮件详情快捷键 -->
      <div class="shortcut-section">
        <h4>邮件详情</h4>
        <div class="shortcut-grid">
          <div class="shortcut-item" v-for="s in detailShortcuts" :key="s.key">
            <kbd>{{ formatKey(s) }}</kbd>
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>

      <!-- 编辑器快捷键 -->
      <div class="shortcut-section">
        <h4>编辑器</h4>
        <div class="shortcut-grid">
          <div class="shortcut-item" v-for="s in editorShortcuts" :key="s.key">
            <kbd>{{ formatKey(s) }}</kbd>
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>

      <!-- 全局快捷键 -->
      <div class="shortcut-section">
        <h4>全局</h4>
        <div class="shortcut-grid">
          <div class="shortcut-item" v-for="s in globalShortcuts" :key="s.key">
            <kbd>{{ formatKey(s) }}</kbd>
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="hint">按 <kbd>?</kbd> 或 <kbd>Esc</kbd> 关闭此对话框</span>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { SHORTCUT_DEFINITIONS } from '@/composables/useKeyboardShortcuts'

const visible = ref(false)

const listShortcuts = computed(() => SHORTCUT_DEFINITIONS.list)
const detailShortcuts = computed(() => SHORTCUT_DEFINITIONS.detail)
const editorShortcuts = computed(() => SHORTCUT_DEFINITIONS.editor)
const globalShortcuts = computed(() => SHORTCUT_DEFINITIONS.global)

function formatKey(shortcut) {
  const parts = []
  if (shortcut.ctrl) parts.push('Ctrl')
  if (shortcut.shift) parts.push('Shift')
  if (shortcut.alt) parts.push('Alt')

  let key = shortcut.key
  // 美化特殊键名
  if (key === 'Enter') key = 'Enter'
  else if (key === 'Escape') key = 'Esc'
  else if (key === '/') key = '/'
  else if (key === '?') key = '?'
  else key = key.toUpperCase()

  parts.push(key)
  return parts.join(' + ')
}

function show() {
  visible.value = true
}

function hide() {
  visible.value = false
}

function toggle() {
  visible.value = !visible.value
}

// 监听全局快捷键 ? 来显示/隐藏
function handleKeyDown(event) {
  // Shift + ? 或单独的 ? 键
  if ((event.key === '?' || (event.shiftKey && event.key === '/')) &&
      !['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) {
    event.preventDefault()
    toggle()
  }
  // Esc 关闭
  if (event.key === 'Escape' && visible.value) {
    event.preventDefault()
    hide()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

// 暴露方法给父组件
defineExpose({ show, hide, toggle })
</script>

<style scoped>
.shortcuts-dialog :deep(.el-dialog__body) {
  padding: 16px 24px;
}

.shortcuts-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.shortcut-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 8px;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.shortcut-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.shortcut-item kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 24px;
  padding: 0 8px;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  background: linear-gradient(180deg, #fff 0%, #f5f5f5 100%);
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.1), inset 0 1px 0 #fff;
}

.shortcut-item span {
  font-size: 13px;
  color: #606266;
}

.dialog-footer {
  text-align: center;
}

.dialog-footer .hint {
  font-size: 12px;
  color: #909399;
}

.dialog-footer .hint kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 4px;
  margin: 0 2px;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 11px;
  font-weight: 500;
  color: #606266;
  background: #f5f5f5;
  border: 1px solid #d0d0d0;
  border-radius: 3px;
}
</style>
