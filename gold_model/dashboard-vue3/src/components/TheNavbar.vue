<template>
  <div class="navbar">
    <div class="nav-left">
      <div class="logo">GOLD COMMAND<span class="ver">V6.0 // VUE3</span></div>
      <span class="live-dot">LIVE</span>
      <span class="clock">{{ clock }}</span>
      <div :class="['signal-badge', sigClass]">{{ sigText }}</div>
      <div class="symbol-switch">
        <span class="ss-label">SYMBOL</span>
        <a-radio-group v-model="selectedSymbol" type="button" size="mini" @change="onSymbolChange">
          <a-radio v-for="s in symbols" :key="s.key" :value="s.key">{{ s.label }}</a-radio>
        </a-radio-group>
      </div>
    </div>
    <div class="nav-btns">
      <a-button size="small" @click="handleRefresh">REFRESH</a-button>
      <a-button type="primary" size="small" @click="$emit('switch', 'adjust')">MANUAL</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { dashboardData, extractValue } from '@/composables/useDashboardData'

defineEmits<{ (e: 'switch', tab: string): void }>()

// L: 多标的切换
const symbols = [
  { key: 'GOLD', label: 'GOLD' },
  { key: 'SILVER', label: 'SILVER' },
  { key: 'COPPER', label: 'COPPER' },
  { key: 'BTC', label: 'BTC' }
]
const selectedSymbol = ref('GOLD')

function onSymbolChange(v: any) {
  const sym = typeof v === 'string' ? v : v
  if (sym === 'GOLD') {
    alert('已切换到 GOLD（当前数据）')
  } else {
    alert(`已切换到 ${sym}\n\n注意：${sym} 标的的数据管道尚未接入，仍显示 GOLD 数据。\n接入流程：\n1. 修改 gold_factor_v5.py 调用 yfinance 的 SLV/HG=F/BTC-USD\n2. 跑出 ${sym} 的 dashboard_data.json\n3. 通过 /api/db/ingest 入库\n4. 前端自动加载新数据`)
  }
}

const clock = ref('--:--:--')
let timer: any

function tick() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  clock.value = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

onMounted(() => {
  tick()
  timer = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(timer))

const action = computed(() => extractValue(dashboardData.value.overview, '建议操作') || '空仓观望')

const sigClass = computed(() => {
  if (action.value.includes('做多')) return 'sig-bull'
  if (action.value.includes('做空')) return 'sig-bear'
  return 'sig-wait'
})

const sigText = computed(() => {
  if (action.value.includes('做多')) return 'LONG'
  if (action.value.includes('做空')) return 'SHORT'
  return 'WAIT'
})

function handleRefresh() {
  location.reload()
}
</script>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: linear-gradient(180deg, rgba(10, 14, 22, 0.95) 0%, rgba(4, 6, 10, 0.85) 100%);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  height: 48px;
  backdrop-filter: blur(8px);
}
.nav-left { display: flex; align-items: center; gap: 20px; }
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.1em;
  color: var(--accent);
  text-shadow: 0 0 12px rgba(0, 212, 255, 0.4);
}
.logo::before {
  content: '◢◣';
  color: var(--accent);
  font-size: 10px;
  letter-spacing: -2px;
}
.logo .ver {
  color: var(--text-3);
  font-weight: 400;
  margin-left: 4px;
  font-size: 11px;
  letter-spacing: 0.05em;
}
.clock {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text-2);
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border: 1px solid var(--border);
  background: rgba(0, 212, 255, 0.04);
  border-radius: 2px;
}
.symbol-switch {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ss-label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.08em;
}
.nav-btns { display: flex; gap: 6px; }
</style>
