<template>
  <a-popover trigger="click" :popup-style="{ background: 'var(--surface-2)' }">
    <span class="info-icon">?</span>
    <template #content>
      <div class="info-panel">
        <div class="info-panel-title">{{ title }}</div>
        <div class="info-panel-body"><slot /></div>
      </div>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<style scoped>
.info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: 1px solid var(--border);
  border-radius: 2px;
  font-family: var(--mono);
  font-size: 9px;
  cursor: pointer;
  color: var(--text-3);
  margin-left: 4px;
  flex-shrink: 0;
  transition: all 0.15s;
}
.info-icon:hover {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}
.info-panel {
  max-width: 380px;
  max-height: 400px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-2);
}
.info-panel :deep(b) { color: var(--text); }
.info-panel :deep(ul) { margin-left: 14px; margin-top: 4px; margin-bottom: 6px; }
.info-panel :deep(li) { margin-bottom: 2px; }
.info-panel-title {
  font-family: var(--mono);
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 6px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
</style>
