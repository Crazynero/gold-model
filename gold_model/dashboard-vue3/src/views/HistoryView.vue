<template>
  <div class="history-grid">
    <HudCard :title="$t('card.timeRange')" :meta="$t('meta.lastNDays')">
      <a-radio-group v-model="range" type="button" size="small" @change="() => {}">
        <a-radio v-for="r in ranges" :key="r.value" :value="r.value">{{ r.label }}</a-radio>
      </a-radio-group>
      <div class="range-info">
        <span>共 {{ filtered.length }} 条记录</span>
        <span class="data-source-tag" :class="apiBase ? 'src-db' : 'src-json'">
          {{ apiBase ? 'SQLite' : 'drift_json' }}
        </span>
        <span v-if="filtered.length > 0">
          {{ filtered[0].run_date || filtered[0].timestamp }} → {{ filtered[filtered.length - 1].run_date || filtered[filtered.length - 1].timestamp }}
        </span>
      </div>
    </HudCard>

    <HudCard :title="$t('card.probabilityTimeline')" :meta="$t('meta.multiWindows')" class="span-2">
      <ChartBox :option="probOpt" height="380px" />
    </HudCard>

    <HudCard :title="$t('card.regimePosition')" :meta="$t('meta.state')" class="span-2">
      <ChartBox :option="regimeOpt" height="280px" />
    </HudCard>

    <HudCard :title="$t('card.mlMetricsDrift')" meta="ACC/AUC/IC" class="span-2">
      <ChartBox :option="metricsOpt" height="320px" />
    </HudCard>

    <HudCard :title="$t('card.bestSharpeTimeline')" :meta="$t('meta.strategyV30e')" class="span-2">
      <ChartBox :option="sharpeOpt" height="260px" />
    </HudCard>

    <HudCard :title="$t('card.historyLog')" :meta="$t('meta.latestNRuns')" class="span-2">
      <a-table :data="logRows" :pagination="{ pageSize: 10, showTotal: true }" size="small" :bordered="{ cell: true }" :scroll="{ x: 1000 }">
        <template #columns>
          <a-table-column :title="$t('col.runAt')" data-index="run_at" :width="140"></a-table-column>
          <a-table-column :title="$t('col.baseDate')" data-index="run_date" :width="100"></a-table-column>
          <a-table-column :title="$t('col.gold')" :width="80">
            <template #cell="{ record }"><span class="mono text-gold">${{ (record.gold_price || 0).toFixed(0) }}</span></template>
          </a-table-column>
          <a-table-column :title="$t('col.regime')" data-index="regime" :width="70"></a-table-column>
          <a-table-column title="POS" :width="60">
            <template #cell="{ record }"><span class="mono">{{ ((record.position || 0) * 100).toFixed(0) }}%</span></template>
          </a-table-column>
          <a-table-column title="P(W)" :width="70">
            <template #cell="{ record }"><span class="mono text-acc">{{ ((record.weighted_prob || 0) * 100).toFixed(1) }}%</span></template>
          </a-table-column>
          <a-table-column title="SHARPE" :width="80">
            <template #cell="{ record }"><span class="mono text-pos">{{ (record.best_sharpe || 0).toFixed(2) }}</span></template>
          </a-table-column>
          <a-table-column :title="$t('col.hitPct')" :width="70">
            <template #cell="{ record }"><span class="mono">{{ ((record.hit_rate_20d || 0) * 100).toFixed(0) }}%</span></template>
          </a-table-column>
          <a-table-column :title="$t('col.action')" data-index="signal_action" :width="100"></a-table-column>
        </template>
      </a-table>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { driftHistory, apiBase, apiStatus, fetchDbHistory } from '@/composables/useDashboardData'
import { fmtNum } from '@/utils/format'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const ranges = [
  { label: '近7天', value: 7 },
  { label: '近30天', value: 30 },
  { label: '近90天', value: 90 },
  { label: '全部', value: 9999 }
]
const range = ref(30)

// SQLite 历史信号（API 模式下从后端拉取）
const dbHistory = ref<any[]>([])

// 加载 SQLite 历史
async function loadDbHistory() {
  if (!apiBase.value) { dbHistory.value = []; return }
  const rows = await fetchDbHistory(365)  // 拉一年
  dbHistory.value = rows || []
}

onMounted(() => {
  loadDbHistory()
})

// API 状态变化时重新加载
watch(apiBase, () => { loadDbHistory() })

// 历史数据源：API 模式用 SQLite，否则用 drift_history
const historySource = computed(() => {
  return apiBase.value && dbHistory.value.length > 0
    ? dbHistory.value
    : (driftHistory.value || [])
})

const C = {
  bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62',
  warn: '#eec170', gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

// 按时间倒序过滤最近 N 天
const filtered = computed(() => {
  const all = historySource.value
  if (all.length === 0) return []
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - range.value)
  const cutoffStr = cutoff.toISOString()
  const sorted = [...all].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''))
  return sorted.filter(r => (r.timestamp || r.run_date || '') >= cutoffStr || range.value >= 9999)
})

// 概率时间序列
function probOpt(): EChartsOption {
  const rows = filtered.value
  if (rows.length === 0) return {}
  const dates = rows.map(r => r.timestamp || r.run_date || '')
  const cur = (r: any, key: string) => {
    const v = r.current_state?.[key]
    return v != null ? v * 100 : null
  }
  // 加权概率 = current_state.probability
  const weighted = rows.map(r => cur(r, 'probability'))
  // 5/10/20/60 日概率在 drift_history 里没有直接字段，从 ml_metrics 推导
  // ml_metrics.{5,10,20,60}.accuracy 是准确率，不是概率。这里用 best_sharpe 反映模型质量
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtNum(v) },
    legend: { data: ['加权概率'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '15%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtNum(v) + '%' }, splitLine: { lineStyle: { color: C.grid } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      {
        name: '加权概率', type: 'line', data: weighted, smooth: true, symbol: 'circle', symbolSize: 5,
        lineStyle: { width: 2, color: C.accent },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(217, 166, 72,0.25)' }, { offset: 1, color: 'rgba(217, 166, 72,0)' }] } },
        markLine: { silent: true, data: [{ yAxis: 60, lineStyle: { color: C.pos, type: 'dashed' }, label: { formatter: '建仓线 60%', color: C.pos } }] }
      }
    ]
  }
}

// Regime + 仓位
function regimeOpt(): EChartsOption {
  const rows = filtered.value
  if (rows.length === 0) return {}
  const dates = rows.map(r => r.timestamp || r.run_date || '')
  const positions = rows.map(r => (r.current_state?.position ?? 0) * 100)
  // Regime 编码：牛市=1, 震荡=0, 熊市=-1
  const regimeMap: Record<string, number> = { '牛市': 1, '震荡': 0, '熊市': -1 }
  const regimes = rows.map(r => regimeMap[r.current_state?.regime || '震荡'] ?? 0)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtNum(v) },
    legend: { data: ['仓位%', 'Regime'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '15%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '仓位%', min: -100, max: 100, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtNum(v) + '%' }, splitLine: { lineStyle: { color: C.grid } } },
      { type: 'value', name: t('chart.regime'), min: -1.5, max: 1.5, position: 'right', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => v === 1 ? '牛' : v === 0 ? '震' : v === -1 ? '熊' : '' }, splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      {
        name: '仓位%', type: 'bar', data: positions, yAxisIndex: 0,
        itemStyle: { color: (p: any) => p.value >= 0 ? C.pos : C.neg }
      },
      {
        name: t('chart.regime'), type: 'line', data: regimes, yAxisIndex: 1, step: 'end',
        symbol: 'none', lineStyle: { width: 1.5, color: C.gold }
      }
    ]
  }
}

// ML 指标漂移
function metricsOpt(): EChartsOption {
  const rows = filtered.value
  if (rows.length === 0) return {}
  const dates = rows.map(r => r.timestamp || r.run_date || '')
  const acc20 = rows.map(r => (r.ml_metrics?.['20']?.accuracy ?? 0) * 100)
  const acc60 = rows.map(r => (r.ml_metrics?.['60']?.accuracy ?? 0) * 100)
  const ic20 = rows.map(r => r.ml_metrics?.['20']?.ic ?? 0)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtNum(v) },
    legend: { data: ['ACC 20D', 'ACC 60D', 'IC 20D'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '15%', top: '12%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: [
      { type: 'value', name: 'ACC%', min: 0, max: 100, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtNum(v) + '%' }, splitLine: { lineStyle: { color: C.grid } } },
      { type: 'value', name: 'IC', position: 'right', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtNum(v) }, splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      { name: 'ACC 20D', type: 'line', data: acc20, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: C.accent } },
      { name: 'ACC 60D', type: 'line', data: acc60, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: C.pos } },
      { name: 'IC 20D', type: 'line', data: ic20, yAxisIndex: 1, smooth: true, symbol: 'none', lineStyle: { width: 1.5, color: C.warn } }
    ]
  }
}

// 最优夏普时间线
function sharpeOpt(): EChartsOption {
  const rows = filtered.value
  if (rows.length === 0) return {}
  const dates = rows.map(r => r.timestamp || r.run_date || '')
  const sharpes = rows.map(r => r.best_sharpe || 0)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: any) => fmtNum(v) },
    grid: { left: '5%', right: '5%', bottom: '15%', top: '8%' },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: (v: number) => fmtNum(v) }, splitLine: { lineStyle: { color: C.grid } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [{
      type: 'line', data: sharpes, smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 2, color: C.gold },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(217, 166, 72,0.2)' }, { offset: 1, color: 'rgba(217, 166, 72,0)' }] } },
      markLine: { silent: true, data: [{ yAxis: 2.0, lineStyle: { color: C.pos, type: 'dashed' }, label: { formatter: '目标 2.0', color: C.pos } }] }
    }]
  }
}

// 历史日志表
const logRows = computed(() => {
  return [...filtered.value].reverse().map(r => ({
    run_at: r.timestamp || '--',
    run_date: r.run_date || '--',
    gold_price: r.current_state?.gold_price || 0,
    regime: r.current_state?.regime || '--',
    position: r.current_state?.position || 0,
    weighted_prob: r.current_state?.probability || 0,
    best_sharpe: r.best_sharpe || 0,
    hit_rate_20d: r.signal_backtest?.recent_20_hit_rate || 0,
    signal_action: r.signal_action ||
      (r.current_state?.regime === '熊市' ? '空仓观望'
       : (r.current_state?.probability > 0.6 ? '建仓' : '观望'))
  }))
})
</script>

<style scoped>
.history-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.history-grid .span-2 { grid-column: span 2; }
.range-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
}
.data-source-tag {
  padding: 1px 6px;
  border: 1px solid;
  font-size: 9px;
  letter-spacing: 0.1em;
}
.src-db { color: var(--pos); border-color: rgba(69,183,137,0.3); }
.src-json { color: var(--warn); border-color: rgba(238,193,112,0.3); }
@media (max-width: 1024px) {
  .history-grid { grid-template-columns: 1fr; }
  .history-grid .span-2 { grid-column: span 1; }
}
</style>
