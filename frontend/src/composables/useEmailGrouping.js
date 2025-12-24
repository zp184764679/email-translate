import { ref, computed, watch } from 'vue'
import { getStorageKey } from '@/api'

/**
 * 邮件分组 Composable
 *
 * 支持按发件人、日期、语言、标签分组显示邮件
 */
export function useEmailGrouping(emails) {
  // 分组方式: null(不分组), 'sender', 'date', 'language', 'label'
  const groupBy = ref(localStorage.getItem(getStorageKey('emailGroupBy')) || null)

  // 展开的分组
  const expandedGroups = ref(new Set(['default']))

  // 保存分组偏好
  watch(groupBy, (val) => {
    if (val) {
      localStorage.setItem(getStorageKey('emailGroupBy'), val)
    } else {
      localStorage.removeItem(getStorageKey('emailGroupBy'))
    }
  })

  // 日期分组标签
  function getDateGroup(dateStr) {
    if (!dateStr) return '未知日期'

    const date = new Date(dateStr)
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)

    if (date >= today) {
      return '今天'
    } else if (date >= yesterday) {
      return '昨天'
    } else if (date >= weekAgo) {
      return '本周'
    } else {
      return '更早'
    }
  }

  // 语言名称映射
  const languageNames = {
    zh: '中文',
    en: '英语',
    ja: '日语',
    ko: '韩语',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    ru: '俄语',
    unknown: '未识别'
  }

  // 分组后的邮件
  const groupedEmails = computed(() => {
    if (!groupBy.value || !emails.value || emails.value.length === 0) {
      return null
    }

    const groups = {}

    emails.value.forEach(email => {
      let key

      switch (groupBy.value) {
        case 'sender':
          key = email.from_email || '未知发件人'
          break
        case 'date':
          key = getDateGroup(email.received_at)
          break
        case 'language':
          key = languageNames[email.language_detected] || '未识别'
          break
        case 'label':
          // 按第一个标签分组，无标签的归入"未分类"
          if (email.labels && email.labels.length > 0) {
            key = email.labels[0].name
          } else {
            key = '未分类'
          }
          break
        default:
          key = '全部'
      }

      if (!groups[key]) {
        groups[key] = {
          name: key,
          emails: [],
          color: null
        }
        // 标签分组时保存颜色
        if (groupBy.value === 'label' && email.labels && email.labels.length > 0) {
          groups[key].color = email.labels[0].color
        }
      }

      groups[key].emails.push(email)
    })

    // 转换为数组并排序
    const result = Object.values(groups)

    // 按不同方式排序
    if (groupBy.value === 'date') {
      const order = ['今天', '昨天', '本周', '更早']
      result.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name))
    } else if (groupBy.value === 'sender') {
      result.sort((a, b) => b.emails.length - a.emails.length)
    } else {
      result.sort((a, b) => b.emails.length - a.emails.length)
    }

    return result
  })

  // 切换分组展开/收起
  function toggleGroup(groupName) {
    if (expandedGroups.value.has(groupName)) {
      expandedGroups.value.delete(groupName)
    } else {
      expandedGroups.value.add(groupName)
    }
  }

  // 展开全部
  function expandAll() {
    if (groupedEmails.value) {
      groupedEmails.value.forEach(g => expandedGroups.value.add(g.name))
    }
  }

  // 收起全部
  function collapseAll() {
    expandedGroups.value.clear()
  }

  // 是否分组模式
  const isGrouped = computed(() => !!groupBy.value)

  // 分组选项
  const groupOptions = [
    { value: null, label: '不分组' },
    { value: 'sender', label: '按发件人' },
    { value: 'date', label: '按日期' },
    { value: 'language', label: '按语言' },
    { value: 'label', label: '按标签' }
  ]

  return {
    groupBy,
    groupedEmails,
    expandedGroups,
    isGrouped,
    groupOptions,
    toggleGroup,
    expandAll,
    collapseAll
  }
}
