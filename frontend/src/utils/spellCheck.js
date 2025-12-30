/**
 * 拼写检查工具
 *
 * 功能：
 * 1. 浏览器原生拼写检查（通过 spellcheck 属性）
 * 2. AI 语法和拼写检查（调用后端 vLLM API）
 */

import api from '@/api'

/**
 * 拼写检查配置
 */
export const SPELL_CHECK_CONFIG = {
  // 启用浏览器原生拼写检查
  enableNative: true,
  // 支持的语言
  languages: ['zh-CN', 'en-US', 'ja', 'ko'],
  // AI 检查的最小文本长度
  minTextLength: 10,
  // AI 检查的最大文本长度
  maxTextLength: 5000
}

/**
 * 检查结果类型
 */
export const CheckType = {
  SPELLING: 'spelling',     // 拼写错误
  GRAMMAR: 'grammar',       // 语法错误
  STYLE: 'style',           // 风格建议
  PUNCTUATION: 'punctuation' // 标点问题
}

/**
 * 启用元素的浏览器原生拼写检查
 * @param {HTMLElement} element - 要启用拼写检查的元素
 * @param {string} lang - 语言代码（默认 'zh-CN'）
 */
export function enableNativeSpellCheck(element, lang = 'zh-CN') {
  if (!element) return

  element.setAttribute('spellcheck', 'true')
  element.setAttribute('lang', lang)

  // 对于 contenteditable 元素
  if (element.contentEditable !== undefined) {
    element.contentEditable = 'true'
  }
}

/**
 * 禁用元素的浏览器原生拼写检查
 * @param {HTMLElement} element - 要禁用拼写检查的元素
 */
export function disableNativeSpellCheck(element) {
  if (!element) return
  element.setAttribute('spellcheck', 'false')
}

/**
 * AI 语法检查结果
 * @typedef {Object} GrammarCheckResult
 * @property {boolean} success - 检查是否成功
 * @property {Array<{type: string, text: string, suggestion: string, position: number}>} issues - 发现的问题
 * @property {string} correctedText - 修正后的文本
 * @property {string} error - 错误信息（如果失败）
 */

/**
 * 使用 AI 进行语法和拼写检查
 * @param {string} text - 要检查的文本
 * @param {string} language - 文本语言
 * @returns {Promise<GrammarCheckResult>}
 */
export async function checkGrammar(text, language = 'zh') {
  if (!text || text.length < SPELL_CHECK_CONFIG.minTextLength) {
    return {
      success: true,
      issues: [],
      correctedText: text,
      message: '文本太短，无需检查'
    }
  }

  if (text.length > SPELL_CHECK_CONFIG.maxTextLength) {
    return {
      success: false,
      issues: [],
      correctedText: text,
      error: `文本过长（最大 ${SPELL_CHECK_CONFIG.maxTextLength} 字符）`
    }
  }

  try {
    const response = await api.checkGrammar(text, language)
    return response.data
  } catch (error) {
    console.error('Grammar check failed:', error)
    return {
      success: false,
      issues: [],
      correctedText: text,
      error: error.message || '语法检查失败'
    }
  }
}

/**
 * 高亮显示问题文本
 * @param {string} text - 原始文本
 * @param {Array} issues - 问题列表
 * @returns {string} - 带有高亮标记的 HTML
 */
export function highlightIssues(text, issues) {
  if (!issues || issues.length === 0) {
    return text
  }

  // 按位置排序（从后向前处理避免位置偏移）
  const sortedIssues = [...issues].sort((a, b) => b.position - a.position)

  let result = text
  for (const issue of sortedIssues) {
    const { position, text: errorText, type } = issue
    if (position >= 0 && errorText) {
      const before = result.substring(0, position)
      const after = result.substring(position + errorText.length)
      const className = `spell-error spell-error-${type}`
      result = `${before}<span class="${className}" title="${issue.suggestion}">${errorText}</span>${after}`
    }
  }

  return result
}

/**
 * 获取问题类型的中文描述
 * @param {string} type - 问题类型
 * @returns {string} - 中文描述
 */
export function getIssueTypeLabel(type) {
  const labels = {
    [CheckType.SPELLING]: '拼写错误',
    [CheckType.GRAMMAR]: '语法错误',
    [CheckType.STYLE]: '风格建议',
    [CheckType.PUNCTUATION]: '标点问题'
  }
  return labels[type] || '未知问题'
}

/**
 * 获取问题类型的颜色
 * @param {string} type - 问题类型
 * @returns {string} - 颜色代码
 */
export function getIssueTypeColor(type) {
  const colors = {
    [CheckType.SPELLING]: '#F56C6C',   // 红色
    [CheckType.GRAMMAR]: '#E6A23C',    // 橙色
    [CheckType.STYLE]: '#409EFF',      // 蓝色
    [CheckType.PUNCTUATION]: '#909399' // 灰色
  }
  return colors[type] || '#909399'
}

/**
 * 创建拼写检查插件（用于富文本编辑器）
 * @param {Object} options - 配置选项
 * @returns {Object} - 插件对象
 */
export function createSpellCheckPlugin(options = {}) {
  const config = { ...SPELL_CHECK_CONFIG, ...options }

  return {
    name: 'spellCheck',

    // 初始化
    init(editor) {
      if (config.enableNative && editor.element) {
        enableNativeSpellCheck(editor.element, config.languages[0])
      }
    },

    // 手动检查
    async check(text, language) {
      return await checkGrammar(text, language)
    },

    // 销毁
    destroy(editor) {
      if (editor.element) {
        disableNativeSpellCheck(editor.element)
      }
    }
  }
}

/**
 * Vue 组合式 API - 拼写检查
 * @param {Ref<string>} textRef - 文本引用
 * @returns {Object} - 拼写检查状态和方法
 */
export function useSpellCheck(textRef) {
  const { ref, watch } = require('vue')

  const issues = ref([])
  const isChecking = ref(false)
  const lastCheckResult = ref(null)

  const check = async (language = 'zh') => {
    if (!textRef.value) return

    isChecking.value = true
    try {
      const result = await checkGrammar(textRef.value, language)
      lastCheckResult.value = result
      issues.value = result.issues || []
    } finally {
      isChecking.value = false
    }
  }

  const clearIssues = () => {
    issues.value = []
    lastCheckResult.value = null
  }

  const applySuggestion = (issue) => {
    if (!textRef.value || !issue.suggestion) return

    const { position, text } = issue
    const before = textRef.value.substring(0, position)
    const after = textRef.value.substring(position + text.length)
    textRef.value = before + issue.suggestion + after

    // 从列表中移除已应用的建议
    issues.value = issues.value.filter(i => i !== issue)
  }

  return {
    issues,
    isChecking,
    lastCheckResult,
    check,
    clearIssues,
    applySuggestion,
    getIssueTypeLabel,
    getIssueTypeColor
  }
}

export default {
  SPELL_CHECK_CONFIG,
  CheckType,
  enableNativeSpellCheck,
  disableNativeSpellCheck,
  checkGrammar,
  highlightIssues,
  getIssueTypeLabel,
  getIssueTypeColor,
  createSpellCheckPlugin,
  useSpellCheck
}
