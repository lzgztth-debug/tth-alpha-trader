import React, { useEffect, useState, useCallback } from 'react'
import { Card, Form, Slider, Switch, Button, Space, Spin, message, Row, Col, Typography, Table, Select, Statistic, Tag, Tabs, DatePicker } from 'antd'
import { DollarOutlined, ApiOutlined, ThunderboltOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import * as api from '../services/api'
import dayjs, { Dayjs } from 'dayjs'
import { useAppStore, CostByProvider, CostByDay, CostSummary } from '../store'

const { Text: AntText } = Typography
const { RangePicker } = DatePicker

interface RiskRules {
  max_position_pct: number
  max_total_position_pct: number
  max_daily_loss_pct: number
  max_single_loss_pct: number
  max_positions: number
  allow_short: boolean
}

type DateRange = 'day' | 'week' | 'month'

const Settings: React.FC = () => {
  const [riskRules, setRiskRules] = useState<RiskRules | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [tradingMode, setTradingMode] = useState<string>('paper')
  const [form] = Form.useForm()

  // 成本相关状态
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null)
  const [costByProvider, setCostByProvider] = useState<CostByProvider[]>([])
  const [costByDay, setCostByDay] = useState<CostByDay[]>([])
  const [costLoading, setCostLoading] = useState(false)
  const [dateRange, setDateRange] = useState<DateRange>('week')

  const { setCostSummary: setStoreCostSummary, setCostByProvider: setStoreCostByProvider, setCostByDay: setStoreCostByDay } = useAppStore()

  useEffect(() => {
    const load = async () => {
      try {
        const [riskRes, modeRes] = await Promise.all([api.getRiskRules(), api.getTradingMode()])
        setRiskRules(riskRes.data as RiskRules)
        setTradingMode(modeRes.data?.mode || 'paper')
        form.setFieldsValue(riskRes.data)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [form])

  // 加载成本数据
  const fetchCostData = useCallback(async (range?: DateRange) => {
    setCostLoading(true)
    const period = range || dateRange
    try {
      const [summaryRes, providerRes, dayRes] = await Promise.all([
        api.getCostSummary().catch(() => ({ data: null })),
        api.getCostByProvider().catch(() => ({ data: [] })),
        api.getCostByDay({ period }).catch(() => ({ data: [] })),
      ])

      const summary = summaryRes.data
      const providers = providerRes.data || []
      const days = dayRes.data || []

      setCostSummary(summary)
      setCostByProvider(providers)
      setCostByDay(days)

      // 同步到 store
      setStoreCostSummary(summary)
      setStoreCostByProvider(providers)
      setStoreCostByDay(days)
    } catch (err) {
      console.error('加载成本数据失败', err)
    } finally {
      setCostLoading(false)
    }
  }, [dateRange, setStoreCostSummary, setStoreCostByProvider, setStoreCostByDay])

  useEffect(() => {
    fetchCostData()
  }, [fetchCostData])

  const handleDateRangeChange = (range: DateRange) => {
    setDateRange(range)
    fetchCostData(range)
  }

  const handleSaveRisk = async (values: RiskRules) => {
    setSaving(true)
    try {
      await api.updateRiskRules(values)
      message.success('风控规则已保存')
      setRiskRules(values)
    } catch (err) {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleSwitchMode = async (mode: string) => {
    try {
      await api.setTradingMode({ mode, paper_initial_cash: null })
      setTradingMode(mode)
      message.success(`已切换到 ${mode === 'paper' ? '模拟盘' : '实盘'}`)
    } catch (err) {
      message.error('切换失败')
    }
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  }

  const lossSliderMarks = { '-0.01': '-1%', '-0.10': '-10%', '-0.30': '-30%' }

  // 成本按供应商表格列
  const costProviderColumns = [
    {
      title: '供应商',
      dataIndex: 'provider',
      key: 'provider',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '调用次数',
      dataIndex: 'call_count',
      key: 'call_count',
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '输入 Tokens',
      dataIndex: 'input_tokens',
      key: 'input_tokens',
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '输出 Tokens',
      dataIndex: 'output_tokens',
      key: 'output_tokens',
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '总 Tokens',
      dataIndex: 'total_tokens',
      key: 'total_tokens',
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '费用 (USD)',
      dataIndex: 'total_cost',
      key: 'total_cost',
      align: 'right' as const,
      render: (v: number) => <AntText strong>${v.toFixed(4)}</AntText>,
    },
  ]

  // 成本趋势 ECharts 配置
  const costTrendOption = {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const },
    },
    legend: {
      data: ['调用次数', '费用 (USD)'],
    },
    xAxis: {
      type: 'category' as const,
      data: costByDay.map((d) => d.date),
      axisLabel: { rotate: 30, fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value' as const,
        name: '调用次数',
        position: 'left' as const,
      },
      {
        type: 'value' as const,
        name: '费用 (USD)',
        position: 'right' as const,
      },
    ],
    series: [
      {
        name: '调用次数',
        type: 'bar',
        yAxisIndex: 0,
        data: costByDay.map((d) => d.call_count),
        itemStyle: { color: '#1890ff', borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '费用 (USD)',
        type: 'line',
        yAxisIndex: 1,
        data: costByDay.map((d) => d.total_cost),
        smooth: true,
        lineStyle: { color: '#f5222d' },
        itemStyle: { color: '#f5222d' },
        areaStyle: { color: 'rgba(245,34,45,0.08)' },
      },
    ],
    grid: { left: 60, right: 60, bottom: 40, top: 40 },
  }

  // 成本汇总卡片
  const renderCostSummary = () => {
    if (!costSummary) {
      return (
        <AntText type="secondary">暂无成本数据</AntText>
      )
    }

    return (
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="总费用"
              value={costSummary.total_cost}
              prefix={<DollarOutlined />}
              precision={4}
              suffix="USD"
              valueStyle={{ color: costSummary.total_cost > 10 ? '#cf1322' : '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="总调用次数"
              value={costSummary.total_calls}
              suffix="次"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="总 Tokens"
              value={costSummary.total_tokens}
              valueStyle={{ fontSize: 16 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="平均每次费用"
              value={costSummary.total_calls > 0 ? costSummary.total_cost / costSummary.total_calls : 0}
              prefix={<DollarOutlined />}
              precision={4}
              suffix="USD"
            />
          </Card>
        </Col>
      </Row>
    )
  }

  const tabItems = [
    {
      key: 'trading',
      label: (
        <span>
          <ThunderboltOutlined />
          交易模式
        </span>
      ),
      children: (
        <div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <Card title="交易模式">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <AntText type="secondary">当前模式：</AntText>
                  <Space>
                    <Switch
                      checked={tradingMode === 'paper'}
                      onChange={(checked) => handleSwitchMode(checked ? 'paper' : 'live')}
                      checkedChildren="模拟盘"
                      unCheckedChildren="实盘"
                    />
                    <AntText strong>{tradingMode === 'paper' ? '模拟盘 (Paper Trading)' : '实盘 (Live)'}</AntText>
                  </Space>
                  <AntText type="secondary" style={{ fontSize: 12 }}>
                    模拟盘使用虚拟资金，所有交易不会产生真实成交
                  </AntText>
                </Space>
              </Card>
            </Col>
            <Col span={12}>
              <Card title="AI 模型供应商">
                <Space direction="vertical">
                  <AntText>已配置：OpenAI / Anthropic / Google / SiliconFlow / 智谱 GLM / Moonshot / DeepSeek</AntText>
                  <AntText type="secondary">请在 backend/.env 中配置 API Key</AntText>
                </Space>
              </Card>
            </Col>
          </Row>
        </div>
      ),
    },
    {
      key: 'risk',
      label: (
        <span>
          <SafetyCertificateOutlined />
          风控规则
        </span>
      ),
      children: (
        <Card title="风控规则">
          <Form form={form} layout="vertical" onFinish={handleSaveRisk} initialValues={riskRules || {}}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="max_position_pct" label="单只仓位上限">
                  <Slider min={0.01} max={0.5} step={0.01} marks={{ 0.01: '1%', 0.2: '20%', 0.5: '50%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_total_position_pct" label="总仓位上限">
                  <Slider min={0.1} max={1} step={0.05} marks={{ 0.1: '10%', 0.8: '80%', 1: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_daily_loss_pct" label="单日最大亏损">
                  <Slider min={0.005} max={0.1} step={0.005} marks={{ 0.01: '1%', 0.03: '3%', 0.1: '10%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_single_loss_pct" label="单只最大亏损（止损线）">
                  <Slider min={-0.3} max={-0.01} step={0.01} marks={lossSliderMarks} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_positions" label="最大持仓数量">
                  <Slider min={1} max={30} step={1} marks={{ 1: '1', 10: '10', 30: '30' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="allow_short" label="允许做空" valuePropName="checked">
                  <Switch checkedChildren="开启" unCheckedChildren="禁止" />
                </Form.Item>
              </Col>
            </Row>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存风控规则
            </Button>
          </Form>
        </Card>
      ),
    },
    {
      key: 'cost',
      label: (
        <span>
          <DollarOutlined />
          AI 成本
        </span>
      ),
      children: (
        <div>
          {/* 日期范围筛选 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space>
              <AntText type="secondary">时间范围：</AntText>
              <Select
                value={dateRange}
                onChange={handleDateRangeChange}
                style={{ width: 120 }}
                options={[
                  { label: '今天', value: 'day' },
                  { label: '最近7天', value: 'week' },
                  { label: '最近30天', value: 'month' },
                ]}
              />
              <Button size="small" onClick={() => fetchCostData()}>刷新</Button>
            </Space>
          </Card>

          {costLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          ) : (
            <div>
              {/* 成本汇总 */}
              {renderCostSummary()}

              {/* 成本趋势图 */}
              {costByDay.length > 0 && (
                <Card title="成本趋势" style={{ marginTop: 16 }}>
                  <ReactECharts option={costTrendOption} style={{ height: 300 }} />
                </Card>
              )}

              {/* 按供应商成本明细 */}
              <Card title="按供应商成本明细" style={{ marginTop: 16 }}>
                <Table
                  dataSource={costByProvider.map((p, idx) => ({ ...p, key: idx }))}
                  columns={costProviderColumns}
                  pagination={false}
                  size="small"
                  summary={(data) => {
                    const totalCalls = data.reduce((sum, row) => sum + (row.call_count || 0), 0)
                    const totalTokens = data.reduce((sum, row) => sum + (row.total_tokens || 0), 0)
                    const totalCost = data.reduce((sum, row) => sum + (row.total_cost || 0), 0)
                    return (
                      <Table.Summary.Row>
                        <Table.Summary.Cell index={0}><AntText strong>合计</AntText></Table.Summary.Cell>
                        <Table.Summary.Cell index={1} align="right"><AntText strong>{totalCalls.toLocaleString()}</AntText></Table.Summary.Cell>
                        <Table.Summary.Cell index={2} align="right">-</Table.Summary.Cell>
                        <Table.Summary.Cell index={3} align="right">-</Table.Summary.Cell>
                        <Table.Summary.Cell index={4} align="right"><AntText strong>{totalTokens.toLocaleString()}</AntText></Table.Summary.Cell>
                        <Table.Summary.Cell index={5} align="right"><AntText strong style={{ color: totalCost > 10 ? '#cf1322' : '#3f8600' }}>${totalCost.toFixed(4)}</AntText></Table.Summary.Cell>
                      </Table.Summary.Row>
                    )
                  }}
                />
              </Card>
            </div>
          )}
        </div>
      ),
    },
  ]

  return (
    <div>
      <Tabs
        defaultActiveKey="trading"
        items={tabItems}
        size="large"
      />
    </div>
  )
}

export default Settings
