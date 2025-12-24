<template>
  <div class="email-group-view">
    <!-- 分组控制栏 -->
    <div class="group-controls">
      <el-select
        v-model="localGroupBy"
        placeholder="分组方式"
        size="small"
        style="width: 120px"
        @change="handleGroupChange"
      >
        <el-option
          v-for="opt in groupOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <div class="expand-controls" v-if="localGroupBy">
        <el-button size="small" text @click="expandAll">全部展开</el-button>
        <el-button size="small" text @click="collapseAll">全部收起</el-button>
      </div>
    </div>

    <!-- 分组列表 -->
    <div class="group-list" v-if="localGroupBy && groupedEmails">
      <div
        v-for="group in groupedEmails"
        :key="group.name"
        class="email-group"
      >
        <!-- 分组头部 -->
        <div
          class="group-header"
          :class="{ 'expanded': isExpanded(group.name) }"
          @click="toggleGroup(group.name)"
        >
          <el-icon class="expand-icon">
            <ArrowRight v-if="!isExpanded(group.name)" />
            <ArrowDown v-else />
          </el-icon>
          <span class="group-name">{{ group.name }}</span>
          <span class="group-count">({{ group.emails.length }}封)</span>
          <div class="group-actions">
            <el-button
              size="small"
              text
              @click.stop="markGroupAsRead(group.emails)"
            >
              全部已读
            </el-button>
          </div>
        </div>

        <!-- 分组内邮件列表 -->
        <transition name="collapse">
          <div class="group-emails" v-show="isExpanded(group.name)">
            <div
              v-for="email in group.emails"
              :key="email.id"
              class="email-item compact"
              :class="{
                'unread': !email.is_read,
                'selected': selectedEmails.includes(email.id),
                'active': activeEmailId === email.id
              }"
              @click="$emit('email-click', email)"
            >
              <div class="email-actions">
                <el-checkbox
                  :model-value="selectedEmails.includes(email.id)"
                  @change="$emit('toggle-select', email.id)"
                  @click.stop
                />
                <el-icon
                  class="star-icon"
                  :class="{ 'starred': email.is_flagged }"
                  @click.stop="$emit('toggle-flag', email)"
                >
                  <component :is="email.is_flagged ? StarFilled : Star" />
                </el-icon>
              </div>
              <div class="email-content">
                <div class="email-top-row">
                  <span class="sender-name">{{ email.from_name || extractEmailName(email.from_email) }}</span>
                  <span class="email-time">{{ formatTime(email.received_at) }}</span>
                </div>
                <div class="email-subject">{{ email.subject_original }}</div>
                <div class="email-preview">{{ getPreview(email) }}</div>
              </div>
              <div class="email-tags">
                <el-tag
                  v-for="label in (email.labels || []).slice(0, 2)"
                  :key="label.id"
                  :color="label.color"
                  :style="{ color: getTextColor(label.color) }"
                  size="small"
                  class="label-tag"
                >
                  {{ label.name }}
                </el-tag>
                <el-tag
                  v-if="email.language_detected && email.language_detected !== 'unknown' && email.language_detected !== 'zh'"
                  size="small"
                  type="info"
                >
                  {{ getLanguageName(email.language_detected) }}
                </el-tag>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <!-- 非分组模式提示 -->
    <div class="no-grouping" v-else>
      <slot>
        <!-- 默认插槽用于显示普通邮件列表 -->
      </slot>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Star, StarFilled, ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { useEmailGrouping } from '@/composables/useEmailGrouping'

const props = defineProps({
  emails: {
    type: Array,
    required: true
  },
  selectedEmails: {
    type: Array,
    default: () => []
  },
  activeEmailId: {
    type: [Number, String],
    default: null
  }
})

const emit = defineEmits([
  'email-click',
  'toggle-select',
  'toggle-flag',
  'mark-read',
  'group-change'
])

// 使用分组 composable
const {
  groupBy,
  groupedEmails: computedGroupedEmails,
  expandedGroups,
  toggleGroup: toggleGroupInternal,
  expandAll: expandAllInternal,
  collapseAll: collapseAllInternal,
  groupOptions
} = useEmailGrouping(computed(() => props.emails))

// 本地分组状态
const localGroupBy = ref(groupBy.value)

// 监听分组方式变化
watch(localGroupBy, (val) => {
  groupBy.value = val
  emit('group-change', val)
})

// 计算分组数据
const groupedEmails = computed(() => computedGroupedEmails.value)

// 判断分组是否展开
function isExpanded(groupName) {
  return expandedGroups.value.has(groupName)
}

// 切换分组展开状态
function toggleGroup(groupName) {
  toggleGroupInternal(groupName)
}

// 展开全部
function expandAll() {
  expandAllInternal()
}

// 收起全部
function collapseAll() {
  collapseAllInternal()
}

// 分组方式变更
function handleGroupChange(val) {
  localGroupBy.value = val
}

// 标记分组内所有邮件为已读
function markGroupAsRead(emails) {
  const ids = emails.map(e => e.id)
  emit('mark-read', ids)
}

// 提取邮箱名称
function extractEmailName(email) {
  if (!email) return '未知'
  const match = email.match(/^([^@]+)/)
  return match ? match[1] : email
}

// 格式化时间
function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = dayjs(dateStr)
  const now = dayjs()
  if (d.isSame(now, 'day')) {
    return d.format('HH:mm')
  }
  if (d.isSame(now.subtract(1, 'day'), 'day')) {
    return '昨天 ' + d.format('HH:mm')
  }
  if (d.isSame(now, 'year')) {
    return d.format('MM/DD HH:mm')
  }
  return d.format('YYYY/MM/DD')
}

// 获取邮件预览
function getPreview(email) {
  const text = email.body_translated || email.body_original || ''
  return text.replace(/<[^>]*>/g, '').substring(0, 80)
}

// 获取语言名称
function getLanguageName(lang) {
  if (!lang || lang === 'unknown') return ''
  const names = {
    en: '英',
    ja: '日',
    ko: '韩',
    de: '德',
    fr: '法',
    es: '西',
    pt: '葡',
    ru: '俄',
    it: '意',
    nl: '荷',
    vi: '越',
    th: '泰',
    ar: '阿',
    tr: '土',
    pl: '波',
    zh: '中'
  }
  return names[lang] || lang
}

// 计算标签文字颜色
function getTextColor(bgColor) {
  if (!bgColor) return '#606266'
  const hex = bgColor.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)
  const brightness = (r * 299 + g * 587 + b * 114) / 1000
  return brightness > 128 ? '#333333' : '#ffffff'
}
</script>

<style scoped>
.email-group-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.group-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.expand-controls {
  display: flex;
  gap: 4px;
}

.group-list {
  flex: 1;
  overflow-y: auto;
}

.email-group {
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.group-header {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  transition: background-color 0.2s;
}

.group-header:hover {
  background: var(--el-fill-color);
}

.group-header.expanded {
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.expand-icon {
  margin-right: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  transition: transform 0.2s;
}

.group-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.group-count {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.group-actions {
  margin-left: auto;
}

.group-emails {
  background: var(--el-bg-color);
}

/* 邮件项样式 */
.email-item {
  display: flex;
  align-items: flex-start;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  cursor: pointer;
  transition: background-color 0.15s;
}

.email-item:hover {
  background: var(--el-fill-color-light);
}

.email-item.unread {
  background: rgba(64, 158, 255, 0.04);
}

.email-item.unread .sender-name,
.email-item.unread .email-subject {
  font-weight: 600;
}

.email-item.selected {
  background: var(--el-color-primary-light-9);
}

.email-item.active {
  background: var(--el-color-primary-light-8);
}

.email-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 12px;
}

.star-icon {
  font-size: 16px;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
}

.star-icon:hover {
  color: var(--el-color-warning);
}

.star-icon.starred {
  color: var(--el-color-warning);
}

.email-content {
  flex: 1;
  min-width: 0;
}

.email-top-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.sender-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.email-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  margin-left: 8px;
}

.email-subject {
  font-size: 13px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 2px;
}

.email-preview {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.email-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: 8px;
}

.label-tag {
  border: none;
  font-size: 11px;
  padding: 0 6px;
  height: 18px;
  line-height: 18px;
}

/* 收起展开动画 */
.collapse-enter-active,
.collapse-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.collapse-enter-from,
.collapse-leave-to {
  opacity: 0;
  max-height: 0;
}

.collapse-enter-to,
.collapse-leave-from {
  opacity: 1;
  max-height: 2000px;
}

.no-grouping {
  flex: 1;
  overflow-y: auto;
}
</style>
