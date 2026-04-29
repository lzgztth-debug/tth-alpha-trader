import React, { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Card, Space, Select, Typography, Button, Modal, Form, InputNumber, Input } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import * as api from '../services/api'
import dayjs from 'dayjs'

const { Text: AntText } = Typography

interface Order {
  order_id: string
  broker: string
  symbol: string
  direction: string
  quantity: number
  price: number
  order_type: string
  status: string
  created_at?: string
}

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const fetchOrders = useCallback(async () => {
    try {
      const res = await api.getOrders()
      setOrders(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOrders()
  }, [fetchOrders])

  const handleSubmit = async (values: any) => {
    try {
      await api.createOrder({
        broker: 'Paper',
        symbol: values.symbol,
        direction: values.direction,
        quantity: values.quantity,
        price: values.price || 0,
        order_type: values.order_type || 'MARKET',
      })
      setModalOpen(false)
      form.resetFields()
      fetchOrders()
    } catch (err) {
      console.error(err)
    }
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '订单号',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 140,
    },
    {
      title: '标的',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 100,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      width: 80,
      render: (v: string) => <Tag color={v === 'BUY' ? 'success' : 'error'}>{v}</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right' as const,
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      align: 'right' as const,
    },
    {
      title: '类型',
      dataIndex: 'order_type',
      key: 'order_type',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => {
        const colors: Record<string, string> = { FILLED: 'success', SUBMITTED: 'processing', CANCELLED: 'default', REJECTED: 'error' }
        return <Tag color={colors[v] || 'default'}>{v}</Tag>
      },
    },
    {
      title: '券商',
      dataIndex: 'broker',
      key: 'broker',
      width: 80,
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            模拟下单
          </Button>
          <AntText type="secondary">共 {orders.length} 条记录</AntText>
        </Space>
      </Card>

      <Table
        dataSource={orders.map((o) => ({ ...o, key: o.order_id }))}
        columns={columns}
        pagination={{ pageSize: 20 }}
        loading={loading}
        size="middle"
      />

      <Modal title="模拟下单" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="symbol" label="标的代码" rules={[{ required: true }]}>
            <Input placeholder="例如: 00700.HK" />
          </Form.Item>
          <Form.Item name="direction" label="方向" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="BUY">买入 BUY</Select.Option>
              <Select.Option value="SELL">卖出 SELL</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
            <InputNumber min={100} step={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="price" label="价格">
            <InputNumber min={0} step={0.01} style={{ width: '100%' }} placeholder="市价单填0" />
          </Form.Item>
          <Form.Item name="order_type" label="订单类型" initialValue="MARKET">
            <Select>
              <Select.Option value="MARKET">市价单</Select.Option>
              <Select.Option value="LIMIT">限价单</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Orders
