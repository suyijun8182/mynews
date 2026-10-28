import axios from 'axios'
import { reactive } from 'vue'
import router from './router.js'

export const auth = reactive({ token: read('mynews.token'), username: read('mynews.user') })

function read(k) {
  try { return localStorage.getItem(k) || '' } catch (e) { return '' }
}

export function setAuth(token, username) {
  auth.token = token || ''
  auth.username = username || ''
  try {
    if (token) { localStorage.setItem('mynews.token', token); localStorage.setItem('mynews.user', username) }
    else { ['mynews.token', 'mynews.user'].forEach(k => localStorage.removeItem(k)) }
  } catch (e) { /* 隐私模式 */ }
}

const http = axios.create({ baseURL: '/api', timeout: 20000 })

http.interceptors.request.use(cfg => {
  if (auth.token) cfg.headers.Authorization = `Bearer ${auth.token}`
  return cfg
})

http.interceptors.response.use(r => r.data, err => {
  const url = err.config?.url || ''
  if (err.response?.status === 503 && !url.startsWith('/setup/')) {
    setupState.configured = false
    router.push({ name: 'setup' })
  } else if (err.response?.status === 401 && !url.startsWith('/auth/') && !url.startsWith('/public/')) {
    setAuth('')
    router.push({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
  }
  err.message = err.response?.data?.detail || err.message
  if (Array.isArray(err.message)) err.message = err.message.map(x => x.msg).join('；')
  return Promise.reject(err)
})

// 安装向导状态：数据库是否已配置（未配置时所有页面都先进入 /setup）
export const setupState = reactive({ checked: false, configured: true, present: true })

export async function checkSetup() {
  const r = await http.get('/setup/status')
  Object.assign(setupState, { checked: true, configured: r.configured, present: r.config_present })
  return setupState
}

export default http
