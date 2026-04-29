import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Card, Row, Col, Statistic, Spin, Tag, Space, Table, Button, Checkbox, Select, Typography, Alert, Divider, Badge } from 'antd'
import {
  DollarOutlined,
  RiseOutlined,
  FallOutlined,
  BankOutlined,
  TrophyOutlined,
  TeamOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import * as api from '../services/api'
import { useAppStore, VotingStrategy, ModelVoteResult } from '../store'
import { useWebSocket } from '../hooks/useWebSocket'

const { Text: AntText, Title } = Typography

interface Portfolio {
  total_asset: number
  cash: Record<string, number>
  position_value: number
  total_pnl: number
  total_pnl_pct: number
  positions: Record<string, any>
}

interface Account {
  broker: string
  market: string
  total_asset: number
  cash: number
  market_value: number
}

interface Position {
  symbol: string
  name: string
  market: string
  broker: string
  quantity: number
  avg_cost: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
}

// 可用 AI 模型列表
const AVAILABLE_MODELS = [
  { label: 'GPT-4o', value: 'openai/gpt-4o', provider: 'OpenAI' },
  { label: 'GPT-4o-mini', value: 'openai/gpt-4o-mini', provider: 'OpenAI' },
  { label: 'Claude 3.5 Sonnet', value: 'anthropic/claude-3-5-sonnet', provider: 'Anthropic' },
  { label: 'Claude 3 Haiku', value: 'anthropic/claude-3-haiku', provider: 'Anthropic' },
  { label: 'Qwen2.5-72B', value: 'siliconflow/Qwen/Qwen2.5-72B-Instruct', provider: 'SiliconFlow' },
  { label: 'Qwen2.5-7B', value: 'siliconflow/Qwen/Qwen2.5-7B-Instruct', provider: 'SiliconFlow' },
  { label: 'DeepSeek V3', value: 'siliconflow/deepseek-ai/DeepSeek-V3', provider: 'SiliconFlow' },
  { label: 'GLM-4-Plus', value: 'zhipu/glm-4-plus', provider: '智谱' },
  { label: 'GLM-4-Flash', value: 'zhipu/glm-4-flash', provider: '智谱' },
  { label: 'Moonshot V1', value: 'moonshot/moonshot-v1-8k', provider: 'Moonshot' },
  { label: 'Gemini Pro', value: 'google/gemini-pro', provider: 'Google' },
]

const VOTING_STRATEGY_OPTIONS = [
  { label: '多数投票 (Majority)', value: 'majority' },
  { label: '置信度加权 (Confidence)', value: 'confidence' },
  { label: '一致通过 (Unanimous)', value: 'unanimous' },
]

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [aiDecisionLoading, setAiDecisionLoading] = useState(false)
  const [aiResult, setAiResult] = useState<any>(null)

  // 多模型投票状态
  const [selectedModels, setSelectedModels] = useState<string[]>(['openai/gpt-4o-mini', 'siliconflow/Qwen/Qwen2.5-7B-Instruct', 'zhipu/glm-4-flash'])
  const [votingStrategy, setVotingStrategy] = useState<VotingStrategy>('majority')
  const [streaming, setStreaming] = useState(false)
  const [streamVotes, setStreamVotes] = useState<ModelVoteResult[]>([])
  const [finalVoteResult, setFinalVoteResult] = useState<any>(null)
  const [multiLoading, setMultiLoading] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const { tradingMode, setWsConnected } = useAppStore()

  // WebSocket 连接
  const { connectionStatus } = useWebSocket({
    channels: ['portfolio_update', 'order_update', 'ai_decision', 'trade_execution'],
    onEvent: (event) => {
      if (event.type === 'portfolio_update') {
        // 收到组合更新时刷新数据
        fetchData()
      }
    },
  })

  useEffect(() => {
    setWsConnected(connectionStatus === 'connected')
  }, [connectionStatus, setWsConnected])

  const fetchData = useCallback(async () => {
    try {
      const [portRes, accRes, posRes] = await Promise.all([
        api.getPortfolioSummary(),
        api.getAccounts(),
        api.getPositions(),
      ])
      setPortfolio(portRes.data)
      setAccounts(accRes.data)
      setPositions(posRes.data)
    } catch (err) {
      console.error('fetch error', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  const handleAIDecision = async () => {
    setAiDecisionLoading(true)
    setAiResult(null)
    try {
      const res = await api.triggerAIDecision({ symbols: [], mode: 'analyze', force_decide: false })
      setAiResult(res.data)
      fetchData()
    } catch (err: any) {
      setAiResult({ decision: 'ERROR', reason: err?.message || '未知错误' })
    } finally {
      setAiDecisionLoading(false)
    }
  }

  // 多模型投票 - 普通请求
  const handleMultiAIDecision = async () => {
    if (selectedModels.length < 2) {
      return
    }
    setMultiLoading(true)
    setFinalVoteResult(null)
    try {
      const res = await api.triggerMultiAIDecision({
        symbols: [],
        models: selectedModels,
        voting_strategy: votingStrategy,
        mode: 'analyze',
        force_decide: false,
      })
      setFinalVoteResult(res.data)
      fetchData()
    } catch (err: any) {
      setFinalVoteResult({ error: true, message: err?.message || '投票决策失败' })
    } finally {
      setMultiLoading(false)
    }
  }

  // 多模型投票 - SSE 流式
  const handleStreamDecision = () => {
    if (selectedModels.length < 2) {
      return
    }
    setStreaming(true)
    setStreamVotes([])
    setFinalVoteResult(null)

    const es = api.streamAIDecision({
      symbols: [],
      models: selectedModels,
      voting_strategy: votingStrategy,
      mode: 'analyze',
      force_decide: false,
    })

    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'model_result') {
          // 单个模型返回结果
          const vote: ModelVoteResult = {
            model: data.model,
            provider: data.provider,
            decision: data.decision,
            confidence: data.confidence,
            reason: data.reason,
            timestamp: data.timestamp,
          }
          setStreamVotes((prev) => [...prev, vote])
        } else if (data.type === 'voting_result') {
          // 最终投票结果
          setFinalVoteResult(data)
          setStreaming(false)
          es.close()
          eventSourceRef.current = null
          fetchData()
        } else if (data.type === 'error') {
          setFinalVoteResult({ error: true, message: data.message })
          setStreaming(false)
          es.close()
          eventSourceRef.current = null
        }
      } catch (e) {
        console.error('SSE 解析错误', e)
      }
    }

    es.onerror = () => {
      setStreaming(false)
      es.close()
      eventSourceRef.current = null
    }
  }

  // 组件卸载时关闭 EventSource
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  const totalCash = portfolio ? Object.values(portfolio.cash).reduce((a, b) => a + b, 0) : 0

  const pieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: { orient: 'vertical', right: 20, top: 'center' },
    series: [
      {
        name: '资产分布',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['35%', '50%'],
        itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{d}%' },
        data: [
          { value: totalCash, name: '现金' },
          { value: portfolio?.position_value || 0, name: '持仓' },
        ].filter((d) => d.value > 0),
      },
    ],
  }

  const marketAllocationOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['市值'] },
    xAxis: {
      type: 'category',
      data: Object.keys(portfolio?.positions || {}),
      axisLabel: { rotate: 30 },
    },
    yAxis: { type: 'value', name: '市值' },
    series: [
      {
        name: '持仓市值',
        type: 'bar',
        data: Object.values(portfolio?.positions || {}).map((p: any) => p.market_value),
        itemStyle: { color: '#1890ff', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }

  const pnlHistoryOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['周一', '周二', '周三', '周四', '周五'] },
    yAxis: { type: 'value', name: '盈亏' },
    series: [
      {
        name: '每日盈亏',
        type: 'line',
        data: [1200, -800, 2100, 500, -300],
        smooth: true,
        lineStyle: { color: '#52c41a' },
        areaStyle: { color: 'rgba(82,196,26,0.1)' },
      },
    ],
  }

  const positionColumns = [
    { title: '标的', dataIndex: 'symbol', key: 'symbol', width: 100 },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 100, render: (v: number) => v.toFixed(0) },
    { title: '成本', dataIndex: 'avg_cost', key: 'avg_cost', width: 100, render: (v: number) => v.toFixed(2) },
    { title: '现价', dataIndex: 'current_price', key: 'current_price', width: 100, render: (v: number) => v.toFixed(2) },
    {
      title: '盈亏额',
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#3f8600' : '#cf1322' }}>{v >= 0 ? '+' : ''}{v.toFixed(2)}</span>
      ),
    },
    {
      title: '盈亏率',
      dataIndex: 'unrealized_pnl_pct',
      key: 'unrealized_pnl_pct',
      render: (v: number) => (
        <Tag color={v >= 0 ? 'success' : 'error'}>{v >= 0 ? '+' : ''}{(v * 100).toFixed(2)}%</Tag>
      ),
    },
  ]

  // 投票结果展示
  const renderVotingResult = () => {
    if (finalVoteResult?.error) {
      return (
        <Alert
          type="error"
          message="投票决策失败"
          description={finalVoteResult.message}
          style={{ marginTop: 8 }}
        />
      )
    }

    if (!finalVoteResult && streamVotes.length === 0) return null

    return (
      <div style={{ marginTop: 12 }}>
        {/* 各模型实时结果 */}
        {streamVotes.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <AntText strong>各模型决策结果：</AntText>
            <div style={{ marginTop: 8 }}>
              {streamVotes.map((vote, idx) => (
                <Card
                  key={idx}
                  size="small"
                  style={{ marginBottom: 8, background: '#fafafa' }}
                >
                  <Space>
                    <Tag color="blue">{vote.provider}</Tag>
                    <AntText strong>{vote.model}</AntText>
                    <Tag color={vote.decision === 'BUY' ? 'success' : vote.decision === 'SELL' ? 'error' : 'default'}>
                      {vote.decision}
                    </Tag>
                    <AntText type="secondary">置信度: {(vote.confidence * 100).toFixed(0)}%</AntText>
                    <AntText type="secondary" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {vote.reason}
                    </AntText>
                  </Space>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* 最终投票结果 */}
        {finalVoteResult && !finalVoteResult.error && (
          <Card size="small" style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />
                <AntText strong style={{ fontSize: 15 }}>投票结果</AntText>
                <Tag color={finalVoteResult.voting_strategy === 'majority' ? 'blue' : finalVoteResult.voting_strategy === 'confidence' ? 'purple' : 'green'}>
                  {VOTING_STRATEGY_OPTIONS.find(s => s.value === finalVoteResult.voting_strategy)?.label}
                </Tag>
              </Space>
              <Space size="large">
                <Space>
                  <AntText type="secondary">最终决策：</AntText>
                  <Tag
                    color={finalVoteResult.final_decision === 'BUY' ? 'success' : finalVoteResult.final_decision === 'SELL' ? 'error' : 'default'}
                    style={{ fontSize: 14, padding: '2px 8px' }}
                  >
                    {finalVoteResult.final_decision}
                  </Tag>
                </Space>
                <Space>
                  <AntText type="secondary">综合置信度：</AntText>
                  <AntText strong>{((finalVoteResult.final_confidence || 0) * 100).toFixed(0)}%</AntText>
                </Space>
                {finalVoteResult.symbol && (
                  <Space>
                    <AntText type="secondary">标的：</AntText>
                    <AntText strong>{finalVoteResult.symbol}</AntText>
                  </Space>
                )}
              </Space>
              {finalVoteResult.votes && (
                <div>
                  <AntText type="secondary" style={{ fontSize: 12 }}>
                    {finalVoteResult.votes.filter((v: any) => v.decision === finalVoteResult.final_decision).length} / {finalVoteResult.votes.length} 票通过
                  </AntText>
                </div>
              )}
            </Space>
          </Card>
        )}

        {/* 流式加载中 */}
        {streaming && (
          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <Spin indicator={<LoadingOutlined style={{ fontSize: 20 }} spin />} />
            <AntText type="secondary" style={{ marginLeft: 8 }}>
              等待模型 {streamVotes.length + 1}/{selectedModels.length} 响应中...
            </AntText>
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Tag color={tradingMode === 'paper' ? 'blue' : 'red'}>
            {tradingMode === 'paper' ? '模拟盘' : '实盘'}
          </Tag>
          <Badge status={connectionStatus === 'connected' ? 'success' : 'error'} text={
            <AntText type="secondary">
              WS {connectionStatus === 'connected' ? '已连接' : connectionStatus === 'connecting' ? '连接中' : '未连接'}
            </AntText>
          } />
          <Button
            type="primary"
            icon={<TrophyOutlined />}
            onClick={handleAIDecision}
            loading={aiDecisionLoading}
          >
            触发 AI 决策
          </Button>
        </Space>
      </div>

      {aiResult && (
        <Card size="small" style={{ marginBottom: 16, background: '#f6ffed' }}>
          <Space>
            <Tag color={aiResult.decision === 'BUY' ? 'success' : aiResult.decision === 'SELL' ? 'error' : 'default'}>
              {aiResult.decision}
            </Tag>
            {aiResult.symbol && <AntText strong>{aiResult.symbol}</AntText>}
            {aiResult.quantity > 0 && <AntText>{aiResult.quantity} 股</AntText>}
            {aiResult.price > 0 && <AntText>@ {aiResult.price}</AntText>}
            <AntText type="secondary">置信度: {(aiResult.confidence * 100).toFixed(0)}%</AntText>
            <AntText type="secondary">|</AntText>
            <AntText type="secondary">{aiResult.reason}</AntText>
          </Space>
        </Card>
      )}

      {/* 多模型投票决策区域 */}
      <Card
        title={
          <Space>
            <TeamOutlined />
            <span>多模型投票决策</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
        size="small"
      >
        <Row gutter={[16, 12]} align="middle">
          <Col flex="auto">
            <AntText type="secondary">选择模型 (至少2个)：</AntText>
            <Checkbox.Group
              options={AVAILABLE_MODELS.map(m => ({ label: `${m.label} (${m.provider})`, value: m.value }))}
              value={selectedModels}
              onChange={(vals) => setSelectedModels(vals as string[])}
              style={{ marginTop: 4 }}
            />
          </Col>
        </Row>
        <Row gutter={[16, 12]} align="middle" style={{ marginTop: 12 }}>
          <Col>
            <AntText type="secondary">投票策略：</AntText>
            <Select
              value={votingStrategy}
              onChange={setVotingStrategy}
              options={VOTING_STRATEGY_OPTIONS}
              style={{ width: 220, marginLeft: 8 }}
            />
          </Col>
          <Col>
            <Space>
              <Button
                type="primary"
                icon={<TeamOutlined />}
                onClick={handleMultiAIDecision}
                loading={multiLoading}
                disabled={selectedModels.length < 2}
              >
                发起投票
              </Button>
              <Button
                icon={<LoadingOutlined />}
                onClick={handleStreamDecision}
                loading={streaming}
                disabled={selectedModels.length < 2}
              >
                流式投票 (SSE)
              </Button>
            </Space>
          </Col>
        </Row>
        {renderVotingResult()}
      </Card>

      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总资产"
              value={portfolio?.total_asset || 0}
              prefix={<DollarOutlined />}
              precision={2}
              suffix="HKD"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总盈亏"
              value={(portfolio?.total_pnl ?? 0)}
              prefix={(portfolio?.total_pnl ?? 0) >= 0 ? <RiseOutlined /> : <FallOutlined />}
              precision={2}
              valueStyle={{ color: ((portfolio?.total_pnl ?? 0)) >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="盈亏率"
              value={((portfolio?.total_pnl_pct ?? 0) * 100)}
              precision={2}
              suffix="%"
              prefix={(portfolio?.total_pnl_pct ?? 0) >= 0 ? <RiseOutlined /> : <FallOutlined />}
              valueStyle={{ color: ((portfolio?.total_pnl_pct ?? 0)) >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="持仓市值"
              value={portfolio?.position_value || 0}
              prefix={<BankOutlined />}
              precision={2}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="资产分布">
            <ReactECharts option={pieOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="每日盈亏走势">
            <ReactECharts option={pnlHistoryOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={16}>
          <Card title="当前持仓">
            <Table
              dataSource={positions.map((p) => ({ ...p, key: p.symbol }))}
              columns={positionColumns}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="市场账户">
            {accounts.map((acc) => (
              <div key={acc.broker + acc.market} style={{ marginBottom: 12 }}>
                <Tag color="blue">{acc.broker}</Tag>
                <AntText type="secondary"> {acc.market}</AntText>
                <div>
                  <AntText strong>{(acc.total_asset || 0).toLocaleString()}</AntText>
                </div>
              </div>
            ))}
          </Card>
        </Col>
      </Row>

      {Object.keys(portfolio?.positions || {}).length > 0 && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card title="持仓分布">
              <ReactECharts option={marketAllocationOption} style={{ height: 250 }} />
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )
}

export default Dashboard
