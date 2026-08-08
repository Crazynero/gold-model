/**
 * 全局数字格式化工具
 * 统一处理 ECharts label/tooltip/axisLabel 与模板 {{ }} 的数值显示，避免浮点精度泄漏
 * （后端原始值如 33.54203636944294 会直接渲染成长小数）
 */

/** 智能数字格式化：整数 0 位、|v|<1 保留 3 位、其余 2 位。null/空 → '--' */
export function fmtNum(v: any): string {
  if (v == null || v === '') return '--'
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  if (isNaN(n)) return String(v)
  if (Number.isInteger(n)) return n.toString()
  if (Math.abs(n) < 1 && n !== 0) return n.toFixed(3)
  return n.toFixed(2)
}

/** 百分比格式化：默认 1 位小数（如 12.3%） */
export function fmtPct(v: any, digits = 1): string {
  if (v == null || v === '') return '--'
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  if (isNaN(n)) return String(v)
  return n.toFixed(digits) + '%'
}

/** 金额格式化：2 位小数 + $ 前缀 */
export function fmtMoney(v: any): string {
  if (v == null || v === '') return '--'
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  if (isNaN(n)) return String(v)
  return '$' + n.toFixed(2)
}
