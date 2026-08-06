<template>
  <div class="hud-card">
    <div v-if="title" class="hud-card-title">
      <span>{{ title }}</span>
      <span v-if="meta" class="meta">{{ meta }}</span>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
  meta?: string
}>()
</script>

<style scoped>
.hud-card .meta {
  margin-left: auto;
  color: var(--text-3);
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0.06em;
}
.hud-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
