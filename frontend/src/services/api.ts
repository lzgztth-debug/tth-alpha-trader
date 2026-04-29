import axios from 'axios'
import { message } from 'antd'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 响应拦截器：解包 ApiResponse 格式 { success, message, data }
api.interceptors.response.use(
  (response) => {
    const res = response.data
    // 如果后端返回标准 ApiResponse 格式，解包返回 data.data
    if (res && typeof res === 'object' && 'success' in res) {
      if (res.success) {
        response.data = res.data
      } else {
        message.error(res.message || '请求失败')
        return Promise.reject(new Error(res.message || '请求失败'))
      }
    }
    return response
  },
  (error) => {
    const msg = error.response?.data?.message || error.message || '网络错误'
    message.error(msg)
    return Promise.reject(error)
  }
)

// Account APIs
export const getAccounts = () => api.get('/account/account')
export const getPositions = () => api.get('/account/positions')
export const getPortfolioSummary = () => api.get('/account/portfolio/summary')

// Order APIs
export const getOrders = (params?: { status?: string }) => api.get('/orders/orders', { params })
export const createOrder = (data: any) => api.post('/orders/orders', data)
export const cancelOrder = (orderId: string) => api.delete(`/orders/orders/${orderId}`)

// AI APIs - 单模型
export const triggerAIDecision = (data: any) => api.post('/ai/decide', data)
export const listProviders = () => api.get('/ai/providers')
export const listPrompts = () => api.get('/ai/prompts')

// AI APIs - 多模型投票
export const triggerMultiAIDecision = (data: {
  symbols?: string[]
  models: string[]
  voting_strategy: 'majority' | 'confidence' | 'unanimous'
  mode?: string
  force_decide?: boolean
}) => api.post('/ai/decide/multi', data)

// AI APIs - SSE 流式决策
export const streamAIDecision = (data: {
  symbols?: string[]
  models: string[]
  voting_strategy: 'majority' | 'confidence' | 'unanimous'
  mode?: string
  force_decide?: boolean
}): EventSource => {
  const params = new URLSearchParams()
  if (data.symbols) params.set('symbols', data.symbols.join(','))
  params.set('models', data.models.join(','))
  params.set('voting_strategy', data.voting_strategy)
  if (data.mode) params.set('mode', data.mode)
  if (data.force_decide !== undefined) params.set('force_decide', String(data.force_decide))
  return new EventSource(`/api/v1/ai/decide/stream?${params.toString()}`)
}

// AI APIs - 模型和供应商
export const getAIModels = () => api.get('/ai/models')
export const getAIProviders = () => api.get('/ai/providers')

// Log APIs
export const getAIDecisions = (params?: { limit?: number; offset?: number; symbol?: string }) =>
  api.get('/logs/ai-decisions', { params })
export const getAIDecisionDetail = (id: number) => api.get(`/logs/ai-decisions/${id}`)
export const getTrades = (params?: { limit?: number; offset?: number; symbol?: string }) =>
  api.get('/logs/trades', { params })

// Config APIs
export const getPrompts = () => api.get('/config/prompts')
export const createPrompt = (data: any) => api.post('/config/prompts', data)
export const activatePrompt = (version: string) => api.put(`/config/prompts/${version}/activate`)
export const getRiskRules = () => api.get('/config/risk/rules')
export const updateRiskRules = (data: any) => api.put('/config/risk/rules', data)
export const getTradingMode = () => api.get('/config/trading/mode')
export const setTradingMode = (data: any) => api.post('/config/trading/mode', data)
export const getSettings = () => api.get('/config/settings')

// Cost APIs
export const getCostSummary = () => api.get('/config/cost/summary')
export const getCostByProvider = () => api.get('/config/cost/by-provider')
export const getCostByDay = (params?: { start_date?: string; end_date?: string; period?: string }) =>
  api.get('/config/cost/by-day', { params })

export default api
