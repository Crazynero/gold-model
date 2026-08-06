<template>
  <div class="app-layout">
    <TheStatusBar />
    <TheNavbar @switch="handleSwitch" />
    <div class="tabs-bar">
      <div
        v-for="t in tabs"
        :key="t.key"
        :class="['tab', { active: active === t.key, 'tab-wall': t.gold }]"
        @click="active = t.key"
      >
        {{ $t(t.tkey) }}
      </div>
      <div class="cmd-trigger" @click="paletteVisible = true">
        <span>⌘K</span>
      </div>
      <div class="lang-switch">
        <a-radio-group :model-value="currentLang" type="button" size="mini" @change="onLangChange">
          <a-radio value="zh">中</a-radio>
          <a-radio value="en">EN</a-radio>
        </a-radio-group>
      </div>
    </div>
    <main class="app-main">
      <component :is="currentView" />
    </main>
    <CmdPalette
      :visible="paletteVisible"
      :tabs="tabs"
      @close="paletteVisible = false"
      @switch-tab="active = $event"
      @run-command="handleCommand"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import TheStatusBar from '@/components/TheStatusBar.vue'
import TheNavbar from '@/components/TheNavbar.vue'
import CmdPalette from '@/components/CmdPalette.vue'
import { useDashboard, loadAll } from '@/composables/useDashboardData'
import { setLang, getLang } from '@/i18n'

const { t } = useI18n()

// 触发数据加载
useDashboard()
onMounted(() => { loadAll() })

// 语言切换
const currentLang = ref(getLang())
function onLangChange(v: any) {
  const lang = typeof v === 'string' ? v : (v as any)
  setLang(lang)
  currentLang.value = lang
}

// W: 命令面板
const paletteVisible = ref(false)

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    paletteVisible.value = !paletteVisible.value
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function handleCommand(cmd: string) {
  if (cmd.startsWith('symbol:')) {
    console.log('[cmd] switch symbol', cmd)
  } else if (cmd.startsWith('run:')) {
    if (cmd === 'run:backtest') active.value = 'custombt'
    else if (cmd === 'run:simulator') active.value = 'simulator'
    else if (cmd === 'run:report') active.value = 'execution'
  } else if (cmd === 'export:csv') {
    active.value = 'data'
  } else if (cmd === 'refresh') {
    loadAll()
  }
}

const tabs = [
  { key: 'wall', tkey: 'nav.wall', gold: true },
  { key: 'overview', tkey: 'nav.overview', gold: false },
  { key: 'factors', tkey: 'nav.factors', gold: false },
  { key: 'backtestHub', tkey: 'nav.backtestHub', gold: false },
  { key: 'custombt', tkey: 'nav.custombt', gold: false },
  { key: 'eventbt', tkey: 'nav.eventbt', gold: false },
  { key: 'simulator', tkey: 'nav.simulator', gold: false },
  { key: 'attribution', tkey: 'nav.attribution', gold: false },
  { key: 'history', tkey: 'nav.history', gold: false },
  { key: 'tuning', tkey: 'nav.tuning', gold: false },
  { key: 'adjust', tkey: 'nav.adjust', gold: false },
  { key: 'data', tkey: 'nav.data', gold: false },
  { key: 'execution', tkey: 'nav.execution', gold: false }
]

const active = ref('wall')

const views: Record<string, () => Promise<any>> = {
  wall: () => import('@/views/WallView.vue'),
  overview: () => import('@/views/OverviewView.vue'),
  factors: () => import('@/views/FactorsView.vue'),
  backtestHub: () => import('@/views/BacktestHubView.vue'),
  backtest: () => import('@/views/BacktestView.vue'),
  compare: () => import('@/views/CompareView.vue'),
  versions: () => import('@/views/ModelVersionsView.vue'),
  walkforward: () => import('@/views/WalkForwardView.vue'),
  validation: () => import('@/views/ValidationView.vue'),
  custombt: () => import('@/views/BacktestCustomView.vue'),
  eventbt: () => import('@/views/EventBacktestView.vue'),
  simulator: () => import('@/views/SimulatorView.vue'),
  attribution: () => import('@/views/AttributionView.vue'),
  history: () => import('@/views/HistoryView.vue'),
  tuning: () => import('@/views/TuningView.vue'),
  adjust: () => import('@/views/AdjustView.vue'),
  data: () => import('@/views/DataView.vue'),
  execution: () => import('@/views/ExecutionView.vue')
}

const currentView = computed(() => defineAsyncComponent(views[active.value]))

function handleSwitch(tab: string) {
  active.value = tab
}
</script>

<style scoped>
.tabs-bar {
  display: flex;
  gap: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  overflow-x: auto;
  height: 36px;
}
.tab {
  padding: 0 16px;
  cursor: pointer;
  color: var(--text-3);
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.tab::before {
  content: '>';
  color: var(--text-dim);
  font-size: 10px;
}
.tab:hover {
  color: var(--text-2);
  background: rgba(0, 212, 255, 0.03);
}
.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: rgba(0, 212, 255, 0.05);
}
.tab.active::before { color: var(--accent); }

.tab-wall { color: var(--gold); }
.tab-wall:hover { color: var(--gold); background: rgba(255, 176, 32, 0.05); }
.tab-wall.active {
  color: var(--gold);
  border-bottom-color: var(--gold);
  background: rgba(255, 176, 32, 0.05);
}
.tab-wall.active::before { color: var(--gold); }

.cmd-trigger {
  margin-left: auto;
  padding: 0 10px;
  cursor: pointer;
  color: var(--text-3);
  border: 1px solid var(--border);
  background: var(--surface-2);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  display: flex;
  align-items: center;
  height: 22px;
  align-self: center;
  transition: all 0.15s;
}
.cmd-trigger:hover {
  color: var(--accent);
  border-color: var(--border-strong);
  background: var(--accent-soft);
}
.lang-switch {
  align-self: center;
}
</style>
