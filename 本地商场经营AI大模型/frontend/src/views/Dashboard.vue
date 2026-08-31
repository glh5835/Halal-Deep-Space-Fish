<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import api from '@/api'

const selectedDate = ref(new Date())
const summary = ref({})
const suggestions = ref([])
const chartDom = ref(null)
let chartInstance = null

async function loadData() {
  const dateStr = selectedDate.value.toISOString().slice(0, 10)
  try {
    summary.value = await api.getDailySummary(dateStr)
    const res = await api.getDailyAdvice(dateStr)
    suggestions.value = res.suggestions || []
    await nextTick()
    initChart()
  } catch (e) {
    console.error(e)
    summary.value = {}
    suggestions.value = []
    if (chartInstance) {
      chartInstance.clear()
    }
  }
}

function initChart() {
  if (!chartDom.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartDom.value)
  }
  const option = {
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
  }
  chartInstance.setOption(option, true)
}

function exportExcel() {
  if (!summary.value.date) return
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
}

async function exportPDF() {
  if (!chartDom.value) return
  const canvas = await html2canvas(chartDom.value)
  const imgData = canvas.toDataURL('image/png')
  const pdf = new jsPDF()
  pdf.addImage(imgData, 'PNG', 10, 10, 190, 100)
  pdf.text(`日期: ${summary.value.date || ''}`, 10, 120)
  pdf.text(`销售额: ${summary.value.total_sales || 0} 元`, 10, 130)
  pdf.text(`毛利: ${summary.value.total_profit || 0} 元`, 10, 140)
  pdf.text(`毛利率: ${summary.value.margin || 0}%`, 10, 150)
  pdf.save(`经营报表_${summary.value.date || 'report'}.pdf`)
}

onMounted(() => {
  loadData()
  window.addEventListener('resize', () => chartInstance?.resize())
})
</script>

<template>
  <div class="dashboard">
    <h2>经营仪表盘</h2>

    <div class="toolbar">
      <el-date-picker
        v-model="selectedDate"
        type="date"
        placeholder="选择日期"
        @change="loadData"
      />
      <el-button type="primary" @click="exportExcel" :disabled="!summary.date">
        导出 Excel
      </el-button>
      <el-button type="success" @click="exportPDF" :disabled="!summary.date">
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

    <el-card style="margin-top: 20px">
      <div ref="chartDom" style="width: 100%; height: 350px"></div>
    </el-card>

    <el-card v-if="suggestions.length" style="margin-top: 20px">
      <template #header>
        <span>AI 运营建议</span>
      </template>
      <el-timeline>
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
    </el-card>

    <el-empty v-else-if="summary.date" description="该日期暂无 AI 建议" style="margin-top: 20px" />
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
</style>