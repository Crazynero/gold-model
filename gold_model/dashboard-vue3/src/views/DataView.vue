<template>
  <div class="data-grid">
    <HudCard :title="$t('card.rawDataTable')" :meta="$t('meta.last250Days')" class="span-2">
      <div class="data-toolbar">
        <a-input v-model="search" :placeholder="$t('common.searchDate')" style="width: 200px" size="small" allow-clear />
        <a-radio-group v-model="filter" size="small" type="button">
          <a-radio value="all">全部</a-radio>
          <a-radio value="recent">近30日</a-radio>
          <a-radio value="signal">有信号变化</a-radio>
        </a-radio-group>
        <a-button size="small" @click="downloadCSV">{{ $t('common.export') }}</a-button>
      </div>
      <a-table
        :data="filteredRows"
        :pagination="{ pageSize: 20, showTotal: true, showPageSize: true }"
        size="small"
        :bordered="{ cell: true }"
        :scroll="{ y: 400 }"
      >
        <template #columns>
          <a-table-column :title="$t('col.date')" data-index="日期" :width="100" fixed="left"></a-table-column>
          <a-table-column :title="$t('col.gold')" :width="90">
            <template #cell="{ record }">
              <span class="mono text-gold">{{ fmtMoney(record['金价']) }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.regime')" data-index="Regime" :width="70">
            <template #cell="{ record }">
              <span :class="record.Regime === '牛市' ? 'text-pos' : record.Regime === '熊市' ? 'text-neg' : 'text-warn'">{{ record.Regime }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.realRate')" :width="90">
            <template #cell="{ record }"><span class="mono">{{ fmtNum(record['10年实际利率']) }}</span></template>
          </a-table-column>
          <a-table-column title="DXY" :width="70">
            <template #cell="{ record }"><span class="mono">{{ fmtNum(record['美元指数']) }}</span></template>
          </a-table-column>
          <a-table-column title="VIX" :width="70">
            <template #cell="{ record }"><span class="mono">{{ fmtNum(record['VIX恐慌']) }}</span></template>
          </a-table-column>
          <a-table-column title="FOMC" :width="70">
            <template #cell="{ record }"><span class="mono text-muted">{{ fmtNum(record['距FOMC天数']) }}</span></template>
          </a-table-column>
          <a-table-column title="CPI" :width="70">
            <template #cell="{ record }"><span class="mono text-muted">{{ fmtNum(record['距CPI天数']) }}</span></template>
          </a-table-column>
          <a-table-column title="COT-Z" :width="70">
            <template #cell="{ record }">
              <span v-if="record['COT净多Z'] !== '' && record['COT净多Z'] !== undefined" :class="parseFloat(record['COT净多Z']) > 0 ? 'mono text-pos' : 'mono text-neg'">{{ parseFloat(record['COT净多Z']).toFixed(2) }}</span>
              <span v-else class="mono text-muted">--</span>
            </template>
          </a-table-column>
          <a-table-column title="VOL20" :width="70">
            <template #cell="{ record }"><span class="mono">{{ (parseFloat(record['20日波动率']) * 100).toFixed(1) }}%</span></template>
          </a-table-column>
          <a-table-column title="MA200%" :width="80">
            <template #cell="{ record }"><span :class="parseFloat(record['MA200偏离']) > 0 ? 'mono text-pos' : 'mono text-neg'">{{ (parseFloat(record['MA200偏离']) * 100).toFixed(1) }}%</span></template>
          </a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.dataSourceStatus')">
      <!-- 修复: 此前写死"25/25 ✅",采集崩溃时页面仍显示全绿;现从主管道回传的真实成功率渲染 -->
      <div class="src-row"><span>市场数据源(八层降级)</span><b :class="srcRatio >= 0.8 ? 'text-pos' : 'text-warn'">{{ mainSources }}</b></div>
      <div class="src-row"><span>FRED 宏观序列</span><b :class="fredRatio >= 0.8 ? 'text-pos' : 'text-warn'">{{ fredSources }}</b></div>
      <div class="src-row"><span>CFTC COT 持仓</span><b :class="cotStatus === '正常' ? 'text-pos' : 'text-neg'">{{ cotStatus }}</b></div>
      <div class="src-row"><span>数据状态</span><b :class="dataState === '正常' ? 'text-pos' : 'text-neg'">{{ dataState }}</b></div>
      <div class="src-row"><span>数据截至</span><b>{{ dataAsOf }}</b></div>
      <div class="src-row"><span>最后更新</span><b>{{ lastUpdate }}</b></div>
      <div class="src-row"><span>样本数</span><b>{{ totalRows }}</b></div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import HudCard from '@/components/HudCard.vue'
import { dashboardData, extractValue } from '@/composables/useDashboardData'
import { fmtNum, fmtMoney } from '@/utils/format'

const { t } = useI18n()
import { Message } from '@arco-design/web-vue'

const search = ref('')
const filter = ref('all')

const lastUpdate = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')
const totalRows = computed(() => (dashboardData.value.raw_data || []).length)
const dataAsOf = computed(() => extractValue(dashboardData.value.overview, '数据截至') || lastUpdate.value)
const dataState = computed(() => extractValue(dashboardData.value.overview, '数据状态') || '--')
const mainSources = computed(() => extractValue(dashboardData.value.overview, '数据源状态') || '--')
const fredSources = computed(() => extractValue(dashboardData.value.overview, 'FRED状态') || '--')
const cotStatus = computed(() => extractValue(dashboardData.value.overview, 'COT状态') || '--')
const srcRatio = computed(() => {
  const [a, b] = String(mainSources.value).split('/').map(Number)
  return b ? a / b : 1
})
const fredRatio = computed(() => {
  const [a, b] = String(fredSources.value).split('/').map(Number)
  return b ? a / b : 1
})

const filteredRows = computed(() => {
  const all = dashboardData.value.raw_data || []
  let rows = all
  if (filter.value === 'recent') rows = all.slice(0, 30)
  if (filter.value === 'signal') rows = all.filter(r => r['Regime'] && r['Regime'] !== '震荡')
  if (search.value) {
    const q = search.value.toLowerCase()
    rows = rows.filter(r => r['日期'] && r['日期'].toLowerCase().includes(q))
  }
  return rows
})


function downloadCSV() {
  const rows = filteredRows.value
  if (rows.length === 0) {
    Message.warning(t('common.noDataExport'))
    return
  }
  const headers = Object.keys(rows[0])
  const csv = [
    headers.join(','),
    ...rows.map(r => headers.map(h => r[h] ?? '').join(','))
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `gold_data_${lastUpdate.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
  Message.success(t('common.exported', { rows: rows.length }))
}
</script>

<style scoped>
.data-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.data-grid .span-2 { grid-column: span 1; }
.data-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.src-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-soft); font-size: 12px; color: var(--text-2); }
.src-row:last-child { border-bottom: none; }
.src-row b { font-family: var(--mono); }
@media (max-width: 1024px) {
  .data-grid { grid-template-columns: 1fr; }
}
</style>
