import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography, Tag, Badge, Space } from 'antd'
import {
  DashboardOutlined,
  TableOutlined,
  HistoryOutlined,
  SettingOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  WifiOutlined,
  DisconnectOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Orders from './pages/Orders'
import AIDecisions from './pages/AIDecisions'
import Settings from './pages/Settings'
import StrategyConfig from './pages/StrategyConfig'
import { useAppStore } from './store'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const menuItems = [
  { key: '1', icon: <DashboardOutlined />, label: <Link to="/">概览</Link> },
  { key: '2', icon: <TableOutlined />, label: <Link to="/positions">持仓</Link> },
  { key: '3', icon: <HistoryOutlined />, label: <Link to="/orders">交易历史</Link> },
  { key: '4', icon: <RobotOutlined />, label: <Link to="/ai-decisions">AI 决策</Link> },
  { key: '5', icon: <ThunderboltOutlined />, label: <Link to="/strategy">策略配置</Link> },
  { key: '6', icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
]

const AppLayout: React.FC = () => {
  const location = useLocation()
  const selectedKey = menuItems.find((item) => location.pathname === item.label.props.to)?.key || '1'
  const { wsConnected, tradingMode } = useAppStore()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={220} collapsible>
        <div
          style={{
            color: '#fff',
            textAlign: 'center',
            padding: '20px 0',
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: 1,
          }}
        >
          AlphaTrader
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
        />
        <div style={{ position: 'absolute', bottom: 16, left: 0, right: 0, textAlign: 'center' }}>
          <Tag color="blue">v2.0.0</Tag>
        </div>
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text strong style={{ fontSize: 16 }}>AI 量化交易平台</Text>
          <Space size="middle">
            <Tag color={tradingMode === 'paper' ? 'blue' : 'red'}>
              {tradingMode === 'paper' ? '模拟盘' : '实盘'}
            </Tag>
            <Badge
              status={wsConnected ? 'success' : 'error'}
              text={
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {wsConnected ? 'WS 已连接' : 'WS 未连接'}
                </Text>
              }
            />
          </Space>
        </Header>
        <Content style={{ margin: 16, background: '#fff', borderRadius: 8, padding: 24, minHeight: 'calc(100vh - 112px)', overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/ai-decisions" element={<AIDecisions />} />
            <Route path="/strategy" element={<StrategyConfig />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}

export default App
