<template>
  <div class="prob-bar-container">
    <div v-for="(b, i) in bars" :key="i" class="prob-bar">
      <div class="bar-value" :style="{ color: b.color }">{{ b.value }}</div>
      <div class="bar" :style="{ height: b.height + 'px', background: b.color, color: b.color }"></div>
      <div class="bar-label">{{ b.label }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  items: Array<{ label: string; pct: number; color?: string }>
  height?: number
}>()

const bars = computed(() => {
  const max = props.height || 160
  return (props.items || []).map(b => {
    const color = b.color || (b.pct >= 0.6 ? 'var(--pos)' : b.pct < 0.5 ? 'var(--neg)' : 'var(--text-3)')
    return {
      label: b.label,
      value: Math.round(b.pct * 100) + '%',
      height: Math.max(8, b.pct * max),
      color
    }
  })
})
</script>

<style scoped>
.prob-bar-container {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 160px;
  padding: 12px 8px;
}
.prob-bar { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.prob-bar .bar {
  width: 32px;
  border-radius: 1px 1px 0 0;
  transition: height 0.3s;
  box-shadow: 0 0 8px current-color;
}
.prob-bar .bar-label {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.08em;
}
.prob-bar .bar-value {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 500;
}
</style>
