<template>
  <div class="hub-wrap">
    <div class="hub-tabs">
      <div
        v-for="s in subs"
        :key="s.key"
        :class="['hub-tab', { active: cur === s.key }]"
        @click="cur = s.key"
      >
        {{ $t(s.tkey) }}
      </div>
    </div>
    <component :is="currentSub" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'

const subs = [
  { key: 'backtest', tkey: 'nav.backtest' },
  { key: 'compare', tkey: 'nav.compare' },
  { key: 'versions', tkey: 'nav.versions' },
  { key: 'walkforward', tkey: 'nav.walkforward' },
  { key: 'validation', tkey: 'nav.validation' }
]

const subViews: Record<string, () => Promise<any>> = {
  backtest: () => import('@/views/BacktestView.vue'),
  compare: () => import('@/views/CompareView.vue'),
  versions: () => import('@/views/ModelVersionsView.vue'),
  walkforward: () => import('@/views/WalkForwardView.vue'),
  validation: () => import('@/views/ValidationView.vue')
}

const cur = ref('backtest')
const currentSub = computed(() => defineAsyncComponent(subViews[cur.value]))
</script>

<style scoped>
.hub-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.hub-tab {
  padding: 6px 14px;
  cursor: pointer;
  color: var(--text-3);
  border-bottom: 2px solid transparent;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
  transition: all 0.15s;
}
.hub-tab:hover { color: var(--text-2); }
.hub-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
</style>
