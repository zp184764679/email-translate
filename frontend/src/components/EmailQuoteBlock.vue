<template>
  <div class="quote-block" :class="{ 'is-collapsed': isCollapsed, 'is-latest': quote.type === 'latest' }">
    <!-- 引用头部 -->
    <div class="quote-header" @click="toggleCollapse">
      <div class="quote-header-left">
        <el-icon v-if="collapsible" class="collapse-icon">
          <ArrowRight v-if="isCollapsed" />
          <ArrowDown v-else />
        </el-icon>
        <span class="quote-type-badge" v-if="quote.type === 'latest'">
          <el-icon><Message /></el-icon>
          最新回复
        </span>
        <span class="quote-header-text" v-else>
          {{ displayHeader }}
        </span>
      </div>
      <div class="quote-header-right" v-if="isCollapsed && quote.original">
        <span class="quote-preview">{{ previewText }}</span>
      </div>
    </div>

    <!-- 内容区：左右分栏 -->
    <div class="quote-content" v-show="!isCollapsed">
      <!-- 左侧原文 -->
      <div class="quote-pane original-pane">
        <div class="pane-label">原文</div>
        <div class="pane-body" v-if="quote.original" v-html="formatContent(quote.original)"></div>
        <div class="pane-body empty" v-else>(无内容)</div>
      </div>

      <!-- 分隔线 -->
      <div class="quote-divider"></div>

      <!-- 右侧翻译 -->
      <div class="quote-pane translated-pane">
        <div class="pane-label">翻译</div>
        <div class="pane-body" v-if="quote.translated" v-html="formatContent(quote.translated)"></div>
        <div class="pane-body empty" v-else-if="quote.type === 'latest'">(待翻译)</div>
        <div class="pane-body same-as-original" v-else>(同原文)</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ArrowRight, ArrowDown, Message } from '@element-plus/icons-vue'

const props = defineProps({
  quote: {
    type: Object,
    required: true
  },
  defaultExpanded: {
    type: Boolean,
    default: true
  },
  collapsible: {
    type: Boolean,
    default: true
  }
})

const isCollapsed = ref(!props.defaultExpanded)

onMounted(() => {
  // 根据 defaultExpanded 设置初始状态
  isCollapsed.value = !props.defaultExpanded
})

const toggleCollapse = () => {
  if (props.collapsible) {
    isCollapsed.value = !isCollapsed.value
  }
}

// 显示的引用头信息
const displayHeader = computed(() => {
  if (props.quote.header) {
    // 清理引用头，使其更简洁
    let header = props.quote.header
    // 移除多余的换行和空格
    header = header.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim()
    // 截断过长的头信息
    if (header.length > 80) {
      header = header.substring(0, 80) + '...'
    }
    return header
  }
  return `引用内容 (第 ${props.quote.depth} 层)`
})

// 折叠时的预览文本
const previewText = computed(() => {
  const text = props.quote.original || ''
  const cleaned = text.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim()
  if (cleaned.length > 50) {
    return cleaned.substring(0, 50) + '...'
  }
  return cleaned
})

// 格式化内容（将URL转为链接，保留换行）
const formatContent = (text) => {
  if (!text) return ''

  // 转义 HTML
  let formatted = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 将URL转为可点击链接
  const urlPattern = /(https?:\/\/[^\s<]+)/g
  formatted = formatted.replace(urlPattern, '<a href="$1" target="_blank" rel="noopener">$1</a>')

  // 保留换行
  formatted = formatted.replace(/\n/g, '<br>')

  return formatted
}
</script>

<style scoped>
.quote-block {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
  background: #fff;
  transition: all 0.2s ease;
}

.quote-block.is-latest {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}

.quote-block.is-collapsed {
  background: #fafafa;
}

.quote-header {
  padding: 10px 16px;
  background: #f5f7fa;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
  transition: background 0.2s;
}

.quote-header:hover {
  background: #eef1f6;
}

.quote-block.is-latest .quote-header {
  background: #ecf5ff;
}

.quote-block.is-latest .quote-header:hover {
  background: #d9ecff;
}

.quote-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.collapse-icon {
  font-size: 12px;
  color: #909399;
  transition: transform 0.2s;
}

.quote-type-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 500;
  color: #409eff;
}

.quote-header-text {
  font-size: 13px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-header-right {
  flex-shrink: 0;
  max-width: 200px;
}

.quote-preview {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-content {
  display: flex;
  min-height: 100px;
}

.quote-pane {
  flex: 1;
  padding: 16px;
  overflow-x: auto;
}

.original-pane {
  background: #fff;
}

.translated-pane {
  background: #fafcff;
}

.quote-divider {
  width: 1px;
  background: #e4e7ed;
  flex-shrink: 0;
}

.pane-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.pane-body {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  word-break: break-word;
}

.pane-body.empty,
.pane-body.same-as-original {
  color: #c0c4cc;
  font-style: italic;
}

.pane-body :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.pane-body :deep(a:hover) {
  text-decoration: underline;
}

/* 响应式 */
@media (max-width: 768px) {
  .quote-content {
    flex-direction: column;
  }

  .quote-divider {
    width: 100%;
    height: 1px;
  }
}
</style>
