// shared/api-config.js
// 前端API统一配置模块
// 使用方式: import { API_BASE_URL, getApiUrl } from '../shared/api-config'

/**
 * 从环境变量获取API基础地址
 * 优先级: 环境变量 > 默认值
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

/**
 * 各系统API地址配置
 */
export const SYSTEM_APIS = {
  quote: import.meta.env.VITE_QUOTE_API_URL || 'http://localhost:8001',
  crm: import.meta.env.VITE_CRM_API_URL || 'http://localhost:8002',
  hr: import.meta.env.VITE_HR_API_URL || 'http://localhost:8003',
  scm: import.meta.env.VITE_SCM_API_URL || 'http://localhost:8004',
  eam: import.meta.env.VITE_EAM_API_URL || 'http://localhost:8005',
  shm: import.meta.env.VITE_SHM_API_URL || 'http://localhost:8006',
  mes: import.meta.env.VITE_MES_API_URL || 'http://localhost:8007',
  procurement: import.meta.env.VITE_PROCUREMENT_API_URL || 'http://localhost:5001',
};

/**
 * 获取完整API URL
 * @param {string} endpoint - API端点路径
 * @param {string} system - 系统名称（可选）
 * @returns {string} 完整URL
 */
export function getApiUrl(endpoint, system = null) {
  const baseUrl = system ? SYSTEM_APIS[system] : API_BASE_URL;
  // 确保endpoint以/开头
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${baseUrl}${path}`;
}

/**
 * 创建统一的axios实例
 */
export function createApiClient() {
  const axios = window.axios || require('axios');

  const client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // 请求拦截器 - 添加认证Token
  client.interceptors.request.use(
    (config) => {
      const token = localStorage.getItem(
        import.meta.env.VITE_AUTH_TOKEN_KEY || 'auth_token'
      );
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }

      // 向后兼容：同时设置User-ID header
      const userStr = localStorage.getItem(
        import.meta.env.VITE_AUTH_USER_KEY || 'current_user'
      );
      if (userStr) {
        try {
          const user = JSON.parse(userStr);
          if (user.id) {
            config.headers['User-ID'] = user.id;
          }
        } catch (e) {
          // 忽略解析错误
        }
      }

      return config;
    },
    (error) => Promise.reject(error)
  );

  // 响应拦截器 - 统一处理响应
  client.interceptors.response.use(
    (response) => {
      // 如果响应包含success字段，检查是否成功
      const data = response.data;
      if (data && typeof data === 'object' && 'success' in data) {
        if (!data.success) {
          return Promise.reject(new Error(data.error || data.message || '请求失败'));
        }
      }
      return response.data;
    },
    (error) => {
      // 处理HTTP错误
      if (error.response) {
        const { status, data } = error.response;

        // 401 未认证 - 跳转登录
        if (status === 401) {
          const errorCode = data?.code || '';
          if (errorCode === 'TOKEN_EXPIRED' || errorCode === 'AUTH_REQUIRED') {
            localStorage.removeItem(import.meta.env.VITE_AUTH_TOKEN_KEY || 'auth_token');
            localStorage.removeItem(import.meta.env.VITE_AUTH_USER_KEY || 'current_user');
            // 可以在这里触发跳转到登录页
            // window.location.href = '/login';
          }
        }

        // 构造友好错误信息
        const message = data?.error || data?.message || `请求失败 (${status})`;
        return Promise.reject(new Error(message));
      }

      // 网络错误
      if (error.request) {
        return Promise.reject(new Error('网络连接失败，请检查网络'));
      }

      return Promise.reject(error);
    }
  );

  return client;
}

/**
 * 统一的API响应处理
 * @param {Promise} apiCall - API调用Promise
 * @returns {Promise} 处理后的Promise
 */
export async function handleApiResponse(apiCall) {
  try {
    const response = await apiCall;
    // 统一返回data字段
    return response.data !== undefined ? response.data : response;
  } catch (error) {
    throw error;
  }
}

/**
 * 构建查询字符串
 * @param {Object} params - 查询参数对象
 * @returns {string} 查询字符串
 */
export function buildQueryString(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value);
    }
  });
  const str = query.toString();
  return str ? `?${str}` : '';
}

export default {
  API_BASE_URL,
  SYSTEM_APIS,
  getApiUrl,
  createApiClient,
  handleApiResponse,
  buildQueryString,
};
