import { onMounted, onUnmounted, ref } from 'vue'

/**
 * 快捷键系统 composable
 * @param {Array} shortcuts - 快捷键配置数组
 * @param {Object} options - 配置选项
 * @returns {Object} - { enabled, setEnabled }
 */
export function useKeyboardShortcuts(shortcuts, options = {}) {
  const { enabled: initialEnabled = true } = options
  const enabled = ref(initialEnabled)

  const handleKeyDown = (event) => {
    if (!enabled.value) return

    // 忽略输入框内的按键（除了 Escape）
    const target = event.target
    const tagName = target.tagName
    const isEditable = target.isContentEditable

    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tagName) || isEditable) {
      // 在输入框中只响应 Escape
      if (event.key !== 'Escape') return
    }

    const key = event.key.toLowerCase()
    const ctrl = event.ctrlKey || event.metaKey  // 支持 Mac 的 Command 键
    const shift = event.shiftKey
    const alt = event.altKey

    // 查找匹配的快捷键
    const shortcut = shortcuts.find(s => {
      const keyMatch = s.key.toLowerCase() === key
      const ctrlMatch = (s.ctrl ?? false) === ctrl
      const shiftMatch = (s.shift ?? false) === shift
      const altMatch = (s.alt ?? false) === alt
      return keyMatch && ctrlMatch && shiftMatch && altMatch
    })

    if (shortcut && shortcut.handler) {
      event.preventDefault()
      event.stopPropagation()
      shortcut.handler(event)
    }
  }

  const setEnabled = (value) => {
    enabled.value = value
  }

  onMounted(() => {
    window.addEventListener('keydown', handleKeyDown, true)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown, true)
  })

  return {
    enabled,
    setEnabled
  }
}

/**
 * 全局快捷键列表（用于帮助弹窗显示）
 */
export const SHORTCUT_DEFINITIONS = {
  // 邮件列表快捷键
  list: [
    { key: 'j', label: '下一封邮件', description: '选择下一封邮件' },
    { key: 'k', label: '上一封邮件', description: '选择上一封邮件' },
    { key: 'Enter', label: '打开邮件', description: '打开选中的邮件' },
    { key: 'x', label: '选择/取消', description: '选择或取消选择邮件' },
    { key: 's', label: '切换星标', description: '为邮件添加或移除星标' },
    { key: 'd', label: '删除', description: '删除选中的邮件' },
    { key: 'u', label: '标记未读', description: '将邮件标记为未读' },
    { key: 'l', label: '添加标签', description: '为邮件添加标签' },
    { key: 'e', label: '归档', description: '归档邮件' },
  ],
  // 邮件详情快捷键
  detail: [
    { key: 'r', label: '回复', description: '回复当前邮件' },
    { key: 'a', label: '全部回复', description: '回复所有人' },
    { key: 'f', label: '转发', description: '转发当前邮件' },
    { key: 's', label: '切换星标', description: '为邮件添加或移除星标' },
    { key: 'd', label: '删除', description: '删除当前邮件' },
    { key: 'u', label: '标记未读', description: '将邮件标记为未读' },
    { key: 'l', label: '添加标签', description: '为邮件添加标签' },
    { key: 'Escape', label: '返回列表', description: '返回邮件列表' },
    { key: 'j', label: '下一封', description: '查看下一封邮件' },
    { key: 'k', label: '上一封', description: '查看上一封邮件' },
  ],
  // 编辑器快捷键
  editor: [
    { key: 'Enter', ctrl: true, label: '发送', description: '发送邮件' },
    { key: 'Escape', label: '取消', description: '取消编辑' },
  ],
  // 全局快捷键
  global: [
    { key: 'n', label: '新邮件', description: '撰写新邮件' },
    { key: '/', label: '搜索', description: '聚焦搜索框' },
    { key: '?', shift: true, label: '快捷键帮助', description: '显示快捷键帮助' },
    { key: 'g', label: '跳转', description: '快速跳转菜单' },
  ]
}
