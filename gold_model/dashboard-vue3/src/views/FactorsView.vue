<template>
  <div class="factors-grid">
    <HudCard title="FEATURE IMPORTANCE" meta="XGBOOST GAIN" class="span-2">
      <ChartBox :option="featOpt" height="440px" />
    </HudCard>

    <HudCard title="TOP FACTORS" meta="RANKED">
      <a-table :data="topFeatures" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column title="#" :width="40">
            <template #cell="{ rowIndex }">{{ rowIndex + 1 }}</template>
          </a-table-column>
          <a-table-column title="FACTOR" data-index="name"></a-table-column>
          <a-table-column title="GAIN" data-index="avg">
            <template #cell="{ record }">
              <span class="mono text-acc">{{ record.avg.toFixed(2) }}</span>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard title="CURRENT FACTOR SNAPSHOT" class="span-2">
      <a-table :data="currentFactors" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column title="FACTOR" data-index="name"></a-table-column>
          <a-table-column title="VALUE" data-index="value">
            <template #cell="{ record }">
              <span class="mono text-acc">{{ fmtNum(record.value) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="MOMENTUM" data-index="momentum"></a-table-column>
          <a-table-column title="SIGNAL" data-index="signal"></a-table-column>
        </template>
      </a-table>
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
  gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

const topFeatures = computed(() => (dashboardData.value.features || []).slice(0, 12))
const currentFactors = computed(() => dashboardData.value.current_factors || [])

// 智能数字格式化
function fmtNum(v: any): string {
  if (v == null || v === '') return '--'
  const n = parseFloat(String(v))
  if (isNaN(n)) return String(v)
  if (Number.isInteger(n)) return n.toString()
  if (Math.abs(n) < 1 && n !== 0) return n.toFixed(3)
  return n.toFixed(2)
}

function featOpt(): EChartsOption {
  const feats = dashboardData.value.features || []
  const top = feats.slice(0, 15).reverse()
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '28%', right: '5%', bottom: '5%', top: '5%' },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 }, splitLine: { lineStyle: { color: C.grid } } },
    yAxis: { type: 'category', data: top.map(f => f.name), axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text2, fontSize: 11 } },
    series: [{
      type: 'bar',
      data: top.map(f => ({ value: f.avg, itemStyle: { color: C.accent } })),
      barWidth: '60%',
      label: { show: true, position: 'right', color: C.text3, fontSize: 10 }
    }]
  }
}
</script>

<style scoped>
.factors-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.factors-grid .span-2 { grid-column: span 2; }
@media (max-width: 1024px) {
  .factors-grid { grid-template-columns: 1fr; }
  .factors-grid .span-2 { grid-column: span 1; }
}
</style>
