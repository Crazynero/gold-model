<template>
  <div :class="['metric-card', colorClass]">
    <div class="value">{{ value }}</div>
    <div class="label">{{ label }}</div>
    <div v-if="sub" class="sub">{{ sub }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: string | number
  label: string
  sub?: string
  color?: 'pos' | 'neg' | 'acc' | 'warn' | 'gold'
}>()

const colorClass = computed(() => `m-${props.color || 'acc'}`)
</script>

<style scoped>
.metric-card { text-align: center; padding: 14px 8px; }
.metric-card .value {
  font-family: var(--mono);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1;
}
.metric-card .label {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-3);
  margin-top: 6px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.metric-card .sub {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-top: 2px;
}
.m-pos .value { color: var(--pos); text-shadow: 0 0 12px rgba(0, 255, 156, 0.25); }
.m-neg .value { color: var(--neg); text-shadow: 0 0 12px rgba(255, 56, 96, 0.25); }
.m-acc .value { color: var(--accent); text-shadow: 0 0 12px rgba(0, 212, 255, 0.25); }
.m-warn .value { color: var(--warn); text-shadow: 0 0 12px rgba(255, 184, 0, 0.25); }
.m-gold .value { color: var(--gold); text-shadow: 0 0 12px rgba(255, 176, 32, 0.25); }
</style>
