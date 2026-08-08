<template>
  <div v-if="visible" class="cmd-palette-overlay" @click.self="close">
    <div class="cmd-palette">
      <div class="cp-header">
        <span class="cp-prompt">&gt;</span>
        <input
          ref="inputRef"
          v-model="query"
          class="cp-input"
          :placeholder="t('cmd.placeholder')"
          @keydown.enter="execute"
          @keydown.esc="close"
          @keydown.up.prevent="moveUp"
          @keydown.down.prevent="moveDown"
        />
      </div>
      <div class="cp-results">
        <div
          v-for="(c, i) in filtered"
          :key="c.id"
          :class="['cp-item', { active: i === selected }]"
          @click="run(c)"
          @mouseenter="selected = i"
        >
          <span class="cp-cat">{{ c.cat }}</span>
          <span class="cp-label">{{ c.label }}</span>
          <span v-if="c.shortcut" class="cp-shortcut">{{ c.shortcut }}</span>
        </div>
        <div v-if="filtered.length === 0" class="cp-empty">{{ t('cmd.empty') }}</div>
      </div>
      <div class="cp-footer">
        <span>{{ t('cmd.navHint') }}</span>
        <span>{{ t('cmd.execHint') }}</span>
        <span>{{ t('cmd.closeHint') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  tabs: Array<{ key: string; tkey?: string; label?: string; gold?: boolean }>
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'switch-tab', key: string): void
  (e: 'run-command', cmd: string): void
}>()

const query = ref('')
const selected = ref(0)
const inputRef = ref<HTMLInputElement>()

interface Cmd {
  id: string
  cat: string
  label: string
  shortcut?: string
  action: 'switch' | 'command'
  target?: string
}

const commands = computed<Cmd[]>(() => {
  const tabs: Cmd[] = (props.tabs || []).map(tab => {
    // tkey 优先（与左侧导航一致走 i18n），无 tkey 时回退到静态 label
    const tabLabel = (tab.tkey && t(tab.tkey)) || tab.label || tab.key
    return {
      id: `tab-${tab.key}`,
      cat: 'TAB',
      label: t('cmd.switchTab', { label: tabLabel }),
      action: 'switch',
      target: tab.key,
      shortcut: ''
    }
  })
  const cmds: Cmd[] = [
    { id: 'cmd-refresh', cat: 'CMD', label: t('cmd.refresh'), action: 'command', target: 'refresh' },
    { id: 'cmd-gold', cat: 'SYMBOL', label: t('cmd.switchSymbol', { symbol: 'GOLD' }), action: 'command', target: 'symbol:GOLD' },
    { id: 'cmd-silver', cat: 'SYMBOL', label: t('cmd.switchSymbol', { symbol: 'SILVER' }), action: 'command', target: 'symbol:SILVER' },
    { id: 'cmd-btc', cat: 'SYMBOL', label: t('cmd.switchSymbol', { symbol: 'BTC' }), action: 'command', target: 'symbol:BTC' },
    { id: 'cmd-run-bt', cat: 'CMD', label: t('cmd.runBt'), action: 'command', target: 'run:backtest' },
    { id: 'cmd-run-sim', cat: 'CMD', label: t('cmd.runSim'), action: 'command', target: 'run:simulator' },
    { id: 'cmd-pdf', cat: 'CMD', label: t('cmd.pdf'), action: 'command', target: 'run:report' },
    { id: 'cmd-csv', cat: 'CMD', label: t('cmd.csv'), action: 'command', target: 'export:csv' },
    { id: 'cmd-toggle-theme', cat: 'CMD', label: t('cmd.theme'), action: 'command', target: 'toggle:theme' }
  ]
  return [...tabs, ...cmds]
})

const filtered = computed<Cmd[]>(() => {
  if (!query.value) return commands.value
  const q = query.value.toLowerCase()
  return commands.value.filter(c =>
    c.label.toLowerCase().includes(q) ||
    c.cat.toLowerCase().includes(q) ||
    c.id.includes(q)
  )
})

watch(() => props.visible, (v) => {
  if (v) {
    query.value = ''
    selected.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

function run(c: Cmd) {
  if (c.action === 'switch' && c.target) {
    emit('switch-tab', c.target)
  } else if (c.action === 'command' && c.target) {
    emit('run-command', c.target)
  }
  close()
}

function execute() {
  if (filtered.value.length > 0) {
    run(filtered.value[selected.value])
  }
}

function moveUp() {
  selected.value = Math.max(0, selected.value - 1)
}

function moveDown() {
  selected.value = Math.min(filtered.value.length - 1, selected.value + 1)
}

function close() {
  emit('close')
}
</script>

<style scoped>
.cmd-palette-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 100px;
  animation: fadeIn 0.15s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
.cmd-palette {
  width: 600px;
  max-width: 90%;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 30px rgba(217, 166, 72, 0.1);
  font-family: var(--mono);
}
.cp-header {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.cp-prompt {
  color: var(--accent);
  margin-right: 10px;
  font-size: 14px;
}
.cp-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
}
.cp-input::placeholder { color: var(--text-3); }
.cp-results {
  max-height: 400px;
  overflow-y: auto;
  padding: 6px 0;
}
.cp-item {
  display: grid;
  grid-template-columns: 70px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-2);
  transition: background 0.1s;
}
.cp-item.active {
  background: var(--accent-soft);
  color: var(--text);
}
.cp-cat {
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.cp-item.active .cp-cat { color: var(--accent); }
.cp-shortcut {
  font-size: 10px;
  color: var(--text-3);
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 2px;
}
.cp-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-3);
  font-size: 11px;
}
.cp-footer {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--border);
  background: var(--surface-2);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.08em;
}
</style>
