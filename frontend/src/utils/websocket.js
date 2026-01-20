/**
 * WebSocket 客户端管理器
 *
 * 提供实时推送功能，自动重连，心跳检测
 * 使用 JWT token 进行认证
 */

// 从 api 导入统一的 storage key 函数（确保前缀一致）
import { getStorageKey } from '@/api'

class WebSocketManager {
  constructor() {
    this.ws = null
    this.accountId = null
    this.token = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 3000
    // 心跳间隔设为 30 秒，与后端保持一致（后端 heartbeat_interval = 30）
    this.heartbeatInterval = 30000
    this.heartbeatTimer = null
    this.listeners = new Map()
    this.isConnecting = false
    this.isManualClose = false
    // 连接版本号，用于防止过期重连
    this.connectionVersion = 0
    // 初始化标志，确保只初始化一次
    this.isInitialized = false
  }

  /**
   * 连接 WebSocket
   * @param {number} accountId - 账户ID（仅用于记录，认证使用 token）
   */
  connect(accountId) {
    // 更健壮的连接状态检查
    if (this.isConnecting) {
      console.log('[WS] Already connecting, skip')
      return
    }

    if (this.ws) {
      const state = this.ws.readyState
      if (state === WebSocket.CONNECTING || state === WebSocket.OPEN) {
        console.log('[WS] Already connected or connecting, skip')
        return
      }
    }

    // 获取 token
    this.token = localStorage.getItem(getStorageKey('token'))
    if (!this.token) {
      console.warn('[WS] No token available, cannot connect')
      return
    }

    // 检查 token 是否可能已过期（简单检查 JWT 格式和 exp）
    if (!this.isTokenValid(this.token)) {
      console.warn('[WS] Token appears expired, triggering re-login')
      window.dispatchEvent(new CustomEvent('token-expired'))
      return
    }

    this.accountId = accountId
    this.isConnecting = true
    this.isManualClose = false
    this.connectionVersion++
    const currentVersion = this.connectionVersion

    // 构建 WebSocket URL - 使用 subprotocol 传递 token（更安全，不暴露在 URL/日志中）
    const isDev = import.meta.env.DEV
    const apiBaseUrl = isDev ? 'http://127.0.0.1:2000' : 'https://jzchardware.cn/email'
    const wsProtocol = apiBaseUrl.startsWith('https') ? 'wss:' : 'ws:'
    const apiUrl = new URL(apiBaseUrl)
    // 不再将 token 放在 URL 中，改用 subprotocol 传递
    const wsUrl = `${wsProtocol}//${apiUrl.host}${apiUrl.pathname}/ws`

    console.log(`[WS] Connecting (version ${currentVersion})...`)

    try {
      // 使用 Sec-WebSocket-Protocol header 传递 token（格式：auth.<base64-encoded-token>）
      // 这样 token 不会暴露在 URL、浏览器历史和服务器日志中
      const tokenProtocol = `auth.${btoa(this.token).replace(/=/g, '')}`
      this.ws = new WebSocket(wsUrl, [tokenProtocol])

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

        // 认证失败不重连
        if (event.code === 4001) {
          console.log('[WS] Authentication failed, not reconnecting')
          return
        }

        // 自动重连（非手动关闭，且版本未变）
        if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          const versionAtClose = currentVersion
          console.log(`[WS] Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)
          // 延迟后再次检查是否仍需要重连（避免用户退出后仍尝试重连）
          setTimeout(() => {
            // 检查版本是否已变化（说明已有新连接或已手动关闭）
            if (!this.isManualClose && this.connectionVersion === versionAtClose) {
              this.connect(this.accountId)
            } else {
              console.log('[WS] Reconnect cancelled (version changed or manual close)')
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
    this.connectionVersion++  // 增加版本号，使待执行的重连失效
    this.isManualClose = true
    this.stopHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.token = null
    this.reconnectAttempts = 0
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

  /**
   * 检查 JWT token 是否有效（未过期）
   * @param {string} token - JWT token
   * @returns {boolean}
   */
  isTokenValid(token) {
    if (!token) return false
    try {
      // JWT 格式: header.payload.signature
      const parts = token.split('.')
      if (parts.length !== 3) return false

      // 解析 payload
      const payload = JSON.parse(atob(parts[1]))

      // 检查过期时间（exp 是 Unix 时间戳，秒）
      if (payload.exp) {
        const expTime = payload.exp * 1000  // 转为毫秒
        const now = Date.now()
        // 提前 5 分钟判定为过期，留出缓冲时间
        if (now > expTime - 5 * 60 * 1000) {
          console.log('[WS] Token will expire soon or already expired')
          return false
        }
      }
      return true
    } catch (e) {
      console.error('[WS] Failed to parse token:', e)
      return false
    }
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
