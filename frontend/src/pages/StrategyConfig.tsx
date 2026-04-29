import React, { useEffect, useState } from 'react'
import { Card, Form, Input, Select, Slider, Switch, Button, Space, Spin, message, Typography, Cascader, Tag, Row, Col, Empty, Descriptions } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, ApiOutlined } from '@ant-design/icons'
import * as api from '../services/api'
import { useAppStore, AIProvider } from '../store'

const { Text: AntText } = Typography
const { TextArea } = Input

interface PromptVersion {
  version: string
  name: string
  system_prompt: string
  user_template: string
  few_shot_examples: any[]
  model_preference: string
  temperature: number
  is_active: boolean
}

// 11 个 AI 供应商及其模型
const PROVIDER_MODEL_OPTIONS = [
  {
    value: 'openai',
    label: 'OpenAI',
    children: [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'gpt-4o-mini', label: 'GPT-4o-mini' },
      { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
    ],
  },
  {
    value: 'anthropic',
    label: 'Anthropic',
    children: [
      { value: 'claude-3-5-sonnet', label: 'Claude 3.5 Sonnet' },
      { value: 'claude-3-haiku', label: 'Claude 3 Haiku' },
    ],
  },
  {
    value: 'google',
    label: 'Google',
    children: [
      { value: 'gemini-pro', label: 'Gemini Pro' },
      { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    ],
  },
  {
    value: 'siliconflow',
    label: 'SiliconFlow',
    children: [
      { value: 'Qwen/Qwen2.5-72B-Instruct', label: 'Qwen2.5-72B' },
      { value: 'Qwen/Qwen2.5-7B-Instruct', label: 'Qwen2.5-7B' },
      { value: 'deepseek-ai/DeepSeek-V3', label: 'DeepSeek V3' },
    ],
  },
  {
    value: 'zhipu',
    label: '智谱 GLM',
    children: [
      { value: 'glm-4-plus', label: 'GLM-4-Plus' },
      { value: 'glm-4-flash', label: 'GLM-4-Flash' },
    ],
  },
  {
    value: 'moonshot',
    label: 'Moonshot',
    children: [
      { value: 'moonshot-v1-8k', label: 'Moonshot V1 8K' },
      { value: 'moonshot-v1-32k', label: 'Moonshot V1 32K' },
    ],
  },
  {
    value: 'baichuan',
    label: '百川',
    children: [
      { value: 'Baichuan4', label: 'Baichuan4' },
    ],
  },
  {
    value: 'minimax',
    label: 'MiniMax',
    children: [
      { value: 'abab6.5s-chat', label: 'abab6.5s' },
    ],
  },
  {
    value: 'stepfun',
    label: '阶跃星辰',
    children: [
      { value: 'step-1-8k', label: 'Step-1 8K' },
    ],
  },
  {
    value: 'yi',
    label: '零一万物',
    children: [
      { value: 'yi-large', label: 'Yi-Large' },
    ],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    children: [
      { value: 'deepseek-chat', label: 'DeepSeek Chat' },
      { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner' },
    ],
  },
]

// 供应商状态 (模拟，实际应从后端获取)
const PROVIDER_STATUS: Record<string, { available: boolean; hasKey: boolean }> = {
  openai: { available: true, hasKey: true },
  anthropic: { available: true, hasKey: true },
  google: { available: true, hasKey: true },
  siliconflow: { available: true, hasKey: true },
  zhipu: { available: true, hasKey: true },
  moonshot: { available: true, hasKey: true },
  baichuan: { available: false, hasKey: false },
  minimax: { available: false, hasKey: false },
  stepfun: { available: false, hasKey: false },
  yi: { available: false, hasKey: false },
  deepseek: { available: true, hasKey: true },
}

const StrategyConfig: React.FC = () => {
  const [prompts, setPrompts] = useState<PromptVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  // AI 供应商和模型选择
  const [selectedProviderModels, setSelectedProviderModels] = useState<string[][]>([])
  const [providerStatus, setProviderStatus] = useState<Record<string, { available: boolean; hasKey: boolean }>>(PROVIDER_STATUS)

  const { selectedModels, setSelectedModels } = useAppStore()

  useEffect(() => {
    const load = async () => {
      try {
        const [promptRes, providerRes] = await Promise.all([
          api.getPrompts(),
          api.getAIProviders().catch(() => ({ data: [] })),
        ])
        setPrompts(promptRes.data || [])
        if (promptRes.data?.length > 0) {
          form.setFieldsValue(promptRes.data[0])
        }

        // 如果后端返回了供应商信息，更新状态
        if (providerRes.data && Array.isArray(providerRes.data)) {
          const statusMap: Record<string, { available: boolean; hasKey: boolean }> = {}
          providerRes.data.forEach((p: any) => {
            statusMap[p.name] = {
              available: p.available ?? false,
              hasKey: p.has_api_key ?? false,
            }
          })
          if (Object.keys(statusMap).length > 0) {
            setProviderStatus((prev) => ({ ...prev, ...statusMap }))
          }
        }
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [form])

  const handleActivate = async (version: string) => {
    try {
      await api.activatePrompt(version)
      message.success(`已激活策略: ${version}`)
      const res = await api.getPrompts()
      setPrompts(res.data || [])
    } catch (err) {
      message.error('激活失败')
    }
  }

  // 级联选择变更：选择多个模型用于投票
  const handleCascaderChange = (values: string[][]) => {
    setSelectedProviderModels(values)
    // 将选择转换为 provider/model 格式
    const models = values.map(([provider, model]) => `${provider}/${model}`)
    setSelectedModels(models)
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  }

  const activePrompt = prompts.find((p) => p.is_active)

  // 统计已配置和未配置的供应商
  const configuredCount = Object.values(providerStatus).filter(p => p.hasKey).length
  const totalCount = Object.keys(providerStatus).length

  return (
    <div>
      {/* AI 供应商选择器 */}
      <Card
        title={
          <Space>
            <ApiOutlined />
            <span>AI 供应商配置</span>
            <Tag color="blue">{configuredCount}/{totalCount} 已配置</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          {/* 供应商状态展示 */}
          <Col span={12}>
            <AntText strong style={{ marginBottom: 8, display: 'block' }}>供应商状态</AntText>
            <Space wrap>
              {PROVIDER_MODEL_OPTIONS.map((provider) => {
                const status = providerStatus[provider.value]
                return (
                  <Tag
                    key={provider.value}
                    icon={status?.hasKey ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                    color={status?.hasKey ? 'success' : 'default'}
                    style={{ fontSize: 13, padding: '2px 8px' }}
                  >
                    {provider.label}
                    {!status?.hasKey && <AntText type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>(未配置)</AntText>}
                  </Tag>
                )
              })}
            </Space>
            <div style={{ marginTop: 12 }}>
              <AntText type="secondary" style={{ fontSize: 12 }}>
                供应商 API Key 请在 backend/.env 中配置。已配置的供应商显示为绿色。
              </AntText>
            </div>
          </Col>

          {/* 多模型选择器 */}
          <Col span={12}>
            <AntText strong style={{ marginBottom: 8, display: 'block' }}>多模型投票选择 (供应商 -&gt; 模型)</AntText>
            <Cascader
              multiple
              options={PROVIDER_MODEL_OPTIONS.map((provider) => ({
                ...provider,
                disabled: !providerStatus[provider.value]?.hasKey,
                children: provider.children,
              }))}
              value={selectedProviderModels}
              onChange={handleCascaderChange}
              placeholder="选择供应商和模型（可多选，用于投票决策）"
              style={{ width: '100%' }}
              expandTrigger="hover"
              tagRender={(props) => {
                const { label, closable, onClose } = props
                return (
                  <Tag
                    color="blue"
                    closable={closable}
                    onClose={onClose}
                    style={{ marginRight: 3 }}
                  >
                    {label}
                  </Tag>
                )
              }}
            />
            {selectedModels.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <AntText type="secondary">
                  已选择 {selectedModels.length} 个模型用于投票决策
                </AntText>
              </div>
            )}
          </Col>
        </Row>
      </Card>

      {/* Prompt 版本管理 */}
      <Card title="Prompt 版本管理" style={{ marginBottom: 16 }}>
        <Space wrap>
          {prompts.map((p) => (
            <Card
              key={p.version}
              size="small"
              style={{ width: 200, border: p.is_active ? '2px solid #1890ff' : '1px solid #d9d9d9' }}
              actions={[
                <Button key="activate" type="link" size="small" onClick={() => handleActivate(p.version)}>
                  {p.is_active ? '使用中' : '激活'}
                </Button>,
              ]}
            >
              <Card.Meta
                title={p.name}
                description={
                  <Space direction="vertical" size={0}>
                    <AntText type="secondary">v{p.version}</AntText>
                    <AntText type="secondary" style={{ fontSize: 11 }}>{p.model_preference}</AntText>
                  </Space>
                }
              />
            </Card>
          ))}
        </Space>
      </Card>

      {activePrompt && (
        <Card title={`编辑 Prompt: ${activePrompt.name}`}>
          <Form form={form} layout="vertical" initialValues={activePrompt}>
            <Form.Item name="name" label="策略名称">
              <Input />
            </Form.Item>
            <Form.Item name="model_preference" label="默认模型">
              <Select>
                <Select.Option value="gpt-4o-mini">GPT-4o-mini</Select.Option>
                <Select.Option value="gpt-4o">GPT-4o</Select.Option>
                <Select.Option value="claude-3-5-sonnet">Claude 3.5 Sonnet</Select.Option>
                <Select.Option value="Qwen/Qwen2.5-7B-Instruct">Qwen 2.5 7B</Select.Option>
                <Select.Option value="glm-4-flash">GLM-4-Flash</Select.Option>
                <Select.Option value="moonshot-v1-8k">Moonshot V1</Select.Option>
                <Select.Option value="deepseek-chat">DeepSeek Chat</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="temperature" label="Temperature">
              <Slider min={0} max={1} step={0.1} marks={{ 0: '0', 0.5: '0.5', 1: '1' }} />
            </Form.Item>
            <Form.Item name="system_prompt" label="系统提示词">
              <TextArea rows={8} style={{ fontFamily: 'monospace', fontSize: 12 }} />
            </Form.Item>
            <Form.Item name="user_template" label="用户消息模板">
              <TextArea rows={6} style={{ fontFamily: 'monospace', fontSize: 12 }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={saving} onClick={() => message.info('保存功能待实现')}>
              保存修改
            </Button>
          </Form>
        </Card>
      )}
    </div>
  )
}

export default StrategyConfig
