<template>
  <div class="sim-grid">
    <HudCard :title="$t('card.simulatorConfig')" :meta="$t('meta.monteCarlo')" class="span-2">
      <div class="config-grid">
        <div class="cfg-item">
          <div class="cfg-label">本金 ($)</div>
          <a-input-number v-model="capital" :min="1000" :step="1000" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">杠杆倍数</div>
          <a-input-number v-model="leverage" :min="1" :max="10" :step="0.5" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">仓位 (%)</div>
          <a-input-number v-model="positionPct" :min="0" :max="100" :step="5" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">持仓天数</div>
          <a-input-number v-model="holdDays" :min="1" :max="250" :step="5" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">模拟路径数</div>
          <a-input-number v-model="paths" :min="100" :max="5000" :step="100" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">波动率来源</div>
          <a-select v-model="volSource" :style="{ width: '100%' }">
            <a-option value="20d">20日历史波动率 ({{ vol20dStr }})</a-option>
            <a-option value="60d">60日历史波动率 ({{ vol60dStr }})</a-option>
            <a-option value="custom">自定义</a-option>
          </a-select>
        </div>
        <div class="cfg-item" v-if="volSource === 'custom'">
          <div class="cfg-label">自定义日波动率</div>
          <a-input-number v-model="customVol" :min="0.001" :max="0.1" :step="0.001" :precision="4" :style="{ width: '100%' }" />
        </div>
        <div class="cfg-item">
          <div class="cfg-label">漂移 (日均值)</div>
          <a-input-number v-model="drift" :min="-0.01" :max="0.01" :step="0.0005" :precision="5" :style="{ width: '100%' }" />
        </div>
      </div>
      <div class="cfg-actions">
        <a-button type="primary" long @click="runSim">{{ $t('common.simulate') }}</a-button>
        <a-button long @click="resetSim">{{ $t('common.reset') }}</a-button>
      </div>
    </HudCard>

    <HudCard :title="$t('card.riskMetrics')" :meta="$t('meta.confidence95')" class="span-2">
      <div v-if="result" class="metrics-grid">
        <div class="metric">
          <div class="m-label">期望终值</div>
          <div class="m-value" :class="result.expectedMultiple >= 1 ? 'text-pos' : 'text-neg'">
            {{ (result.expectedFinal).toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
          </div>
          <div class="m-sub" :class="result.expectedMultiple >= 1 ? 'text-pos' : 'text-neg'">
            {{ (result.expectedMultiple * 100).toFixed(2) }}%
          </div>
        </div>
        <div class="metric">
          <div class="m-label">中位数</div>
          <div class="m-value text-acc">{{ result.median.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</div>
          <div class="m-sub">{{ (result.medianMultiple * 100).toFixed(2) }}%</div>
        </div>
        <div class="metric">
          <div class="m-label">95% VaR</div>
          <div class="m-value text-neg">{{ result.var95.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</div>
          <div class="m-sub text-neg">{{ ((result.var95Multiple - 1) * 100).toFixed(2) }}%</div>
        </div>
        <div class="metric">
          <div class="m-label">5% VaR</div>
          <div class="m-value text-pos">{{ result.p95.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</div>
          <div class="m-sub text-pos">{{ ((result.p95Multiple - 1) * 100).toFixed(2) }}%</div>
        </div>
        <div class="metric">
          <div class="m-label">最大盈利</div>
          <div class="m-value text-pos">{{ result.maxFinal.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</div>
          <div class="m-sub text-pos">{{ (result.maxMultiple * 100).toFixed(2) }}%</div>
        </div>
        <div class="metric">
          <div class="m-label">最大亏损</div>
          <div class="m-value text-neg">{{ result.minFinal.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</div>
          <div class="m-sub text-neg">{{ (result.minMultiple * 100).toFixed(2) }}%</div>
        </div>
        <div class="metric">
          <div class="m-label">破仓概率</div>
          <div class="m-value" :class="result.liquidationProb > 0.05 ? 'text-neg' : 'text-pos'">
            {{ (result.liquidationProb * 100).toFixed(2) }}%
          </div>
          <div class="m-sub">本金亏 ≥ 50%</div>
        </div>
        <div class="metric">
          <div class="m-label">日波动率</div>
          <div class="m-value text-warn">{{ (result.dailyVol * 100).toFixed(2) }}%</div>
          <div class="m-sub">年化 {{ (result.dailyVol * Math.sqrt(252) * 100).toFixed(1) }}%</div>
        </div>
      </div>
      <div v-else class="hint">{{ $t('common.clickSimulate') }}</div>
    </HudCard>

    <HudCard :title="$t('card.pathFan')" :meta="$t('meta.n1000Paths')" class="span-2">
      <ChartBox v-if="result" :option="pathOpt" height="380px" />
      <div v-else class="hint">{{ $t('common.waitSimulation') }}</div>
    </HudCard>

    <HudCard :title="$t('card.finalNavDistribution')" :meta="$t('meta.histogram')" class="span-2">
      <ChartBox v-if="result" :option="distOpt" height="280px" />
      <div v-else class="hint">{{ $t('common.waitSimulation') }}</div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, extractValue } from '@/composables/useDashboardData'
import { fmtNum, fmtMoney } from '@/utils/format'
import { Message } from '@arco-design/web-vue'

const { t } = useI18n()

const capital = ref(100000)
const leverage = ref(1)
const positionPct = ref(60)
const holdDays = ref(20)
const paths = ref(1000)
const volSource = ref('20d')
const customVol = ref(0.015)
const drift = ref(0)

// 历史波动率从 overview 字段取
const vol60d = computed(() => {
  const v = extractValue(dashboardData.value.overview, '60日波动率')
  return v ? parseFloat(v.replace('%', '')) / 100 : 0.27
})
const vol20d = computed(() => {
  // 从 raw_data 最新一条取 20日波动率。
  // 修复: raw_data为时间升序,此前取raw[0]拿到的是最老一行(扩到250日后≈一年前的旧值)
  const raw = dashboardData.value.raw_data || []
  if (raw.length === 0) return 0.21
  const v = raw[raw.length - 1]['20日波动率']
  return v ? parseFloat(v) : 0.21
})
const vol20dStr = computed(() => (vol20d.value * 100).toFixed(1) + '%')
const vol60dStr = computed(() => (vol60d.value * 100).toFixed(1) + '%')

const dailyVol = computed(() => {
  if (volSource.value === '20d') return vol20d.value / Math.sqrt(252)
  if (volSource.value === '60d') return vol60d.value / Math.sqrt(252)
  return customVol.value
})

interface SimResult {
  expectedFinal: number
  expectedMultiple: number
  median: number
  medianMultiple: number
  var95: number
  var95Multiple: number
  p95: number
  p95Multiple: number
  maxFinal: number
  maxMultiple: number
  minFinal: number
  minMultiple: number
  liquidationProb: number
  dailyVol: number
  // 路径数据（用于图表）
  pathLines: number[][]
  finalValues: number[]
  dates: string[]
}

const result = ref<SimResult | null>(null)

// Box-Muller 转换：均匀分布 → 标准正态分布
function gaussian(): number {
  let u = 0, v = 0
  while (u === 0) u = Math.random()
  while (v === 0) v = Math.random()
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v)
}

function runSim() {
  const N = paths.value
  const D = holdDays.value
  const vol = dailyVol.value
  const pos = positionPct.value / 100
  const lev = leverage.value
  const cap = capital.value
  const dr = drift.value

  if (N < 100 || D < 1) {
    Message.error(t('common.invalidParams'))
    return
  }

  // 生成 N 条路径，每条 D 天
  const allPaths: number[][] = []
  const finals: number[] = []
  // 实际仓位 = pos * leverage（受杠杆放大）
  const effPos = pos * lev

  for (let i = 0; i < N; i++) {
    let nav = cap
    const path = [nav]
    for (let d = 0; d < D; d++) {
      // 几何布朗运动：nav *= (1 + drift + effPos * vol * gaussian())
      const r = dr + effPos * vol * gaussian()
      nav *= (1 + r)
      // 保证金不足时强平（杠杆 > 1 时）
      if (lev > 1 && nav < cap * (1 - 1 / lev)) {
        nav = cap * (1 - 1 / lev)  // 强平后剩余
        for (let dd = d + 1; dd < D; dd++) path.push(nav)
        break
      }
      path.push(nav)
    }
    allPaths.push(path)
    finals.push(nav)
  }

  // 排序计算分位数
  const sorted = [...finals].sort((a, b) => a - b)
  const pct = (p: number) => sorted[Math.floor(p * N)]
  const expected = finals.reduce((s, v) => s + v, 0) / N
  const median = pct(0.5)
  const var95 = pct(0.05)
  const p95 = pct(0.95)
  const max = sorted[N - 1]
  const min = sorted[0]
  const liquidation = finals.filter(v => v < cap * 0.5).length / N

  // 生成日期（虚拟，从今天开始）
  const dates: string[] = ['D0']
  const today = new Date()
  for (let d = 1; d <= D; d++) {
    const dt = new Date(today)
    dt.setDate(dt.getDate() + d)
    dates.push(`D${d}`)
  }

  // 为了图表性能，只取前 50 条路径
  const samplePaths = allPaths.slice(0, Math.min(50, N))

  result.value = {
    expectedFinal: expected,
    expectedMultiple: expected / cap,
    median,
    medianMultiple: median / cap,
    var95,
    var95Multiple: var95 / cap,
    p95,
    p95Multiple: p95 / cap,
    maxFinal: max,
    maxMultiple: max / cap,
    minFinal: min,
    minMultiple: min / cap,
    liquidationProb: liquidation,
    dailyVol: vol,
    pathLines: samplePaths,
    finalValues: finals,
    dates
  }

  Message.success(t('common.simulationDone', { n: N, d: D, expected: (expected / cap * 100).toFixed(2) }))
}

function resetSim() {
  capital.value = 100000
  leverage.value = 1
  positionPct.value = 60
  holdDays.value = 20
  paths.value = 1000
  volSource.value = '20d'
  customVol.value = 0.015
  drift.value = 0
  result.value = null
  Message.info(t('common.configReset'))
}

// 路径扇形图
function pathOpt(): EChartsOption {
  if (!result.value) return {}
  const r = result.value
  const C = { bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62', warn: '#eec170', gold: '#d9a648', text3: '#66635c', border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)' }
  // 计算分位数曲线
  const D = r.dates.length
  const p5: number[] = [], p25: number[] = [], p50: number[] = [], p75: number[] = [], p95: number[] = []
  for (let d = 0; d < D; d++) {
    const vals = r.pathLines.map(p => p[d] || p[p.length - 1]).sort((a, b) => a - b)
    const n = vals.length
    p5.push(vals[Math.floor(0.05 * n)])
    p25.push(vals[Math.floor(0.25 * n)])
    p50.push(vals[Math.floor(0.5 * n)])
    p75.push(vals[Math.floor(0.75 * n)])
    p95.push(vals[Math.floor(0.95 * n)])
  }
  const series: any[] = [
    // 5-95% 扇形（最外层）
    { name: '5-95%', type: 'line', data: p5, symbol: 'none', lineStyle: { opacity: 0 }, stack: 'ci', areaStyle: { color: 'rgba(217, 166, 72,0.05)' } },
    { name: '95-5%', type: 'line', data: p95.map((v, i) => v - p5[i]), symbol: 'none', lineStyle: { opacity: 0 }, stack: 'ci', areaStyle: { color: 'rgba(217, 166, 72,0.05)' } },
    // 中位数
    { name: t('chart.median'), type: 'line', data: p50, symbol: 'none', lineStyle: { width: 2, color: C.gold } },
    // 25-75% 扇形（内层）
    { name: '25-75%', type: 'line', data: p25, symbol: 'none', lineStyle: { opacity: 0 }, stack: 'inner', areaStyle: { color: 'rgba(217, 166, 72,0.12)' } },
    { name: '75-25%', type: 'line', data: p75.map((v, i) => v - p25[i]), symbol: 'none', lineStyle: { opacity: 0 }, stack: 'inner', areaStyle: { color: 'rgba(217, 166, 72,0.12)' } },
    // 本金线
    { name: t('chart.principal'), type: 'line', data: Array(D).fill(capital.value), symbol: 'none', lineStyle: { width: 1, color: C.text3, type: 'dashed' } }
  ]
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtMoney(v) },
    legend: { data: [t('chart.median'), t('chart.principal')], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '8%', right: '3%', bottom: '8%', top: '10%' },
    xAxis: { type: 'category', data: r.dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, interval: Math.floor(D / 10) } },
    yAxis: { type: 'value', scale: true, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtMoney(v) }, splitLine: { lineStyle: { color: C.grid } } },
    series
  }
}

// 终值分布直方图
function distOpt(): EChartsOption {
  if (!result.value) return {}
  const r = result.value
  const C = { bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62', warn: '#eec170', gold: '#d9a648', text3: '#66635c', border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)' }
  // 分桶
  const finals = r.finalValues
  const min = Math.min(...finals), max = Math.max(...finals)
  const bins = 30
  const binSize = (max - min) / bins
  const histogram = new Array(bins).fill(0)
  for (const v of finals) {
    let idx = Math.floor((v - min) / binSize)
    if (idx >= bins) idx = bins - 1
    histogram[idx]++
  }
  const xData = Array.from({ length: bins }, (_, i) => Math.round((min + i * binSize) / 1000) + 'k')
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtNum(v) },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '5%' },
    xAxis: { type: 'category', data: xData, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, interval: 2 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'bar', data: histogram, barWidth: '90%',
      itemStyle: { color: (p: any) => {
        const v = min + p.dataIndex * binSize
        return v >= capital.value ? C.pos : C.neg
      } }
    }],
    markLine: {
      silent: true,
      data: [
        { xAxis: ((r.median - min) / binSize).toFixed(0), lineStyle: { color: C.gold, type: 'dashed' }, label: { formatter: '中位', color: C.gold } },
        { xAxis: ((capital.value - min) / binSize).toFixed(0), lineStyle: { color: C.text3, type: 'dashed' }, label: { formatter: '本金', color: C.text3 } }
      ]
    }
  }
}
</script>

<style scoped>
.sim-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.sim-grid .span-2 { grid-column: 1 / -1; }
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 10px;
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
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 8px;
}
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 4px 0;
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
.m-sub {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-top: 2px;
}
.hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  text-align: center;
  padding: 40px 0;
}
@media (max-width: 1024px) {
  .sim-grid { grid-template-columns: 1fr; }
  .sim-grid .span-2 { grid-column: span 1; }
  .config-grid { grid-template-columns: 1fr 1fr; }
}
</style>
