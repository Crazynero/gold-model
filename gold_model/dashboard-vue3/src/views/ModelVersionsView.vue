<template>
  <div class="mv-grid">
    <HudCard :title="$t('card.versionComparisonTable')" meta="V3.0-A → V3.0-E + BH" class="span-2">
      <a-table :data="strategyRows" :pagination="false" size="small" :bordered="{ cell: true }" row-key="策略">
        <template #columns>
          <a-table-column :title="$t('col.strategy')" data-index="策略" :width="180" fixed="left">
            <template #cell="{ record }">
              <span :class="record['策略'].includes('V3.0-E') ? 'text-acc mono' : 'mono'">{{ record['策略'] }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.annualRet')" data-index="年化收益" :sortable="{ sortDirections: ['descend','ascend'] }">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record['年化收益']) > 25 ? 'text-pos' : 'text-2'">{{ record['年化收益'] }}</span>
            </template>
          </a-table-column>
          <a-table-column title="SHARPE" data-index="夏普" :sortable="{ sortDirections: ['descend','ascend'] }">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record.夏普) > 2 ? 'text-pos' : 'text-2'">{{ record.夏普 }}</span>
            </template>
          </a-table-column>
          <a-table-column title="MAX DD" data-index="最大回撤">
            <template #cell="{ record }">
              <span class="mono text-neg">{{ record['最大回撤'] }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.win')" data-index="胜率"></a-table-column>
          <a-table-column :title="$t('col.cumRet')" data-index="累计收益"></a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.evolutionChain')" meta="V1→V5" class="span-2">
      <ChartBox :option="evolutionOpt" height="320px" />
    </HudCard>

    <HudCard :title="$t('card.multiMetricRadar')" :meta="$t('meta.dimensions6')">
      <ChartBox :option="radarOpt" height="320px" />
    </HudCard>

    <HudCard :title="$t('card.keyObservations')" :meta="$t('meta.lessons')">
      <div class="obs-list">
        <div class="obs-item">
          <span class="obs-tag text-pos">V3.0-B</span>
          <p>加 Vol靶向使夏普 1.25→2.24（年化波动 18%→12.6%，回撤 22%→8.6%）—— 风险预算管理是关键</p>
        </div>
        <div class="obs-item">
          <span class="obs-tag text-warn">V3.0-D</span>
          <p>Kelly 加仓后收益大幅下滑（28%→5.5%）—— Kelly 在低胜率策略上会过度加仓，需配合质量熔断</p>
        </div>
        <div class="obs-item">
          <span class="obs-tag text-acc">V3.0-E</span>
          <p>多周期集成（5/10/20/60d）让概率估计更稳，夏普维持 2.44，但回撤从 8.6% 升至 6.9%—— 集成降波动</p>
        </div>
        <div class="obs-item">
          <span class="obs-tag text-2">买入持有</span>
          <p>BH 夏普 1.31 / 回撤 -25%—— 牛市表现好但回撤失控，Regime+非对称仓位是超额收益核心来源</p>
        </div>
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

const C = {
  bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62',
  warn: '#eec170', gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

const strategyRows = computed(() => dashboardData.value.strategies || [])

function evolutionOpt(): EChartsOption {
  const rows = dashboardData.value.strategies || []
  const ordered = ['V1.0 线性IC', 'V2.0 ML+趋势', 'V3.0-A Regime+非对称', 'V3.0-B +Vol靶向', 'V3.0-C +止损', 'V3.0-D +Kelly', 'V3.0-E 多周期集成', '买入持有']
  const labels = ['V1.0', 'V2.0', 'V3.0-A', 'V3.0-B', 'V3.0-C', 'V3.0-D', 'V3.0-E', 'BH']
  const byName = (n: string) => rows.find(r => r.策略 === n)
  const sharpes = ordered.map(n => parseFloat(byName(n)?.夏普 || '0'))
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '10%', top: '10%' },
    xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', name: 'Sharpe', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'line',
      data: sharpes,
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { width: 2, color: C.accent },
      itemStyle: { color: C.accent },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(217, 166, 72,0.2)' }, { offset: 1, color: 'rgba(217, 166, 72,0)' }] } },
      label: { show: true, position: 'top', color: C.text2, fontSize: 10, formatter: '{c}' }
    }]
  }
}

function radarOpt(): EChartsOption {
  const rows = dashboardData.value.strategies || []
  const v3e = rows.find(r => r.策略?.includes('V3.0-E'))
  const bh = rows.find(r => r.策略?.includes('买入持有'))
  const v3b = rows.find(r => r.策略?.includes('V3.0-B'))
  const toArr = (s: any) => [
    parseFloat(s?.夏普 || '0'),
    parseFloat(s?.年化收益 || '0'),
    parseFloat(s?.胜率 || '0'),
    parseFloat(s?.Calmar || '0'),
    -parseFloat(s?.最大回撤 || '0'),
    -parseFloat(s?.年化波动 || '0')
  ]
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: {},
    legend: { data: ['V3.0-E', 'V3.0-B', '买入持有'], textStyle: { color: C.text3, fontSize: 10 }, bottom: 0 },
    radar: {
      indicator: [
        { name: 'Sharpe', max: 3 },
        { name: '收益%', max: 30 },
        { name: '胜率%', max: 60 },
        { name: 'Calmar', max: 4 },
        { name: '回撤%(反)', max: 30 },
        { name: '波动%(反)', max: 25 }
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: C.text2, fontSize: 10 },
      splitLine: { lineStyle: { color: C.grid } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: C.border } }
    },
    series: [{
      type: 'radar',
      data: [
        { value: toArr(v3e), name: 'V3.0-E', lineStyle: { color: C.accent }, areaStyle: { color: 'rgba(217, 166, 72,0.15)' } },
        { value: toArr(v3b), name: 'V3.0-B', lineStyle: { color: C.pos }, areaStyle: { color: 'rgba(69, 183, 137,0.1)' } },
        { value: toArr(bh), name: '买入持有', lineStyle: { color: C.text2 }, areaStyle: { color: 'rgba(139,148,158,0.08)' } }
      ]
    }]
  }
}
</script>

<style scoped>
.mv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.mv-grid .span-2 { grid-column: span 2; }
.obs-list { padding: 4px 0; }
.obs-item { padding: 10px 0; border-bottom: 1px solid var(--border-soft); display: flex; align-items: flex-start; gap: 8px; }
.obs-item:last-child { border-bottom: none; }
.obs-tag {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  font-weight: 500;
  flex-shrink: 0;
  padding-top: 2px;
}
.obs-item p { margin: 0; font-size: 11px; color: var(--text-2); line-height: 1.6; }
@media (max-width: 1024px) {
  .mv-grid { grid-template-columns: 1fr; }
  .mv-grid .span-2 { grid-column: span 1; }
}
</style>
