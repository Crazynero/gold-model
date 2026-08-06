<template>
  <div class="compare-grid">
    <HudCard title="STRATEGY PERFORMANCE TABLE" meta="ALL 8" class="span-2">
      <a-table
        :data="strategies"
        :pagination="false"
        size="small"
        :bordered="{ cell: true }"
        row-key="策略"
        :scroll="{ x: 800 }"
      >
        <template #columns>
          <a-table-column title="STRATEGY" data-index="策略" :width="180" fixed="left">
            <template #cell="{ record }">
              <a-checkbox :model-value="selected.includes(record['策略'])" @change="toggleSelect(record['策略'])">
                <span :class="record['策略'].includes('V3.0-E') ? 'text-acc mono' : 'mono'">{{ record['策略'] }}</span>
              </a-checkbox>
            </template>
          </a-table-column>
          <a-table-column title="ANNUAL RET" data-index="年化收益" :sortable="{ sortDirections: ['descend','ascend'] }">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record['年化收益']) > 25 ? 'text-pos' : ''">{{ record['年化收益'] }}</span>
            </template>
          </a-table-column>
          <a-table-column title="VOL" data-index="年化波动" :sortable="{ sortDirections: ['descend','ascend'] }"></a-table-column>
          <a-table-column title="SHARPE" data-index="夏普" :sortable="{ sortDirections: ['descend','ascend'] }">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record['夏普']) > 1.5 ? 'text-pos' : parseFloat(record['夏普']) < 1 ? 'text-neg' : ''">{{ record['夏普'] }}</span>
            </template>
          </a-table-column>
          <a-table-column title="MAX DD" data-index="最大回撤" :sortable="{ sortDirections: ['descend','ascend'] }">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record['最大回撤']) < -15 ? 'text-neg' : ''">{{ record['最大回撤'] }}</span>
            </template>
          </a-table-column>
          <a-table-column title="WIN" data-index="胜率"></a-table-column>
          <a-table-column title="CALMAR" data-index="Calmar" :sortable="{ sortDirections: ['descend','ascend'] }"></a-table-column>
          <a-table-column title="CUM RET" data-index="累计收益"></a-table-column>
          <a-table-column title="VS BH" data-index="vs买入持有" :width="100">
            <template #cell="{ record }">
              <span class="mono" :class="parseFloat(record['vs买入持有']) > 0 ? 'text-pos' : 'text-neg'">
                {{ parseFloat(record['vs买入持有']) > 0 ? '+' : '' }}{{ record['vs买入持有'] }}
              </span>
            </template>
          </a-table-column>
        </template>
      </a-table>
      <div class="period-note">
        回测区间：近 5 年（{{ periodStart }} ~ {{ periodEnd }}）· 绝对收益未做风险调整，模型优势应看 SHARPE / MAX DD / CALMAR，而非累计收益
      </div>
    </HudCard>

    <HudCard title="MULTI-STRATEGY COMPARE" meta="SELECTED">
      <div class="control-bar">
        <a-radio-group v-model="metric" type="button" size="small">
          <a-radio value="夏普">SHARPE</a-radio>
          <a-radio value="年化收益">RET</a-radio>
          <a-radio value="最大回撤">MAX DD</a-radio>
          <a-radio value="Calmar">CALMAR</a-radio>
          <a-radio value="胜率">WIN</a-radio>
        </a-radio-group>
      </div>
      <ChartBox :option="barOpt" height="380px" />
      <div v-if="selected.length === 0" class="hint">{{ $t('common.selectStrategies') }}</div>
      <div v-else class="selected-list">
        <a-tag v-for="s in selected" :key="s" color="arcoblue" closable @close="toggleSelect(s)">{{ s }}</a-tag>
      </div>
    </HudCard>

    <HudCard title="RADAR OVERLAY" meta="5-AXIS" class="span-2">
      <div class="control-bar">
        <span class="hint">已选 <b class="text-acc">{{ selected.length }}</b> / 4 策略做雷达叠加</span>
        <a-button size="mini" @click="selected = ['V3.0-E 多周期集成', '买入持有', 'V3.0-D +Kelly']">默认对比</a-button>
        <a-button size="mini" @click="selected = []">清空</a-button>
      </div>
      <ChartBox :option="radarOpt" height="440px" />
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, extractValue } from '@/composables/useDashboardData'

const { t } = useI18n()

const C = {
  bg: '#04060a', accent: '#00d4ff', pos: '#00ff9c', neg: '#ff3860',
  warn: '#ffb800', gold: '#ffb020', text2: '#8b949e', text3: '#6e7681',
  border: 'rgba(0,212,255,0.14)', grid: 'rgba(0,212,255,0.05)',
  purple: '#a855f7', cyan: '#14b8a6'
}
const COLORS = [C.accent, C.gold, C.pos, C.purple]

const strategies = computed(() => dashboardData.value.strategies || [])
const periodEnd = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')
const periodStart = computed(() => {
  const m = /^(\d{4})-(\d{2})/.exec(periodEnd.value)
  if (!m) return '--'
  return `${parseInt(m[1], 10) - 5}-${m[2]}`
})
const selected = ref<string[]>(['V3.0-E 多周期集成', '买入持有', 'V3.0-D +Kelly'])
const metric = ref<'夏普' | '年化收益' | '最大回撤' | 'Calmar' | '胜率'>('夏普')

function toggleSelect(name: string) {
  const idx = selected.value.indexOf(name)
  if (idx >= 0) {
    selected.value.splice(idx, 1)
  } else {
    if (selected.value.length >= 4) {
      selected.value.shift()
    }
    selected.value.push(name)
  }
}

function parseNum(s: string | undefined): number {
  if (!s) return 0
  return parseFloat(s.replace('%', '').replace('+', '')) || 0
}

function barOpt(): EChartsOption {
  const rows = strategies.value.filter(s => selected.value.includes(s['策略'] || ''))
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '12%', right: '5%', bottom: '15%', top: '8%' },
    xAxis: {
      type: 'category',
      data: rows.map(r => r['策略']),
      axisLine: { lineStyle: { color: C.border } },
      axisLabel: { color: C.text3, fontSize: 10, rotate: 25, formatter: (v: string) => v.length > 8 ? v.substring(0, 8) + '…' : v }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: { color: C.text3, fontSize: 10 },
      splitLine: { lineStyle: { color: C.grid } }
    },
    series: [{
      type: 'bar',
      data: rows.map((r, i) => ({
        value: parseNum(r[metric.value]),
        itemStyle: { color: COLORS[i % COLORS.length] }
      })),
      barWidth: '40%',
      label: { show: true, position: 'top', color: C.text2, fontSize: 11 }
    }]
  }
}

function radarOpt(): EChartsOption {
  const rows = strategies.value.filter(s => selected.value.includes(s['策略'] || ''))
  // 雷达 5 维：夏普/收益/胜率/Calmar/(-回撤)
  const indicators = [
    { name: 'SHARPE', max: 3 },
    { name: 'RET%', max: 30 },
    { name: 'WIN%', max: 100 },
    { name: 'CALMAR', max: 4 },
    { name: '-DD%', max: 30 }
  ]
  const data = rows.map((r, i) => {
    const sharpe = parseNum(r['夏普'])
    const ret = parseNum(r['年化收益'])
    const win = parseNum(r['胜率'])
    const cal = parseNum(r['Calmar'])
    const dd = -parseNum(r['最大回撤'])  // 转为正
    return {
      name: r['策略'],
      value: [sharpe, ret, win, cal, dd],
      lineStyle: { color: COLORS[i % COLORS.length], width: 2 },
      areaStyle: { color: COLORS[i % COLORS.length], opacity: 0.12 },
      itemStyle: { color: COLORS[i % COLORS.length] }
    }
  })
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'item' },
    legend: {
      data: rows.map(r => r['策略']),
      textStyle: { color: C.text3, fontSize: 10 },
      top: 0, type: 'scroll'
    },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      center: ['50%', '58%'],
      radius: '65%',
      splitNumber: 4,
      axisName: { color: C.text2, fontSize: 11 },
      splitLine: { lineStyle: { color: C.grid } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: C.border } }
    },
    series: [{ type: 'radar', data }]
  }
}

watch([selected, metric, strategies], () => {}, { deep: true })
</script>

<style scoped>
.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.compare-grid .span-2 { grid-column: span 2; }
.control-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.control-bar .hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-2);
  margin-right: auto;
}
.control-bar .hint b { font-family: var(--mono); }
.selected-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  text-align: center;
  padding: 20px 0;
}
.period-note {
  margin-top: 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.6;
}
@media (max-width: 1024px) {
  .compare-grid { grid-template-columns: 1fr; }
  .compare-grid .span-2 { grid-column: span 1; }
}
</style>
