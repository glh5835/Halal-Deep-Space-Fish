<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '@/api'

const msg = ref('')
const msgType = ref('success')
const uploading = ref(false)
const mode = ref('overwrite') // overwrite=覆盖当日 / append=追加去重
const errorDialogVisible = ref(false)
const errorRows = ref([])

// 预览确认：先解析再入库
const previewVisible = ref(false)
const previewLoading = ref(false)
const preview = ref(null)
const mappingOverrides = ref({})
const pendingFile = ref(null)

// 最近导入记录
const batches = ref([])

const TARGET_LABELS = {
  date: '日期',
  product_name: '商品名称',
  category: '品类',
  unit_price: '售价',
  cost_price: '成本价',
  quantity: '数量',
}

// el-upload 使用自定义请求：先预览，确认后才真正入库
const handleUpload = async (options) => {
  pendingFile.value = options.file
  preview.value = null
  previewVisible.value = true
  previewLoading.value = true
  try {
    const res = await api.uploadPreview(options.file)
    preview.value = res
    mappingOverrides.value = { ...res.detected_mapping }
    if (res.missing_columns.length) {
      ElMessage.warning('有必需列未能自动识别，请在预览中手动指定')
    }
  } catch (e) {
    previewVisible.value = false
    msgType.value = 'error'
    msg.value = '文件解析失败: ' + e.message
  } finally {
    previewLoading.value = false
  }
}

const confirmUpload = async () => {
  if (!pendingFile.value) return
  const unselected = Object.keys(TARGET_LABELS).filter((t) => !mappingOverrides.value[t])
  if (unselected.length) {
    ElMessage.warning('请先为所有必需列指定对应的源列：' + unselected.map((t) => TARGET_LABELS[t]).join('、'))
    return
  }
  previewVisible.value = false
  uploading.value = true
  msg.value = ''
  try {
    const res = await api.uploadSalesFile(pendingFile.value, mode.value, mappingOverrides.value)
    if (res.failed > 0) {
      msgType.value = 'warning'
      msg.value = `导入完成：成功 ${res.success} 条，失败 ${res.failed} 条（共 ${res.total} 条）`
      errorRows.value = res.errors || []
      errorDialogVisible.value = errorRows.value.length > 0
    } else if (res.skipped > 0) {
      msgType.value = 'warning'
      msg.value = `导入完成：新增 ${res.success} 条，跳过重复 ${res.skipped} 条（共 ${res.total} 条）`
    } else {
      msgType.value = 'success'
      msg.value = `导入成功：共 ${res.total} 条`
    }
    loadBatches()
  } catch (e) {
    msgType.value = 'error'
    msg.value = '上传失败: ' + e.message
  } finally {
    uploading.value = false
    pendingFile.value = null
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

async function loadBatches() {
  try {
    batches.value = await api.getBatches()
  } catch (e) {
    console.error(e)
  }
}

async function undoBatch(row) {
  try {
    await ElMessageBox.confirm(
      `确认撤销批次 #${row.id}（${row.filename}，${row.row_count} 条记录）？被覆盖前的数据无法恢复，该操作不可撤销回去。`,
      '撤销导入',
      { type: 'warning', confirmButtonText: '确认撤销', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    const res = await api.deleteBatch(row.id)
    ElMessage.success(`已撤销批次 #${row.id}，删除 ${res.deleted_rows} 条记录`)
    loadBatches()
  } catch (e) {
    ElMessage.error('撤销失败：' + e.message)
  }
}

onMounted(loadBatches)
</script>

<template>
  <div>
    <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 16px">
      <span>导入模式：</span>
      <el-radio-group v-model="mode">
        <el-radio value="overwrite">覆盖当日（同日数据以本次为准）</el-radio>
        <el-radio value="append">追加去重（按 日期+商品+单价 跳过重复）</el-radio>
      </el-radio-group>
      <a :href="api.templateUrl()" style="margin-left: auto">
        <el-button size="small">下载标准模板</el-button>
      </a>
    </div>

    <el-upload
      drag
      :http-request="handleUpload"
      accept=".xlsx,.csv"
    >
      <el-icon><upload-filled /></el-icon>
      <div>拖拽或点击上传 Excel/CSV（上传后先预览确认）</div>
    </el-upload>
    <el-alert
      v-if="msg"
      :title="msg"
      :type="msgType"
      style="margin-top:20px"
      closable
      @close="msg=''"
    />

    <el-dialog v-model="previewVisible" title="导入预览（确认后才会写入数据库）" width="720px">
      <el-skeleton v-if="previewLoading" :rows="6" animated />
      <template v-else-if="preview">
        <el-alert
          v-if="preview.missing_columns.length"
          :title="`有必需列未能自动识别：${preview.missing_columns.map(t => TARGET_LABELS[t]).join('、')}，请在下方手动指定`"
          type="warning"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <h4>列映射（可手动修正）</h4>
        <el-row :gutter="12">
          <el-col
            v-for="(label, tgt) in TARGET_LABELS"
            :key="tgt"
            :span="8"
            style="margin-bottom: 8px"
          >
            {{ label }} →
            <el-select
              v-model="mappingOverrides[tgt]"
              placeholder="选择源列"
              size="small"
              clearable
              style="width: 150px"
            >
              <el-option v-for="col in preview.columns" :key="col" :label="col" :value="col" />
            </el-select>
          </el-col>
        </el-row>

        <h4>前 5 行样例</h4>
        <el-table :data="preview.sample_rows" size="small" max-height="220">
          <el-table-column
            v-for="(label, tgt) in TARGET_LABELS"
            :key="tgt"
            :prop="tgt"
            :label="label"
            min-width="90"
          />
        </el-table>

        <p style="margin-top: 10px">
          共 <strong>{{ preview.estimated_total }}</strong> 行数据，预计可导入
          <strong>{{ preview.estimated_valid }}</strong> 行，失败
          <strong>{{ preview.estimated_total - preview.estimated_valid }}</strong> 行
        </p>
      </template>
      <template #footer>
        <el-button @click="previewVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="confirmUpload">确认导入</el-button>
      </template>
    </el-dialog>

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

    <el-card style="margin-top: 20px">
      <template #header>
        <span>最近导入记录</span>
      </template>
      <el-empty v-if="!batches.length" description="暂无导入记录" :image-size="60" />
      <el-table v-else :data="batches" size="small">
        <el-table-column prop="id" label="批次" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="160" />
        <el-table-column label="模式" width="90">
          <template #default="{ row }">{{ row.mode === 'overwrite' ? '覆盖' : '追加' }}</template>
        </el-table-column>
        <el-table-column prop="row_count" label="行数" width="80" />
        <el-table-column label="日期范围" min-width="175">
          <template #default="{ row }">{{ row.date_from || '-' }} ~ {{ row.date_to || '-' }}</template>
        </el-table-column>
        <el-table-column prop="imported_at" label="导入时间" min-width="160" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="undoBatch(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
