<template>
  <div class="compose-email">
    <!-- 收件人区域 -->
    <div class="compose-field">
      <label>收件人：</label>
      <el-input v-model="form.to" placeholder="请输入收件人邮箱地址" />
    </div>

    <div class="compose-field">
      <label>抄送：</label>
      <el-input v-model="form.cc" placeholder="请输入抄送邮箱地址（可选）" />
    </div>

    <div class="compose-field">
      <label>主题：</label>
      <el-input v-model="form.subject" placeholder="请输入邮件主题" />
    </div>

    <!-- 正文编辑区 -->
    <div class="compose-body">
      <div class="body-section">
        <div class="section-header">
          <span>邮件内容</span>
          <el-select v-model="form.targetLanguage" size="small" style="width: 120px;" placeholder="翻译目标语言">
            <el-option label="英语" value="en" />
            <el-option label="日语" value="ja" />
            <el-option label="韩语" value="ko" />
            <el-option label="德语" value="de" />
            <el-option label="法语" value="fr" />
          </el-select>
        </div>
        <el-input
          v-model="form.bodyChinese"
          type="textarea"
          :rows="10"
          placeholder="输入邮件内容（可直接发送，或点击翻译后发送译文）"
        />
      </div>

      <div class="body-section">
        <div class="section-header">
          <span>翻译预览 ({{ getLanguageName(form.targetLanguage) }})</span>
          <el-button size="small" type="primary" @click="translateContent" :loading="translating">
            翻译
          </el-button>
        </div>
        <el-input
          v-model="form.bodyTranslated"
          type="textarea"
          :rows="10"
          placeholder="点击翻译按钮生成译文，或直接在此编辑..."
        />
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="compose-actions">
      <span class="send-hint" v-if="!form.bodyTranslated.trim() && form.bodyChinese.trim()">
        将发送左侧内容
      </span>
      <el-button @click="$emit('cancel')">取消</el-button>
      <el-button @click="saveDraft">保存草稿</el-button>
      <el-button type="primary" @click="sendEmail" :loading="sending" :disabled="!canSend">
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

// 接收原邮件语言，用于设置默认目标语言
const props = defineProps({
  replyTo: { type: Object, default: null },  // 回复的原邮件
  defaultLanguage: { type: String, default: '' }  // 默认目标语言
})

const emit = defineEmits(['sent', 'cancel'])

const translating = ref(false)
const sending = ref(false)

const form = reactive({
  to: '',
  cc: '',
  subject: '',
  bodyChinese: '',
  bodyTranslated: '',
  targetLanguage: 'en'
})

// 初始化时设置默认语言
onMounted(() => {
  if (props.defaultLanguage) {
    form.targetLanguage = props.defaultLanguage
  } else if (props.replyTo?.detected_language) {
    // 根据原邮件语言设置目标语言
    const lang = props.replyTo.detected_language.toLowerCase()
    if (['en', 'ja', 'ko', 'de', 'fr'].includes(lang)) {
      form.targetLanguage = lang
    }
  }
  // 如果是回复，设置收件人和主题
  if (props.replyTo) {
    form.to = props.replyTo.from_email || ''
    form.subject = props.replyTo.subject?.startsWith('Re:')
      ? props.replyTo.subject
      : `Re: ${props.replyTo.subject || ''}`
  }
})

// 发送条件：左边或右边有内容即可
const canSend = computed(() => {
  const hasContent = form.bodyChinese.trim() || form.bodyTranslated.trim()
  return form.to.trim() && form.subject.trim() && hasContent
})

function getLanguageName(lang) {
  const names = {
    en: '英语',
    ja: '日语',
    ko: '韩语',
    de: '德语',
    fr: '法语',
    es: '西班牙语',
    pt: '葡萄牙语',
    ru: '俄语'
  }
  return names[lang] || lang
}

async function translateContent() {
  if (!form.bodyChinese.trim()) {
    ElMessage.warning('请先输入中文内容')
    return
  }

  translating.value = true
  try {
    const result = await api.translateReply(
      form.bodyChinese,
      form.targetLanguage,
      null,
      null
    )
    form.bodyTranslated = result.translated_text
    ElMessage.success('翻译完成')
  } catch (e) {
    console.error('Translation failed:', e)
    ElMessage.error('翻译失败')
  } finally {
    translating.value = false
  }
}

async function saveDraft() {
  if (!form.bodyChinese.trim()) {
    ElMessage.warning('请输入邮件内容')
    return
  }

  try {
    await api.createDraft({
      body_chinese: form.bodyChinese,
      body_translated: form.bodyTranslated,
      target_language: form.targetLanguage
    })
    ElMessage.success('草稿已保存')
  } catch (e) {
    console.error('Failed to save draft:', e)
    ElMessage.error('保存草稿失败')
  }
}

async function sendEmail() {
  if (!canSend.value) {
    ElMessage.warning('请填写完整的邮件信息')
    return
  }

  // 优先发送右边翻译内容，没有则发送左边原始内容
  const bodyToSend = form.bodyTranslated.trim() || form.bodyChinese.trim()

  sending.value = true
  try {
    await api.sendEmail({
      to: form.to,
      cc: form.cc,
      subject: form.subject,
      body: bodyToSend
    })
    emit('sent')
  } catch (e) {
    console.error('Failed to send email:', e)
    ElMessage.error('发送失败')
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.compose-email {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compose-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compose-field label {
  width: 60px;
  flex-shrink: 0;
  color: #606266;
  font-size: 14px;
}

.compose-field .el-input {
  flex: 1;
}

.compose-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.body-section {
  display: flex;
  flex-direction: column;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  color: #606266;
}

.compose-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #e0e0e0;
}

.send-hint {
  margin-right: auto;
  font-size: 12px;
  color: #909399;
}
</style>
