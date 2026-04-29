import React, { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Card, Space, Button, Modal, Spin, Typography, Progress, Descriptions } from 'antd'
import { TeamOutlined, RobotOutlined } from '@ant-design/icons'
import * as api from '../services/api'
import dayjs from 'dayjs'

const { Text: Txt, Paragraph } = Typography

interface AIDecision {
  id: number
  decision_time: string
  prompt_version: string
  model: string
  parsed_decision: any
  risk_check_passed: boolean
  risk_reject_reason: string
  execution_status: string
  linked_order_id: string
  confidence?: number
  voting_type?: 'single' | 'voting'
  voting_strategy?: string
  voting_details?: VotingDetail[]
}

interface VotingDetail {
  model: string
  provider: string
  decision: string
  confidence: number
  reason: string
}

interface AIDecisionDetail extends AIDecision {
  input_prompt: string
  output_response: string
}

const AIDecisions: React.FC = () => {
  const [decisions, setDecisions] = useState<AIDecision[]>([])
  const [loading, setLoading] = useState(true)
  const [detailModal, setDetailModal] = useState(false)
  const [detail, setDetail] = useState<AIDecisionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchDecisions = useCallback(async () => {
    try {
      const res = await api.getAIDecisions({ limit: 50 })
      setDecisions(res.data?.items || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDecisions()
  }, [fetchDecisions])

  const openDetail = async (id: number) => {
    setDetailModal(true)
    setDetailLoading(true)
    try {
      const res = await api.getAIDecisionDetail(id)
      setDetail(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setDetailLoading(false)
    }
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'decision_time',
      key: 'decision_time',
      width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '决策类型',
      key: 'voting_type',
      width: 100,
      render: (_: any, record: AIDecision) => (
        <Tag
          icon={record.voting_type === 'voting' ? <TeamOutlined /> : <RobotOutlined />}
          color={record.voting_type === 'voting' ? 'purple' : 'blue'}
        >
          {record.voting_type === 'voting' ? '投票' : '单模型'}
        </Tag>
      ),
    },
    {
      title: '决策',
      dataIndex: 'parsed_decision',
      key: 'parsed_decision',
      width: 80,
      render: (v: any) => (
        <Tag color={v?.decision === 'BUY' ? 'success' : v?.decision === 'SELL' ? 'error' : 'default'}>
          {v?.decision || '-'}
        </Tag>
      ),
    },
    {
      title: '标的',
      dataIndex: 'parsed_decision',
      key: 'symbol',
      width: 100,
      render: (v: any) => v?.symbol || '-',
    },
    {
      title: '数量',
      dataIndex: 'parsed_decision',
      key: 'quantity',
      width: 80,
      render: (v: any) => v?.quantity || '-',
    },
    {
      title: '价格',
      dataIndex: 'parsed_decision',
      key: 'price',
      width: 80,
      render: (v: any) => v?.price || '-',
    },
    {
      title: '置信度',
      key: 'confidence',
      width: 120,
      render: (_: any, record: AIDecision) => {
        const confidence = record.confidence ?? record.parsed_decision?.confidence
        if (!confidence) return <Txt type="secondary">-</Txt>
        const pct = Math.round(confidence * 100)
        return (
          <Space>
            <Progress
              percent={pct}
              size="small"
              style={{ width: 60 }}
              strokeColor={pct >= 80 ? '#52c41a' : pct >= 60 ? '#faad14' : '#ff4d4f'}
              format={(p) => `${p}%`}
            />
          </Space>
        )
      },
    },
    {
      title: '模型',
      key: 'model',
      width: 120,
      render: (_: any, record: AIDecision) => {
        if (record.voting_type === 'voting') {
          return (
            <Tag color="purple">
              {record.voting_details?.length || 0} 个模型
            </Tag>
          )
        }
        return <Txt style={{ fontSize: 12 }}>{record.model || '-'}</Txt>
      },
    },
    {
      title: '风控',
      dataIndex: 'risk_check_passed',
      key: 'risk_check_passed',
      width: 80,
      render: (v: boolean) => <Tag color={v ? 'success' : 'error'}>{v ? '通过' : '拒绝'}</Tag>,
    },
    {
      title: '执行',
      dataIndex: 'execution_status',
      key: 'execution_status',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Prompt',
      dataIndex: 'prompt_version',
      key: 'prompt_version',
      width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, record: AIDecision) => (
        <Button size="small" type="link" onClick={() => openDetail(record.id)}>
          查看详情
        </Button>
      ),
    },
  ]

  // 投票详情展开行
  const expandedRowRender = (record: AIDecision) => {
    if (record.voting_type !== 'voting' || !record.voting_details || record.voting_details.length === 0) {
      return null
    }

    const voteColumns = [
      {
        title: '供应商',
        dataIndex: 'provider',
        key: 'provider',
        render: (v: string) => <Tag color="blue">{v}</Tag>,
      },
      {
        title: '模型',
        dataIndex: 'model',
        key: 'model',
        render: (v: string) => <Txt>{v}</Txt>,
      },
      {
        title: '决策',
        dataIndex: 'decision',
        key: 'decision',
        render: (v: string) => (
          <Tag color={v === 'BUY' ? 'success' : v === 'SELL' ? 'error' : 'default'}>
            {v}
          </Tag>
        ),
      },
      {
        title: '置信度',
        dataIndex: 'confidence',
        key: 'confidence',
        render: (v: number) => (
          <Progress
            percent={Math.round(v * 100)}
            size="small"
            style={{ width: 80 }}
            strokeColor={v >= 0.8 ? '#52c41a' : v >= 0.6 ? '#faad14' : '#ff4d4f'}
            format={(p) => `${p}%`}
          />
        ),
      },
      {
        title: '理由',
        dataIndex: 'reason',
        key: 'reason',
        render: (v: string) => (
          <Txt type="secondary" style={{ fontSize: 12, maxWidth: 400, display: 'inline-block' }}>
            {v}
          </Txt>
        ),
      },
    ]

    return (
      <div style={{ padding: '8px 0' }}>
        <Space style={{ marginBottom: 8 }}>
          <Txt strong>投票详情</Txt>
          <Tag color="purple">
            {record.voting_strategy === 'majority' ? '多数投票' :
             record.voting_strategy === 'confidence' ? '置信度加权' : '一致通过'}
          </Tag>
          <Txt type="secondary">
            {record.voting_details.filter(v => v.decision === record.parsed_decision?.decision).length} / {record.voting_details.length} 票通过
          </Txt>
        </Space>
        <Table
          dataSource={record.voting_details.map((v, idx) => ({ ...v, key: idx }))}
          columns={voteColumns}
          pagination={false}
          size="small"
        />
      </div>
    )
  }

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Txt type="secondary">共 {decisions.length} 条决策记录</Txt>
          <Button size="small" onClick={fetchDecisions}>刷新</Button>
        </Space>
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
      ) : (
        <Table
          dataSource={decisions.map((d) => ({ ...d, key: d.id }))}
          columns={columns}
          pagination={{ pageSize: 20 }}
          size="middle"
          expandable={{
            expandedRowRender,
            rowExpandable: (record) => record.voting_type === 'voting' && (record.voting_details?.length || 0) > 0,
          }}
        />
      )}

      <Modal
        title="AI 决策详情"
        open={detailModal}
        onCancel={() => setDetailModal(false)}
        width={800}
        footer={null}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : detail ? (
          <div>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {/* 决策类型和基本信息 */}
              <Card size="small" title="基本信息">
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="决策类型">
                    <Tag
                      icon={detail.voting_type === 'voting' ? <TeamOutlined /> : <RobotOutlined />}
                      color={detail.voting_type === 'voting' ? 'purple' : 'blue'}
                    >
                      {detail.voting_type === 'voting' ? '投票决策' : '单模型决策'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="模型">
                    {detail.model || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="置信度">
                    {detail.confidence ? `${(detail.confidence * 100).toFixed(0)}%` : '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Prompt 版本">
                    <Tag>{detail.prompt_version}</Tag>
                  </Descriptions.Item>
                </Descriptions>
              </Card>

              {/* 投票详情 */}
              {detail.voting_type === 'voting' && detail.voting_details && detail.voting_details.length > 0 && (
                <Card size="small" title="投票详情">
                  <Space style={{ marginBottom: 8 }}>
                    <Tag color="purple">
                      {detail.voting_strategy === 'majority' ? '多数投票' :
                       detail.voting_strategy === 'confidence' ? '置信度加权' : '一致通过'}
                    </Tag>
                  </Space>
                  {detail.voting_details.map((vote, idx) => (
                    <Card key={idx} size="small" style={{ marginBottom: 8, background: '#fafafa' }}>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                          <Tag color="blue">{vote.provider}</Tag>
                          <Txt strong>{vote.model}</Txt>
                          <Tag color={vote.decision === 'BUY' ? 'success' : vote.decision === 'SELL' ? 'error' : 'default'}>
                            {vote.decision}
                          </Tag>
                          <Txt type="secondary">置信度: {(vote.confidence * 100).toFixed(0)}%</Txt>
                        </Space>
                        <Txt type="secondary" style={{ fontSize: 12 }}>{vote.reason}</Txt>
                      </Space>
                    </Card>
                  ))}
                </Card>
              )}

              <Card size="small" title="解析决策">
                <pre style={{ fontSize: 12, overflow: 'auto' }}>
                  {JSON.stringify(detail.parsed_decision, null, 2)}
                </pre>
              </Card>
              <Card size="small" title="AI 输入 Prompt">
                <Paragraph style={{ maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {detail.input_prompt || '无'}
                </Paragraph>
              </Card>
              <Card size="small" title="AI 输出">
                <Paragraph style={{ maxHeight: 200, overflow: 'auto', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {detail.output_response || '无'}
                </Paragraph>
              </Card>
            </Space>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default AIDecisions
