# ARCHITECTURE.md — GOLD COMMAND V6 架构决策

## 1. 为什么选 Vue3 + ArcoDesign

**用户要求**：v6 版本前端页面使用 vue3+arcodesign 重新实现。原 V5 是单 HTML + 原生 JS（2226 行），组件化困难。

**选型理由**：
- Vue3 Composition API + script setup → 组件逻辑清晰
- ArcoDesign 字节跳动出品，Vue3 原生支持，组件丰富（Table/Slider/Radio/DatePicker/Popover）
- Vite 构建快，HMR 友好
- ECharts 不用 vue-echarts 封装，直接用（避免额外抽象层）

## 2. 为什么用 vite-plugin-singlefile 打包成单 HTML

**问题**：agent-browser（沙箱浏览器）不能访问 127.0.0.1，只能用 file:// 协议。但 ES module 在 file:// 下被 Chrome 拦截。

**解决**：
- `vite-plugin-singlefile` 把所有 JS/CSS inline 到 index.html
- `inject_data.py` 把 JSON 数据也内联到 window 全局
- file:// 协议下：fetch 失败 → 回退 window 全局 → 数据正常加载

**好处**：单 HTML 离线可用，PWA 友好，部署简单（一个文件）。

## 3. ChartBox 公共组件设计

**问题**：14+ 个图表，每个 View 手写 echarts.init/setOption/dispose/resize 样板代码太多。

**设计**：
```vue
<ChartBox :option="xxxOpt" height="380px" />
```
- prop `option` 是**函数**（不是 computed），返回 EChartsOption
- `watchEffect({ flush: 'post' })` 自动追踪 option 函数内部访问的响应式数据
- 数据变化 → option 重新调用 → setOption 自动更新
- onMounted init + resize listener，onUnmounted dispose

**坑**：option 必须是函数，不能是 computed。computed 返回对象，watchEffect 调用 `props.option()` 会报错。

## 4. 数据加载三层 fallback

```ts
async function loadAll() {
  // 1. 优先 fetch（http(s):// 协议）
  // 2. 失败回退 window.__DASHBOARD_DATA__（file:// 协议，由 inject_data.py 注入）
  // 3. 最终 fallback 空数据
}
```

**好处**：
- http(s):// 模式下：30s 轮询 + WS 实时推送
- file:// 模式下：内联数据，离线可用
- 切换无缝

## 5. 主题覆盖策略

ArcoDesign 默认蓝色主题，与 V6 深黑霓虹青风格冲突。

**策略**：
- `theme.css` 用 CSS 变量覆盖 ArcoDesign 主题变量
- 自定义组件（HudCard / MetricCard 等）用 CSS 变量
- ECharts 配色硬编码（不通过 CSS 变量，因为 canvas 不支持）

**关键变量**：
```css
--bg: #04060a;
--accent: #00d4ff;
--pos: #00ff9c;
--neg: #ff3860;
```

## 6. SQLite 数据层设计

**signals 表**（22 字段）：
- run_at / base_date / gold_price / regime / position / weighted_prob
- prob_5d/10d/20d/60d / v3e_sharpe/max_dd/annual_ret/win_rate
- holdout_sharpe/decay / signal_action / hit_rate_20d/wf_base/pos_factor
- dashboard_json / execution_json（全量 JSON 备份）

**parse_pct 智能解析**：
- `"59.6%"` → 0.596（带 % 除 100）
- `"2.44"` → 2.44（纯数字保持）
- `"-6.9%"` → -0.069

**坑**：最初用 `abs(n) > 1.5` 判断是否百分数，导致夏普 2.44 被误除 100。改为只对带 % 的字符串除 100。

## 7. cron 任务设计

**任务**：每周一~五 08:00（Asia/Shanghai）跑 V5 + ingest SQLite
- 必须显式设 `tz: 'Asia/Shanghai'`，否则按 UTC 解读
- 周一~五（工作日），周末不跑
- prompt 含执行命令 + 关键结果报告 + 异常处理

**ingest_current.py 独立脚本**：
- 不依赖 FastAPI 服务运行
- cron 直接 python3 调用
- 写入 SQLite + 打印结果

## 8. PDF 周报设计

**ReportLab + NotoSerifSC**：
- 不用 NotoSansSC（可变字体，ReportLab 报 struct.error）
- 不用 html2pdf（Playwright 在沙箱不稳定）
- 5 页结构：封面 + 策略 + ML + 特征 + 告警

## 9. 多标的接入策略

**GOLD**：走完整 V5 数据（dashboard_data.json）
**其他**（SILVER/COPPER/BTC）：yfinance 实时拉 + 计算 MA/Regime

**简化原因**：
- V5 模型为黄金定制（DXY/实际利率/金矿等因子），其他标的不适用
- 跑完整 V5 需要重新设计特征空间，工程量大
- 简化版提供价格 + Regime，足够做基础判断

## 10. 命令面板（Ctrl+K）设计

**触发**：Ctrl+K / Cmd+K 全局快捷键
**分类**：TAB / RUN / EXPORT / SYMBOL / REFRESH
**模糊匹配**：输入"监控" → 显示"切换到 监控墙"

**实现**：
- App.vue 加 keydown 监听
- CmdPalette.vue 组件独立
- emit 事件回传命令，App.vue handleCommand 分发

## 11. 资金归因（Brinson 三因素）

**分解**：
- 配置效应（Regime择时）：根据 Regime 切换仓位带来的超额
- 选股效应（实际vs理论仓位）：实际仓位 vs 满仓的差异
- 交互效应（共同影响）：两者协同的额外收益

**基准**：买入持有（仓位恒定 1.0）

**公式**：
- Alpha = 策略总收益 - BH 收益
- 配置效应 = Σ (实际仓位 - 基准仓位) × 金价日收益
- 选股效应 = Σ 基准仓位 × (实际日收益 - 金价日收益)
- 交互效应 = Alpha - 配置 - 选股

## 12. 已知技术债

- [ ] V5 脚本不支持命令行参数（调优界面通过环境变量，需脚本小改）
- [ ] 告警 webhook 内存存储（重启失效，应改 SQLite alerts 表）
- [ ] 多标的（SILVER/COPPER/BTC）只有简化数据，未跑 ML 模型
- [ ] Walk-Forward 视图复用 drift_history，没有真正的 WF 滚动窗口数据
- [ ] 事件回测的事件类型有限（只有 FOMC/CPI/Regime 切换），缺非农/地缘事件
- [ ] 移动端未优化（大屏优先，单列堆叠未实现）
- [ ] 主题色未做切换（青/紫/绿/橙 4 套 HUD 配色未实现）

---

最后更新：2026-08-06
