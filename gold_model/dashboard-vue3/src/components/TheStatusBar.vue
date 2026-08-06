<template>
  <div class="status-bar">
    <div class="left">
      <span>SYS: <b>ONLINE</b></span>
      <span>MODEL: <b>V6.0/VUE3</b></span>
      <span>DATA: <b class="src-tag" :class="srcClass">{{ srcLabel }}</b></span>
      <span v-if="wsConnected" class="ws-tag">
        <span class="ws-dot"></span>WS LIVE
      </span>
      <span v-else-if="apiBase" class="ws-tag dim">WS OFF</span>
      <span v-if="lastUpdate" class="updt">
        <span class="dot" :class="dotClass"></span>
        UPD {{ lastUpdateStr }}
      </span>
    </div>
    <div class="right">
      <span>REGIME: <b class="text-acc">{{ regime }}</b></span>
      <span>POSITION: <b class="text-acc">{{ position }}</b></span>
      <span>BASE: <b class="text-acc">{{ baseDate }}</b></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  dashboardData, executionData, extractValue,
  lastUpdate, updateSource, apiBase,
  wsConnected, wsMessageCount
} from '@/composables/useDashboardData'

const srcLabel = computed(() => {
  if (wsConnected.value) return 'WS'
  if (updateSource.value === 'api') return 'API'
  if (updateSource.value === 'fetch') return 'LIVE'
  if (updateSource.value === 'window') return 'INLINE'
  return 'OFFLINE'
})

const srcClass = computed(() => {
  if (wsConnected.value) return 'src-ws'
  if (updateSource.value === 'fetch' || updateSource.value === 'api') return 'src-live'
  if (updateSource.value === 'window') return 'src-inline'
  return 'src-off'
})

const dotClass = computed(() => {
  if (updateSource.value === 'fetch' || updateSource.value === 'api' || wsConnected.value) return 'live'
  if (updateSource.value === 'window') return 'inline'
  return 'off'
})

const regime = computed(() => extractValue(dashboardData.value.overview, '当前Regime') || '--')
const position = computed(() => {
  const exec = executionData.value?.current
  if (exec?.position !== undefined) {
    const p = typeof exec.position === 'number' ? exec.position : parseFloat(String(exec.position))
    return `${(p * 100).toFixed(1)}%`
  }
  return extractValue(dashboardData.value.overview, '建议操作') || '空仓观望'
})
const baseDate = computed(() => extractValue(dashboardData.value.overview, '预测基准日') || '--')

const lastUpdateStr = computed(() => {
  if (!lastUpdate.value) return '--:--:--'
  const d = lastUpdate.value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})
</script>

<style scoped>
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.08em;
}
.left, .right { display: flex; gap: 16px; align-items: center; }
b { color: var(--accent); font-weight: 500; }
.src-tag {
  padding: 0 4px;
  border: 1px solid var(--border);
  border-radius: 2px;
  font-size: 9px;
  letter-spacing: 0.1em;
}
.src-tag.src-live { color: var(--pos); border-color: rgba(0,255,156,0.3); }
.src-tag.src-ws { color: var(--accent); border-color: rgba(0,212,255,0.4); }
.src-tag.src-inline { color: var(--warn); border-color: rgba(255,184,0,0.3); }
.src-tag.src-off { color: var(--neg); border-color: rgba(255,56,96,0.3); }

.ws-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--accent);
}
.ws-tag.dim { color: var(--text-3); }
.ws-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 5px var(--accent);
  animation: pulse 1.5s infinite;
}

.updt { display: inline-flex; align-items: center; gap: 4px; }
.dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.dot.live {
  background: var(--pos);
  box-shadow: 0 0 6px var(--pos);
  animation: pulse 2s infinite;
}
.dot.inline { background: var(--warn); }
.dot.off { background: var(--neg); }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
