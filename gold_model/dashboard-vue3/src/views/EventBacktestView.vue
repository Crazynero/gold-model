<template>
  <div class="eb-grid">
    <HudCard :title="$t('card.eventSelector')" :meta="$t('meta.preset')">
      <div class="event-list">
        <div
          v-for="(e, i) in eventTypes"
          :key="e.key"
          :class="['event-item', { active: selected === e.key }]"
          @click="selected = e.key"
        >
          <span class="e-name">{{ e.label }}</span>
          <span class="e-count">{{ eventDates(e.key).length }} 个事件日</span>
        </div>
      </div>
    </HudCard>

    <HudCard :title="$t('card.eventWindows')" meta="RECENT · V5 真实仓位" class="span-2">
      <div class="preset-hint">
        <b>✓ 真实仓位 + 事件窗口：</b>
        事件窗口策略收益优先使用 <b>V5 真实仓位序列</b>（从 position_history 对齐日期）。
        事件日识别来自 raw_data 的"距FOMC天数/距CPI天数"字段（真实）。
        未匹配日期才回退到简化策略。
      </div>
      <a-table :data="eventRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column :title="$t('col.eventDate')" data-index="date" :width="110"></a-table-column>
          <a-table-column :title="$t('col.type')" data-index="type" :width="80"></a-table-column>
          <a-table-column :title="$t('col.gold')" :width="100">
            <template #cell="{ record }">
              <span class="mono text-gold">${{ record.gold.toFixed(2) }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.window')" :width="120">
            <template #cell="{ record }">
              <span class="mono text-muted">{{ record.window }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.windowRet')" :width="100">
            <template #cell="{ record }">
              <span :class="record.windowRet >= 0 ? 'text-pos mono' : 'text-neg mono'">
                {{ (record.windowRet * 100).toFixed(2) }}%
              </span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.strategy')" :width="100">
            <template #cell="{ record }">
              <span :class="record.stratRet >= 0 ? 'text-pos mono' : 'text-neg mono'">
                {{ (record.stratRet * 100).toFixed(2) }}%
              </span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.vsBh')" :width="80">
            <template #cell="{ record }">
              <span :class="record.alpha >= 0 ? 'text-pos mono' : 'text-neg mono'">
                {{ (record.alpha * 100).toFixed(2) }}%
              </span>
            </template>
          </a-table-column>
        </template>
      </a-table>
      <div v-if="eventRows.length === 0" class="hint">{{ $t('common.selectEvent') }}</div>
    </HudCard>

    <HudCard :title="$t('card.eventPerformance')" :meta="$t('meta.aggregate')" class="span-2">
      <ChartBox :option="perfOpt" height="280px" />
    </HudCard>

    <HudCard :title="$t('card.eventWindowDetail')" :meta="$t('meta.timeline')">
      <a-select v-model="selectedDate" placeholder="选择事件日" size="small" :style="{ width: '100%' }">
        <a-option v-for="d in eventDates(selected)" :key="d" :value="d">{{ d }}</a-option>
      </a-select>
      <ChartBox :option="windowOpt" height="260px" />
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, executionData } from '@/composables/useDashboardData'

const { t } = useI18n()

const C = {
  bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62',
  warn: '#eec170', gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

const eventTypes = [
  { key: 'fomc', label: 'FOMC 会议日' },
  { key: 'cpi', label: 'CPI 公布日' },
  { key: 'regime', label: 'Regime 切换日' },
  { key: 'prob_jump', label: '概率突变日' }
]

const selected = ref('fomc')
const selectedDate = ref('')

const raw = computed(() => {
  const r = dashboardData.value.raw_data || []
  return [...r].reverse()  // 升序
})

// 找事件日
function eventDates(type: string): string[] {
  const arr = raw.value
  if (arr.length === 0) return []
  const dates: string[] = []
  if (type === 'fomc') {
    for (const r of arr) {
      const d = parseFloat(String(r['距FOMC天数'] || '999'))
      if (d === 0) dates.push(r['日期']!)
    }
  } else if (type === 'cpi') {
    for (const r of arr) {
      const d = parseFloat(String(r['距CPI天数'] || '999'))
      if (d === 0) dates.push(r['日期']!)
    }
  } else if (type === 'regime') {
    let prev = ''
    for (const r of arr) {
      const cur = r['Regime'] || ''
      if (prev && cur !== prev) dates.push(r['日期']!)
      prev = cur
    }
  } else if (type === 'prob_jump') {
    // 概率突变：当前概率 vs 前一日 差值 > 0.15
    const probs = arr.map(r => parseFloat(String(r['加权概率'] || '0').replace('%', '')) / 100)
    for (let i = 1; i < probs.length; i++) {
      if (Math.abs(probs[i] - probs[i-1]) > 0.15) dates.push(arr[i]['日期']!)
    }
  }
  return dates
}

// 事件窗口（前3后5 = 8天）
function getWindow(date: string, before = 3, after = 5) {
  const arr = raw.value
  const idx = arr.findIndex(r => r['日期'] === date)
  if (idx < 0) return []
  const start = Math.max(0, idx - before)
  const end = Math.min(arr.length, idx + after + 1)
  return arr.slice(start, end)
}

const eventRows = computed(() => {
  const dates = eventDates(selected.value)
  return dates.map(d => {
    const win = getWindow(d, 3, 5)
    if (win.length < 2) return { date: d, type: selected.value, gold: 0, window: '--', windowRet: 0, stratRet: 0, alpha: 0 }
    const prices = win.map(r => parseFloat(String(r['金价'])))
    const goldStart = prices[0]
    const goldEnd = prices[prices.length - 1]
    const windowRet = (goldEnd - goldStart) / goldStart
    // 优先使用 V5 真实仓位序列
    const ph = executionData.value.position_history
    const phMap: Record<string, number> = {}
    if (ph?.dates && ph?.positions) {
      ph.dates.forEach((d: string, i: number) => { phMap[d] = ph.positions[i] })
    }
    let stratRet = 0
    let usingReal = 0
    for (let i = 1; i < win.length; i++) {
      const r = win[i]
      const regime = r['Regime']
      // 优先用 V5 真实仓位
      let pos = phMap[r['日期']!]
      if (pos == null || isNaN(pos)) {
        // fallback 简化策略
        pos = regime === '牛市' ? 1 : regime === '熊市' ? 0 : 0.5
      } else {
        usingReal++
      }
      const dayRet = (prices[i] - prices[i-1]) / prices[i-1]
      stratRet += pos * dayRet
    }
    return {
      date: d,
      type: selected.value.toUpperCase(),
      gold: goldEnd,
      window: `${win[0]['日期']} ~ ${win[win.length-1]['日期']}`,
      windowRet,
      stratRet,
      alpha: stratRet - windowRet
    }
  })
})

function perfOpt(): EChartsOption {
  const rows = eventRows.value
  if (rows.length === 0) return {}
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['窗口收益', '策略收益', 'Alpha'], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '3%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: rows.map(r => r.date), axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: '{value}%' }, splitLine: { lineStyle: { color: C.grid } } },
    series: [
      { name: '窗口收益', type: 'bar', data: rows.map(r => +(r.windowRet * 100).toFixed(2)), itemStyle: { color: C.gold }, barWidth: '25%' },
      { name: '策略收益', type: 'bar', data: rows.map(r => +(r.stratRet * 100).toFixed(2)), itemStyle: { color: C.accent }, barWidth: '25%' },
      { name: 'Alpha', type: 'line', data: rows.map(r => +(r.alpha * 100).toFixed(2)), lineStyle: { color: C.pos, width: 2 }, symbol: 'circle', symbolSize: 6 }
    ]
  }
}

function windowOpt(): EChartsOption {
  if (!selectedDate.value) return {}
  const win = getWindow(selectedDate.value, 3, 5)
  if (win.length === 0) return {}
  const prices = win.map(r => parseFloat(String(r['金价'])))
  const regimes = win.map(r => r['Regime'] || '震荡')
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '15%', top: '5%' },
    xAxis: { type: 'category', data: win.map(r => r['日期']), axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', scale: true, axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'line',
      data: prices,
      smooth: true,
      lineStyle: { width: 2, color: C.gold },
      areaStyle: { color: 'rgba(217, 166, 72,0.1)' },
      markPoint: {
        data: [
          { type: 'max', name: 'Max' },
          { type: 'min', name: 'Min' }
        ],
        itemStyle: { color: C.accent }
      }
    }]
  }
}
</script>

<style scoped>
.eb-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 12px; }
.eb-grid .span-2 { grid-column: span 2; }
.event-list { display: flex; flex-direction: column; gap: 4px; }
.event-item {
  padding: 10px 12px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: all 0.15s;
}
.event-item:hover { background: var(--surface-3); border-color: var(--border-strong); }
.event-item.active {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.event-item.active .e-name { color: var(--accent); }
.e-name { color: var(--text-2); font-size: 12px; }
.e-count { color: var(--text-3); font-family: var(--mono); font-size: 10px; }
.hint { text-align: center; color: var(--text-3); font-family: var(--mono); font-size: 11px; padding: 20px 0; }
@media (max-width: 1024px) {
  .eb-grid { grid-template-columns: 1fr; }
  .eb-grid .span-2 { grid-column: span 1; }
}
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
</style>
