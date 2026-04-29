import { useEffect, useRef, useCallback, useState } from 'react'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface WSEvent {
  type: 'portfolio_update' | 'order_update' | 'ai_decision' | 'trade_execution'
  data: any
  timestamp?: string
}

interface UseWebSocketOptions {
  channels?: string[]
  onEvent?: (event: WSEvent) => void
  autoReconnect?: boolean
  reconnectInterval?: number
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    channels = [],
    onEvent,
    autoReconnect = true,
    reconnectInterval = 3000,
  } = options

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    // 使用当前页面 host，通过 vite proxy 转发
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    setConnectionStatus('connecting')

    try {
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        setConnectionStatus('connected')
        clearReconnectTimer()
        // 订阅频道
        if (channels.length > 0) {
          ws.send(JSON.stringify({ action: 'subscribe', channels }))
        }
      }

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data)

          // 处理不同事件类型
          if (parsed.type) {
            const wsEvent: WSEvent = {
              type: parsed.type,
              data: parsed.data || parsed,
              timestamp: parsed.timestamp,
            }
            onEvent?.(wsEvent)
          }
        } catch (e) {
          console.error('WS 消息解析错误', e)
        }
      }

      ws.onclose = (event) => {
        setConnectionStatus('disconnected')
        wsRef.current = null

        // 自动重连
        if (autoReconnect && !event.wasClean) {
          reconnectTimerRef.current = setTimeout(connect, reconnectInterval)
        }
      }

      ws.onerror = () => {
        setConnectionStatus('error')
      }

      wsRef.current = ws
    } catch (e) {
      console.error('WebSocket 连接失败', e)
      setConnectionStatus('error')
      if (autoReconnect) {
        reconnectTimerRef.current = setTimeout(connect, reconnectInterval)
      }
    }
  }, [channels.join(','), onEvent, autoReconnect, reconnectInterval, clearReconnectTimer])

  const disconnect = useCallback(() => {
    clearReconnectTimer()
    if (wsRef.current) {
      wsRef.current.close(1000, '用户主动断开')
      wsRef.current = null
    }
    setConnectionStatus('disconnected')
  }, [clearReconnectTimer])

  const sendMessage = useCallback((data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return {
    connectionStatus,
    isConnected: connectionStatus === 'connected',
    wsRef,
    sendMessage,
    reconnect: connect,
    disconnect,
  }
}
