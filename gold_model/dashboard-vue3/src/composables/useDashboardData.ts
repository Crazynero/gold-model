import { ref, onMounted, onUnmounted } from 'vue'

/** V6 黄金 Dashboard 数据契约（dashboard_data.json + execution_data.json） */

export interface DashboardData {
  overview?: Record<string, string | number>
  strategies?: StrategyRow[]
  features?: FeatureRow[]
  ml_models?: MLModelRow[]
  current_factors?: FactorRow[]
  raw_data?: RawDataRow[]
  v5_holdout?: HoldoutRow[]
  v5_regression?: RegressionRow[]
  v5_feature_count?: number
  v5_original_feature_count?: number
  signal_stats?: SignalStats
}

export interface StrategyRow {
  策略?: string
  年化收益?: string
  年化波动?: string
  夏普?: string
  最大回撤?: string
  胜率?: string
  Calmar?: string
  累计收益?: string
  vs买入持有?: string
}

export interface FeatureRow { name: string; avg: number }
export interface MLModelRow { period: string; accuracy: string; auc: string; ic: string }
export interface FactorRow { name: string; value: string; momentum: string; signal: string }

export interface RawDataRow {
  日期?: string
  金价?: string
  Regime?: string
  仓位?: string
  加权概率?: string
  [key: string]: string | undefined
}

export interface HoldoutRow {
  strategy: string
  sharpe: number
  full_sharpe: number
}
export interface RegressionRow {
  horizon: string
  r2: number
  dir_acc: string
}
export interface SignalStats {
  hit_rate_20d?: string
  wf_base?: string
  deviation?: string
}

export interface ExecutionData {
  current?: { position?: number | string }
  scenarios?: any[]
  execution_rules?: any
  signal_stats?: SignalStats
  cost_comparison?: Array<{ scenario: string; annual_cost: number }>
  position_history?: {
    dates: string[]
    positions: number[]
    gold_prices: number[]
  }
}

/** 全局响应式状态 */
export const dashboardData = ref<DashboardData>({})
export const executionData = ref<ExecutionData>({})
export const driftHistory = ref<any[]>([])
export const dataReady = ref(false)
export const dataError = ref<string | null>(null)
export const lastUpdate = ref<Date | null>(null)
export const updateSource = ref<'fetch' | 'window' | 'api' | 'ws' | null>(null)

/** API base URL（生产环境配置后启用API模式） */
export const apiBase = ref<string>('')
/** WebSocket 连接状态 */
export const wsConnected = ref(false)
export const wsMessageCount = ref(0)
/** API 探测状态：'detecting' | 'online' | 'offline' */
export const apiStatus = ref<'detecting' | 'online' | 'offline'>('detecting')

let pollTimer: any = null
let ws: WebSocket | null = null
const POLL_INTERVAL = 30000  // 30秒
const API_DETECT_TIMEOUT = 2500  // 探测超时 2.5s
const API_DEFAULT_URL = 'http://localhost:8000'

/** 从overview中按key子串匹配取值（容错中文键名变化） */
export function extractValue(o: Record<string, string | number> | undefined, k: string): string | null {
  if (!o) return null
  for (const key in o) {
    if (key.includes(k)) return String(o[key])
  }
  return null
}

/** 简单移动平均 */
export function simpleMA(d: number[], p: number): (number | null)[] {
  const r: (number | null)[] = []
  for (let i = 0; i < d.length; i++) {
    if (i < p - 1) { r.push(null); continue }
    let s = 0
    for (let j = 0; j < p; j++) s += d[i - j]
    r.push(s / p)
  }
  return r
}

/** 加载JSON数据 — 优先API，其次fetch本地JSON，失败回退到window全局 */
export async function loadAll() {
  dataReady.value = false
  dataError.value = null

  // 1) 优先 API 模式
  if (apiBase.value) {
    try {
      const resp = await fetch(`${apiBase.value}/api/state`)
      if (resp.ok) {
        const d = await resp.json()
        dashboardData.value = d.dashboard || {}
        executionData.value = d.execution || {}
        dataReady.value = true
        lastUpdate.value = new Date()
        updateSource.value = 'api'
        connectWS()
        return
      }
    } catch (e) {
      console.warn('[data] API load failed, fallback to local fetch')
    }
  }

  // 2) 本地 fetch（http(s)://协议下生效）
  try {
    const [dRes, eRes] = await Promise.all([
      fetch('./dashboard_data.json').catch(() => null),
      fetch('./execution_data.json').catch(() => null)
    ])
    if (dRes && dRes.ok) {
      dashboardData.value = await dRes.json()
      if (eRes && eRes.ok) executionData.value = await eRes.json()
      dataReady.value = true
      lastUpdate.value = new Date()
      updateSource.value = 'fetch'
      return
    }
    throw new Error('fetch failed')
  } catch (e: any) {
    // 3) 回退：window全局（file://协议下由HTML inline script注入）
    const w = window as any
    if (w.__DASHBOARD_DATA__) {
      dashboardData.value = w.__DASHBOARD_DATA__
      executionData.value = w.__EXECUTION_DATA__ || {}
      driftHistory.value = w.__DRIFT_DATA__ || []
      dataReady.value = true
      lastUpdate.value = new Date()
      updateSource.value = 'window'
      return
    }
    // 4) 最终fallback：空数据
    dashboardData.value = {
      overview: { 加权集成概率: '0%', 建议操作: '数据加载失败', 当前Regime: '--', 预测基准日: '--', 当前金价: '$----' },
      strategies: [], features: [], ml_models: [], current_factors: [], raw_data: []
    }
    dataError.value = e?.message || 'load failed'
    dataReady.value = true
  }
}

/** 启动30s轮询 — 仅 http(s):// 协议下生效 */
export function startPolling() {
  stopPolling()
  const isHttp = typeof window !== 'undefined' && /^https?:/.test(window.location.protocol)
  if (!isHttp || apiBase.value) return  // API模式下用WS替代轮询
  pollTimer = setInterval(async () => {
    try {
      const [dRes, eRes] = await Promise.all([
        fetch('./dashboard_data.json?t=' + Date.now()).catch(() => null),
        fetch('./execution_data.json?t=' + Date.now()).catch(() => null)
      ])
      if (dRes && dRes.ok) {
        dashboardData.value = await dRes.json()
        if (eRes && eRes.ok) executionData.value = await eRes.json()
        lastUpdate.value = new Date()
        updateSource.value = 'fetch'
      }
    } catch (e) { /* 静默失败 */ }
  }, POLL_INTERVAL)
}

export function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

/** WebSocket 连接 — 仅 API 模式下启用 */
export function connectWS() {
  if (!apiBase.value) return
  if (ws) { try { ws.close() } catch {} ws = null }
  const wsUrl = apiBase.value.replace(/^http/, 'ws') + '/ws'
  try {
    ws = new WebSocket(wsUrl)
    ws.onopen = () => { wsConnected.value = true }
    ws.onclose = () => { wsConnected.value = false; setTimeout(() => connectWS(), 5000) }
    ws.onerror = () => { wsConnected.value = false }
    ws.onmessage = (ev) => {
      wsMessageCount.value++
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'initial' || msg.type === 'state_update') {
          if (msg.data?.dashboard) dashboardData.value = msg.data.dashboard
          if (msg.data?.execution) executionData.value = msg.data.execution
          lastUpdate.value = new Date()
          updateSource.value = 'ws'
        }
      } catch {}
    }
  } catch (e) {
    console.warn('[ws] connect failed', e)
  }
}

export function disconnectWS() {
  if (ws) { try { ws.close() } catch {} ws = null }
  wsConnected.value = false
}

/** 设置 API base URL — 切换到 API 模式 */
export function setApiBase(url: string) {
  apiBase.value = url
  if (url) {
    stopPolling()
    loadAll()
    connectWS()
  } else {
    disconnectWS()
    loadAll()
    startPolling()
  }
}

/** 自动探测本地 API 是否可用，成功则启用 API 模式，失败回退 JSON */
export async function autoDetectApi(url: string = API_DEFAULT_URL): Promise<boolean> {
  apiStatus.value = 'detecting'
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), API_DETECT_TIMEOUT)
    const resp = await fetch(`${url}/api/health`, { signal: ctrl.signal })
    clearTimeout(timer)
    if (resp.ok) {
      const d = await resp.json()
      if (d?.status === 'ok') {
        apiBase.value = url
        apiStatus.value = 'online'
        return true
      }
    }
  } catch {
    // 探测失败（连接拒绝/超时/CORS），静默回退
  }
  apiBase.value = ''
  apiStatus.value = 'offline'
  return false
}

/** 手动重试 API 探测（用户在 UI 点击重试时调用） */
export async function retryApiDetection(url?: string) {
  const ok = await autoDetectApi(url)
  if (ok) {
    stopPolling()
    await loadAll()
    connectWS()
  }
  return ok
}

export function useDashboard() {
  onMounted(async () => {
    // 先探测本地 API，成功启用 API 模式（读 SQLite 历史），失败回退 JSON 模式
    if (apiStatus.value === 'detecting') {
      const ok = await autoDetectApi()
      if (ok) {
        await loadAll()  // API 模式加载
        connectWS()
        return
      }
    }
    // JSON 回退模式
    if (!dataReady.value) loadAll()
    startPolling()
  })
  onUnmounted(() => {
    stopPolling()
    disconnectWS()
  })
  return {
    dashboardData, executionData, dataReady, dataError,
    lastUpdate, updateSource, apiBase, apiStatus,
    wsConnected, wsMessageCount
  }
}

// === 高级 API（配合 E 接口）===

/** 从 SQLite 查历史信号（需 API 模式，返回字段与 drift_history 格式对齐便于复用） */
export async function fetchDbHistory(days: number = 90, regime?: string) {
  if (!apiBase.value) return null
  try {
    const params = new URLSearchParams({ days: String(days) })
    if (regime) params.append('regime', regime)
    const resp = await fetch(`${apiBase.value}/api/db/history?${params}`)
    if (!resp.ok) return null
    const r = await resp.json()
    // 把 SQLite 字段映射成 drift_history 兼容格式
    const rows = (r?.data || []).map((s: any) => ({
      timestamp: s.run_at,
      run_date: s.base_date,
      current_state: {
        regime: s.regime || '震荡',
        probability: s.weighted_prob ?? 0,
        position: s.position ?? 0,
        gold_price: s.gold_price ?? 0,
      },
      ml_metrics: {},  // SQLite 不存逐 horizon 指标，留空
      best_sharpe: s.v3e_sharpe ?? 0,
      signal_backtest: {
        recent_20_hit_rate: s.hit_rate_20d ?? 0,
      },
      // SQLite 独有字段
      prob_5d: s.prob_5d,
      prob_10d: s.prob_10d,
      prob_20d: s.prob_20d,
      prob_60d: s.prob_60d,
      holdout_sharpe: s.holdout_sharpe,
      holdout_decay: s.holdout_decay,
      signal_action: s.signal_action,
      pos_factor: s.pos_factor,
    }))
    return rows
  } catch { return null }
}

export async function fetchHistory(days: number = 30, regime?: string) {
  if (!apiBase.value) return null
  try {
    const params = new URLSearchParams({ days: String(days) })
    if (regime) params.append('regime', regime)
    const resp = await fetch(`${apiBase.value}/api/history?${params}`)
    if (!resp.ok) return null
    return await resp.json()
  } catch (e) { return null }
}

export async function fetchDrift() {
  if (!apiBase.value) return null
  try {
    const resp = await fetch(`${apiBase.value}/api/drift`)
    if (!resp.ok) return null
    return await resp.json()
  } catch (e) { return null }
}

export async function fetchRecentSignals(limit: number = 10) {
  if (!apiBase.value) return null
  try {
    const resp = await fetch(`${apiBase.value}/api/signals/recent?limit=${limit}`)
    if (!resp.ok) return null
    return await resp.json()
  } catch (e) { return null }
}
