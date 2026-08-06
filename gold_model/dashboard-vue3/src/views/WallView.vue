<template>
  <div class="wall-grid">
    <!-- Cell 1: Big signal readout -->
    <div class="wall-cell span-row-2">
      <div class="wall-cell-title">
        <span>CURRENT SIGNAL</span>
        <span class="meta">BASE {{ baseDate }}</span>
      </div>
      <div class="big-signal">
        <div class="big-prob">{{ prob }}</div>
        <div class="big-prob-label">集成看多概率</div>
        <div class="big-action">
          <span>{{ action }}</span>
        </div>
        <div class="signal-grid">
          <div>
            <div class="mini-label">REGIME</div>
            <div class="mini-value" :style="{ color: regimeColor }">{{ regime }}</div>
          </div>
          <div>
            <div class="mini-label">PRICE</div>
            <div class="mini-value text-gold">{{ goldPrice }}</div>
          </div>
          <div>
            <div class="mini-label">VOL60</div>
            <div class="mini-value text-2">{{ vol60d }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Cell 2: Multi-horizon -->
    <div class="wall-cell">
      <div class="wall-cell-title">
        <span>MULTI-HORIZON</span>
        <span class="meta">5D/10D/20D/60D</span>
      </div>
      <ProbBars :items="multiHorizon" :height="120" />
    </div>

    <!-- Cell 3: Key metrics -->
    <div class="wall-cell">
      <div class="wall-cell-title"><span>KEY METRICS</span></div>
      <div class="key-metric-grid">
        <div>
          <div class="mini-label">SHARPE</div>
          <div class="key-value text-pos">{{ sharpe }}</div>
        </div>
        <div>
          <div class="mini-label">MAX DD</div>
          <div class="key-value text-neg">{{ maxDD }}</div>
        </div>
        <div>
          <div class="mini-label">ACC 20D</div>
          <div class="key-value text-acc">{{ acc20 }}</div>
        </div>
        <div>
          <div class="mini-label">AUC 20D</div>
          <div class="key-value text-acc">{{ auc20 }}</div>
        </div>
      </div>
    </div>

    <!-- Cell 4: Price chart -->
    <div class="wall-cell span-2">
      <div class="wall-cell-title">
        <span>GOLD PRICE // WEEKLY K</span>
        <span class="meta">{{ goldPrice }}</span>
      </div>
      <ChartBox :option="priceOpt" height="160px" />
    </div>

    <!-- Cell 5: Strategy nav -->
    <div class="wall-cell">
      <div class="wall-cell-title"><span>STRATEGY NAV</span></div>
      <ChartBox :option="strategyOpt" height="160px" />
    </div>

    <!-- Cell 6: Holdout decay -->
    <div class="wall-cell">
      <div class="wall-cell-title"><span>OVERFIT CHECK</span></div>
      <div class="decay-block">
        <div class="decay-value">{{ decay }}</div>
        <div class="mini-label">SHARPE DECAY</div>
        <div class="decay-detail">
          FULL <span class="text-pos">{{ full }}</span> → OOS <span class="text-neg">{{ oos }}</span>
        </div>
        <div class="decay-detail">
          FEATURES <span class="text-acc">{{ feat }}</span> | DIR <span class="text-acc">{{ dirAcc }}</span>
        </div>
      </div>
    </div>

    <!-- Cell 7: Top 8 features -->
    <div class="wall-cell span-2">
      <div class="wall-cell-title"><span>TOP 8 FEATURES</span></div>
      <ChartBox :option="featOpt" height="160px" />
    </div>

    <!-- Cell 8: Position history -->
    <div class="wall-cell span-row">
      <div class="wall-cell-title">
        <span>POSITION HISTORY (250D)</span>
        <span class="meta">MODEL / ETF / FUT / GOLD</span>
      </div>
      <ChartBox :option="posOpt" height="180px" />
    </div>

    <!-- Cell 9: Alerts stream -->
    <div class="wall-cell span-2">
      <div class="wall-cell-title">
        <span>ALERTS STREAM</span>
        <span class="meta">{{ alerts.length }} ACTIVE</span>
      </div>
      <div class="alerts-list">
        <div v-for="(a, i) in alerts" :key="i" :class="['alert-item', `sev-${a.severity}`]">
          <span class="alert-sev">{{ a.severity.toUpperCase() }}</span>
          <span class="alert-type">{{ a.type }}</span>
          <span class="alert-title">{{ a.title }}</span>
          <span class="alert-detail">{{ a.detail }}</span>
          <span class="alert-time">{{ a.time }}</span>
        </div>
        <div v-if="alerts.length === 0" class="no-alerts">NO ACTIVE ALERTS</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import ProbBars from '@/components/ProbBars.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, executionData, driftHistory, extractValue, simpleMA } from '@/composables/useDashboardData'

const C = {
  bg: '#04060a',
  accent: '#00d4ff',
  pos: '#00ff9c',
  neg: '#ff3860',
  warn: '#ffb800',
  gold: '#ffb020',
  text2: '#8b949e',
  text3: '#6e7681',
  border: 'rgba(0,212,255,0.14)',
  grid: 'rgba(0,212,255,0.05)'
}

const prob = computed(() => extractValue(dashboardData.value.overview, '加权集成概率') || '--%')
const action = computed(() => extractValue(dashboardData.value.overview, '建议操作') || '空仓观望')
const regime = computed(() => extractValue(dashboardData.value.overview, '当前Regime') || '震荡')
const baseDate = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')
const goldPrice = computed(() => extractValue(dashboardData.value.overview, '当前金价') || '$----')
const vol60d = computed(() => {
  const d = dashboardData.value
  if (!d.raw_data || d.raw_data.length === 0) return '--%'
  try {
    const prices = d.raw_data.slice(0, 60).map(r => parseFloat(String(r['金价']))).filter(v => !isNaN(v))
    if (prices.length < 30) return '--%'
    const ret = []
    for (let i = 1; i < prices.length; i++) ret.push(Math.log(prices[i - 1] / prices[i]))
    const mean = ret.reduce((a, b) => a + b, 0) / ret.length
    const varr = ret.reduce((a, b) => a + (b - mean) ** 2, 0) / ret.length
    return (Math.sqrt(varr * 252) * 100).toFixed(1) + '%'
  } catch {
    return '--%'
  }
})

const regimeColor = computed(() => {
  if (regime.value.includes('牛')) return 'var(--pos)'
  if (regime.value.includes('熊')) return 'var(--neg)'
  return 'var(--warn)'
})

const multiHorizon = computed(() => {
  const ov = dashboardData.value.overview || {}
  const parse = (k: string) => {
    const v = ov[k]
    if (v == null) return 0
    const n = parseFloat(String(v).replace('%', ''))
    return isNaN(n) ? 0 : n / 100
  }
  const p5 = parse('5日看多概率')
  const p10 = parse('10日看多概率')
  const p20 = parse('20日看多概率')
  const p60 = parse('60日看多概率')
  const arr = [p5, p10, p20, p60]
  return [
    { label: '5D', pct: p5 },
    { label: '10D', pct: p10 },
    { label: '20D', pct: p20 },
    { label: '60D', pct: p60 }
  ].map((b, i) => ({
    ...b,
    color: arr[i] >= 0.6 ? C.pos : arr[i] < 0.5 ? C.neg : C.text3
  }))
})

const v3e = computed(() => dashboardData.value.strategies?.find(s => s.策略 && s.策略.includes('V3.0-E')))
const sharpe = computed(() => v3e.value?.夏普 || '--')
const maxDD = computed(() => v3e.value?.最大回撤 || '--')
const acc20 = computed(() => {
  const m20 = dashboardData.value.ml_models?.find(m => m.period.includes('20'))
  return m20?.accuracy || '--'
})
const auc20 = computed(() => {
  const m20 = dashboardData.value.ml_models?.find(m => m.period.includes('20'))
  return m20?.auc || '--'
})

const full = computed(() => {
  const v = v3e.value?.夏普 ? parseFloat(v3e.value.夏普) : 0
  return v.toFixed(2)
})
const oos = computed(() => {
  const h = dashboardData.value.v5_holdout?.find(s => s.strategy && s.strategy.includes('V3.0-E'))
  return h ? h.sharpe.toFixed(2) : '--'
})
const decay = computed(() => {
  const fullV = parseFloat(full.value)
  const h = dashboardData.value.v5_holdout?.find(s => s.strategy && s.strategy.includes('V3.0-E'))
  if (!h || fullV <= 0 || h.sharpe === 0) return '--%'
  return Math.round((1 - h.sharpe / fullV) * 100) + '%'
})
const feat = computed(() => dashboardData.value.v5_feature_count || '--')
const dirAcc = computed(() => {
  const r20 = dashboardData.value.v5_regression?.find(r => r.horizon === '20日')
  return r20?.dir_acc || '--'
})

// === Chart option builders (pure functions, no side effects) ===

// 周聚合：把日 close 合成 weekly OHLC（每5个交易日一周）
function weeklyOHLC(dates: string[], prices: number[]) {
  const out: { date: string; ohlc: [number, number, number, number] }[] = []
  for (let i = 0; i < prices.length; i += 5) {
    const slice = prices.slice(i, i + 5)
    const dSlice = dates.slice(i, i + 5)
    if (slice.length === 0) break
    const open = slice[0]
    const close = slice[slice.length - 1]
    const high = Math.max(...slice)
    const low = Math.min(...slice)
    out.push({ date: dSlice[0], ohlc: [open, close, low, high] })
  }
  return out
}

function priceOpt(): EChartsOption {
  const d = dashboardData.value
  if (!d.raw_data || d.raw_data.length === 0) return {}
  const sorted = [...d.raw_data].reverse()
  const dates = sorted.map(r => r['日期']).filter(Boolean) as string[]
  const prices = sorted.map(r => parseFloat(String(r['金价']))).filter(v => !isNaN(v))
  if (prices.length === 0) return {}
  // 周聚合
  const weekly = weeklyOHLC(dates, prices)
  const wDates = weekly.map(w => w.date)
  const wData = weekly.map(w => w.ohlc)
  // MA5 周
  const wCloses = weekly.map(w => w.ohlc[1])
  const ma5raw: number[] = []
  for (let i = 0; i < wCloses.length; i++) {
    if (i < 4) { ma5raw.push(NaN as any); continue }
    let s = 0
    for (let j = 0; j < 5; j++) s += wCloses[i - j]
    ma5raw.push(s / 5)
  }
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { left: '3%', right: '3%', bottom: '5%', top: '8%' },
    xAxis: {
      type: 'category',
      data: wDates,
      axisLine: { lineStyle: { color: C.border } },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value', scale: true,
      axisLine: { show: false },
      axisLabel: { show: false, color: C.text3 },
      splitLine: { lineStyle: { color: C.grid } }
    },
    series: [
      {
        name: 'WEEKLY K',
        type: 'candlestick',
        data: wData,
        itemStyle: {
          color: C.pos,        // 涨
          color0: C.neg,       // 跌
          borderColor: C.pos,
          borderColor0: C.neg
        }
      },
      {
        name: 'MA5W',
        type: 'line',
        data: ma5raw,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1, color: C.accent, opacity: 0.7 }
      }
    ]
  }
}

function strategyOpt(): EChartsOption {
  const d = dashboardData.value
  if (!d.raw_data || d.raw_data.length === 0) return {}
  const sorted = [...d.raw_data].reverse()
  const dates = sorted.map(r => r['日期']).filter(Boolean) as string[]
  const gp = sorted.map(r => parseFloat(String(r['金价']))).filter(v => !isNaN(v))
  if (gp.length === 0) return {}
  const bh = [1]
  for (let i = 1; i < gp.length; i++) bh.push(bh[i - 1] * gp[i] / gp[0])
  const v3e = bh.map(v => 1 + (v - 1) * 0.34)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '3%', bottom: '5%', top: '5%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { show: false }, splitLine: { show: false } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { show: false, color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: 'BH', type: 'line', data: bh, symbol: 'none', lineStyle: { width: 1, color: C.text3, opacity: 0.5 } },
      { name: 'V3.0-E', type: 'line', data: v3e, symbol: 'none', lineStyle: { width: 1.5, color: C.accent } }
    ]
  }
}

function featOpt(): EChartsOption {
  const d = dashboardData.value
  if (!d.features) return {}
  const top8 = d.features.slice(0, 8).reverse()
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '30%', right: '5%', bottom: '5%', top: '5%' },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9 }, splitLine: { lineStyle: { color: C.grid } } },
    yAxis: { type: 'category', data: top8.map(f => f.name), axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: '#8b949e', fontSize: 10 } },
    series: [{ type: 'bar', data: top8.map(f => ({ value: f.avg, itemStyle: { color: C.accent } })), barWidth: '60%', label: { show: true, position: 'right', color: C.text3, fontSize: 9 } }]
  }
}

function posOpt(): EChartsOption {
  const ph = executionData.value.position_history
  if (!ph || !ph.dates || ph.dates.length === 0) return {}
  const positions = ph.positions.map(p => p * 100)
  const etf = positions.map(p => p * 0.65)
  const fut = positions.map(p => p * 0.35)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['MODEL', 'ETF', 'FUT', 'GOLD'], textStyle: { color: C.text3, fontSize: 9 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: ph.dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9 } },
    yAxis: [
      { type: 'value', name: 'POS%', min: -100, max: 100, axisLine: { show: false }, axisLabel: { color: C.text3, fontSize: 9, formatter: '{value}%' }, splitLine: { lineStyle: { color: C.grid } } },
      { type: 'value', name: 'GOLD', position: 'right', scale: true, axisLine: { show: false }, axisLabel: { color: C.text3, fontSize: 9 }, splitLine: { show: false } }
    ],
    series: [
      { name: 'MODEL', type: 'line', data: positions, symbol: 'none', lineStyle: { width: 1.5, color: C.gold } },
      { name: 'ETF', type: 'line', data: etf, symbol: 'none', lineStyle: { width: 1, color: C.accent, opacity: 0.6 } },
      { name: 'FUT', type: 'line', data: fut, symbol: 'none', lineStyle: { width: 1, color: C.accent, opacity: 0.4, type: 'dashed' } },
      { name: 'GOLD', type: 'line', data: ph.gold_prices, symbol: 'none', lineStyle: { width: 1, color: C.pos, opacity: 0.5 }, yAxisIndex: 1 }
    ]
  }
}

// === K: ALERTS 告警流 ===
interface Alert {
  severity: 'high' | 'medium' | 'low' | 'info'
  type: string
  title: string
  detail: string
  time: string
}

const alerts = computed<Alert[]>(() => {
  const out: Alert[] = []
  const hist = driftHistory.value || []
  if (hist.length < 2) return out
  const latest = hist[hist.length - 1]
  const prev = hist[hist.length - 2] || hist[0]
  const ts = latest.timestamp || latest.run_date || '--'

  // 1. 命中率告警
  const sb = latest.signal_backtest || {}
  const hitRate = sb.recent_20_hit_rate
  const wfBase = sb.wf_baseline_acc
  if (hitRate != null && wfBase != null) {
    const dev = hitRate - wfBase
    if (dev < -0.20) {
      out.push({
        severity: 'high',
        type: 'HIT_RATE',
        title: `命中率 ${(hitRate * 100).toFixed(0)}% 远低于基准`,
        detail: `WF基准 ${(wfBase * 100).toFixed(0)}%，偏差 ${(dev * 100).toFixed(0)}% → 信号质量熔断生效`,
        time: ts
      })
    } else if (dev < -0.10) {
      out.push({
        severity: 'medium',
        type: 'HIT_RATE',
        title: `命中率 ${Math.round(hitRate * 100)}% 低于基准`,
        detail: `偏差 ${(dev * 100).toFixed(0)}%，关注模型有效性`,
        time: ts
      })
    }
  }

  // 2. 概率漂移告警
  const cur = latest.current_state || {}
  const ps = latest.prob_stats || {}
  if (cur.probability != null && ps.mean != null) {
    const diff = cur.probability - ps.mean
    if (Math.abs(diff) > 0.20) {
      out.push({
        severity: diff > 0 ? 'low' : 'medium',
        type: 'PROB_DRIFT',
        title: `当前概率 ${(cur.probability * 100).toFixed(1)}% vs 历史均值 ${(ps.mean * 100).toFixed(1)}%`,
        detail: `偏离 ${(diff * 100).toFixed(1)}%（${diff > 0 ? '高估' : '低估'}）`,
        time: ts
      })
    }
  }

  // 3. 特征TOP5排名变化
  const curTop5 = Object.keys(latest.feature_importance_top10 || {}).slice(0, 5)
  const prevTop5 = Object.keys(prev.feature_importance_top10 || {}).slice(0, 5)
  const newEntries = curTop5.filter(f => !prevTop5.includes(f))
  const dropped = prevTop5.filter(f => !curTop5.includes(f))
  if (newEntries.length > 0 || dropped.length > 0) {
    out.push({
      severity: 'low',
      type: 'FEAT_SHIFT',
      title: `TOP5 特征排名变化`,
      detail: `新进: ${newEntries.join(', ') || '无'} | 退出: ${dropped.join(', ') || '无'}`,
      time: ts
    })
  }

  // 4. IC 衰减
  const m60Latest = (latest.ml_metrics || {})['60'] || {}
  const m60Prev = (prev.ml_metrics || {})['60'] || {}
  if (m60Latest.ic != null && m60Prev.ic != null) {
    const delta = m60Latest.ic - m60Prev.ic
    if (Math.abs(delta) > 0.03) {
      out.push({
        severity: 'medium',
        type: 'IC_DRIFT',
        title: `60日IC ${(m60Latest.ic).toFixed(3)} ${delta > 0 ? '↑' : '↓'}`,
        detail: `Δ${delta > 0 ? '+' : ''}${delta.toFixed(3)}（基线 ${(m60Prev.ic).toFixed(3)}）`,
        time: ts
      })
    }
  }

  // 5. Best Sharpe 衰减
  if (latest.best_sharpe != null && prev.best_sharpe != null) {
    const sDelta = latest.best_sharpe - prev.best_sharpe
    if (Math.abs(sDelta) > 0.1) {
      out.push({
        severity: 'medium',
        type: 'SHARPE_DRIFT',
        title: `最优夏普 ${latest.best_sharpe.toFixed(2)} ${sDelta > 0 ? '↑' : '↓'}`,
        detail: `Δ${sDelta > 0 ? '+' : ''}${sDelta.toFixed(2)}（上次 ${prev.best_sharpe.toFixed(2)}）`,
        time: ts
      })
    }
  }

  // 6. Regime 切换告警
  if (cur.regime && prev.current_state?.regime && cur.regime !== prev.current_state.regime) {
    out.push({
      severity: 'high',
      type: 'REGIME_SHIFT',
      title: `Regime 切换: ${prev.current_state.regime} → ${cur.regime}`,
      detail: `Regime 变更将影响非对称仓位规则`,
      time: ts
    })
  }

  return out
})
</script>

<style scoped>
.wall-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  grid-template-rows: auto auto auto auto;
  gap: 12px;
}
.wall-cell {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 14px;
  position: relative;
  min-height: 200px;
}
.wall-cell::before,
.wall-cell::after {
  content: '';
  position: absolute;
  width: 8px;
  height: 8px;
  border-color: var(--accent);
  border-style: solid;
  border-width: 0;
  pointer-events: none;
}
.wall-cell::before { top: -1px; left: -1px; border-top-width: 1px; border-left-width: 1px; }
.wall-cell::after { bottom: -1px; right: -1px; border-bottom-width: 1px; border-right-width: 1px; }
.wall-cell.span-2 { grid-column: span 2; }
.wall-cell.span-row { grid-column: 1 / -1; }
.wall-cell.span-row-2 { grid-row: span 2; }
.wall-cell-title {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
  color: var(--text-3);
  margin-bottom: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.wall-cell-title::before { content: '//'; color: var(--accent); opacity: 0.6; margin-right: 6px; }
.wall-cell-title .meta { color: var(--text-3); font-size: 9px; }

.big-signal {
  text-align: center;
  padding: 20px 0;
}
.big-prob {
  font-family: var(--mono);
  font-size: 64px;
  font-weight: 500;
  color: var(--accent);
  line-height: 1;
  letter-spacing: -0.02em;
  text-shadow: 0 0 24px rgba(0, 212, 255, 0.4);
}
.big-prob-label {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-top: 8px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.big-action {
  margin-top: 16px;
  padding: 6px 14px;
  display: inline-block;
  border: 1px solid var(--border-strong);
  border-radius: 2px;
  background: var(--accent-soft);
  font-family: var(--mono);
  font-size: 13px;
  color: var(--accent);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.signal-grid {
  margin-top: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}
.mini-label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.mini-value {
  font-family: var(--mono);
  font-size: 18px;
  margin-top: 4px;
}

.key-metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  align-items: center;
}
.key-value {
  font-family: var(--mono);
  font-size: 22px;
  margin-top: 2px;
  text-shadow: 0 0 10px current-color;
}

.decay-block {
  text-align: center;
  padding: 10px 0;
}
.decay-value {
  font-family: var(--mono);
  font-size: 42px;
  color: var(--neg);
  text-shadow: 0 0 14px rgba(255, 56, 96, 0.3);
}
.decay-detail {
  margin-top: 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-2);
}
.decay-detail:first-of-type { margin-top: 12px; }

@media (max-width: 768px) {
  .wall-grid { grid-template-columns: 1fr; }
  .wall-cell.span-2 { grid-column: span 1; }
  .wall-cell.span-row-2 { grid-row: auto; }
}

.alerts-list {
  max-height: 200px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.alert-item {
  display: grid;
  grid-template-columns: 50px 90px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-left: 2px solid;
  font-size: 11px;
  font-family: var(--mono);
}
.alert-item.sev-high { border-color: var(--neg); background: rgba(255, 56, 96, 0.06); }
.alert-item.sev-medium { border-color: var(--warn); background: rgba(255, 184, 0, 0.05); }
.alert-item.sev-low { border-color: var(--accent); background: rgba(0, 212, 255, 0.04); }
.alert-item.sev-info { border-color: var(--text-3); }
.alert-sev {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
}
.sev-high .alert-sev { color: var(--neg); }
.sev-medium .alert-sev { color: var(--warn); }
.sev-low .alert-sev { color: var(--accent); }
.alert-type { color: var(--text-3); font-size: 9px; letter-spacing: 0.06em; }
.alert-title { color: var(--text); }
.alert-detail { color: var(--text-2); grid-column: 1 / -1; padding-left: 58px; font-size: 10px; }
.alert-time { color: var(--text-3); font-size: 9px; }
.no-alerts {
  text-align: center;
  color: var(--pos);
  font-family: var(--mono);
  font-size: 11px;
  padding: 20px 0;
  letter-spacing: 0.1em;
}
</style>
