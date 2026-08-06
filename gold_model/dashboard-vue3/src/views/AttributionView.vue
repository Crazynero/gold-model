<template>
  <div class="attr-grid">
    <HudCard title="ATTRIBUTION SUMMARY" meta="BRINSON · 真实仓位" class="span-2">
      <div v-if="metrics" class="attr-summary">
        <div class="attr-row">
          <span class="a-label">策略总收益</span>
          <b class="text-acc mono">{{ (metrics.totalStratRet * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-row">
          <span class="a-label">买入持有收益</span>
          <b class="text-2 mono">{{ (metrics.bhRet * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-row">
          <span class="a-label">超额收益 (Alpha)</span>
          <b :class="metrics.alpha >= 0 ? 'text-pos mono' : 'text-neg mono'">{{ (metrics.alpha * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-divider"></div>
        <div class="attr-row">
          <span class="a-label">配置效应（Regime择时）</span>
          <b :class="metrics.allocation >= 0 ? 'text-pos mono' : 'text-neg mono'">+{{ (metrics.allocation * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-row">
          <span class="a-label">选股效应（实际vs理论）</span>
          <b :class="metrics.selection >= 0 ? 'text-pos mono' : 'text-neg mono'">+{{ (metrics.selection * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-row">
          <span class="a-label">交互效应</span>
          <b :class="metrics.interaction >= 0 ? 'text-pos mono' : 'text-neg mono'">+{{ (metrics.interaction * 100).toFixed(2) }}%</b>
        </div>
        <div class="attr-divider"></div>
        <div class="attr-row">
          <span class="a-label">牛/熊/震荡天数</span>
          <b class="text-2 mono">{{ metrics.bullDays }}/{{ metrics.bearDays }}/{{ metrics.rangeDays }}</b>
        </div>
        <div class="attr-row">
          <span class="a-label">真实仓位覆盖</span>
          <b class="text-pos mono">{{ metrics.usingReal }} / {{ metrics.totalDays }} 天</b>
        </div>
        <div class="attr-row">
          <span class="a-label">持仓时间占比</span>
          <b class="text-2 mono">{{ (metrics.holdingRatio * 100).toFixed(1) }}%</b>
        </div>
      </div>
      <div v-else class="hint">{{ $t('common.clickAnalyze') }}</div>
    </HudCard>

    <HudCard title="ALPHA DECOMPOSITION" meta="BAR CHART" class="span-2">
      <ChartBox v-if="metrics" :option="decompOpt" height="280px" />
      <div v-else class="hint">等待归因结果</div>
    </HudCard>

    <HudCard title="REGIME BREAKDOWN" meta="BY STATE" class="span-2">
      <ChartBox v-if="metrics" :option="regimeOpt" height="280px" />
      <div v-else class="hint">{{ $t('common.waitResult') }}</div>
    </HudCard>

    <HudCard title="CONTROLS" meta="ANALYZE">
      <div class="preset-hint">
        <b>✓ 真实仓位 + Brinson 分解：</b>
        归因分析优先使用 <b>V5 真实仓位序列</b>（从 execution_data.position_history 读，对齐日期）。
        未匹配日期才回退到简化策略（牛市1/熊市0/震荡30%）。
        结果与 V5 真实策略归因一致。
      </div>
      <div class="controls">
        <a-button type="primary" long @click="analyze">ANALYZE</a-button>
        <a-button long @click="reset">RESET</a-button>
      </div>
      <div class="ctrl-info">
        <p>Brinson 三因素分解：</p>
        <p>1. <b>配置效应</b>（Regime择时）</p>
        <p>2. <b>选股效应</b>（实际vs理论仓位）</p>
        <p>3. <b>交互效应</b>（共同影响）</p>
        <p>基准：买入持有（仓位恒定1.0）</p>
      </div>
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
import { Message } from '@arco-design/web-vue'

const metrics = ref<any>(null)

function analyze() {
  const raw = dashboardData.value.raw_data || []
  if (raw.length < 10) {
    Message.error('数据点太少')
    return
  }
  const sorted = [...raw].reverse().filter(r => r['日期'] && r['金价'])
  const prices = sorted.map(r => parseFloat(String(r['金价'])))
  const dates = sorted.map(r => r['日期']!)

  // 日收益率
  const rets: number[] = []
  for (let i = 1; i < prices.length; i++) {
    rets.push((prices[i] - prices[i - 1]) / prices[i - 1])
  }

  // 策略仓位：从 V5 真实仓位序列读，对齐日期
  const ph = executionData.value.position_history
  const phMap: Record<string, number> = {}
  if (ph?.dates && ph?.positions) {
    ph.dates.forEach((d: string, i: number) => {
      phMap[d] = ph.positions[i]
    })
  }
  const positions: number[] = [0]
  let bullDays = 0, bearDays = 0, rangeDays = 0, holdingDays = 0
  let usingReal = 0
  for (let i = 1; i < sorted.length; i++) {
    const r = sorted[i]
    const regime = r['Regime'] || '震荡'
    // 优先用 V5 真实仓位，无则回退简化策略
    let pos = phMap[r['日期']!]
    if (pos == null || isNaN(pos)) {
      // fallback：简化策略（牛市1/熊市0/震荡0.3）
      if (regime === '牛市') pos = 1.0
      else if (regime === '熊市') pos = 0
      else pos = 0.3
    } else {
      usingReal++
    }
    if (regime === '牛市') bullDays++
    else if (regime === '熊市') bearDays++
    else rangeDays++
    if (pos > 0) holdingDays++
    positions.push(pos)
  }

  // 策略收益 = sum(pos * ret)
  let stratRet = 0
  let bhRet = 0
  for (let i = 0; i < rets.length; i++) {
    stratRet += positions[i + 1] * rets[i]
    bhRet += 1.0 * rets[i]
  }
  const alpha = stratRet - bhRet

  // Brinson 分解：
  // 1. 配置效应 = sum((Qp_b - Qb_b) * (Rb_b - Rb))
  //   Qp_b = 策略在 Regime b 的平均仓位, Qb_b = 基准仓位(1.0)
  //   Rb_b = 基准在 Regime b 的收益, Rb = 基准整体收益
  // 2. 选股效应 = sum(Qb_b * (Rp_b - Rb_b))
  //   Rp_b = 策略在 Regime b 的收益
  // 3. 交互 = sum((Qp_b - Qb_b) * (Rp_b - Rb_b))

  const regimes = ['牛市', '熊市', '震荡']
  const regimeData: any = {}
  regimes.forEach(r => {
    regimeData[r] = { stratRet: 0, bhRet: 0, posSum: 0, days: 0 }
  })
  for (let i = 0; i < rets.length; i++) {
    const regime = sorted[i + 1]['Regime'] || '震荡'
    const d = regimeData[regime]
    d.stratRet += positions[i + 1] * rets[i]
    d.bhRet += rets[i]
    d.posSum += positions[i + 1]
    d.days++
  }

  let allocation = 0, selection = 0, interaction = 0
  regimes.forEach(r => {
    const d = regimeData[r]
    const Qp = d.days > 0 ? d.posSum / d.days : 0  // 策略平均仓位
    const Qb = 1.0  // 基准仓位
    const Rp = d.stratRet  // 策略在 Regime r 的收益
    const Rb = d.bhRet  // 基准在 Regime r 的收益
    allocation += (Qp - Qb) * (Rb - bhRet)
    selection += Qb * (Rp - Rb)
    interaction += (Qp - Qb) * (Rp - Rb)
  })

  metrics.value = {
    totalStratRet: stratRet,
    bhRet,
    alpha,
    allocation,
    selection,
    interaction,
    bullDays, bearDays, rangeDays,
    usingReal,
    totalDays: sorted.length - 1,
    holdingRatio: sorted.length > 0 ? holdingDays / sorted.length : 0,
    regimeData
  }
  Message.success(`t('common.attributionDone', { alpha: (alpha*100).toFixed(2), usingReal, total: sorted.length - 1 })`)
}

function reset() {
  metrics.value = null
  Message.info('已重置')
}

function decompOpt(): EChartsOption {
  if (!metrics.value) return {}
  const m = metrics.value
  return {
    backgroundColor: '#04060a', animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: '15%', right: '5%', bottom: '10%', top: '10%' },
    xAxis: { type: 'category', data: ['配置效应', '选股效应', '交互效应', '总 Alpha'], axisLine: { lineStyle: { color: 'rgba(0,212,255,0.14)' } }, axisLabel: { color: '#6e7681', fontSize: 10 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: '#6e7681', formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(0,212,255,0.05)' } } },
    series: [{
      type: 'bar',
      data: [
        { value: +(m.allocation * 100).toFixed(2), itemStyle: { color: m.allocation >= 0 ? '#00ff9c' : '#ff3860' } },
        { value: +(m.selection * 100).toFixed(2), itemStyle: { color: m.selection >= 0 ? '#00ff9c' : '#ff3860' } },
        { value: +(m.interaction * 100).toFixed(2), itemStyle: { color: m.interaction >= 0 ? '#00ff9c' : '#ff3860' } },
        { value: +(m.alpha * 100).toFixed(2), itemStyle: { color: '#00d4ff' } }
      ],
      barWidth: '40%',
      label: { show: true, position: 'top', color: '#8b949e', fontSize: 10, formatter: '{c}%' }
    }]
  }
}

function regimeOpt(): EChartsOption {
  if (!metrics.value) return {}
  const rd = metrics.value.regimeData
  return {
    backgroundColor: '#04060a', animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['策略', '买入持有'], textStyle: { color: '#6e7681', fontSize: 10 }, top: 0 },
    grid: { left: '10%', right: '5%', bottom: '10%', top: '15%' },
    xAxis: { type: 'category', data: ['牛市', '熊市', '震荡'], axisLine: { lineStyle: { color: 'rgba(0,212,255,0.14)' } }, axisLabel: { color: '#6e7681', fontSize: 11 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: '#6e7681', formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(0,212,255,0.05)' } } },
    series: [
      { name: '策略', type: 'bar', data: ['牛市', '熊市', '震荡'].map(r => +(rd[r].stratRet * 100).toFixed(2)), itemStyle: { color: '#00d4ff' }, barWidth: '30%' },
      { name: '买入持有', type: 'bar', data: ['牛市', '熊市', '震荡'].map(r => +(rd[r].bhRet * 100).toFixed(2)), itemStyle: { color: '#8b949e' }, barWidth: '30%' }
    ]
  }
}
</script>

<style scoped>
.attr-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.attr-grid .span-2 { grid-column: span 2; }
.attr-summary { padding: 8px 0; }
.attr-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 12px;
  color: var(--text-2);
}
.attr-row b { font-weight: 500; }
.a-label { color: var(--text-2); }
.attr-divider { height: 1px; background: var(--border-soft); margin: 8px 0; }
.controls { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.ctrl-info { font-size: 11px; color: var(--text-3); line-height: 1.7; padding: 8px 0; border-top: 1px solid var(--border); }
.ctrl-info p { margin: 4px 0; }
.ctrl-info b { color: var(--accent); }
.preset-hint {
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.7;
  padding: 8px 10px;
  border-left: 2px solid var(--pos);
  background: rgba(0, 255, 156, 0.05);
  margin-bottom: 10px;
  font-family: var(--mono);
}
.preset-hint b { color: var(--pos); }
.hint { text-align: center; color: var(--text-3); font-family: var(--mono); font-size: 11px; padding: 30px 0; }
@media (max-width: 1024px) {
  .attr-grid { grid-template-columns: 1fr; }
  .attr-grid .span-2 { grid-column: span 1; }
}
</style>
