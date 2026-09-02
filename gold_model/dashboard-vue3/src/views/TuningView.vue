<template>
  <div class="tuning-grid">
    <HudCard :title="$t('card.v5TuningParameters')" :meta="$t('meta.params6')" class="span-2">
      <div class="params-grid">
        <div class="p-item">
          <div class="p-label">训练窗口 (日)</div>
          <a-input-number v-model="params.train_window" :min="100" :max="2000" :step="50" :style="{ width: '100%' }" />
          <div class="p-hint">默认 500，建议 250-1000（映射 V5_TRAIN_WINDOW）</div>
        </div>
        <div class="p-item">
          <div class="p-label">Purge gap (日)</div>
          <a-input-number v-model="params.purge_gap" :min="0" :max="120" :step="5" :style="{ width: '100%' }" />
          <div class="p-hint">train/test 间隔，防标签泄漏；默认 60（映射 V5_PURGE_GAP）</div>
        </div>
      </div>
      <div class="actions">
        <a-button type="primary" long :loading="running" :disabled="!apiBase" @click="runV5">
          {{ running ? 'V5 运行中...（3-5 分钟）' : 'RUN V5' }}
        </a-button>
        <a-button long @click="resetParams">{{ $t('common.reset') }}</a-button>
      </div>
      <div class="p-hint" style="padding: 4px 0;">
        ℹ 修复假交互：此前展示 6 个参数但主管道只认 2 个（其余收下即弃）。现仅暴露实际生效的参数；标签horizon/VIF阈值等需改 gold_factor_v5.py 硬编码。
      </div>
      <div v-if="!apiBase" class="hint-warn">
        ⚠ file:// 协议下不可用。需启动后端：python3 -m uvicorn api_server:app --port 8000
      </div>
    </HudCard>

    <HudCard :title="$t('card.runResult')" :meta="$t('meta.live')" class="span-2">
      <div v-if="result" class="result-area">
        <div class="r-status" :class="result.status === 'ok' ? 'ok' : 'fail'">
          {{ result.status === 'ok' ? 'SUCCESS' : 'FAILED' }}
        </div>
        <div class="r-time">运行时间: {{ result.ran_at?.substring(11, 19) }}</div>
        <div v-if="result.metrics">
          <div v-for="(v, k) in result.metrics" :key="k" class="r-metric">
            <span class="rm-key">{{ k }}</span>
            <span class="rm-val">{{ v }}</span>
          </div>
        </div>
        <div v-if="result.params" class="r-params">
          <div class="rp-title">使用参数</div>
          <div v-for="(v, k) in result.params" :key="k" class="rp-item">
            <span>{{ k }}</span><b>{{ v }}</b>
          </div>
        </div>
      </div>
      <div v-else-if="running" class="hint">
        ⏳ V5 脚本运行中，约 3-5 分钟...<br>
        yfinance 拉数据 + XGBoost 训练 + Walk-Forward 验证
      </div>
      <div v-else class="hint">点击 RUN V5 开始（需后端服务）</div>
    </HudCard>

    <HudCard :title="$t('card.stdoutLog')" :meta="$t('meta.tail')" class="span-2">
      <pre v-if="result?.stdout_tail" class="stdout">{{ result.stdout_tail }}</pre>
      <div v-else class="hint">等待运行日志</div>
    </HudCard>

    <HudCard :title="$t('card.stderr')" :meta="$t('meta.error')" class="span-2">
      <pre v-if="result?.stderr_tail" class="stderr">{{ result.stderr_tail }}</pre>
      <div v-else class="hint">无错误</div>
    </HudCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import HudCard from '@/components/HudCard.vue'
import { apiBase } from '@/composables/useDashboardData'
import { Message } from '@arco-design/web-vue'

const params = ref({
  train_window: 500,
  purge_gap: 60
})

const running = ref(false)
const result = ref<any>(null)

async function runV5() {
  if (!apiBase.value) {
    Message.warning('需先启动 FastAPI 后端')
    return
  }
  running.value = true
  result.value = null
  try {
    const resp = await fetch(`${apiBase.value}/api/v5/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params.value)
    })
    result.value = await resp.json()
    if (resp.ok) {
      Message.success('V5 运行完成')
    } else {
      Message.error('V5 运行失败：' + (result.value?.detail || ''))
    }
  } catch (e: any) {
    Message.error('请求失败：' + e?.message)
  } finally {
    running.value = false
  }
}

function resetParams() {
  params.value = { train_window: 500, purge_gap: 60 }
  result.value = null
  Message.info('参数已重置')
}
</script>

<style scoped>
.tuning-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tuning-grid .span-2 { grid-column: span 2; }
.params-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.p-item { display: flex; flex-direction: column; gap: 4px; }
.p-label {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.p-hint {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-dim);
  margin-top: 2px;
}
.actions { display: grid; grid-template-columns: 2fr 1fr; gap: 8px; margin-top: 10px; }
.hint-warn {
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(238, 193, 112, 0.06);
  border-left: 2px solid var(--warn);
  color: var(--warn);
  font-family: var(--mono);
  font-size: 11px;
}
.result-area { display: flex; flex-direction: column; gap: 10px; }
.r-status {
  font-family: var(--mono);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.1em;
}
.r-status.ok { color: var(--pos); }
.r-status.fail { color: var(--neg); }
.r-time { font-family: var(--mono); font-size: 11px; color: var(--text-3); }
.r-metric {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 11px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border-soft);
}
.r-metric .rm-key { color: var(--text-3); }
.r-metric .rm-val { color: var(--accent); text-align: right; word-break: break-all; }
.r-params { margin-top: 8px; }
.rp-title { font-family: var(--mono); font-size: 10px; color: var(--text-3); margin-bottom: 4px; letter-spacing: 0.08em; }
.rp-item {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-2);
  padding: 2px 0;
}
.rp-item b { color: var(--accent); }
.hint { text-align: center; color: var(--text-3); font-family: var(--mono); font-size: 11px; padding: 20px; line-height: 1.8; }
.stdout, .stderr {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-2);
  background: var(--bg);
  padding: 10px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.stderr { color: var(--neg); }
@media (max-width: 1024px) {
  .tuning-grid { grid-template-columns: 1fr; }
  .tuning-grid .span-2 { grid-column: span 1; }
  .params-grid { grid-template-columns: 1fr 1fr; }
}
</style>
