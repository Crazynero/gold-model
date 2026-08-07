<template>
  <div class="sys-grid">
    <!-- 连接与数据状态 -->
    <HudCard title="数据连接" :meta="$t('meta.loadState')">
      <div class="ov-row"><span>数据来源</span><b class="text-acc">{{ srcLabel }}</b></div>
      <div class="ov-row"><span>最近更新</span><b>{{ lastUpdateStr }}</b></div>
      <div class="ov-row"><span>WS 实时通道</span><b :class="wsConnected ? 'text-pos' : 'text-muted'">{{ wsConnected ? '已连接' : '未连接' }}</b></div>
      <div class="ov-row"><span>预测基准日</span><b>{{ baseDate }}</b></div>
    </HudCard>

    <!-- 模型健康 -->
    <HudCard title="模型健康" :meta="$t('meta.v30eHoldout')">
      <div class="ov-row"><span>{{ $t('txt.fullSharpe') }}<i class="tag-bt">回测</i></span><b class="text-pos">{{ full }}</b></div>
      <div class="ov-row"><span>{{ $t('txt.oosSharpe') }}<i class="tag-oos">样本外</i></span><b class="text-neg">{{ oos }}</b></div>
      <div class="ov-row"><span>衰减</span><b class="text-neg">{{ decay }}</b></div>
      <div class="ov-row"><span>20日方向准确率</span><b>{{ dirAcc }}</b></div>
      <div class="ov-row"><span>特征数</span><b>{{ feat }}</b></div>
    </HudCard>

    <!-- 漂移监控 -->
    <HudCard title="漂移监控" :meta="$t('meta.driftHistory')" class="span-2">
      <div v-if="driftRows.length === 0" class="empty-note">
        无漂移记录。漂移历史由后端 <span class="mono">/api/drift</span> 提供，静态部署下不可用。
      </div>
      <a-table v-else :data="driftRows" :pagination="{ pageSize: 8 }" size="small">
        <template #columns>
          <a-table-column title="日期" data-index="date"></a-table-column>
          <a-table-column title="指标" data-index="metric"></a-table-column>
          <a-table-column title="数值" data-index="value"></a-table-column>
          <a-table-column title="状态" data-index="status"></a-table-column>
        </template>
      </a-table>
    </HudCard>

    <!-- 数据源架构 -->
    <HudCard title="数据源架构" :meta="$t('meta.fallbackChain')">
      <div class="src-line" v-for="s in sources" :key="s.name">
        <b>{{ s.name }}</b>
        <span class="chain-text">{{ s.chain }}</span>
      </div>
    </HudCard>

    <!-- 自动化 -->
    <HudCard title="自动化" meta="LAUNCHD">
      <div class="ov-row"><span>每日信号检查</span><b class="text-acc">22:30</b></div>
      <div class="ov-row"><span>任务脚本</span><b class="mono" style="font-size:11px">daily_signal_check.sh</b></div>
      <div class="ov-row"><span>执行内容</span><b>V5 管道 → JSON → 告警</b></div>
    </HudCard>

    <!-- 已知问题 -->
    <HudCard title="已知问题" :meta="$t('meta.knownIssues')" class="span-2">
      <ul class="issue-list">
        <li><b>回归分支不可用</b> — 金价回归模型 R² = −0.36，预测结果劣于均值基线，仓位决策已切换至分类分支。</li>
        <li><b>多头偏见治理观察期</b> — 至 8 月中旬，期间做多信号需 Regime 二次确认。</li>
        <li><b>东财接口限流</b> — 金价主源频繁 429，已启用新浪/腾讯自动降级；Yahoo 在中国大陆不可达。</li>
      </ul>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import HudCard from '@/components/HudCard.vue'
import {
  dashboardData, extractValue, fetchDrift,
  lastUpdate, updateSource, wsConnected
} from '@/composables/useDashboardData'

const baseDate = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')

const srcLabel = computed(() => {
  if (wsConnected.value) return 'WS 实时'
  if (updateSource.value === 'api') return 'API'
  if (updateSource.value === 'fetch') return '本地 JSON 轮询'
  if (updateSource.value === 'window') return '内联数据'
  return '未加载'
})

const lastUpdateStr = computed(() => {
  if (!lastUpdate.value) return '--'
  const d = lastUpdate.value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

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
const feat = computed(() => dashboardData.value.v5_feature_count || '--')
const dirAcc = computed(() => {
  const r = dashboardData.value.v5_regression?.find(r => r.horizon === '20日')
  return r?.dir_acc || '--'
})

// 漂移记录（仅 API 模式可用）
const driftRows = ref<any[]>([])
onMounted(async () => {
  const d = await fetchDrift()
  if (Array.isArray(d)) driftRows.value = d
  else if (d && Array.isArray(d.history)) driftRows.value = d.history
})

const sources = [
  { name: '金价', chain: '东方财富 → 新浪 → 腾讯 → Yahoo（主源限流时自动降级）' },
  { name: '利率/宏观', chain: 'FRED（10Y 实际利率、通胀预期、美元指数）' },
  { name: '波动率', chain: 'CBOE VIX' },
  { name: '事件日历', chain: 'FOMC / CPI 本地缓存（fomc_cache.json / cpi_cache.json）' }
]
</script>

<style scoped>
.sys-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.span-2 { grid-column: span 2; }
.ov-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13px;
}
.ov-row:last-child { border-bottom: none; }
.ov-row span { color: var(--text-3); }
.ov-row b { font-weight: 600; }
.tag-bt, .tag-oos {
  font-style: normal;
  font-size: 10px;
  padding: 0 6px;
  border-radius: 3px;
  margin-left: 6px;
  letter-spacing: 0.06em;
  vertical-align: 1px;
}
.tag-bt { color: var(--text-3); border: 1px solid var(--border); }
.tag-oos { color: var(--gold); border: 1px solid rgba(217, 166, 72, 0.4); background: var(--gold-dim); }
.empty-note {
  color: var(--text-3);
  font-size: 12px;
  padding: 12px 0;
  line-height: 1.7;
}
.src-line {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13px;
}
.src-line:last-child { border-bottom: none; }
.src-line b { display: block; margin-bottom: 2px; }
.chain-text { color: var(--text-3); font-size: 12px; }
.issue-list {
  list-style: none;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.8;
}
.issue-list b { color: var(--text); }
.issue-list li { padding: 6px 0; border-bottom: 1px solid var(--border-soft); }
.issue-list li:last-child { border-bottom: none; }
@media (max-width: 860px) {
  .sys-grid { grid-template-columns: 1fr; }
  .span-2 { grid-column: span 1; }
}
</style>
