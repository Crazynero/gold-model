import { createI18n } from 'vue-i18n'

const messages = {
  en: {
    nav: {
      wall: 'Wall', overview: 'Overview', factors: 'Factors', backtest: 'Backtest',
      backtestHub: 'Backtest Hub',
      compare: 'Compare', versions: 'Versions', walkforward: 'Walk-Forward',
      validation: 'Validation', custombt: 'Signal BT', eventbt: 'Event BT',
      simulator: 'Simulator', attribution: 'Attribution', history: 'History',
      tuning: 'Tuning', adjust: 'Adjust', data: 'Data', execution: 'Execution',
      system: 'System'
    },
    group: {
      decision: 'Decision', model: 'Model', data: 'Data', system: 'System',
      mask: 'Mask', masked: 'Masked', privacyTip: 'Privacy mask (press P)'
    },
    common: {
      online: 'ONLINE', live: 'LIVE', refresh: 'REFRESH', manual: 'MANUAL',
      symbol: 'SYMBOL', run: 'RUN', reset: 'RESET', analyze: 'ANALYZE',
      simulate: 'RUN SIMULATION', export: 'EXPORT CSV',
      generate: 'Generate PDF Weekly', download: 'Download Latest',
      apply: 'APPLY', loading: 'Loading...', noData: 'No Data',
      waiting: 'Waiting...', days: 'days', records: 'records',
      preset: 'PRESET', calculated: 'CALCULATED', current: 'CURRENT',
      // 提示文案
      clickRun: 'Click RUN to start backtest',
      clickSimulate: 'Click RUN SIMULATION to start',
      clickAnalyze: 'Click ANALYZE to start attribution',
      waitResult: 'Waiting for result',
      waitBacktest: 'Waiting for backtest result',
      waitSimulation: 'Waiting for simulation result',
      noDataShort: 'No data',
      noDataExport: 'No data to export',
      selectDateRange: 'Please select date range',
      tooFewData: 'Too few data points ({n}), please expand date range',
      backtestDone: 'Backtest done: {days} days, Sharpe {sharpe} ({usingReal}/{days} days with real positions)',
      simulationDone: 'Simulation done: {n} paths × {d} days, expected {expected}%',
      attributionDone: 'Attribution done: Alpha {alpha}% ({usingReal}/{total} days with real positions)',
      configReset: 'Config reset',
      invalidParams: 'Invalid parameters',
      exported: 'Exported {rows} rows',
      savedAt: 'Saved at {time}',
      searchDate: 'Search date...',
      selectStrategies: 'Select strategies from table above to compare',
      selectedRadar: '{n}/4 strategies selected for radar',
      selectEvent: 'Select event type to see window performance'
    },
    status: { sys: 'SYS', model: 'MODEL', data: 'DATA', regime: 'REGIME', position: 'POSITION', base: 'BASE', upd: 'UPD' },
    metric: {
      sharpe: 'SHARPE', maxDD: 'MAX DD', annualRet: 'ANNUAL RET', vol: 'VOL',
      win: 'WIN', calmar: 'CALMAR', cumRet: 'CUM RET', totalRet: 'TOTAL RET',
      acc: 'ACC', auc: 'AUC', ic: 'IC', dirAcc: 'DIR ACC', days: 'DAYS',
      decay: 'DECAY', features: 'FEATURES', alpha: 'ALPHA'
    },
    label: {
      goldPrice: 'Gold Price', regime: 'Regime', weightedProb: 'Integrated Prob',
      multiHorizon: 'Multi-Horizon', currentSignal: 'Current Signal',
      keyMetrics: 'Key Metrics', strategyNav: 'Strategy NAV',
      overfitCheck: 'Overfit Check', topFeatures: 'Top Features',
      positionHistory: 'Position History', alertsStream: 'Alerts Stream',
      active: 'ACTIVE', baseDate: 'Base Date', ma50: 'MA50', ma200: 'MA200',
      suggestion: 'Suggestion', vol60: 'VOL60', realRate: 'REAL RATE',
      dxy: 'DXY', vix: 'VIX', fomc: 'FOMC', cpi: 'CPI', vol20: 'VOL20',
      ma200pct: 'MA200%', date: 'DATE', type: 'TYPE', window: 'WINDOW',
      windowRet: 'WINDOW RET', strategy: 'STRATEGY', vsBh: 'VS BH',
      step: 'STEP', action: 'ACTION', target: 'TARGET', amount: 'AMOUNT',
      note: 'NOTE', hitRate: 'Hit Rate', wfBase: 'WF Base',
      deviation: 'Deviation', posFactor: 'Pos Factor', status: 'Status',
      circuit: 'Circuit Breaker', normal: 'Normal', capital: 'Capital',
      leverage: 'Leverage', position: 'Position', holdDays: 'Hold Days',
      paths: 'Paths', volSource: 'Vol Source', hisVol20d: '20D Hist Vol',
      hisVol60d: '60D Hist Vol', custom: 'Custom', drift: 'Drift (Daily Mean)',
      expectedPnl: 'Expected PnL', median: 'Median', var95: 'VaR 95%',
      ruinProb: 'Ruin Prob', maxGain: 'Max Gain', maxLoss: 'Max Loss',
      optimalPos: 'Optimal Pos', pathFan: 'Path Fan', finalNav: 'Final NAV Dist',
      stratTotal: 'Strategy Total', bhReturn: 'BH Return',
      alphaDecomp: 'Alpha Decomposition', allocation: 'Allocation',
      selection: 'Selection', interaction: 'Interaction',
      regimeBreakdown: 'Regime Breakdown', bullBearRange: 'Bull/Bear/Range',
      realCoverage: 'Real Coverage', holdingRatio: 'Holding Ratio',
      timeRange: 'Time Range', last7d: 'Last 7D', last30d: 'Last 30D',
      last90d: 'Last 90D', all: 'All', probTimeline: 'Probability Timeline',
      regimePosition: 'Regime & Position', mlDrift: 'ML Metrics Drift',
      sharpeHistory: 'Best Sharpe History', total: 'Total Runs', span: 'Span',
      latestSharpe: 'Latest Sharpe', latestHit: 'Latest Hit',
      icMedian: 'IC Median', stability: 'Stability', stable: 'STABLE',
      rollingMetrics: 'Rolling Metrics', stabilityAnalysis: 'Stability Analysis',
      trainWindow: 'Train Window', horizon: 'Label Horizon', purgeGap: 'Purge Gap',
      vifThreshold: 'VIF Threshold', vifMax: 'VIF Max', regimeWindow: 'Regime Window',
      autoAdaptive: 'Auto Adaptive', runV5: 'RUN V5', runResult: 'Run Result',
      stdoutLog: 'Stdout Log', stderr: 'Stderr', weeklyReport: 'Weekly Report',
      reportCycle: 'Report Cycle', reportContent: 'Report Content',
      outputPath: 'Output Path', marketView: 'Market View',
      positionAdj: 'Position Adj', leverageMult: 'Leverage Mult',
      useV5: 'Use V5 Real Positions', eventOverlay: 'Event Overlay',
      blackSwan: 'Black Swan', costComparison: 'Cost Comparison',
      costScenario: '3 Scenarios', executionPlan: 'Execution Plan',
      executionInst: 'Execution Instructions', signalQuality: 'Signal Quality',
      stopLoss: 'Stop Loss', takeProfit: 'Take Profit', volTarget: 'Vol Target',
      kelly: 'Kelly Fraction', regimeThreshold: 'Regime Threshold'
    },
    hint: {
      realPos: '✓ Real Positions + Brinson',
      realPosEv: '✓ Real Positions + Event Window',
      realPosBt: '✓ V5 Real Positions + Simplified Strategy dual mode',
      presetEvent: '⚠ Preset Estimate',
      template: '⚠ Operation Template',
      clickRun: 'Click RUN to start backtest',
      clickAnalyze: 'Click ANALYZE to start attribution',
      clickSimulate: 'Click SIMULATE to run Monte Carlo',
      waitResult: 'Waiting for result',
      waitLog: 'Waiting for log',
      noError: 'No errors',
      noMatches: 'No matches found',
      cmdHint: 'Type command or Tab name...',
      needBackend: 'Backend required (file:// protocol)',
      useBackend: 'Start api_server.py to use',
      noSaved: 'No saved data'
    }
  },

  zh: {
    nav: {
      wall: '监控墙', overview: '总览', factors: '因子分析', backtest: '策略回测',
      backtestHub: '回测中心',
      compare: '策略对比', versions: '版本对比', walkforward: 'Walk-Forward',
      validation: '过拟合验证', custombt: '信号回测', eventbt: '事件回测',
      simulator: '仓位模拟器', attribution: '资金归因', history: '历史趋势',
      tuning: '参数调优', adjust: '人工调整', data: '数据管理', execution: '执行方案',
      system: '系统状态'
    },
    common: {
      online: 'ONLINE', live: 'LIVE', refresh: 'REFRESH', manual: 'MANUAL',
      symbol: 'SYMBOL', run: 'RUN', reset: 'RESET', analyze: 'ANALYZE',
      simulate: 'RUN SIMULATION', export: '导出 CSV',
      generate: '生成 PDF 周报', download: '下载最近一份',
      apply: '应用调整', loading: '加载中...', noData: '无数据',
      waiting: '等待...', days: '天', records: '条记录',
      preset: 'PRESET', calculated: 'CALCULATED', current: 'CURRENT',
      // 提示文案
      clickRun: '点击 RUN 开始回测',
      clickSimulate: '点击 RUN SIMULATION 开始模拟',
      clickAnalyze: '点击 ANALYZE 开始归因分析',
      waitResult: '等待结果',
      waitBacktest: '等待回测结果',
      waitSimulation: '等待模拟结果',
      noDataShort: '无数据',
      noDataExport: '无数据可导出',
      selectDateRange: '请选择日期范围',
      tooFewData: '数据点太少 ({n})，请扩大日期范围',
      backtestDone: '回测完成：{days} 天，夏普 {sharpe}（{usingReal}/{days} 天用真实仓位）',
      simulationDone: '模拟完成：{n} 路径 × {d} 天，期望 {expected}%',
      attributionDone: '归因完成：Alpha {alpha}%（{usingReal}/{total} 天用真实仓位）',
      configReset: '配置已重置',
      invalidParams: '参数无效',
      exported: '已导出 {rows} 行数据',
      savedAt: '已保存 {time}',
      searchDate: '搜索日期...',
      selectStrategies: '从上表勾选策略以对比',
      selectedRadar: '已选 {n}/4 策略做雷达叠加',
      selectEvent: '选择事件类型查看窗口表现'
    },
    status: { sys: 'SYS', model: 'MODEL', data: 'DATA', regime: 'REGIME', position: 'POSITION', base: 'BASE', upd: 'UPD' },
    metric: {
      sharpe: 'SHARPE', maxDD: 'MAX DD', annualRet: 'ANNUAL RET', vol: 'VOL',
      win: 'WIN', calmar: 'CALMAR', cumRet: 'CUM RET', totalRet: 'TOTAL RET',
      acc: 'ACC', auc: 'AUC', ic: 'IC', dirAcc: 'DIR ACC', days: 'DAYS',
      decay: 'DECAY', features: 'FEATURES', alpha: 'ALPHA'
    },
    label: {
      goldPrice: 'Gold Price', regime: 'Regime', weightedProb: 'Integrated Prob',
      multiHorizon: 'Multi-Horizon', currentSignal: 'Current Signal',
      keyMetrics: 'Key Metrics', strategyNav: 'Strategy NAV',
      overfitCheck: 'Overfit Check', topFeatures: 'Top Features',
      positionHistory: 'Position History', alertsStream: 'Alerts Stream',
      active: 'ACTIVE', baseDate: 'Base Date', ma50: 'MA50', ma200: 'MA200',
      suggestion: 'Suggestion', vol60: 'VOL60', realRate: 'REAL RATE',
      dxy: 'DXY', vix: 'VIX', fomc: 'FOMC', cpi: 'CPI', vol20: 'VOL20',
      ma200pct: 'MA200%', date: 'DATE', type: 'TYPE', window: 'WINDOW',
      windowRet: 'WINDOW RET', strategy: 'STRATEGY', vsBh: 'VS BH',
      step: 'STEP', action: 'ACTION', target: 'TARGET', amount: 'AMOUNT',
      note: 'NOTE', hitRate: 'Hit Rate', wfBase: 'WF Base',
      deviation: 'Deviation', posFactor: 'Pos Factor', status: 'Status',
      circuit: 'Circuit Breaker', normal: 'Normal', capital: 'Capital',
      leverage: 'Leverage', position: 'Position', holdDays: 'Hold Days',
      paths: 'Paths', volSource: 'Vol Source', hisVol20d: '20D Hist Vol',
      hisVol60d: '60D Hist Vol', custom: 'Custom', drift: 'Drift (Daily Mean)',
      expectedPnl: 'Expected PnL', median: 'Median', var95: 'VaR 95%',
      ruinProb: 'Ruin Prob', maxGain: 'Max Gain', maxLoss: 'Max Loss',
      optimalPos: 'Optimal Pos', pathFan: 'Path Fan', finalNav: 'Final NAV Dist',
      stratTotal: 'Strategy Total', bhReturn: 'BH Return',
      alphaDecomp: 'Alpha Decomposition', allocation: 'Allocation',
      selection: 'Selection', interaction: 'Interaction',
      regimeBreakdown: 'Regime Breakdown', bullBearRange: 'Bull/Bear/Range',
      realCoverage: 'Real Coverage', holdingRatio: 'Holding Ratio',
      timeRange: 'Time Range', last7d: 'Last 7D', last30d: 'Last 30D',
      last90d: 'Last 90D', all: 'All', probTimeline: 'Probability Timeline',
      regimePosition: 'Regime & Position', mlDrift: 'ML Metrics Drift',
      sharpeHistory: 'Best Sharpe History', total: 'Total Runs', span: 'Span',
      latestSharpe: 'Latest Sharpe', latestHit: 'Latest Hit',
      icMedian: 'IC Median', stability: 'Stability', stable: 'STABLE',
      rollingMetrics: 'Rolling Metrics', stabilityAnalysis: 'Stability Analysis',
      trainWindow: 'Train Window', horizon: 'Label Horizon', purgeGap: 'Purge Gap',
      vifThreshold: 'VIF Threshold', vifMax: 'VIF Max', regimeWindow: 'Regime Window',
      autoAdaptive: 'Auto Adaptive', runV5: 'RUN V5', runResult: 'Run Result',
      stdoutLog: 'Stdout Log', stderr: 'Stderr', weeklyReport: 'Weekly Report',
      reportCycle: 'Report Cycle', reportContent: 'Report Content',
      outputPath: 'Output Path', marketView: 'Market View',
      positionAdj: 'Position Adj', leverageMult: 'Leverage Mult',
      useV5: 'Use V5 Real Positions', eventOverlay: 'Event Overlay',
      blackSwan: 'Black Swan', costComparison: 'Cost Comparison',
      costScenario: '3 Scenarios', executionPlan: 'Execution Plan',
      executionInst: 'Execution Instructions', signalQuality: 'Signal Quality',
      stopLoss: 'Stop Loss', takeProfit: 'Take Profit', volTarget: 'Vol Target',
      kelly: 'Kelly Fraction', regimeThreshold: 'Regime Threshold'
    },
    hint: {
      realPos: '✓ 真实仓位 + Brinson 分解',
      realPosEv: '✓ 真实仓位 + 事件窗口',
      realPosBt: '✓ V5 真实仓位 + 简化策略双模式',
      presetEvent: '⚠ 预设影响估算',
      template: '⚠ 操作模板',
      clickRun: '点击 RUN 开始回测',
      clickAnalyze: '点击 ANALYZE 开始归因分析',
      clickSimulate: '点击 SIMULATE 运行蒙特卡洛',
      waitResult: '等待结果',
      waitLog: '等待日志',
      noError: '无错误',
      noMatches: '无匹配结果',
      cmdHint: '输入命令或 Tab 名（如：监控墙 / RUN 回测 / 切标的）...',
      needBackend: '需启动后端（file://协议）',
      useBackend: '请启动 api_server.py 后使用',
      noSaved: '无保存数据'
    }
  }
}

const savedLang = typeof localStorage !== 'undefined' ? (localStorage.getItem('gold-cmd-lang') || 'zh') : 'zh'

export const i18n = createI18n({
  legacy: false,
  locale: savedLang,
  fallbackLocale: 'en',
  messages
})

export function setLang(lang: 'en' | 'zh') {
  i18n.global.locale.value = lang
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('gold-cmd-lang', lang)
  }
}

export function getLang(): 'en' | 'zh' {
  return i18n.global.locale.value as 'en' | 'zh'
}
