<template>
  <div class="backtest-grid">
    <HudCard title="BACKTEST CONFIG" meta="CUSTOM · 真实仓位可切换" class="span-2">
      <div class="preset-hint">
        <b>✓ V5 真实仓位 + 简化策略双模式：</b>
        默认开启"使用 V5 真实仓位"，从 position_history 读真实仓位序列。
        关闭则用简化策略（牛满仓/熊做空50%/震荡30% + Kelly/Vol靶向/止损止盈参数）。
      </div>
      <div class="config-grid">
        <div class="cfg-item">
          <div class="cfg-label">开始日期</div>
          <a-date-picker v-model="startDate" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">结束日期</div>
          <a-date-picker v-model="endDate" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">策略</div>
          <a-select v-model="strategy" :style="{ width: '100%' }">
            <a-option v-for="s in strategies" :key="s.策略" :value="s.策略">{{ s.策略 }}</a-option>
          </a-select>
        </div>
        <div class="cfg-item">
          <div class="cfg-label">初始资金</div>
          <a-input-number v-model="capital" :min="1000" :step="1000" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">仓位倍数</div>
          <a-input-number v-model="positionScale" :min="0.1" :max="3" :step="0.1" :style="{ width: '100%' }" />
        </div>
        <!-- K: 新增 5 个回测参数 -->
        <div class="cfg-item">
          <div class="cfg-label">止损位 (%)</div>
          <a-input-number v-model="stopLoss" :min="-20" :max="0" :step="0.5" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">止盈位 (%)</div>
          <a-input-number v-model="takeProfit" :min="0" :max="50" :step="1" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">Vol 靶向 (%)</div>
          <a-input-number v-model="volTarget" :min="5" :max="40" :step="1" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">Kelly 分数</div>
          <a-input-number v-model="kellyFraction" :min="0.1" :max="1.5" :step="0.1" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">Regime 阈值 (MA200 偏离%)</div>
          <a-input-number v-model="regimeThreshold" :min="1" :max="20" :step="0.5" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item cfg-toggle">
          <a-switch v-model="useRealPositions" />
          <span class="toggle-label">使用 V5 真实仓位</span>
        </div>
        <div class="cfg-item cfg-actions">
          <a-button type="primary" long @click="runBacktest">RUN</a-button>
          <a-button long @click="resetConfig">RESET</a-button>
        </div>
      </div>
    </HudCard>

    <HudCard title="PERFORMANCE METRICS" meta="CALCULATED">
      <div v-if="metrics" class="metrics-grid">
        <div class="metric"><div class="m-label">TOTAL RET</div><div class="m-value" :class="metrics.totalRet >= 0 ? 'text-pos' : 'text-neg'">{{ (metrics.totalRet * 100).toFixed(2) }}%</div></div>
        <div class="metric"><div class="m-label">ANNUAL RET</div><div class="m-value" :class="metrics.annualRet >= 0 ? 'text-pos' : 'text-neg'">{{ (metrics.annualRet * 100).toFixed(2) }}%</div></div>
        <div class="metric"><div class="m-label">SHARPE</div><div class="m-value text-acc">{{ metrics.sharpe.toFixed(2) }}</div></div>
        <div class="metric"><div class="m-label">MAX DD</div><div class="m-value text-neg">{{ (metrics.maxDD * 100).toFixed(2) }}%</div></div>
        <div class="metric"><div class="m-label">WIN RATE</div><div class="m-value text-acc">{{ (metrics.winRate * 100).toFixed(1) }}%</div></div>
        <div class="metric"><div class="m-label">CALMAR</div><div class="m-value">{{ metrics.calmar.toFixed(2) }}</div></div>
        <div class="metric"><div class="m-label">DAYS</div><div class="m-value">{{ metrics.days }}</div></div>
        <div class="metric"><div class="m-label">VOL</div><div class="m-value">{{ (metrics.vol * 100).toFixed(2) }}%</div></div>
      </div>
      <div v-else class="hint">{{ $t('common.clickRun') }}</div>
    </HudCard>

    <HudCard title="EQUITY CURVE" meta="NAV" class="span-2">
      <ChartBox v-if="metrics" :option="navOpt" height="380px" />
      <div v-else class="hint">{{ $t('common.waitBacktest') }}</div>
    </HudCard>

    <HudCard title="DRAWDOWN" meta="UNDERWATER" class="span-2">
      <ChartBox v-if="metrics" :option="ddOpt" height="260px" />
      <div v-else class="hint">{{ $t('common.waitBacktest') }}</div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EChartsOption } from 'echarts'
import { Message } from '@arco-design/web-vue'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, executionData } from '@/composables/useDashboardData'

const { t } = useI18n()

// 配置
const startDate = ref<string>('')
const endDate = ref<string>('')
const strategy = ref('V3.0-E 多周期集成')
const capital = ref(100000)
const positionScale = ref(1)
// K: 新增 5 个参数
const stopLoss = ref(-5)            // 止损 -5%
const takeProfit = ref(20)          // 止盈 +20%
const volTarget = ref(15)           // Vol靶向 15% 年化
const kellyFraction = ref(0.5)      // Kelly 分数 0.5
const regimeThreshold = ref(5)      // Regime 阈值 5%
const useRealPositions = ref(true)   // 优先使用 V5 真实仓位序列

// 计算结果
const navSeries = ref<{ date: string; nav: number; gold: number; dd: number }[]>([])
const metrics = ref<any>(null)

const strategies = computed(() => dashboardData.value.strategies || [])

// 初始化日期范围（默认取 raw_data 全部）
function initDates() {
  const raw = dashboardData.value.raw_data || []
  if (raw.length === 0) return
  // 找出最早和最晚日期（raw_data 顺序可能不稳定）
  const dates = raw.map(r => r['日期']).filter(Boolean) as string[]
  dates.sort()  // 字符串排序 = 日期升序 (YYYY-MM-DD)
  startDate.value = dates[0] || ''
  endDate.value = dates[dates.length - 1] || ''
}

watch([dashboardData], () => initDates(), { immediate: true })

function runBacktest() {
  const raw = dashboardData.value.raw_data || []
  if (raw.length === 0) {
    Message.error(t('common.noDataShort'))
    return
  }
  if (!startDate.value || !endDate.value) {
    Message.warning(t('common.selectDateRange'))
    return
  }
  const sorted = [...raw].reverse().filter(r => r['日期'] && r['金价'])
  const start = startDate.value
  const end = endDate.value
  const filtered = sorted.filter(r => {
    const d = r['日期']!
    return d >= start && d <= end
  })
  if (filtered.length < 5) {
    Message.error(t('common.tooFewData', { n: filtered.length }))
    return
  }

  // 计算金价日收益率
  const prices = filtered.map(r => parseFloat(String(r['金价'])))
  const dates = filtered.map(r => r['日期']!)
  const rets: number[] = []
  for (let i = 1; i < prices.length; i++) {
    rets.push((prices[i] - prices[i - 1]) / prices[i - 1])
  }

  // 仓位策略：根据 Regime + Kelly + Vol靶向
  // 优先用 V5 真实仓位序列（如开启），否则用简化策略
  const ph = executionData.value.position_history
  const phMap: Record<string, number> = {}
  if (useRealPositions.value && ph?.dates && ph?.positions) {
    ph.dates.forEach((d: string, i: number) => { phMap[d] = ph.positions[i] })
  }
  const positions: number[] = [0]
  let lastEntryPrice = 0  // 用于止损止盈判断
  let usingReal = 0
  for (let i = 1; i < filtered.length; i++) {
    const r = filtered[i]
    let pos: number
    // 优先用 V5 真实仓位
    const realPos = phMap[r['日期']!]
    if (useRealPositions.value && realPos != null && !isNaN(realPos)) {
      pos = realPos * positionScale.value
      usingReal++
    } else {
      // fallback：简化策略
      const regime = r['Regime'] || '震荡'
      const ma200偏离 = parseFloat(String(r['MA200偏离'] || '0')) * 100
      const usedRegime = ma200偏离 > regimeThreshold.value ? '牛市'
        : ma200偏离 < -regimeThreshold.value ? '熊市'
        : '震荡'
      if (usedRegime === '牛市') pos = 1.0 * positionScale.value * kellyFraction.value
      else if (usedRegime === '熊市') pos = -0.5 * positionScale.value * kellyFraction.value
      else pos = 0.3 * positionScale.value * kellyFraction.value
    }

    // K: Vol靶向（自定义目标）
    const targetVol = volTarget.value / 100  // 年化目标波动率
    const recentRets = rets.slice(Math.max(0, i - 20), i)
    if (recentRets.length >= 10) {
      const mean = recentRets.reduce((a, b) => a + b, 0) / recentRets.length
      const variance = recentRets.reduce((a, b) => a + (b - mean) ** 2, 0) / recentRets.length
      const recentVol = Math.sqrt(variance) * Math.sqrt(252)  // 年化
      if (recentVol > 0) {
        pos *= targetVol / recentVol  // Vol靶向
        pos = Math.max(-1.5, Math.min(1.5, pos))  // 限幅 ±150%
      }
    }

    // K: 止损/止盈检测
    if (lastEntryPrice > 0 && i > 0) {
      const price = prices[i]
      const pnlPct = (price - lastEntryPrice) / lastEntryPrice * (pos > 0 ? 1 : -1) * 100
      if (pnlPct <= stopLoss.value || (takeProfit.value > 0 && pnlPct >= takeProfit.value)) {
        pos = 0  // 触发止损/止盈，平仓
        lastEntryPrice = 0
      }
    }
    if (pos !== 0 && lastEntryPrice === 0) {
      lastEntryPrice = prices[i]  // 记录进场价
    }
    positions.push(pos)
  }

  // 策略日收益 = 仓位 × 金价日收益
  const stratRets: number[] = [0]
  for (let i = 1; i < filtered.length; i++) {
    stratRets.push(positions[i] * rets[i - 1])
  }

  // NAV 曲线
  let nav = capital.value
  const navData: { date: string; nav: number; gold: number; dd: number }[] = []
  const navArr: number[] = []
  for (let i = 0; i < filtered.length; i++) {
    if (i === 0) {
      nav = capital.value
    } else {
      nav *= (1 + stratRets[i])
    }
    navArr.push(nav)
    navData.push({
      date: dates[i],
      nav: nav,
      gold: prices[i],
      dd: 0  // 待计算
    })
  }
  // 计算回撤
  let peak = navArr[0]
  for (let i = 0; i < navArr.length; i++) {
    if (navArr[i] > peak) peak = navArr[i]
    navData[i].dd = (navArr[i] - peak) / peak
  }
  navSeries.value = navData

  // 计算指标
  const tradingRets = stratRets.slice(1)
  const mean = tradingRets.reduce((a, b) => a + b, 0) / tradingRets.length
  const variance = tradingRets.reduce((a, b) => a + (b - mean) ** 2, 0) / tradingRets.length
  const dailyVol = Math.sqrt(variance)
  const annualVol = dailyVol * Math.sqrt(252)
  const totalRet = (navArr[navArr.length - 1] - capital.value) / capital.value
  const days = filtered.length
  const years = days / 252
  const annualRet = Math.pow(navArr[navArr.length - 1] / capital.value, 1 / years) - 1
  const sharpe = annualVol > 0 ? annualRet / annualVol : 0
  // 最大回撤
  let maxDD = 0
  for (const d of navData) {
    if (d.dd < maxDD) maxDD = d.dd
  }
  const winDays = tradingRets.filter(r => r > 0).length
  const winRate = winDays / tradingRets.length
  const calmar = maxDD < 0 ? Math.abs(annualRet / maxDD) : 0

  metrics.value = {
    totalRet, annualRet, sharpe, maxDD, winRate, calmar,
    days, vol: annualVol
  }
  Message.success(t('common.backtestDone', { days, sharpe: sharpe.toFixed(2), usingReal, days }))
}

function resetConfig() {
  initDates()
  strategy.value = 'V3.0-E 多周期集成'
  capital.value = 100000
  positionScale.value = 1
  stopLoss.value = -5
  takeProfit.value = 20
  volTarget.value = 15
  kellyFraction.value = 0.5
  regimeThreshold.value = 5
  useRealPositions.value = true
  navSeries.value = []
  metrics.value = null
  Message.info(t('common.configReset'))
}

function navOpt(): EChartsOption {
  const data = navSeries.value
  if (data.length === 0) return {}
  return {
    backgroundColor: '#0e0f11', animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['策略NAV', '金价基准'], textStyle: { color: '#66635c', fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: data.map(d => d.date), axisLine: { lineStyle: { color: 'rgba(217, 166, 72,0.14)' } }, axisLabel: { color: '#66635c', fontSize: 10 } },
    yAxis: [
      { type: 'value', scale: true, axisLine: { show: false }, axisLabel: { color: '#66635c', formatter: '${value}' }, splitLine: { lineStyle: { color: 'rgba(217, 166, 72,0.05)' } } },
      { type: 'value', scale: true, position: 'right', axisLine: { show: false }, axisLabel: { color: '#66635c', formatter: '${value}' }, splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      { name: '策略NAV', type: 'line', data: data.map(d => d.nav), symbol: 'none', smooth: true, lineStyle: { width: 2, color: '#d9a648' }, areaStyle: { color: 'rgba(217, 166, 72,0.08)' } },
      { name: '金价基准', type: 'line', data: data.map(d => d.gold), symbol: 'none', yAxisIndex: 1, lineStyle: { width: 1, color: '#d9a648', opacity: 0.6 } }
    ]
  }
}

function ddOpt(): EChartsOption {
  const data = navSeries.value
  if (data.length === 0) return {}
  return {
    backgroundColor: '#0e0f11', animation: false,
    tooltip: { trigger: 'axis', formatter: (p: any) => p[0] ? `${p[0].axisValue}<br/>回撤: ${(p[0].value * 100).toFixed(2)}%` : '' },
    grid: { left: '5%', right: '5%', bottom: '8%', top: '5%' },
    xAxis: { type: 'category', data: data.map(d => d.date), axisLine: { lineStyle: { color: 'rgba(217, 166, 72,0.14)' } }, axisLabel: { color: '#66635c', fontSize: 10 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: '#66635c', formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(217, 166, 72,0.05)' } } },
    dataZoom: [{ type: 'inside' }],
    series: [{
      name: '回撤', type: 'line', data: data.map(d => +(d.dd * 100).toFixed(2)), symbol: 'none',
      lineStyle: { width: 1, color: '#cf6b62' }, areaStyle: { color: 'rgba(207, 107, 98,0.15)' }
    }]
  }
}
</script>

<style scoped>
.backtest-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.backtest-grid .span-2 { grid-column: span 2; }
.preset-hint {
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.7;
  padding: 8px 10px;
  border-left: 2px solid var(--pos);
  background: rgba(69, 183, 137, 0.05);
  margin-bottom: 10px;
  font-family: var(--mono);
}
.preset-hint b { color: var(--pos); }
.cfg-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toggle-label {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-2);
}
.config-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.cfg-item { display: flex; flex-direction: column; gap: 4px; }
.cfg-label {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.cfg-actions {
  grid-column: span 3;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 4px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  padding: 8px 0;
}
.metric { text-align: center; padding: 8px 0; }
.m-label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.m-value {
  font-family: var(--mono);
  font-size: 22px;
  margin-top: 4px;
  font-weight: 500;
}
.hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  text-align: center;
  padding: 40px 0;
}
@media (max-width: 1024px) {
  .backtest-grid { grid-template-columns: 1fr; }
  .backtest-grid .span-2 { grid-column: span 1; }
  .config-grid { grid-template-columns: 1fr 1fr; }
}
</style>
