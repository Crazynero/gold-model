<template>
  <div ref="elRef" :style="{ width: '100%', height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watchEffect, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  option: () => echarts.EChartsOption
  height?: string
}>()

const elRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function ensureChart(): echarts.ECharts | null {
  if (!elRef.value) return null
  if (!chart) chart = echarts.init(elRef.value, undefined, { renderer: 'canvas' })
  return chart
}

function render() {
  const c = ensureChart()
  if (!c) return
  try {
    const opt = props.option()
    c.setOption(opt, true)
  } catch (e) {
    console.error('[ChartBox] render error', e)
  }
}

function resize() {
  chart && chart.resize()
}

// post 模式：在 DOM 更新后运行，确保 elRef 已就位
watchEffect(() => {
  // 调用 props.option 触发对其内部访问的响应式数据（如 dashboardData.value）的依赖追踪
  // 当 dashboardData 变化时，effect 重新运行
  if (!elRef.value) return
  const c = ensureChart()
  if (!c) return
  try {
    const opt = props.option()
    c.setOption(opt, true)
  } catch (e) {
    console.error('[ChartBox] effect error', e)
  }
}, { flush: 'post' })

onMounted(() => {
  nextTick(render)
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
  chart = null
})

defineExpose({ resize, render })
</script>
