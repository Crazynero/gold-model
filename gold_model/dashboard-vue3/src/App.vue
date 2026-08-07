<template>
  <div class="app-layout">
    <TheStatusBar />
    <TheNavbar @switch="handleSwitch" />
    <div class="group-bar">
      <div
        v-for="g in groups"
        :key="g.key"
        :class="['group-tab', { active: activeGroup === g.key }]"
        @click="switchGroup(g.key)"
      >
        {{ $t('group.' + g.key) }}
      </div>
      <button class="priv-toggle" :title="$t('group.privacyTip')" @click="togglePrivacy">
        {{ privacyOn ? '🙈' : '👁' }} {{ privacyOn ? $t('group.masked') : $t('group.mask') }}
      </button>
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
    <div v-if="visibleSubTabs.length > 1" class="sub-bar">
      <div
        v-for="t in visibleSubTabs"
        :key="t.key"
        :class="['sub-tab', { active: active === t.key }]"
        @click="active = t.key"
      >
        {{ $t(t.tkey) }}
      </div>
    </div>
    <main class="app-main">
      <component :is="currentView" />
    </main>
    <CmdPalette
      :visible="paletteVisible"
      :tabs="tabs"
      @close="paletteVisible = false"
      @switch-tab="handleSwitch"
      @run-command="handleCommand"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
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

// ── 隐私遮罩（快捷键 P）──
const privacyOn = ref(false)
function applyPrivacy(on: boolean) {
  privacyOn.value = on
  document.body.classList.toggle('privacy', on)
  try { localStorage.setItem('v7-privacy', on ? '1' : '0') } catch (e) {}
}
function togglePrivacy() {
  applyPrivacy(!privacyOn.value)
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    paletteVisible.value = !paletteVisible.value
    return
  }
  const target = e.target as HTMLElement
  const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
  if ((e.key === 'p' || e.key === 'P') && !e.metaKey && !e.ctrlKey && !e.altKey && !typing) {
    togglePrivacy()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  try { if (localStorage.getItem('v7-privacy') === '1') applyPrivacy(true) } catch (e) {}
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function handleCommand(cmd: string) {
  if (cmd.startsWith('symbol:')) {
    console.log('[cmd] switch symbol', cmd)
  } else if (cmd.startsWith('run:')) {
    if (cmd === 'run:backtest') handleSwitch('custombt')
    else if (cmd === 'run:simulator') handleSwitch('simulator')
    else if (cmd === 'run:report') handleSwitch('execution')
  } else if (cmd === 'export:csv') {
    handleSwitch('data')
  } else if (cmd === 'refresh') {
    loadAll()
  }
}

// ── V7 四分组信息架构 ──
const groups = [
  { key: 'decision', tabs: ['overview', 'wall', 'execution', 'simulator', 'adjust'] },
  { key: 'model', tabs: ['factors', 'backtestHub', 'custombt', 'eventbt', 'attribution', 'tuning'] },
  { key: 'data', tabs: ['data', 'history'] },
  { key: 'system', tabs: ['system'] }
]

// 从回测中心内部跳转进来的隐藏页，归属于模型组
const hiddenTabGroup: Record<string, string> = {
  backtest: 'model', compare: 'model', versions: 'model',
  walkforward: 'model', validation: 'model'
}

const tabs = [
  { key: 'overview', tkey: 'nav.overview', gold: false },
  { key: 'wall', tkey: 'nav.wall', gold: false },
  { key: 'execution', tkey: 'nav.execution', gold: false },
  { key: 'simulator', tkey: 'nav.simulator', gold: false },
  { key: 'adjust', tkey: 'nav.adjust', gold: false },
  { key: 'factors', tkey: 'nav.factors', gold: false },
  { key: 'backtestHub', tkey: 'nav.backtestHub', gold: false },
  { key: 'custombt', tkey: 'nav.custombt', gold: false },
  { key: 'eventbt', tkey: 'nav.eventbt', gold: false },
  { key: 'attribution', tkey: 'nav.attribution', gold: false },
  { key: 'tuning', tkey: 'nav.tuning', gold: false },
  { key: 'data', tkey: 'nav.data', gold: false },
  { key: 'history', tkey: 'nav.history', gold: false },
  { key: 'system', tkey: 'nav.system', gold: false }
]

const active = ref('overview')

const activeGroup = computed(() => {
  for (const g of groups) {
    if (g.tabs.includes(active.value)) return g.key
  }
  return hiddenTabGroup[active.value] || 'decision'
})

const visibleSubTabs = computed(() => {
  const g = groups.find(x => x.key === activeGroup.value)
  if (!g) return []
  return tabs.filter(t => g.tabs.includes(t.key))
})

function switchGroup(key: string) {
  const g = groups.find(x => x.key === key)
  if (g && g.tabs.length) active.value = g.tabs[0]
}

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
  execution: () => import('@/views/ExecutionView.vue'),
  system: () => import('@/views/SystemView.vue')
}

const currentView = computed(() => defineAsyncComponent(views[active.value]))

function handleSwitch(tab: string) {
  active.value = tab
}

// ── 深链：#tab=<key> 直达指定页面 ──
function applyHash() {
  const m = location.hash.match(/tab=([a-zA-Z]+)/)
  if (m && views[m[1]]) active.value = m[1]
}
onMounted(() => {
  applyHash()
  window.addEventListener('hashchange', applyHash)
})
onUnmounted(() => {
  window.removeEventListener('hashchange', applyHash)
})
watch(active, v => {
  try { history.replaceState(null, '', '#tab=' + v) } catch (e) {}
})
</script>

<style scoped>
.group-bar {
  display: flex;
  gap: 24px;
  align-items: center;
  padding: 0 32px;
  height: 44px;
  border-bottom: 1px solid var(--border-soft);
}
.group-tab {
  cursor: pointer;
  color: var(--text-3);
  font-size: 14px;
  font-weight: 500;
  height: 44px;
  line-height: 44px;
  border-bottom: 2px solid transparent;
  transition: color 0.15s;
}
.group-tab:hover { color: var(--text-2); }
.group-tab.active {
  color: var(--gold);
  border-bottom-color: var(--gold);
}
.sub-bar {
  display: flex;
  gap: 4px;
  padding: 0 32px;
  height: 36px;
  border-bottom: 1px solid var(--border-soft);
  overflow-x: auto;
  background: var(--surface);
}
.sub-tab {
  padding: 0 14px;
  cursor: pointer;
  color: var(--text-3);
  font-size: 12px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  border-bottom: 2px solid transparent;
  transition: color 0.15s;
}
.sub-tab:hover { color: var(--text-2); }
.sub-tab.active {
  color: var(--text);
  border-bottom-color: var(--gold);
}
.cmd-trigger {
  margin-left: auto;
  padding: 0 10px;
  cursor: pointer;
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface-2);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  display: flex;
  align-items: center;
  height: 22px;
  transition: all 0.15s;
}
.cmd-trigger:hover {
  color: var(--gold);
  border-color: var(--border-strong);
  background: var(--accent-soft);
}
.lang-switch { align-self: center; }
.group-bar .priv-toggle { margin-left: auto; }
.group-bar .priv-toggle + .cmd-trigger { margin-left: 0; }
</style>
