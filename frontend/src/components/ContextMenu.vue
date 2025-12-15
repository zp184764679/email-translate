<template>
  <teleport to="body">
    <transition name="context-menu-fade">
      <div
        v-show="visible"
        ref="menuRef"
        class="context-menu"
        :style="menuStyle"
        @click.stop
      >
        <template v-for="(item, index) in items" :key="item.key || index">
          <!-- 分隔线 -->
          <div v-if="item.divider" class="context-menu-divider" />

          <!-- 菜单项 -->
          <div
            v-else
            :class="[
              'context-menu-item',
              {
                'is-danger': item.danger,
                'is-disabled': item.disabled
              }
            ]"
            @click="handleItemClick(item)"
          >
            <el-icon v-if="item.icon" class="menu-icon">
              <component :is="item.icon" />
            </el-icon>
            <span class="menu-label">{{ item.label }}</span>
            <span v-if="item.shortcut" class="menu-shortcut">{{ item.shortcut }}</span>
          </div>
        </template>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  x: {
    type: Number,
    default: 0
  },
  y: {
    type: Number,
    default: 0
  },
  items: {
    type: Array,
    default: () => []
    // item: { key, icon, label, shortcut?, danger?, disabled?, divider? }
  }
})

const emit = defineEmits(['select', 'close'])

const menuRef = ref(null)
const adjustedX = ref(0)
const adjustedY = ref(0)

// 计算菜单位置，确保不超出视窗
const menuStyle = computed(() => ({
  left: `${adjustedX.value}px`,
  top: `${adjustedY.value}px`
}))

// 调整菜单位置以防止超出视窗
async function adjustPosition() {
  await nextTick()

  if (!menuRef.value) {
    adjustedX.value = props.x
    adjustedY.value = props.y
    return
  }

  const menu = menuRef.value
  const menuRect = menu.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  let newX = props.x
  let newY = props.y

  // 检查右边界
  if (newX + menuRect.width > viewportWidth - 10) {
    newX = viewportWidth - menuRect.width - 10
  }

  // 检查下边界
  if (newY + menuRect.height > viewportHeight - 10) {
    newY = viewportHeight - menuRect.height - 10
  }

  // 确保不小于0
  adjustedX.value = Math.max(10, newX)
  adjustedY.value = Math.max(10, newY)
}

// 监听位置变化
watch(() => [props.x, props.y, props.visible], () => {
  if (props.visible) {
    adjustPosition()
  }
}, { immediate: true })

// 处理菜单项点击
function handleItemClick(item) {
  if (item.disabled) return
  emit('select', item.key)
  emit('close')
}

// 点击外部关闭菜单
function handleClickOutside(event) {
  if (props.visible && menuRef.value && !menuRef.value.contains(event.target)) {
    emit('close')
  }
}

// 按 Escape 关闭
function handleKeydown(event) {
  if (props.visible && event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('contextmenu', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('contextmenu', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style>
/* 不使用 scoped，因为 teleport 到 body 时 scoped 样式可能失效 */
.context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 160px;
  max-width: 280px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 14px;
  color: #303133;
  cursor: pointer;
  transition: background-color 0.15s;
  white-space: nowrap;
}

.context-menu-item:hover {
  background-color: #f5f7fa;
}

.context-menu-item.is-danger {
  color: #f56c6c;
}

.context-menu-item.is-danger:hover {
  background-color: #fef0f0;
}

.context-menu-item.is-disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}

.context-menu-item.is-disabled:hover {
  background-color: transparent;
}

.menu-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.menu-label {
  flex: 1;
}

.menu-shortcut {
  margin-left: 16px;
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.context-menu-divider {
  height: 1px;
  background-color: #ebeef5;
  margin: 4px 0;
}

/* 过渡动画 */
.context-menu-fade-enter-active,
.context-menu-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.context-menu-fade-enter-from,
.context-menu-fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
