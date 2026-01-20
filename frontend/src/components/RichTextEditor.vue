<template>
  <div class="rich-text-editor">
    <!-- 工具栏 -->
    <Toolbar
      class="editor-toolbar"
      :editor="editorRef"
      :defaultConfig="toolbarConfig"
      mode="default"
    />
    <!-- 编辑器 -->
    <Editor
      class="editor-content"
      :style="{ height: height }"
      v-model="valueHtml"
      :defaultConfig="editorConfig"
      mode="default"
      @onCreated="handleCreated"
      @onChange="handleChange"
    />
  </div>
</template>

<script setup>
import '@wangeditor/editor/dist/css/style.css'
import { ref, shallowRef, computed, onBeforeUnmount, watch } from 'vue'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  height: {
    type: String,
    default: '200px'
  },
  placeholder: {
    type: String,
    default: '请输入内容...'
  },
  // 是否禁用
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

// 编辑器实例
const editorRef = shallowRef()

// HTML 内容（双向绑定）
const valueHtml = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 工具栏配置（完整功能版）
const toolbarConfig = {
  toolbarKeys: [
    // 撤销/重做
    'undo', 'redo',
    '|',
    // 标题
    'headerSelect',
    '|',
    // 基础格式
    'bold', 'italic', 'underline', 'through',
    '|',
    // 颜色
    'color', 'bgColor',
    '|',
    // 对齐
    'justifyLeft', 'justifyCenter', 'justifyRight',
    '|',
    // 列表
    'bulletedList', 'numberedList', 'todo',
    '|',
    // 插入
    'insertLink', 'insertTable',
    '|',
    // 缩进
    'indent', 'delIndent',
    '|',
    // 清除格式
    'clearStyle'
  ],
  // 排除不需要的菜单
  excludeKeys: [
    'uploadImage',  // 暂不支持图片上传
    'uploadVideo',  // 暂不支持视频上传
    'codeBlock',    // 代码块在邮件中不常用
    'blockquote',   // 引用块
    'emotion',      // 表情
    'fullScreen'    // 全屏
  ]
}

// 编辑器配置
const editorConfig = computed(() => ({
  placeholder: props.placeholder,
  readOnly: props.disabled,
  // 自动聚焦
  autoFocus: false,
  // 滚动条
  scroll: true,
  // 最大长度限制（可选）
  maxLength: 50000,
  // 粘贴配置
  MENU_CONF: {
    // 插入链接配置
    insertLink: {
      checkLink: (text, url) => {
        if (!url) return '请输入链接地址'
        if (!url.startsWith('http://') && !url.startsWith('https://') && !url.startsWith('mailto:')) {
          return '链接格式不正确，请以 http:// 或 https:// 开头'
        }
        return true
      }
    },
    // 表格配置
    insertTable: {
      // 默认 3 行 3 列
      defaultRowCount: 3,
      defaultColCount: 3
    }
  }
}))

// 编辑器创建完成
function handleCreated(editor) {
  editorRef.value = editor

  // 如果禁用，设置只读
  if (props.disabled) {
    editor.disable()
  }
}

// 内容变化
function handleChange(editor) {
  emit('change', editor.getHtml())
}

// 监听禁用状态变化
watch(() => props.disabled, (val) => {
  if (editorRef.value) {
    if (val) {
      editorRef.value.disable()
    } else {
      editorRef.value.enable()
    }
  }
})

// 组件销毁前，销毁编辑器实例
onBeforeUnmount(() => {
  const editor = editorRef.value
  if (editor) {
    editor.destroy()
  }
})

// 暴露方法给父组件
defineExpose({
  // 获取纯文本内容（用于翻译）
  getText: () => {
    if (editorRef.value) {
      return editorRef.value.getText()
    }
    return ''
  },
  // 获取 HTML 内容
  getHtml: () => {
    if (editorRef.value) {
      return editorRef.value.getHtml()
    }
    return ''
  },
  // 设置内容
  setHtml: (html) => {
    if (editorRef.value) {
      editorRef.value.setHtml(html)
    }
  },
  // 清空内容
  clear: () => {
    if (editorRef.value) {
      editorRef.value.clear()
    }
  },
  // 聚焦
  focus: () => {
    if (editorRef.value) {
      editorRef.value.focus()
    }
  },
  // 获取编辑器实例
  getEditor: () => editorRef.value
})
</script>

<style scoped>
.rich-text-editor {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.rich-text-editor:focus-within {
  border-color: #409eff;
}

.editor-toolbar {
  border-bottom: 1px solid #e8e8e8;
  background-color: #fafafa;
}

/* 工具栏样式调整 */
.editor-toolbar :deep(.w-e-toolbar) {
  padding: 4px 8px;
  flex-wrap: wrap;
}

.editor-toolbar :deep(.w-e-bar-item) {
  padding: 2px;
}

.editor-toolbar :deep(.w-e-bar-item button) {
  padding: 4px 8px;
  font-size: 14px;
}

/* 编辑器内容区域 */
.editor-content {
  overflow-y: auto;
}

.editor-content :deep(.w-e-text-container) {
  background-color: #fff;
}

.editor-content :deep(.w-e-text-placeholder) {
  color: #c0c4cc;
  font-style: normal;
}

/* 编辑器内容样式 */
.editor-content :deep(p) {
  margin: 0.5em 0;
  line-height: 1.6;
}

.editor-content :deep(ul),
.editor-content :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}

.editor-content :deep(li) {
  line-height: 1.6;
}

.editor-content :deep(a) {
  color: #409eff;
  text-decoration: underline;
}

.editor-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5em 0;
}

.editor-content :deep(table td),
.editor-content :deep(table th) {
  border: 1px solid #dcdfe6;
  padding: 8px 12px;
  min-width: 60px;
}

.editor-content :deep(table th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

/* 禁用状态样式 */
.rich-text-editor.disabled {
  background-color: #f5f7fa;
  cursor: not-allowed;
}

.rich-text-editor.disabled .editor-toolbar {
  opacity: 0.6;
  pointer-events: none;
}

.rich-text-editor.disabled .editor-content {
  background-color: #f5f7fa;
}
</style>
