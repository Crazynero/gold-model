<template>
  <div class="exec-grid">
    <HudCard :title="$t('card.executionPlan')" :meta="$t('meta.current')" class="span-2">
      <div class="exec-summary">
        <div class="exec-cell sens">
          <div class="mini-label">建议操作</div>
          <div class="exec-value text-acc">{{ action }}</div>
        </div>
        <div class="exec-cell sens">
          <div class="mini-label">目标仓位</div>
          <div class="exec-value text-gold">{{ targetPos }}</div>
        </div>
        <div class="exec-cell sens">
          <div class="mini-label">ETF层 (65%)</div>
          <div class="exec-value">{{ etfLayer }}</div>
        </div>
        <div class="exec-cell sens">
          <div class="mini-label">期货层 (35%)</div>
          <div class="exec-value">{{ futLayer }}</div>
        </div>
        <div class="exec-cell">
          <div class="mini-label">杠杆</div>
          <div class="exec-value">1x</div>
        </div>
      </div>
    </HudCard>

    <HudCard :title="$t('card.executionInstructions')" meta="STEP BY STEP · 操作模板" class="span-2">
      <div class="preset-hint">
        <b>⚠ 操作模板：</b>
        以下指令根据当前信号（空仓/建仓）<b>预设</b>，非动态生成。
        具体执行需结合券商接口/持仓状态/流动性判断。
      </div>
      <a-table :data="execRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column :title="$t('col.step')" :width="60">
            <template #cell="{ rowIndex }">{{ rowIndex + 1 }}</template>
          </a-table-column>
          <a-table-column :title="$t('col.action')" data-index="action"></a-table-column>
          <a-table-column :title="$t('col.target')" data-index="target"></a-table-column>
          <a-table-column :title="$t('col.amount')" data-index="amount">
            <template #cell="{ record }">
              <span class="mono text-gold">{{ record.amount }}</span>
            </template>
          </a-table-column>
          <a-table-column :title="$t('col.note')" data-index="note"></a-table-column>
        </template>
      </a-table>
    </HudCard>

    <HudCard :title="$t('card.signalQuality')" :meta="$t('meta.hitRateCost')">
      <div class="sq-row"><span>20日命中率</span><b :class="hitOk ? 'text-pos' : 'text-neg'">{{ hitRate }}</b></div>
      <div class="sq-row"><span>WF基准</span><b class="text-muted">{{ baseRate }}</b></div>
      <div class="sq-row"><span>偏差</span><b :class="hitOk ? 'text-pos' : 'text-neg'">{{ deviation }}</b></div>
      <div class="sq-row"><span>仓位系数</span><b class="text-acc">{{ posFactor }}</b></div>
      <div class="sq-row"><span>状态</span><b :class="hitOk ? 'text-pos' : 'text-neg'">{{ hitOk ? '正常' : '熔断中' }}</b></div>
    </HudCard>

    <HudCard :title="$t('card.costComparison')" :meta="$t('meta.scenarios3')">
      <div class="capital-select">
        <span class="cs-label">资金规模</span>
        <a-radio-group v-model="selectedCapital" type="button" size="small">
          <a-radio v-for="opt in capitalOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</a-radio>
        </a-radio-group>
      </div>
      <ChartBox :option="costOpt" height="320px" />
    </HudCard>

    <HudCard :title="$t('card.positionHistory')" :meta="$t('meta.d250')" class="span-2">
      <ChartBox :option="posOpt" height="440px" />
    </HudCard>

    <HudCard :title="$t('card.weeklyReport')" meta="PDF" class="span-2">
      <div class="report-area">
        <div class="report-info">
          <div>
            <div class="r-label">报告周期</div>
            <div class="r-value">每日生成（cron 工作日 8:00 触发）</div>
          </div>
          <div>
            <div class="r-label">报告内容</div>
            <div class="r-value">信号摘要 / 策略对比 / 特征TOP10 / Holdout / 告警汇总</div>
          </div>
          <div>
            <div class="r-label">输出路径</div>
            <div class="r-value">weekly_reports/gold_weekly_YYYYMMDD.pdf</div>
          </div>
        </div>
        <div class="report-actions">
          <a-button type="primary" long :loading="generating" @click="generateReport">
            {{ generating ? '生成中...' : '生成 PDF 周报' }}
          </a-button>
          <a-button long :disabled="!reportPath" @click="downloadReport">
            下载最近一份
          </a-button>
        </div>
        <div v-if="lastResult" class="report-result" :class="lastResult.ok ? 'ok' : 'err'">
          <span class="r-status">{{ lastResult.ok ? 'OK' : 'FAIL' }}</span>
          <span>{{ lastResult.msg }}</span>
        </div>
      </div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EChartsOption } from 'echarts'
import HudCard from '@/components/HudCard.vue'
import ChartBox from '@/components/ChartBox.vue'
import { dashboardData, executionData, extractValue, apiBase } from '@/composables/useDashboardData'
import { Message } from '@arco-design/web-vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// M: PDF 周报
const generating = ref(false)
const reportPath = ref<string>('')
const lastResult = ref<{ ok: boolean; msg: string } | null>(null)

async function generateReport() {
  generating.value = true
  lastResult.value = null
  try {
    // 优先调用 FastAPI 后端
    if (apiBase.value) {
      const resp = await fetch(`${apiBase.value}/api/report/weekly`)
      const d = await resp.json()
      if (resp.ok) {
        reportPath.value = d.pdf_path
        lastResult.value = { ok: true, msg: `生成成功: ${d.pdf_path}` }
        Message.success('PDF 周报已生成')
      } else {
        throw new Error(d.detail || '生成失败')
      }
    } else {
      // 沙箱回退：直接打开已生成的 PDF（如果有）
      lastResult.value = { ok: false, msg: '后端未连接（file://协议）— 请启动 api_server.py 后使用' }
      Message.warning('需启动 FastAPI 后端才能生成 PDF')
    }
  } catch (e: any) {
    lastResult.value = { ok: false, msg: e?.message || '生成失败' }
    Message.error('生成失败：' + (e?.message || 'unknown'))
  } finally {
    generating.value = false
  }
}

function downloadReport() {
  if (reportPath.value) {
    // 下载路径文件
    window.open(reportPath.value, '_blank')
  }
}

// 资金规模选择（10万/50万/100万/500万）
const selectedCapital = ref('100000')
const capitalOptions = [
  { label: '10万', value: '100000' },
  { label: '50万', value: '500000' },
  { label: '100万', value: '1000000' },
  { label: '500万', value: '5000000' }
]

const C = {
  bg: '#0e0f11', accent: '#d9a648', pos: '#45b789', neg: '#cf6b62',
  warn: '#eec170', gold: '#d9a648', text2: '#a09d94', text3: '#66635c',
  border: 'rgba(217, 166, 72,0.14)', grid: 'rgba(217, 166, 72,0.05)'
}

const action = computed(() => extractValue(dashboardData.value.overview, '建议操作') || '空仓观望')
const targetPos = computed(() => {
  const exec = executionData.value.current
  if (exec?.position !== undefined) {
    const p = typeof exec.position === 'number' ? exec.position : parseFloat(String(exec.position))
    return (p * 100).toFixed(1) + '%'
  }
  return '0%'
})
const etfLayer = computed(() => {
  const exec = executionData.value.current
  if (exec?.position !== undefined) {
    const p = typeof exec.position === 'number' ? exec.position : parseFloat(String(exec.position))
    return (p * 65).toFixed(1) + '%'
  }
  return '0%'
})
const futLayer = computed(() => {
  const exec = executionData.value.current
  if (exec?.position !== undefined) {
    const p = typeof exec.position === 'number' ? exec.position : parseFloat(String(exec.position))
    return (p * 35).toFixed(1) + '%'
  }
  return '0%'
})

const execRows = computed(() => {
  if (action.value.includes('空仓')) {
    return [
      { action: '清仓 ETF', target: 'GLD / IAU', amount: '100%', note: '市价卖出' },
      { action: '平仓期货', target: 'GC=F 多头', amount: '100%', note: '市价平' },
      { action: '保留看跌期权', target: '持仓保护', amount: '原仓位', note: '若存在' },
      { action: '等待信号', target: 'P(W)>0.6', amount: '-', note: '回归条件' }
    ]
  }
  return [
    { action: '建仓 ETF', target: 'GLD / IAU', amount: '65% 仓位', note: '分3日建仓' },
    { action: '建仓期货', target: 'GC=F 多头', amount: '35% 仓位', note: '分2日建仓' },
    { action: '设置止损', target: '-3% / MA50', amount: '-', note: '触发即平' },
    { action: '设置止盈', target: '+5% / Regime转熊', amount: '-', note: '动态调整' }
  ]
})

const hitRate = computed(() => executionData.value.signal_stats?.hit_rate_20d || '35%')
const baseRate = computed(() => executionData.value.signal_stats?.wf_base || '58%')
const deviation = computed(() => executionData.value.signal_stats?.deviation || '-23%')
const hitOk = computed(() => {
  const h = parseFloat(hitRate.value)
  const b = parseFloat(baseRate.value)
  return h - b > -10
})
const posFactor = computed(() => {
  const h = parseFloat(hitRate.value)
  const b = parseFloat(baseRate.value)
  const dev = h - b
  if (dev < -25) return '×0.2'
  if (dev < -15) return '×0.5'
  if (dev < -5) return '×0.8'
  return '×1.0'
})

function costOpt(): EChartsOption {
  const costsRaw = executionData.value.cost_comparison
  if (!costsRaw || typeof costsRaw !== 'object') return {}
  // 默认用 100000 资金规模的数据
  const sizeKey = selectedCapital.value
  const sizeData = costsRaw[sizeKey] || costsRaw[Object.keys(costsRaw)[0]]
  if (!sizeData) return {}
  // 3 个场景：纯ETF / 纯期货 / ETF+期货分层
  const labels = ['纯ETF', '纯期货', 'ETF+期货分层']
  const data1 = labels.map(n => {
    const s = sizeData[n]
    if (!s) return 0
    // 分层场景取总成本，单场景取总成本
    return typeof s['总成本'] === 'number' ? s['总成本'] : 0
  })
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const p = params[0]
        const sizeData = costsRaw[sizeKey]
        const s = sizeData ? sizeData[labels[p.dataIndex]] : null
        if (!s) return ''
        let html = `<b>${labels[p.dataIndex]}</b><br/>总成本: $${p.value.toFixed(2)}<br/>`
        if (s['总佣金'] !== undefined) html += `佣金: $${s['总佣金'].toFixed(2)}<br/>`
        if (s['总管理费'] !== undefined) html += `管理费: $${s['总管理费'].toFixed(2)}<br/>`
        if (s['保证金机会成本'] !== undefined) html += `保证金成本: $${s['保证金机会成本'].toFixed(2)}<br/>`
        if (s['日均成本'] !== undefined) html += `日均: $${s['日均成本'].toFixed(4)}`
        return html
      }
    },
    grid: { left: '15%', right: '5%', bottom: '8%', top: '5%' },
    xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: C.text3, formatter: '${value}' }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: 'bar',
      data: data1.map((v, i) => ({
        value: v,
        itemStyle: { color: i === 2 ? C.accent : C.text2 }  // 分层方案高亮
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', color: C.text2, fontSize: 10, formatter: '${c}' }
    }]
  }
}

function posOpt(): EChartsOption {
  const ph = executionData.value.position_history
  if (!ph || !ph.dates || ph.dates.length === 0) return {}
  const positions = ph.positions.map((p: number) => p * 100)
  const etf = positions.map((p: number) => p * 0.65)
  const fut = positions.map((p: number) => p * 0.35)
  return {
    backgroundColor: C.bg, animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: [t('chart.modelPos'), t('chart.etfLayer'), t('chart.futLayer'), t('chart.goldPrice')], textStyle: { color: C.text3, fontSize: 10 }, top: 0 },
    grid: { left: '5%', right: '5%', bottom: '8%', top: '12%' },
    xAxis: { type: 'category', data: ph.dates, axisLine: { lineStyle: { color: C.border } }, axisLabel: { color: C.text3, fontSize: 10 } },
    yAxis: [
      { type: 'value', name: '仓位%', min: -100, max: 100, axisLine: { show: false }, axisLabel: { color: C.text3, formatter: '{value}%' }, splitLine: { lineStyle: { color: C.grid } } },
      { type: 'value', name: '金价$', position: 'right', scale: true, axisLine: { show: false }, axisLabel: { color: C.text3 }, splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider' }],
    series: [
      { name: t('chart.modelPos'), type: 'line', data: positions, symbol: 'none', smooth: true, lineStyle: { width: 2, color: C.gold }, yAxisIndex: 0 },
      { name: t('chart.etfLayer'), type: 'line', data: etf, symbol: 'none', smooth: true, lineStyle: { width: 1, color: C.accent, opacity: 0.7 }, areaStyle: { color: 'rgba(217, 166, 72,0.08)' }, yAxisIndex: 0 },
      { name: t('chart.futLayer'), type: 'line', data: fut, symbol: 'none', smooth: true, lineStyle: { width: 1, color: C.text2, opacity: 0.7 }, yAxisIndex: 0 },
      { name: t('chart.goldPrice'), type: 'line', data: ph.gold_prices, symbol: 'none', lineStyle: { width: 1, color: C.pos, opacity: 0.5 }, yAxisIndex: 1 }
    ]
  }
}
</script>

<style scoped>
.exec-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.exec-grid .span-2 { grid-column: span 2; }
.exec-summary { display: flex; justify-content: space-around; padding: 20px 0; gap: 12px; }
.exec-cell { text-align: center; }
.exec-value { font-family: var(--mono); font-size: 22px; margin-top: 4px; font-weight: 500; }
.sq-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-soft); font-size: 12px; color: var(--text-2); }
.sq-row:last-child { border-bottom: none; }
.sq-row b { font-family: var(--mono); }
.capital-select {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-family: var(--mono);
  font-size: 11px;
}
.cs-label { color: var(--text-3); letter-spacing: 0.08em; }

.report-area {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  padding: 8px 0;
}
.report-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.r-label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.r-value {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-2);
}
.report-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-self: center;
}
.report-result {
  grid-column: 1 / -1;
  padding: 8px 12px;
  border-left: 2px solid;
  font-family: var(--mono);
  font-size: 11px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.report-result.ok {
  background: rgba(69, 183, 137, 0.06);
  border-color: var(--pos);
  color: var(--pos);
}
.report-result.err {
  background: rgba(207, 107, 98, 0.06);
  border-color: var(--neg);
  color: var(--neg);
}
.r-status { font-weight: 600; }
.report-result.ok .r-status { color: var(--pos); }
.report-result.err .r-status { color: var(--neg); }
.report-result span:last-child { color: var(--text-2); }
.preset-hint {
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.7;
  padding: 8px 10px;
  border-left: 2px solid var(--warn);
  background: rgba(238, 193, 112, 0.05);
  margin-bottom: 10px;
  font-family: var(--mono);
}
.preset-hint b { color: var(--warn); }

@media (max-width: 1024px) {
  .exec-grid { grid-template-columns: 1fr; }
  .exec-grid .span-2 { grid-column: span 1; }
}
</style>
