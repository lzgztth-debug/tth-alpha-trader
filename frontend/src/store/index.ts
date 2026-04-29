import { create } from 'zustand'

// AI 模型信息
export interface AIModel {
  id: string
  name: string
  provider: string
  available: boolean
}

// AI 供应商信息
export interface AIProvider {
  name: string
  display_name: string
  available: boolean
  models: AIModel[]
}

// 投票策略
export type VotingStrategy = 'majority' | 'confidence' | 'unanimous'

// 单个模型的投票结果
export interface ModelVoteResult {
  model: string
  provider: string
  decision: string
  confidence: number
  reason: string
  timestamp?: string
}

// 最终投票结果
export interface VotingResult {
  final_decision: string
  final_confidence: number
  voting_strategy: VotingStrategy
  votes: ModelVoteResult[]
  symbol?: string
  timestamp?: string
}

// 成本汇总
export interface CostSummary {
  total_cost: number
  total_calls: number
  total_tokens: number
  total_input_tokens: number
  total_output_tokens: number
}

// 按供应商的成本
export interface CostByProvider {
  provider: string
  call_count: number
  total_tokens: number
  input_tokens: number
  output_tokens: number
  total_cost: number
}

// 按天的成本
export interface CostByDay {
  date: string
  call_count: number
  total_tokens: number
  total_cost: number
}

interface AppState {
  // 交易模式
  tradingMode: string
  paperInitialCash: Record<string, number>
  setTradingMode: (mode: string, cash?: Record<string, number>) => void

  // 侧边栏
  sidebarCollapsed: boolean
  activeKey: string
  setSidebarCollapsed: (collapsed: boolean) => void
  setActiveKey: (key: string) => void

  // WebSocket
  wsConnected: boolean
  setWsConnected: (connected: boolean) => void

  // AI 模型与投票
  aiProviders: AIProvider[]
  aiModels: AIModel[]
  selectedModels: string[]
  votingStrategy: VotingStrategy
  votingResults: VotingResult | null
  setAiProviders: (providers: AIProvider[]) => void
  setAiModels: (models: AIModel[]) => void
  setSelectedModels: (models: string[]) => void
  setVotingStrategy: (strategy: VotingStrategy) => void
  setVotingResults: (results: VotingResult | null) => void
  addModelVoteResult: (vote: ModelVoteResult) => void

  // 成本追踪
  costSummary: CostSummary | null
  costByProvider: CostByProvider[]
  costByDay: CostByDay[]
  setCostSummary: (summary: CostSummary | null) => void
  setCostByProvider: (data: CostByProvider[]) => void
  setCostByDay: (data: CostByDay[]) => void
}

export const useAppStore = create<AppState>((set) => ({
  // 交易模式
  tradingMode: 'paper',
  paperInitialCash: { HK: 1000000, US: 100000, CN: 500000, CRYPTO: 100000 },
  setTradingMode: (mode, cash) =>
    set((state) => ({
      tradingMode: mode,
      paperInitialCash: cash || state.paperInitialCash,
    })),

  // 侧边栏
  sidebarCollapsed: false,
  activeKey: '1',
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setActiveKey: (key) => set({ activeKey: key }),

  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  // AI 模型与投票
  aiProviders: [],
  aiModels: [],
  selectedModels: [],
  votingStrategy: 'majority',
  votingResults: null,
  setAiProviders: (providers) => set({ aiProviders: providers }),
  setAiModels: (models) => set({ aiModels: models }),
  setSelectedModels: (models) => set({ selectedModels: models }),
  setVotingStrategy: (strategy) => set({ votingStrategy: strategy }),
  setVotingResults: (results) => set({ votingResults: results }),
  addModelVoteResult: (vote) =>
    set((state) => {
      const currentVotes = state.votingResults?.votes || []
      const updatedVotes = [...currentVotes, vote]
      return {
        votingResults: {
          ...(state.votingResults || {
            final_decision: '',
            final_confidence: 0,
            voting_strategy: state.votingStrategy,
            votes: [],
          }),
          votes: updatedVotes,
        },
      }
    }),

  // 成本追踪
  costSummary: null,
  costByProvider: [],
  costByDay: [],
  setCostSummary: (summary) => set({ costSummary: summary }),
  setCostByProvider: (data) => set({ costByProvider: data }),
  setCostByDay: (data) => set({ costByDay: data }),
}))
