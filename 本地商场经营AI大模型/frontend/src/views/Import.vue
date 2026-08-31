<script setup>
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '@/api'

const msg = ref('')
const uploading = ref(false)

// el-upload 使用自定义请求
const handleUpload = async (options) => {
  uploading.value = true
  try {
    const res = await api.uploadSalesFile(options.file)
    msg.value = res.message
    options.onSuccess(res)
  } catch (e) {
    msg.value = '上传失败: ' + e.message
    options.onError(e)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div>
    <el-upload
      drag
      :http-request="handleUpload"
      accept=".xlsx,.csv"
    >
      <el-icon><upload-filled /></el-icon>
      <div>拖拽或点击上传 Excel/CSV</div>
    </el-upload>
    <el-alert v-if="msg" :title="msg" type="success" style="margin-top:20px" closable @close="msg=''" />
  </div>
</template>