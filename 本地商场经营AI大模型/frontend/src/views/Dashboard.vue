<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import api from '@/api'
import { ElMessage } from 'element-plus'
import { formatLocalDate } from '@/utils/date'

const selectedDate = ref(new Date())
const summary = ref({})
const categories = ref([])
const trend = ref([])
const suggestions = ref([])
const adviceLoading = ref(false)
const adviceWarning = ref('')
const regenerating = ref(false)
const chartDom = ref(null)
const pieDom = ref(null)
const trendDom = ref(null)
const reportDom = ref(null)
const exportingPdf = ref(false)
const exportingExcel = ref(false)
let barChart = null
let pieChart = null
let trendChart = null

function renderBar() {
  if (!chartDom.value) return
  if (!barChart) barChart = echarts.init(chartDom.value)
  barChart.setOption({
    title: { text: '当日经营概览', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['销售额', '成本', '毛利'] },
    yAxis: { type: 'value' },
    series: [{
      data: [
        summary.value.total_sales || 0,
        summary.value.total_cost || 0,
        summary.value.total_profit || 0
      ],
      type: 'bar',
      itemStyle: {
        color: (params) => {
          const colors = ['#5470c6', '#91cc75', '#fac858']
          return colors[params.dataIndex]
        }
      }
    }]
  }, true)
}

function renderPie() {
  if (!pieDom.value) return
  if (!pieChart) pieChart = echarts.init(pieDom.value)
  pieChart.setOption({
    title: { text: '品类销售占比', left: 'center' },
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c}（{d}%）' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      data: categories.value.map((c) => ({ name: c.category, value: c.sales })),
      label: { formatter: '{b}\n{d}%' }
    }]
  }, true)
}

function renderTrend() {
  if (!trendDom.value) return
  if (!trendChart) trendChart = echarts.init(trendDom.value)
  trendChart.setOption({
    title: { text: '近30天销售趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['销售额', '毛利率'], bottom: 0 },
    grid: { top: 50, left: 70, right: 70, bottom: 70 },
    xAxis: { type: 'category', data: trend.value.map((t) => t.date.slice(5)) },
    yAxis: [
      { type: 'value', name: '销售额(元)' },
      { type: 'value', name: '毛利率(%)', axisLabel: { formatter: '{value}%' } }
    ],
    series: [
      {
        name: '销售额', type: 'bar', data: trend.value.map((t) => t.total_sales),
        itemStyle: { color: '#5470c6' }
      },
      {
        name: '毛利率', type: 'line', yAxisIndex: 1, smooth: true,
        data: trend.value.map((t) => t.margin), itemStyle: { color: '#91cc75' }
      }
    ]
  }, true)
}

function renderCharts() {
  renderBar()
  renderPie()
  renderTrend()
}

function clearCharts() {
  barChart?.clear()
  pieChart?.clear()
  trendChart?.clear()
}

// 汇总/品类/趋势并行加载，先画图；AI 建议单独异步加载，不阻塞图表
async function loadData() {
  const dateStr = formatLocalDate(selectedDate.value)
  const [sumRes, catRes, trendRes] = await Promise.allSettled([
    api.getDailySummary(dateStr),
    api.getCategories(dateStr),
    api.getTrend(30)
  ])
  summary.value = sumRes.status === 'fulfilled' ? sumRes.value : {}
  categories.value = catRes.status === 'fulfilled' ? catRes.value : []
  trend.value = trendRes.status === 'fulfilled' ? trendRes.value : []
  await nextTick()
  if (!summary.value.date) {
    clearCharts()
    suggestions.value = []
    adviceWarning.value = ''
    return
  }
  renderCharts()
  loadAdvice()
}

async function loadAdvice() {
  const dateStr = formatLocalDate(selectedDate.value)
  adviceLoading.value = true
  adviceWarning.value = ''
  try {
    const res = await api.getDailyAdvice(dateStr)
    suggestions.value = res.suggestions || []
    adviceWarning.value = res.warning || ''
  } catch (e) {
    suggestions.value = []
    adviceWarning.value = 'AI 建议加载失败：' + e.message
  } finally {
    adviceLoading.value = false
  }
}

async function regenerate() {
  const dateStr = formatLocalDate(selectedDate.value)
  regenerating.value = true
  try {
    const res = await api.regenerateAdvice(dateStr)
    suggestions.value = res.suggestions || []
    adviceWarning.value = res.warning || ''
    ElMessage.success('已重新生成')
  } catch (e) {
    adviceWarning.value = '重新生成失败：' + e.message
  } finally {
    regenerating.value = false
  }
}

function exportExcel() {
  if (!summary.value.date || exportingExcel.value) return
  exportingExcel.value = true
  try {
    const data = [
      ['日期', '总销售额', '总成本', '总毛利', '毛利率(%)', '记录数'],
      [
        summary.value.date,
        summary.value.total_sales,
        summary.value.total_cost,
        summary.value.total_profit,
        summary.value.margin,
        summary.value.record_count
      ]
    ]
    const ws = XLSX.utils.aoa_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '汇总')
    XLSX.writeFile(wb, `经营汇总_${summary.value.date}.xlsx`)
  } catch (e) {
    ElMessage.error('Excel 导出失败：' + e.message)
  } finally {
    exportingExcel.value = false
  }
}

async function exportPDF() {
  if (!reportDom.value || exportingPdf.value) return
  exportingPdf.value = true
  try {
    // 关掉 ECharts 入场动画，避免截到半截柱子
    ;[barChart, pieChart, trendChart].forEach((c) => c && c.setOption({ animation: false }))
    await nextTick()
    const canvas = await html2canvas(reportDom.value, {
      backgroundColor: '#ffffff',
      scale: 2,
      useCORS: true,
      scrollY: -window.scrollY
    })
    const imgData = canvas.toDataURL('image/png')
    // jsPDF 默认 a4 尺寸、mm 单位：页面 210x297，左右留 10mm，内容宽 190mm
    const pdf = new jsPDF()
    const imgWidth = 190
    const imgHeight = (canvas.height * imgWidth) / canvas.width
    const contentHeight = 277 // 297 - 上下各 10mm
    pdf.addImage(imgData, 'PNG', 10, 10, imgWidth, imgHeight)
    let remaining = imgHeight - contentHeight
    let offset = contentHeight
    while (remaining > 0) {
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 10, 10 - offset, imgWidth, imgHeight)
      offset += contentHeight
      remaining -= contentHeight
    }
    pdf.save(`经营报表_${summary.value.date || 'report'}.pdf`)
  } catch (e) {
    ElMessage.error('PDF 导出失败：' + e.message)
  } finally {
    exportingPdf.value = false
  }
}

onMounted(() => {
  loadData()
  window.addEventListener('resize', () => {
    barChart?.resize()
    pieChart?.resize()
    trendChart?.resize()
  })
})
</script>

<template>
  <div class="dashboard" ref="reportDom">
    <h2>经营仪表盘</h2>

    <div class="toolbar">
      <el-date-picker
        v-model="selectedDate"
        type="date"
        placeholder="选择日期"
        @change="loadData"
      />
      <el-button type="primary" @click="exportExcel" :loading="exportingExcel" :disabled="!summary.date">
        导出 Excel
      </el-button>
      <el-button type="success" @click="exportPDF" :loading="exportingPdf" :disabled="!summary.date">
        导出 PDF
      </el-button>
    </div>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="6">
        <el-card>
          <div class="stat-label">总销售额</div>
          <div class="stat-value">¥{{ summary.total_sales?.toFixed(2) || '0.00' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-label">总成本</div>
          <div class="stat-value">¥{{ summary.total_cost?.toFixed(2) || '0.00' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-label">总毛利</div>
          <div class="stat-value">¥{{ summary.total_profit?.toFixed(2) || '0.00' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-label">毛利率</div>
          <div class="stat-value">{{ summary.margin || '0.00' }}%</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <el-card>
          <div ref="chartDom" style="width: 100%; height: 350px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <div ref="pieDom" style="width: 100%; height: 350px"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px">
      <div ref="trendDom" style="width: 100%; height: 320px"></div>
    </el-card>

    <el-card style="margin-top: 20px">
      <template #header>
        <div class="advice-header">
          <span>AI 运营建议</span>
          <el-tag v-if="summary.date && adviceWarning" type="info" size="small">数据日期 {{ summary.date }}</el-tag>
          <el-button
            size="small"
            type="primary"
            plain
            :loading="regenerating"
            :disabled="!summary.date"
            @click="regenerate"
          >
            重新生成
          </el-button>
        </div>
      </template>
      <el-alert
        v-if="adviceWarning"
        :title="adviceWarning"
        type="warning"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-skeleton v-if="adviceLoading" :rows="5" animated />
      <el-timeline v-else-if="suggestions.length">
        <el-timeline-item
          v-for="(s, i) in suggestions"
          :key="i"
          :type="i === 0 ? 'primary' : 'info'"
        >
          <h4>{{ s.title }}</h4>
          <p><strong>问题/机会：</strong>{{ s.reason }}</p>
          <p><strong>执行措施：</strong>{{ s.action }}</p>
          <p><strong>预期效果：</strong>{{ s.effect }}</p>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else-if="summary.date" description="暂无 AI 建议" />
      <el-empty v-else description="该日期无数据" />
    </el-card>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 20px;
}
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
}
.stat-label {
  font-size: 14px;
  color: #666;
}
.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin-top: 8px;
}
.advice-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.advice-header span:first-child {
  font-weight: bold;
}
</style>
