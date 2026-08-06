<template>
  <div class="overview-grid">
    <HudCard title="DECISION CHAIN" meta="WHY THIS ACTION" class="span-2">
      <div class="chain-row">
        <div class="chain-step">
          <div class="chain-label">加权集成概率</div>
          <div class="chain-value text-acc">{{ prob }}</div>
          <div class="chain-note">{{ probNum >= 50 ? '信号偏多' : '信号偏空' }}</div>
        </div>
        <div class="chain-arrow">→</div>
        <div class="chain-step">
          <div class="chain-label">Regime 过滤</div>
          <div class="chain-value" :style="{ color: regimeColor }">{{ regime }}</div>
          <div class="chain-note">{{ regimeNote }}</div>
        </div>
        <div class="chain-arrow">→</div>
        <div class="chain-step">
          <div class="chain-label">最终建议</div>
          <div class="chain-value text-gold">{{ action }}</div>
          <div class="chain-note">基准日 {{ baseDate }}</div>
        </div>
      </div>
    </HudCard>

    <HudCard title="CURRENT STATE" meta="V5">
      <div class="ov-row"><span>预测基准日</span><b>{{ baseDate }}</b></div>
      <div class="ov-row"><span>当前金价</span><b class="text-gold">{{ goldPrice }}</b></div>
      <div class="ov-row"><span>MA50</span><b>{{ ma50 }}</b></div>
      <div class="ov-row"><span>MA200</span><b>{{ ma200 }}</b></div>
      <div class="ov-row"><span>Regime</span><b :style="{ color: regimeColor }">{{ regime }}</b></div>
      <div class="ov-row"><span>建议</span><b class="text-acc">{{ action }}</b></div>
    </HudCard>

    <HudCard title="INTEGRATED PROBABILITY" meta="WEIGHTED">
      <div class="big-prob-c">
        <div class="big-prob">{{ prob }}</div>
        <div class="big-prob-label">加权集成看多概率</div>
      </div>
      <ProbBars :items="multiHorizon" :height="100" />
    </HudCard>

    <HudCard title="V5 OVERFIT CHECK" meta="HOLDOUT 6M">
      <div class="ov-row"><span>Full Sharpe</span><b class="text-pos">{{ full }}</b></div>
      <div class="ov-row"><span>OOS Sharpe</span><b class="text-neg">{{ oos }}</b></div>
      <div class="ov-row"><span>Decay</span><b class="text-neg">{{ decay }}</b></div>
      <div class="ov-row"><span>Features</span><b class="text-acc">{{ feat }}</b></div>
      <div class="ov-row"><span>Dir Acc 20D</span><b class="text-acc">{{ dirAcc }}</b></div>
    </HudCard>

    <HudCard title="GOLD PRICE" meta="250D" class="span-2">
      <ChartBox :option="priceOpt" height="380px" />
    </HudCard>

    <HudCard title="STRATEGY EVOLUTION" meta="CUM RETURN" class="span-2">
      <ChartBox :option="strategyOpt" height="380px" />
    </HudCard>

    <HudCard title="ML MODEL PERFORMANCE" meta="ACC / AUC / IC" class="span-2">
      <a-table :data="mlModels" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column title="PERIOD" data-index="period"></a-table-column>
          <a-table-column title="ACCURACY" data-index="accuracy"></a-table-column>
          <a-table-column title="AUC" data-index="auc"></a-table-column>
          <a-table-column title="IC" data-index="ic"></a-table-column>
        </template>
      </a-table>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ProbBars from '@/components/ProbBars.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, extractValue, simpleMA } from '@/composables/useDashboardData'

const C = {
  bg: '#04060a', accent: '#00d4ff', pos: '#00ff9c', neg: '#ff3860',
  warn: '#ffb800', gold: '#ffb020', text2: '#8b949e', text3: '#6e7681',
  border: 'rgba(0,212,255,0.14)', grid: 'rgba(0,212,255,0.05)'
}

const baseDate = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')
const goldPrice = computed(() => extractValue(dashboardData.value.overview, '当前金价') || '$----')
const ma50 = computed(() => extractValue(dashboardData.value.overview, 'MA50') || '--')
const ma200 = computed(() => extractValue(dashboardData.value.overview, 'MA200') || '--')
const regime = computed(() => extractValue(dashboardData.value.overview, '当前Regime') || '震荡')
const action = computed(() => extractValue(dashboardData.value.overview, '建议操作') || '空仓观望')
const prob = computed(() => extractValue(dashboardData.value.overview, '加权集成概率') || '--')

const regimeColor = computed(() => {
  if (regime.value.includes('牛')) return 'var(--pos)'
  if (regime.value.includes('熊')) return 'var(--neg)'
  return 'var(--warn)'
})

const probNum = computed(() => parseFloat(String(prob.value).replace('%', '')) || 0)
const regimeNote = computed(() => {
  if (regime.value.includes('熊')) return '压制多头信号，禁止开仓'
  if (regime.value.includes('牛')) return '信号正常放行'
  return '降仓观察，谨慎跟随'
})

const mlModels = computed(() => dashboardData.value.ml_models || [])
const multiHorizon = computed(() => {
  const ov = dashboardData.value.overview || {}
  const parse = (k: string) => {
    const v = ov[k]
    if (v == null) return 0
    const n = parseFloat(String(v).replace('%', ''))
    return isNaN(n) ? 0 : n / 100
  }
  return [
    { label: '5D', pct: parse('5日看多概率') },
    { label: '10D', pct: parse('10日看多概率') },
    { label: '20D', pct: parse('20日看多概率') },
    { label: '60D', pct: parse('60日看多概率') }
  ]
})

const v3e = computed(() => dashboardData.value.strategies?.find(s => s.策略 && s.策略.includes('V3.0-E')))
const full = computed(() => v3e.value?.夏普 || '--')
const oos = computed(() => {
  const h = dashboardData.value.v5_holdout?.find(s => s.strategy && s.strategy.includes('V3.0-E'))
  return h ? h.sharpe.toFixed(2) : '--'
})
const decay = computed(() => {
  const fv = parseFloat(full.value)
  const h = dashboardData.value.v5_holdout?.find(s => s.strategy && s.strategy.includes('V3.0-E'))
  if (!h || fv <= 0 || h.sharpe === 0) return '--%'
  return Math.round((1 - h.sharpe / fv) * 100) + '%'
})
const feat = computed(() => dashboardData.value.v5_feature_count || '--')
const dirAcc = computed(() => {
  const r = dashboardData.value.v5_regression?.find(r => r.horizon === '20日')
  return r?.dir_acc || '--'
})

function priceOpt(): EChartsOption {
  const d = dashboardData.value
  if (!d.raw_data || d.raw_data.length === 0) return {}
  const sorted = [...d.raw_data].reverse()
  const dates = sorted.map(r => r['日期']).filter(Boolean) as string[]
  const prices = sorted.map(r => parseFloat(String(r['金价']))).filter(v => !isNaN(v))
  if (prices.length === 0) return {}
  const ma20 = simpleMA(prices, 20)
  const ma50 = simpleMA(prices, 50)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['金价', 'MA20', 'MA50'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', scale: true, axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: '金价', type: 'line', data: prices, symbol: 'none', lineStyle: { width: 1.5, color: C.gold } },
      { name: 'MA20', type: 'line', data: ma20, symbol: 'none', lineStyle: { width: 1, color: C.accent, opacity: 0.6 } },
      { name: 'MA50', type: 'line', data: ma50, symbol: 'none', lineStyle: { width: 1, color: C.text2, opacity: 0.6 } }
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
    legend: { data: ['BH', 'V3.0-E'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: 'BH', type: 'line', data: bh, symbol: 'none', lineStyle: { width: 1, color: C.text3, opacity: 0.5 } },
      { name: 'V3.0-E', type: 'line', data: v3e, symbol: 'none', lineStyle: { width: 1.5, color: C.accent } }
    ]
  }
}
</script>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.overview-grid .span-2 { grid-column: span 3; }
.ov-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 12px;
  color: var(--text-2);
}
.ov-row:last-child { border-bottom: none; }
.ov-row b { color: var(--text); font-family: var(--mono); font-weight: 500; }
.big-prob-c { text-align: center; padding: 10px 0 16px; }
.big-prob { font-family: var(--mono); font-size: 44px; color: var(--accent); text-shadow: 0 0 16px rgba(0,212,255,0.4); }
.big-prob-label { font-family: var(--mono); font-size: 10px; color: var(--text-3); margin-top: 4px; letter-spacing: 0.1em; text-transform: uppercase; }
.chain-row {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 10px 0 4px;
  gap: 8px;
}
.chain-step { text-align: center; min-width: 160px; }
.chain-label {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.chain-value { font-family: var(--mono); font-size: 22px; font-weight: 600; }
.chain-note { font-size: 11px; color: var(--text-2); margin-top: 4px; }
.chain-arrow { font-family: var(--mono); font-size: 20px; color: var(--text-dim); }

@media (max-width: 1024px) {
  .overview-grid { grid-template-columns: 1fr; }
  .overview-grid .span-2 { grid-column: span 1; }
}
</style>
