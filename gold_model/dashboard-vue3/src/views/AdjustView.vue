<template>
  <div class="adjust-grid">
    <HudCard title="MARKET VIEW ADJUSTMENT" meta="MANUAL OVERRIDE">
      <div class="adjust-section">
        <div class="adj-label">市场观点 <InfoIcon title="市场观点">取值范围 -5（极度看空）到 +5（极度看多），0 为中性。Regime 自动判定：>2 牛市，<-2 熊市，其他震荡。</InfoIcon></div>
        <a-slider v-model="viewValue" :min="-5" :max="5" :step="1" show-input :marks="{ [-5]: '熊', [-2]: '熊市', 0: '震荡', 2: '牛市', 5: '牛' }" />
        <div class="adj-result">
          当前 Regime: <b :class="`text-${regimeClass}`">{{ regimeFromView }}</b>
        </div>
      </div>

      <div class="adjust-section">
        <div class="adj-label">仓位调整 <InfoIcon title="仓位调整">手动覆盖模型建议仓位。-100% 到 +100%。负值为做空。</InfoIcon></div>
        <a-slider v-model="posValue" :min="-100" :max="100" :step="5" show-input />
        <div class="adj-result">
          目标仓位: <b class="text-acc">{{ posValue }}%</b>
          <span class="text-muted">ETF层: {{ (posValue * 0.65).toFixed(1) }}% / 期货层: {{ (posValue * 0.35).toFixed(1) }}%</span>
        </div>
      </div>

      <div class="adjust-section">
        <div class="adj-label">杠杆倍数 <InfoIcon title="杠杆倍数">1x = 无杠杆。3x = 三倍杠杆（高风险）。建议不超过 2x。</InfoIcon></div>
        <a-input-number v-model="leverage" :min="1" :max="5" :step="0.5" />
      </div>

      <div class="adjust-actions">
        <a-button type="primary" @click="handleApply">{{ $t('common.apply') }}</a-button>
        <a-button @click="handleReset">{{ $t('common.reset') }}</a-button>
        <span v-if="lastSavedAt" class="saved-tag">
          <span class="saved-dot"></span>{{ $t('common.savedAt', { time: savedTimeStr }) }}
        </span>
      </div>
    </HudCard>

    <HudCard title="EVENT OVERLAY" meta="BLACK SWAN · 估算影响">
      <div class="preset-hint">
        <b>⚠ 预设影响估算：</b>
        以下事件的影响幅度（如"金价 +3%"）为<b>手动估算</b>，非历史回测数据。
        实际影响会因市场环境/持仓结构/时间窗口而异。
      </div>
      <div class="event-list">
        <div v-for="ev in eventTemplates" :key="ev.id" class="event-item">
          <div class="event-header">
            <a-tag :color="ev.severity === 'high' ? 'red' : ev.severity === 'medium' ? 'orange' : 'gray'">{{ ev.severity.toUpperCase() }}</a-tag>
            <span class="event-name">{{ ev.name }}</span>
          </div>
          <p class="event-desc">{{ ev.desc }}</p>
          <div class="event-impact">建议影响: <b>{{ ev.impact }}</b></div>
        </div>
      </div>
    </HudCard>

    <HudCard title="MANUAL OVERRIDE PREVIEW" class="span-2">
      <a-table :data="previewRows" :pagination="false" size="small" :bordered="{ cell: true }">
        <template #columns>
          <a-table-column title="维度" data-index="dim"></a-table-column>
          <a-table-column title="MODEL" data-index="model"></a-table-column>
          <a-table-column title="MANUAL" data-index="manual"></a-table-column>
          <a-table-column title="DELTA" data-index="delta">
            <template #cell="{ record }">
              <span :class="parseFloat(record.delta) >= 0 ? 'text-pos mono' : 'text-neg mono'">{{ record.delta }}</span>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import HudCard from '@/components/HudCard.vue'
import InfoIcon from '@/components/InfoIcon.vue'
import { dashboardData, extractValue } from '@/composables/useDashboardData'

const { t } = useI18n()
import { Message } from '@arco-design/web-vue'

// === localStorage 持久化 ===
const STORAGE_KEY = 'gold-command-adjust-v1'

interface PersistedAdjust {
  viewValue: number
  posValue: number
  leverage: number
  savedAt: number
}

function loadPersisted(): Partial<PersistedAdjust> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

function savePersisted(data: Partial<PersistedAdjust>) {
  try {
    const cur = loadPersisted()
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...cur,
      ...data,
      savedAt: Date.now()
    }))
  } catch {
    // 隐私模式或storage不可用，忽略
  }
}

const persisted = loadPersisted()
const viewValue = ref(persisted.viewValue ?? 0)
const posValue = ref(persisted.posValue ?? 0)
const leverage = ref(persisted.leverage ?? 1)

// 响应式 savedAt — 用于驱动 saved-tag 显示
const savedAtRef = ref<number | null>(persisted.savedAt ?? null)

// 监听变化自动保存（防抖1秒）
let saveTimer: any
watch([viewValue, posValue, leverage], () => {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    savePersisted({
      viewValue: viewValue.value,
      posValue: posValue.value,
      leverage: leverage.value
    })
    // 同步刷新 savedAtRef（重新读 localStorage 拿到 savedAt）
    const p = loadPersisted()
    savedAtRef.value = p.savedAt ?? null
  }, 1000)
})

const lastSavedAt = computed(() => savedAtRef.value ? new Date(savedAtRef.value) : null)

const savedTimeStr = computed(() => {
  if (!lastSavedAt.value) return ''
  const d = lastSavedAt.value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

const regimeFromView = computed(() => {
  if (viewValue.value > 2) return '牛市'
  if (viewValue.value < -2) return '熊市'
  return '震荡'
})

const regimeClass = computed(() => {
  if (viewValue.value > 2) return 'pos'
  if (viewValue.value < -2) return 'neg'
  return 'warn'
})

const eventTemplates = [
  { id: 1, name: '美联储紧急降息', severity: 'high', desc: '联储在议息会议外降息 ≥50bp，通常为危机响应。', impact: '金价 +3% / 美元 -2%' },
  { id: 2, name: '地缘冲突升级', severity: 'high', desc: '中东/东欧热战扩散，避险溢价快速上升。', impact: '金价 +5% / VIX +30%' },
  { id: 3, name: '美国CPI超预期', severity: 'medium', desc: 'CPI同比高于预期 0.5pt+，降息预期后撤。', impact: '金价 -2% / 实际利率 +20bp' },
  { id: 4, name: '非农大幅低于预期', severity: 'medium', desc: '就业弱化，衰退预期升温。', impact: '金价 +1.5% / 美元 -1%' },
  { id: 5, name: '央行购金超预期', severity: 'low', desc: '中国/印度/土耳其央行月度购金 >100 吨。', impact: '金价 +1% (结构性)' }
]

const previewRows = computed(() => {
  const modelProb = extractValue(dashboardData.value.overview, '加权集成概率') || '0%'
  const modelPos = extractValue(dashboardData.value.overview, '建议操作') || '空仓'
  const modelRegime = extractValue(dashboardData.value.overview, '当前Regime') || '震荡'
  return [
    { dim: '市场观点', model: '0 (auto)', manual: viewValue.value.toString(), delta: viewValue.value.toString() },
    { dim: 'Regime', model: modelRegime, manual: regimeFromView.value, delta: regimeFromView.value === modelRegime ? '0' : '变更' },
    { dim: '仓位', model: modelPos, manual: posValue.value + '%', delta: (posValue.value - 0).toString() },
    { dim: '杠杆', model: '1x', manual: leverage.value + 'x', delta: (leverage.value - 1).toString() },
    { dim: '概率', model: modelProb, manual: modelProb + ' (沿用)', delta: '0' }
  ]
})

function handleApply() {
  savePersisted({
    viewValue: viewValue.value,
    posValue: posValue.value,
    leverage: leverage.value
  })
  const p = loadPersisted()
  savedAtRef.value = p.savedAt ?? null
  Message.success(`调整已应用：观点 ${viewValue.value} / 仓位 ${posValue.value}% / 杠杆 ${leverage.value}x`)
}
function handleReset() {
  viewValue.value = 0
  posValue.value = 0
  leverage.value = 1
  savePersisted({ viewValue: 0, posValue: 0, leverage: 1 })
  const p = loadPersisted()
  savedAtRef.value = p.savedAt ?? null
  Message.info('已重置为默认值')
}
</script>

<style scoped>
.adjust-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.adjust-grid .span-2 { grid-column: span 2; }
.adjust-section { padding: 12px 0; border-bottom: 1px solid var(--border-soft); }
.adjust-section:last-of-type { border-bottom: none; }
.adj-label { font-size: 12px; color: var(--text-2); margin-bottom: 12px; display: flex; align-items: center; }
.adj-result { margin-top: 10px; font-size: 13px; color: var(--text-2); }
.adj-result b { font-family: var(--mono); }
.adj-result .text-muted { margin-left: 12px; font-size: 11px; color: var(--text-3); }
.adjust-actions { display: flex; gap: 8px; margin-top: 16px; align-items: center; }
.saved-tag {
  margin-left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.06em;
}
.saved-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--pos);
  box-shadow: 0 0 4px var(--pos);
}

.event-list { padding: 4px 0; }
.event-item { padding: 12px 0; border-bottom: 1px solid var(--border-soft); }
.event-item:last-child { border-bottom: none; }
.event-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.event-name { color: var(--text); font-weight: 500; font-size: 13px; }
.event-desc { font-size: 12px; color: var(--text-2); margin: 4px 0; line-height: 1.6; }
.event-impact { font-size: 11px; color: var(--text-3); font-family: var(--mono); }
.event-impact b { color: var(--accent); }
.preset-hint {
  font-size: 10px;
  color: var(--text-3);
  line-height: 1.7;
  padding: 8px 10px;
  border-left: 2px solid var(--warn);
  background: rgba(255, 184, 0, 0.05);
  margin-bottom: 10px;
  font-family: var(--mono);
}
.preset-hint b { color: var(--warn); }

@media (max-width: 1024px) {
  .adjust-grid { grid-template-columns: 1fr; }
  .adjust-grid .span-2 { grid-column: span 1; }
}
</style>
