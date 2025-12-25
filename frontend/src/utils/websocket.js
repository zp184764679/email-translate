/**
 * WebSocket 客户端管理器
 *
 * 提供实时推送功能，自动重连，心跳检测
 */

class WebSocketManager {
  constructor() {
    this.ws = null
    this.accountId = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 3000
    this.heartbeatInterval = 25000
    this.heartbeatTimer = null
    this.listeners = new Map()
    this.isConnecting = false
    this.isManualClose = false
  }

  /**
   * 连接 WebSocket
   * @param {number} accountId - 账户ID
   */
  connect(accountId) {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
      console.log('[WS] Already connected or connecting')
      return
    }

    this.accountId = accountId
    this.isConnecting = true
    this.isManualClose = false

    // 构建 WebSocket URL - 使用与 API 相同的逻辑
    const isDev = import.meta.env.DEV
    const apiBaseUrl = isDev ? 'http://127.0.0.1:2000' : 'https://jzchardware.cn/email'
    const wsProtocol = apiBaseUrl.startsWith('https') ? 'wss:' : 'ws:'
    const apiUrl = new URL(apiBaseUrl)
    const wsUrl = `${wsProtocol}//${apiUrl.host}${apiUrl.pathname}/ws/${accountId}`

    console.log(`[WS] Connecting to ${wsUrl}`)

    try {
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        const wasReconnecting = this.reconnectAttempts > 0
        console.log('[WS] Connected' + (wasReconnecting ? ' (reconnected)' : ''))
        this.isConnecting = false
        this.reconnectAttempts = 0
        this.startHeartbeat()
        this.emit('connected', { accountId })

        // 如果是重连成功，触发额外的重连事件供组件刷新数据
        if (wasReconnecting) {
          this.emit('reconnected', { accountId })
          // 同时触发全局事件
          window.dispatchEvent(new CustomEvent('ws:reconnected'))
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (e) {
          console.error('[WS] Failed to parse message:', e)
        }
      }

      this.ws.onclose = (event) => {
        console.log(`[WS] Disconnected: ${event.code} ${event.reason}`)
        this.isConnecting = false
        this.stopHeartbeat()
        this.emit('disconnected', { code: event.code, reason: event.reason })

        // 自动重连（非手动关闭）
        if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          console.log(`[WS] Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)
          // 延迟后再次检查是否仍需要重连（避免用户退出后仍尝试重连）
          setTimeout(() => {
            if (!this.isManualClose) {
              this.connect(this.accountId)
            } else {
              console.log('[WS] Reconnect cancelled (manual close)')
            }
          }, this.reconnectDelay)
        }
      }

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error)
        this.isConnecting = false
        this.emit('error', error)
      }
    } catch (e) {
      console.error('[WS] Failed to create WebSocket:', e)
      this.isConnecting = false
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    this.isManualClose = true
    this.stopHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    console.log('[WS] Manually disconnected')
  }

  /**
   * 处理收到的消息
   * @param {Object} message - 消息对象
   */
  handleMessage(message) {
    const { type, data, timestamp } = message

    console.log(`[WS] Received: ${type}`, data)

    // 处理心跳响应
    if (type === 'pong' || type === 'heartbeat') {
      return
    }

    // 触发对应事件
    this.emit(type, data)

    // 触发通用消息事件
    this.emit('message', { type, data, timestamp })
  }

  /**
   * 发送消息
   * @param {Object} data - 消息数据
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.warn('[WS] Cannot send, not connected')
    }
  }

  /**
   * 开始心跳
   */
  startHeartbeat() {
    this.stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, this.heartbeatInterval)
  }

  /**
   * 停止心跳
   */
  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  /**
   * 订阅事件
   * @param {string} event - 事件名称
   * @param {Function} callback - 回调函数
   * @returns {Function} 取消订阅函数
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event).add(callback)

    // 返回取消订阅函数
    return () => {
      const callbacks = this.listeners.get(event)
      if (callbacks) {
        callbacks.delete(callback)
      }
    }
  }

  /**
   * 取消订阅事件
   * @param {string} event - 事件名称
   * @param {Function} callback - 回调函数（可选，不传则清除所有）
   */
  off(event, callback) {
    if (callback) {
      const callbacks = this.listeners.get(event)
      if (callbacks) {
        callbacks.delete(callback)
      }
    } else {
      this.listeners.delete(event)
    }
  }

  /**
   * 触发事件
   * @param {string} event - 事件名称
   * @param {*} data - 事件数据
   */
  emit(event, data) {
    const callbacks = this.listeners.get(event)
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(data)
        } catch (e) {
          console.error(`[WS] Event handler error (${event}):`, e)
        }
      })
    }
  }

  /**
   * 检查连接状态
   * @returns {boolean}
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN
  }
}

// 单例实例
const wsManager = new WebSocketManager()

export default wsManager

// 便捷函数
export function connectWebSocket(accountId) {
  wsManager.connect(accountId)
}

export function disconnectWebSocket() {
  wsManager.disconnect()
}

export function onWebSocketEvent(event, callback) {
  return wsManager.on(event, callback)
}

export function sendWebSocketMessage(data) {
  wsManager.send(data)
}
