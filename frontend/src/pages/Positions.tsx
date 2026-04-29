import React, { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Card, Space, Select, Spin } from 'antd'
import { Typography } from 'antd'
import * as api from '../services/api'

const { Text: AntText } = Typography

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

const Positions: React.FC = () => {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [marketFilter, setMarketFilter] = useState<string>('ALL')

  const fetchPositions = useCallback(async () => {
    try {
      const res = await api.getPositions()
      setPositions(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPositions()
    const interval = setInterval(fetchPositions, 15000)
    return () => clearInterval(interval)
  }, [fetchPositions])

  const filtered = marketFilter === 'ALL' ? positions : positions.filter((p) => p.market === marketFilter)

  const columns = [
    {
      title: '标的',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (symbol: string, record: Position) => (
        <Space direction="vertical" size={0}>
          <AntText strong>{symbol}</AntText>
          <AntText type="secondary" style={{ fontSize: 12 }}>{record.name || '-'}</AntText>
        </Space>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      key: 'market',
      width: 80,
      render: (m: string) => <Tag>{m}</Tag>,
    },
    {
      title: '券商',
      dataIndex: 'broker',
      key: 'broker',
      width: 80,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '平均成本',
      dataIndex: 'avg_cost',
      key: 'avg_cost',
      width: 100,
      align: 'right' as const,
      render: (v: number) => v.toFixed(4),
    },
    {
      title: '当前价',
      dataIndex: 'current_price',
      key: 'current_price',
      width: 100,
      align: 'right' as const,
      render: (v: number) => v.toFixed(4),
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      key: 'market_value',
      width: 120,
      align: 'right' as const,
      render: (v: number) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    },
    {
      title: '盈亏额',
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      width: 120,
      align: 'right' as const,
      render: (v: number) => (
        <AntText style={{ color: v >= 0 ? '#3f8600' : '#cf1322' }}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}
        </AntText>
      ),
    },
    {
      title: '盈亏率',
      dataIndex: 'unrealized_pnl_pct',
      key: 'unrealized_pnl_pct',
      width: 100,
      align: 'right' as const,
      render: (v: number) => (
        <Tag color={v >= 0 ? 'success' : 'error'}>
          {v >= 0 ? '+' : ''}{(v * 100).toFixed(2)}%
        </Tag>
      ),
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <AntText>市场筛选：</AntText>
          <Select value={marketFilter} onChange={setMarketFilter} style={{ width: 120 }}>
            <Select.Option value="ALL">全部</Select.Option>
            <Select.Option value="HK">港股</Select.Option>
            <Select.Option value="US">美股</Select.Option>
            <Select.Option value="CN">A股</Select.Option>
            <Select.Option value="CRYPTO">加密</Select.Option>
          </Select>
          <AntText type="secondary">共 {filtered.length} 条持仓</AntText>
        </Space>
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
      ) : (
        <Table
          dataSource={filtered.map((p) => ({ ...p, key: p.symbol + p.broker }))}
          columns={columns}
          pagination={{ pageSize: 20 }}
          size="middle"
        />
      )}
    </div>
  )
}

export default Positions
