<script setup>
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '@/api'

const msg = ref('')
const msgType = ref('success')
const uploading = ref(false)
const errorDialogVisible = ref(false)
const errorRows = ref([])

// el-upload 使用自定义请求
const handleUpload = async (options) => {
  uploading.value = true
  msg.value = ''
  try {
    const res = await api.uploadSalesFile(options.file)
    if (res.failed > 0) {
      msgType.value = 'warning'
      msg.value = `导入完成：成功 ${res.success} 条，失败 ${res.failed} 条（共 ${res.total} 条）`
      errorRows.value = res.errors || []
      errorDialogVisible.value = errorRows.value.length > 0
    } else {
      msgType.value = 'success'
      msg.value = `导入成功：共 ${res.total} 条`
    }
    options.onSuccess(res)
  } catch (e) {
    msgType.value = 'error'
    msg.value = '上传失败: ' + e.message
    options.onError(e)
  } finally {
    uploading.value = false
  }
}

// 失败明细导出 CSV（带 BOM，Excel 打开中文不乱码）
function exportErrors() {
  const lines = ['行号,失败原因']
  for (const e of errorRows.value) {
    lines.push(`${e.row},"${String(e.reason).replace(/"/g, '""')}"`)
  }
  const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = '导入失败明细.csv'
  a.click()
  URL.revokeObjectURL(a.href)
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
    <el-alert
      v-if="msg"
      :title="msg"
      :type="msgType"
      style="margin-top:20px"
      closable
      @close="msg=''"
    />

    <el-dialog v-model="errorDialogVisible" title="导入失败明细" width="560px">
      <el-table :data="errorRows" size="small" max-height="360">
        <el-table-column prop="row" label="行号" width="80" />
        <el-table-column prop="reason" label="失败原因" />
      </el-table>
      <template #footer>
        <el-button @click="exportErrors">导出失败行 CSV</el-button>
        <el-button type="primary" @click="errorDialogVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>
