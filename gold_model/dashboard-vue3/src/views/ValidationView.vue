<template>
  <div class="val-grid">
    <HudCard :title="$t('card.holdoutVerification')" :meta="$t('meta.oos6m')" class="span-2">
      <div class="val-summary">
        <div class="val-cell">
          <div class="val-label">{{ $t('txt.fullSharpe') }}</div>
          <div class="val-value text-pos">{{ full }}</div>
        </div>
        <div class="val-arrow">→</div>
        <div class="val-cell">
          <div class="val-label">{{ $t('txt.oosSharpe') }}</div>
          <div class="val-value text-neg">{{ oos }}</div>
        </div>
        <div class="val-arrow">·</div>
        <div class="val-cell">
          <div class="val-label">{{ $t('txt.decay') }}</div>
          <div class="val-value text-neg">{{ decay }}</div>
        </div>
        <div class="val-cell">
          <div class="val-label">BH OOS</div>
          <div class="val-value text-neg">{{ bhOos }}</div>
        </div>
        <div class="val-cell">
          <div class="val-label">{{ $t('txt.features') }}</div>
          <div class="val-value text-acc">{{ feat }}/{{ featOrig }}</div>
        </div>
      </div>
    </HudCard>

    <HudCard :title="$t('card.fullVsOosSharpe')" :meta="$t('meta.byStrategy')" class="span-2">
      <ChartBox :option="compOpt" height="440px" />
    </HudCard>

    <HudCard :title="$t('card.regressionBranch')" :meta="$t('meta.rDirAcc')">
      <a-table :data="regressionRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column :title="$t('col.horizon')" data-index="horizon"></a-table-column>
          <a-table-column title="R²" data-index="r2">
            <template #cell="{ record }">
              <span :class="parseFloat(record.r2) < 0 ? 'text-neg mono' : 'text-pos mono'">{{ record.r2 }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.dirAcc')" data-index="dir_acc">
            <template #cell="{ record }">
              <span class="text-acc mono">{{ record.dir_acc }}</span>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.holdoutDetail')" :meta="$t('meta.strategies6m')" class="span-2">
      <a-table :data="holdoutRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column :title="$t('col.strategy')" data-index="strategy" fixed="left" :width="180"></a-table-column>
          <a-table-column :title="$t('col.fullSharpe')" :width="120">
            <template #cell="{ record }">
              <span class="mono text-pos">{{ findFullSharpe(record.strategy) }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.oosSharpe')" :width="120">
            <template #cell="{ record }">
              <span :class="record.sharpe > 0 ? 'text-pos mono' : 'text-neg mono'">{{ record.sharpe.toFixed(2) }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.decayPct')" :width="100">
            <template #cell="{ record }">
              <span class="text-neg mono">{{ calcDecay(record) }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.oosRet')" data-index="ann_ret" :width="100">
            <template #cell="{ record }">
              <span :class="parseFloat(record.ann_ret) > 0 ? 'text-pos mono' : 'text-neg mono'">{{ record.ann_ret }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.oosDd')" data-index="max_dd" :width="100">
            <template #cell="{ record }">
              <span class="text-neg mono">{{ record.max_dd }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.win')" data-index="win_rate" :width="80"></a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.overfittingDiagnosis')" class="span-2">
      <div class="diagnosis">
        <div class="diag-item"><span class="badge badge-red">{{ $t('txt.cause1') }}</span><p>V1→V4 在同一 5 年数据上反复迭代调参，每版看着回测结果加料（数据窥探）。</p></div>
        <div class="diag-item"><span class="badge badge-red">{{ $t('txt.cause2') }}</span><p>2020-2025 黄金大牛市，"牛市不做空"规则恰好匹配此段历史，非模型泛化能力。</p></div>
        <div class="diag-item"><span class="badge badge-red">{{ $t('txt.cause3') }}</span><p>8 个策略在同一数据上选最优 V3.0-E，"选最优"本身就在看回测结果。</p></div>
        <div class="diag-item"><span class="badge badge-green">{{ $t('txt.conclusion') }}</span><p>实盘夏普预期 ≈ -0.1，非回测的 2.5。但 OOS 仍跑赢 BH（-1.5），模型有 OOS 价值只是被夸大。</p></div>
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
  text2: '#a09d94', text3: '#66635c', border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

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
const bhOos = computed(() => {
  const h = dashboardData.value.v5_holdout?.find(s => s.strategy && (s.strategy.includes('BH') || s.strategy.includes('买入')))
  return h ? h.sharpe.toFixed(2) : '-1.47'
})
const feat = computed(() => dashboardData.value.v5_feature_count || '--')
const featOrig = computed(() => dashboardData.value.v5_original_feature_count || 42)

const holdoutRows = computed(() => dashboardData.value.v5_holdout || [])
const regressionRows = computed(() => dashboardData.value.v5_regression || [])

// 从 strategies 表里找对应策略的 Full Sharpe
function findFullSharpe(strategyName?: string): string {
  if (!strategyName) return '--'
  const s = dashboardData.value.strategies?.find(x => x.策略 === strategyName)
  return s?.夏普 || '--'
}

// 计算 decay%：(1 - oos/full) * 100
function calcDecay(row: any): string {
  const fullStr = findFullSharpe(row.strategy)
  const full = parseFloat(fullStr)
  if (!full || !row.sharpe) return '--'
  const decay = (1 - row.sharpe / full) * 100
  return decay.toFixed(0) + '%'
}

function compOpt(): EChartsOption {
  const rows = dashboardData.value.v5_holdout || []
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['FULL', 'OOS'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '3%', bottom: '15%', top: '12%' },
    xAxis: { type: 'category', data: rows.map(r => r.strategy), axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: t('chart.full'), type: 'bar', data: rows.map(r => r.full_sharpe), itemStyle: { color: C.accent }, barWidth: '30%' },
      { name: 'OOS', type: 'bar', data: rows.map(r => r.sharpe), itemStyle: { color: C.neg }, barWidth: '30%' }
    ]
  }
}
</script>

<style scoped>
.val-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.val-grid .span-2 { grid-column: span 2; }
.val-summary {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 20px 0;
  gap: 12px;
}
.val-cell { text-align: center; }
.val-label { font-family: var(--mono); font-size: 9px; color: var(--text-3); letter-spacing: 0.1em; text-transform: uppercase; }
.val-value { font-family: var(--mono); font-size: 28px; margin-top: 6px; text-shadow: 0 0 12px current-color; }
.val-arrow { color: var(--text-3); font-size: 20px; }

.diagnosis { padding: 8px 0; }
.diag-item { display: flex; align-items: flex-start; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border-soft); }
.diag-item:last-child { border-bottom: none; }
.diag-item p { margin: 0; font-size: 12px; color: var(--text-2); line-height: 1.7; }
.badge { padding: 2px 8px; border-radius: 2px; font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; flex-shrink: 0; }
.badge-red { background: rgba(207, 107, 98, 0.1); color: var(--neg); border: 1px solid rgba(207, 107, 98, 0.3); }
.badge-green { background: rgba(69, 183, 137, 0.1); color: var(--pos); border: 1px solid rgba(69, 183, 137, 0.3); }

@media (max-width: 1024px) {
  .val-grid { grid-template-columns: 1fr; }
  .val-grid .span-2 { grid-column: span 1; }
}
</style>
