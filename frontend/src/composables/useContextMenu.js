import { ref, reactive } from 'vue'

/**
 * 右键菜单 composable
 * @returns {Object} context menu state and methods
 */
export function useContextMenu() {
  const state = reactive({
    visible: false,
    x: 0,
    y: 0,
    data: null  // 存储右键点击的目标数据
  })

  /**
   * 显示右键菜单
   * @param {MouseEvent} event - 鼠标事件
   * @param {any} data - 关联的数据（如邮件对象）
   */
  function show(event, data = null) {
    event.preventDefault()
    state.x = event.clientX
    state.y = event.clientY
    state.data = data
    state.visible = true
  }

  /**
   * 隐藏右键菜单
   */
  function hide() {
    state.visible = false
    state.data = null
  }

  return {
    state,
    show,
    hide
  }
}

export default useContextMenu
