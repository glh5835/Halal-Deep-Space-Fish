import axios from 'axios'

// 配置基础路径，开发环境代理到后端8000端口
const apiClient = axios.create({
  baseURL: '/api',          // 生产环境 nginx 反向代理，开发环境 vite proxy
  timeout: 60000,           // AI建议生成可能较慢，适当延长
})

// 响应拦截器：统一处理错误
apiClient.interceptors.response.use(
  response => response.data,
  error => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('API Error:', message)
    return Promise.reject(new Error(message))
  }
)

export default {
  // 上传销售数据文件（mode: overwrite=覆盖当日 / append=追加去重；mapping 可手动指定列映射）
  uploadSalesFile(file, mode = 'overwrite', mapping = null) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode)
    if (mapping) formData.append('mapping', JSON.stringify(mapping))
    return apiClient.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 解析预览（不入库）：返回列映射识别结果、样例行、预计成功/失败行数
  uploadPreview(file) {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/upload/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 下载标准导入模板 xlsx
  templateUrl() {
    return '/api/template'
  },

  // 获取某日销售汇总
  getDailySummary(date) {
    return apiClient.get(`/summary/${date}`)
  },

  // 获取某日品类销售占比
  getCategories(date) {
    return apiClient.get(`/categories/${date}`)
  },

  // 获取近 N 天销售趋势
  getTrend(days = 30) {
    return apiClient.get(`/trend?days=${days}`)
  },

  // 获取某日AI运营建议（带缓存，命中时秒回）
  getDailyAdvice(date) {
    return apiClient.get(`/advice/${date}`)
  },

  // 强制重新生成某日AI建议
  regenerateAdvice(date) {
    return apiClient.post(`/advice/${date}/regenerate`)
  },

  // 获取所有有数据的日期列表
  getAvailableDates() {
    return apiClient.get('/dates')
  },

  // 最近导入批次记录
  getBatches() {
    return apiClient.get('/batches')
  },

  // 撤销某次导入批次
  deleteBatch(id) {
    return apiClient.delete(`/batches/${id}`)
  }
}
