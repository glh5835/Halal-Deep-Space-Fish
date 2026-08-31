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
  // 上传销售数据文件
  uploadSalesFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 获取某日销售汇总
  getDailySummary(date) {
    return apiClient.get(`/summary/${date}`)
  },

  // 获取某日AI运营建议
  getDailyAdvice(date) {
    return apiClient.get(`/advice/${date}`)
  },

  // 获取所有有数据的日期列表（可选）
  getAvailableDates() {
    return apiClient.get('/dates')
  }
}