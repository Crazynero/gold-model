<template>
  <div class="wf-grid">
    <HudCard title="WALK-FORWARD OVERVIEW" meta="ML METRICS DRIFT" class="span-2">
      <div class="wf-summary">
        <div class="wf-cell">
          <div class="m-label">总运行数</div>
          <div class="m-value text-acc">{{ records.length }}</div>
        </div>
        <div class="wf-cell">
          <div class="m-label">时间跨度</div>
          <div class="m-value text-2">{{ spanDays }}</div>
          <div class="m-sub">天</div>
        </div>
        <div class="wf-cell">
          <div class="m-label">最新夏普</div>
          <div class="m-value text-pos">{{ latestSharpe }}</div>
        </div>
        <div class="wf-cell">
          <div class="m-label">最新命中率</div>
          <div class="m-value" :class="latestHitRate >= 0.5 ? 'text-pos' : 'text-neg'">{{ (latestHitRate * 100).toFixed(0) }}%</div>
        </div>
        <div class="wf-cell">
          <div class="m-label">IC 中位</div>
          <div class="m-value text-2">{{ icMedian }}</div>
        </div>
        <div class="wf-cell">
          <div class="m-label">稳定性</div>
          <div class="m-value" :class="stabilityClass">{{ stabilityLabel }}</div>
        </div>
      </div>
    </HudCard>

    <HudCard title="ROLLING METRICS" meta="4 HORIZONS" class="span-2">
      <a-radio-group v-model="metric" type="button" size="small">
        <a-radio value="accuracy">ACC</a-radio>
        <a-radio value="auc">AUC</a-radio>
        <a-radio value="ic">IC</a-radio>
      </a-radio-group>
      <ChartBox :option="rollingOpt" height="320px" />
    </HudCard>

    <HudCard title="BEST SHARPE HISTORY" meta="OBSERVED">
      <ChartBox :option="sharpeOpt" height="260px" />
    </HudCard>

    <HudCard title="HIT RATE vs BASELINE" meta="20D ROLLING">
      <ChartBox :option="hitRateOpt" height="260px" />
    </HudCard>

    <HudCard title="STABILITY ANALYSIS" meta="VARIANCE">
      <a-table :data="stabilityRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column title="METRIC" data-index="metric" :width="100"></a-table-column>
          <a-table-column title="MEAN" data-index="mean" :width="80">
            <template #cell="{ record }"><span class="mono">{{ record.mean }}</span></template>
          </a-table-column>
          <a-table-column title="STD" data-index="std" :width="80">
            <template #cell="{ record }"><span class="mono" :class="parseFloat(record.std) > 0.05 ? 'text-neg' : 'text-pos'">{{ record.std }}</span></template>
          </a-table-column>
          <a-table-column title="CV" data-index="cv" :width="80">
            <template #cell="{ record }"><span class="mono" :class="parseFloat(record.cv) > 0.3 ? 'text-neg' : 'text-pos'">{{ record.cv }}</span></template>
          </a-table-column>
          <a-table-column title="MIN" data-index="min" :width="80"></a-table-column>
          <a-table-column title="MAX" data-index="max" :width="80"></a-table-column>
          <a-table-column title="RANGE" data-index="range" :width="80">
            <template #cell="{ record }"><span class="mono text-warn">{{ record.range }}</span></template>
          </a-table-column>
        </template>
      </a-table>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { driftHistory } from '@/composables/useDashboardData'

const C = {
  bg: '#04060a', accent: '#00d4ff', pos: '#00ff9c', neg: '#ff3860',
  warn: '#ffb800', text2: '#8b949e', text3: '#6e7681',
  border: 'rgba(0,212,255,0.14)', grid: 'rgba(0,212,255,0.05)'
}

const metric = ref<'accuracy' | 'auc' | 'ic'>('ic')

const records = computed(() => driftHistory.value || [])

const spanDays = computed(() => {
  if (records.value.length < 2) return 0
  const first = records.value[0].timestamp || records.value[0].run_date
  const last = records.value[records.value.length - 1].timestamp || records.value[records.value.length - 1].run_date
  const d1 = new Date(first).getTime()
  const d2 = new Date(last).getTime()
  return Math.max(1, Math.round((d2 - d1) / 86400000))
})

const latestSharpe = computed(() => {
  const r = records.value[records.value.length - 1]
  return r?.best_sharpe?.toFixed(2) || '--'
})

const latestHitRate = computed(() => {
  const r = records.value[records.value.length - 1]
  return r?.signal_backtest?.recent_20_hit_rate || 0
})

const icValues = computed(() => {
  return records.value.map(r => r.ml_metrics?.['60']?.ic || 0).filter(v => v != null)
})

const icMedian = computed(() => {
  if (icValues.value.length === 0) return '--'
  const sorted = [...icValues.value].sort()
  const mid = Math.floor(sorted.length / 2)
  return (sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2).toFixed(3)
})

const stabilityClass = computed(() => {
  if (icValues.value.length < 2) return 'text-2'
  const mean = icValues.value.reduce((a, b) => a + b, 0) / icValues.value.length
  const variance = icValues.value.reduce((a, b) => a + (b - mean) ** 2, 0) / icValues.value.length
  const std = Math.sqrt(variance)
  const cv = Math.abs(mean) > 0 ? std / Math.abs(mean) : 1
  if (cv < 0.3) return 'text-pos'
  if (cv < 0.6) return 'text-warn'
  return 'text-neg'
})

const stabilityLabel = computed(() => {
  if (stabilityClass.value === 'text-pos') return 'STABLE'
  if (stabilityClass.value === 'text-warn') return 'OK'
  return 'UNSTABLE'
})

const stabilityRows = computed(() => {
  const metrics = ['accuracy', 'auc', 'ic']
  return metrics.map(m => {
    const collect = (h: string) => records.value.map(r => r.ml_metrics?.[h]?.[m]).filter(v => v != null) as number[]
    const all5 = collect('5')
    const all10 = collect('10')
    const all20 = collect('20')
    const all60 = collect('60')
    const all = [...all5, ...all10, ...all20, ...all60]
    if (all.length === 0) return { metric: m.toUpperCase(), mean: '--', std: '--', cv: '--', min: '--', max: '--', range: '--' }
    const mean = all.reduce((a, b) => a + b, 0) / all.length
    const variance = all.reduce((a, b) => a + (b - mean) ** 2, 0) / all.length
    const std = Math.sqrt(variance)
    const min = Math.min(...all)
    const max = Math.max(...all)
    return {
      metric: m.toUpperCase(),
      mean: mean.toFixed(3),
      std: std.toFixed(3),
      cv: (Math.abs(mean) > 0 ? std / Math.abs(mean) : 1).toFixed(2),
      min: min.toFixed(3),
      max: max.toFixed(3),
      range: (max - min).toFixed(3)
    }
  })
})

function rollingOpt(): EChartsOption {
  const horizons = ['5', '10', '20', '60']
  const colors = [C.accent, C.pos, C.warn, C.text2]
  const dates = records.value.map(r => r.timestamp || r.run_date || '--')
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: horizons.map(h => h + 'd'), textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '10%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: horizons.map((h, i) => ({
      name: h + 'd',
      type: 'line',
      data: records.value.map(r => r.ml_metrics?.[h]?.[metric.value] || null),
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { width: 1.5, color: colors[i] },
      itemStyle: { color: colors[i] }
    }))
  }
}

function sharpeOpt(): EChartsOption {
  const dates = records.value.map(r => r.timestamp || r.run_date || '--')
  const values = records.value.map(r => r.best_sharpe || 0)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '10%', top: '8%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', name: 'Sharpe', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2, color: C.pos },
      itemStyle: { color: C.pos },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,255,156,0.15)' }, { offset: 1, color: 'rgba(0,255,156,0)' }] } },
      markLine: { data: [{ type: 'average', name: '均值' }], lineStyle: { color: C.text3, type: 'dashed' } }
    }]
  }
}

function hitRateOpt(): EChartsOption {
  const dates = records.value.map(r => r.timestamp || r.run_date || '--')
  const hitRates = records.value.map(r => r.signal_backtest?.recent_20_hit_rate || 0)
  const wfBase = records.value[0]?.signal_backtest?.wf_baseline_acc || 0.58
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '10%', top: '8%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: '{value}%' }, splitLine: { lineStyle: { color: C.grid } }, min: 0, max: 1 },
    series: [
      {
        type: 'bar',
        data: hitRates.map(h => ({ value: h, itemStyle: { color: h >= wfBase ? C.pos : C.neg } })),
        barWidth: '50%',
        name: '命中率'
      },
      {
        type: 'line',
        data: dates.map(() => wfBase),
        name: 'WF基准',
        lineStyle: { color: C.warn, type: 'dashed', width: 1.5 },
        symbol: 'none'
      }
    ]
  }
}
</script>

<style scoped>
.wf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.wf-grid .span-2 { grid-column: span 2; }
.wf-summary { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; padding: 8px 0; }
.wf-cell { text-align: center; padding: 8px 0; }
.m-label { font-family: var(--mono); font-size: 9px; color: var(--text-3); letter-spacing: 0.1em; text-transform: uppercase; }
.m-value { font-family: var(--mono); font-size: 22px; margin-top: 4px; font-weight: 500; }
.m-sub { font-family: var(--mono); font-size: 9px; color: var(--text-3); }
@media (max-width: 1024px) {
  .wf-grid { grid-template-columns: 1fr; }
  .wf-grid .span-2 { grid-column: span 1; }
  .wf-summary { grid-template-columns: 1fr 1fr 1fr; }
}
</style>
