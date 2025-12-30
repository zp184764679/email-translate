/**
 * 离线草稿存储服务
 *
 * 使用 IndexedDB 存储草稿，支持：
 * - 自动保存（每30秒）
 * - 网络断开时提示
 * - 恢复连接后自动同步
 */

const DB_NAME = 'EmailDraftsDB'
const DB_VERSION = 1
const STORE_NAME = 'drafts'
const AUTO_SAVE_INTERVAL = 30000 // 30秒

let db = null
let autoSaveTimer = null

/**
 * 初始化 IndexedDB
 */
export async function initOfflineStorage() {
  return new Promise((resolve, reject) => {
    if (db) {
      resolve(db)
      return
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onerror = () => {
      console.error('[OfflineDrafts] 初始化失败:', request.error)
      reject(request.error)
    }

    request.onsuccess = () => {
      db = request.result
      console.log('[OfflineDrafts] 初始化成功')
      resolve(db)
    }

    request.onupgradeneeded = (event) => {
      const database = event.target.result

      // 创建草稿存储
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, {
          keyPath: 'localId',
          autoIncrement: true
        })
        store.createIndex('serverId', 'serverId', { unique: false })
        store.createIndex('updatedAt', 'updatedAt', { unique: false })
        store.createIndex('syncStatus', 'syncStatus', { unique: false })
        console.log('[OfflineDrafts] 数据库结构已创建')
      }
    }
  })
}

/**
 * 保存草稿到本地
 * @param {Object} draft - 草稿对象
 * @returns {Promise<number>} 本地 ID
 */
export async function saveLocalDraft(draft) {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite')
    const store = transaction.objectStore(STORE_NAME)

    const draftData = {
      ...draft,
      localId: draft.localId || undefined,
      serverId: draft.id || null,
      updatedAt: new Date().toISOString(),
      syncStatus: 'pending' // pending, synced, conflict
    }

    const request = draftData.localId
      ? store.put(draftData)
      : store.add(draftData)

    request.onsuccess = () => {
      console.log('[OfflineDrafts] 草稿已保存到本地:', request.result)
      resolve(request.result)
    }

    request.onerror = () => {
      console.error('[OfflineDrafts] 保存失败:', request.error)
      reject(request.error)
    }
  })
}

/**
 * 获取所有本地草稿
 * @returns {Promise<Array>}
 */
export async function getLocalDrafts() {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.getAll()

    request.onsuccess = () => {
      resolve(request.result || [])
    }

    request.onerror = () => {
      reject(request.error)
    }
  })
}

/**
 * 获取未同步的草稿
 * @returns {Promise<Array>}
 */
export async function getPendingDrafts() {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    const index = store.index('syncStatus')
    const request = index.getAll('pending')

    request.onsuccess = () => {
      resolve(request.result || [])
    }

    request.onerror = () => {
      reject(request.error)
    }
  })
}

/**
 * 通过本地 ID 获取草稿
 * @param {number} localId
 * @returns {Promise<Object|null>}
 */
export async function getLocalDraftById(localId) {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.get(localId)

    request.onsuccess = () => {
      resolve(request.result || null)
    }

    request.onerror = () => {
      reject(request.error)
    }
  })
}

/**
 * 删除本地草稿
 * @param {number} localId
 */
export async function deleteLocalDraft(localId) {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.delete(localId)

    request.onsuccess = () => {
      console.log('[OfflineDrafts] 草稿已删除:', localId)
      resolve()
    }

    request.onerror = () => {
      reject(request.error)
    }
  })
}

/**
 * 标记草稿为已同步
 * @param {number} localId
 * @param {number} serverId - 服务器返回的 ID
 */
export async function markDraftSynced(localId, serverId) {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite')
    const store = transaction.objectStore(STORE_NAME)

    const getRequest = store.get(localId)

    getRequest.onsuccess = () => {
      const draft = getRequest.result
      if (draft) {
        draft.serverId = serverId
        draft.syncStatus = 'synced'
        draft.syncedAt = new Date().toISOString()

        const putRequest = store.put(draft)
        putRequest.onsuccess = () => resolve()
        putRequest.onerror = () => reject(putRequest.error)
      } else {
        resolve()
      }
    }

    getRequest.onerror = () => reject(getRequest.error)
  })
}

/**
 * 清理已同步的旧草稿（保留最近7天）
 */
export async function cleanupSyncedDrafts() {
  if (!db) await initOfflineStorage()

  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - 7)

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    const index = store.index('syncStatus')
    const request = index.openCursor(IDBKeyRange.only('synced'))

    let deletedCount = 0

    request.onsuccess = (event) => {
      const cursor = event.target.result
      if (cursor) {
        const draft = cursor.value
        if (new Date(draft.syncedAt) < cutoffDate) {
          cursor.delete()
          deletedCount++
        }
        cursor.continue()
      } else {
        console.log(`[OfflineDrafts] 已清理 ${deletedCount} 个旧草稿`)
        resolve(deletedCount)
      }
    }

    request.onerror = () => reject(request.error)
  })
}

/**
 * 同步所有待同步草稿到服务器
 * @param {Function} syncFn - 同步函数 (draft) => Promise<serverId>
 */
export async function syncPendingDrafts(syncFn) {
  const pendingDrafts = await getPendingDrafts()

  if (pendingDrafts.length === 0) {
    return { synced: 0, failed: 0 }
  }

  let synced = 0
  let failed = 0

  for (const draft of pendingDrafts) {
    try {
      const serverId = await syncFn(draft)
      if (serverId) {
        await markDraftSynced(draft.localId, serverId)
        synced++
      }
    } catch (error) {
      console.error('[OfflineDrafts] 同步失败:', error)
      failed++
    }
  }

  console.log(`[OfflineDrafts] 同步完成: 成功 ${synced}, 失败 ${failed}`)
  return { synced, failed }
}

/**
 * 启动自动保存定时器
 * @param {Function} saveFn - 保存函数，返回当前草稿内容
 */
export function startAutoSave(saveFn) {
  stopAutoSave()

  autoSaveTimer = setInterval(async () => {
    try {
      const draft = saveFn()
      if (draft && (draft.body_chinese || draft.subject)) {
        await saveLocalDraft(draft)
        console.log('[OfflineDrafts] 自动保存成功')
      }
    } catch (error) {
      console.error('[OfflineDrafts] 自动保存失败:', error)
    }
  }, AUTO_SAVE_INTERVAL)

  console.log('[OfflineDrafts] 自动保存已启动')
}

/**
 * 停止自动保存
 */
export function stopAutoSave() {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
    console.log('[OfflineDrafts] 自动保存已停止')
  }
}

/**
 * 检查是否在线
 */
export function isOnline() {
  return navigator.onLine
}

/**
 * 监听网络状态变化
 * @param {Function} onOnline - 恢复在线时的回调
 * @param {Function} onOffline - 断网时的回调
 */
export function watchNetworkStatus(onOnline, onOffline) {
  window.addEventListener('online', () => {
    console.log('[OfflineDrafts] 网络已恢复')
    if (onOnline) onOnline()
  })

  window.addEventListener('offline', () => {
    console.log('[OfflineDrafts] 网络已断开')
    if (onOffline) onOffline()
  })
}

/**
 * 获取本地草稿数量
 */
export async function getLocalDraftCount() {
  if (!db) await initOfflineStorage()

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    const request = store.count()

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export default {
  initOfflineStorage,
  saveLocalDraft,
  getLocalDrafts,
  getPendingDrafts,
  getLocalDraftById,
  deleteLocalDraft,
  markDraftSynced,
  cleanupSyncedDrafts,
  syncPendingDrafts,
  startAutoSave,
  stopAutoSave,
  isOnline,
  watchNetworkStatus,
  getLocalDraftCount
}
