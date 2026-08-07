<template>
  <div class="backtest-grid">
    <HudCard :title="$t('card.strategyComparison')" :meta="$t('meta.strategies8')" class="span-2">
      <a-table :data="strategies" :pagination="false" size="small" :bordered="{ cell: true }" row-key="策略">
        <template #columns>
          <a-table-column :title="$t('col.strategy')" data-index="策略">
            <template #cell="{ record }">
              <span :class="record['策略'].includes('V3.0-E') ? 'text-acc mono' : 'mono'">{{ record['策略'] }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.annualRet')" data-index="年化收益"></a-table-column>
          <a-table-column title="VOL" data-index="年化波动"></a-table-column>
          <a-table-column title="SHARPE" data-index="夏普">
            <template #cell="{ record }">
              <span :class="parseFloat(record.夏普) > 1.5 ? 'text-pos mono' : 'mono'">{{ record.夏普 }}</span>
            </template>
          </a-table-column>
          <a-table-column title="MAX DD" data-index="最大回撤">
            <template #cell="{ record }">
              <span class="text-neg mono">{{ record.最大回撤 }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.winRate')" data-index="胜率"></a-table-column>
          <a-table-column title="CALMAR" data-index="Calmar"></a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.strategyEvolution')" :meta="$t('meta.cumulativeReturn')" class="span-2">
      <ChartBox :option="strategyOpt" height="440px" />
    </HudCard>

    <HudCard :title="$t('card.drawdownProfile')" :meta="$t('meta.underwaterCurve')" class="span-2">
      <ChartBox :option="drawdownOpt" height="380px" />
    </HudCard>

    <HudCard :title="$t('card.regimeRadar')" meta="V3.0-E vs BH · 真实数据">
      <ChartBox :option="radarOpt" height="380px" />
    </HudCard>

    <HudCard :title="$t('card.backtestNotes')" class="span-2">
      <div class="notes">
        <p><b>V3.0-E</b> 多周期集成：5日/10日/20日/60日XGBoost加权</p>
        <p><b>非对称仓位</b>：牛市做多不做空，熊市做空不做多</p>
        <p><b>Vol靶向</b>：目标年化15%波动率，动态调整</p>
        <p><b>信号质量熔断</b>：滚动命中率<30%→仓位×0.2</p>
      </div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData } from '@/composables/useDashboardData'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const C = {
  bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62',
  warn: '#eec170', gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

const strategies = computed(() => dashboardData.value.strategies || [])

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
    legend: { data: [t('chart.bh'), 'V3.0-E'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: t('chart.bh'), type: 'line', data: bh, symbol: 'none', lineStyle: { width: 1, color: C.text3, opacity: 0.5 } },
      { name: 'V3.0-E', type: 'line', data: v3e, symbol: 'none', lineStyle: { width: 1.5, color: C.accent } }
    ]
  }
}

function drawdownOpt(): EChartsOption {
  const d = dashboardData.value
  if (!d.raw_data || d.raw_data.length === 0) return {}
  const sorted = [...d.raw_data].reverse()
  const dates = sorted.map(r => r['日期']).filter(Boolean) as string[]
  const gp = sorted.map(r => parseFloat(String(r['金价']))).filter(v => !isNaN(v))
  if (gp.length === 0) return {}
  const peak = [gp[0]]
  for (let i = 1; i < gp.length; i++) peak.push(Math.max(peak[i - 1], gp[i]))
  const dd = gp.map((p, i) => i > 0 ? (p / peak[i] - 1) * 100 : 0)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '5%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', max: 0, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: '{value}%' }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'line', data: dd, symbol: 'none', lineStyle: { width: 1, color: C.neg },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(207, 107, 98,0.05)' }, { offset: 1, color: 'rgba(207, 107, 98,0.3)' }] } }
    }]
  }
}

function radarOpt(): EChartsOption {
  const rows = dashboardData.value.strategies || []
  const v3e = rows.find(r => r.策略?.includes('V3.0-E')) || {}
  const bh = rows.find(r => r.策略?.includes('买入持有')) || {}
  const parse = (v: any) => parseFloat(String(v ?? '0').replace('%', '').replace('+', ''))
  const toArr = (s: any) => [
    parse(s?.夏普),
    parse(s?.年化收益),
    parse(s?.胜率),
    parse(s?.Calmar),
    Math.abs(parse(s?.最大回撤)),
    parse(s?.年化波动)
  ]
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'item' },
    legend: { data: ['V3.0-E', t('chart.bh')], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    radar: {
      indicator: [
        { name: 'SHARPE', max: 3 },
        { name: 'RET', max: 30 },
        { name: 'WIN%', max: 70 },
        { name: 'CALMAR', max: 4 },
        { name: '-DD%', max: 30 },
        { name: 'VOL%', max: 25 }
      ],
      axisName: { color: C.text2, fontSize: 10 },
      splitLine: { lineStyle: { color: C.grid } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: C.border } }
    },
    series: [{
      type: 'radar',
      data: [
        { value: toArr(v3e), name: 'V3.0-E', lineStyle: { color: C.accent }, areaStyle: { color: 'rgba(217, 166, 72,0.15)' } },
        { value: toArr(bh), name: t('chart.bh'), lineStyle: { color: C.text3 }, areaStyle: { color: 'rgba(139,148,158,0.08)' } }
      ]
    }]
  }
}
</script>

<style scoped>
.backtest-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.backtest-grid .span-2 { grid-column: span 2; }
.notes { padding: 8px 0; font-size: 12px; color: var(--text-2); line-height: 1.8; }
.notes p { margin: 4px 0; }
.notes b { color: var(--accent); }
@media (max-width: 1024px) {
  .backtest-grid { grid-template-columns: 1fr; }
  .backtest-grid .span-2 { grid-column: span 1; }
}
</style>
