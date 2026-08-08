# GOLD COMMAND V6 — Vue3 + ArcoDesign Dashboard

> 黄金多因子预测命令中心 · 单 HTML 文件可离线运行 · 17 Tab · FastAPI 后端 · SQLite 持久化 · PWA

## 快速开始

### 单文件成品（开箱即用）

直接双击 `dashboard-vue3.html` 即可在浏览器打开。所有 JS/CSS/数据已内联，无需后端。

### 开发模式

```bash
cd dashboard-vue3
npm install
npm run dev          # http://localhost:5173
npm run build        # 输出到 dist/
PYTHONPATH=../src python3 inject_data.py   # 把 JSON + drift_history 内联到 dist/index.html
```

### 后端 API（可选，启用实时数据 + WS + PDF + 飞书）

```bash
bash ../scripts/start_api.sh start   # 或 PYTHONPATH=src python3 -m gold_model.api_server
```

前端自动探测同源的 `/api/health`：在线显示 `API:ON`（实时数据 + SQLite 历史），离线回退内联静态数据，无需手动配置。

## 文件结构

```
dashboard-vue3/
├── dashboard-vue3.html         # 单文件成品（2.5MB，离线可用）
├── index.html                  # Vite 入口模板
├── vite.config.ts              # Vite + vite-plugin-singlefile 配置
├── package.json
├── inject_data.py              # JSON 内联到 dist 的脚本
├── public/
│   ├── dashboard_data.json     # V5 脚本输出的全量数据
│   ├── execution_data.json     # 执行方案 + 仓位历史
│   ├── manifest.json           # PWA manifest
│   └── sw.js                   # Service Worker
└── src/
    ├── main.ts                 # 应用入口 + SW 注册
    ├── App.vue                 # 根布局 + 17 Tab + Ctrl+K 命令面板
    ├── styles/theme.css        # ArcoDesign 主题覆盖（V7 暖金晨报）
    ├── composables/
    │   └── useDashboardData.ts # 数据加载 + WS + 轮询 + API
    ├── components/
    │   ├── ChartBox.vue        # ECharts 公共组件（watchEffect 自动追踪）
    │   ├── CmdPalette.vue      # Ctrl+K 命令面板
    │   ├── HudCard.vue         # HUD 卡片（角标）
    │   ├── MetricCard.vue      # 指标卡
    │   ├── ProbBars.vue        # 概率条
    │   ├── InfoIcon.vue        # 信息图标（Popover）
    │   ├── TheNavbar.vue      # 顶部命令栏 + 多标的切换
    │   └── TheStatusBar.vue   # 状态栏 + WS 状态 + 时间戳
    └── views/                  # 17 个 Tab 视图
        ├── WallView.vue              # 1. 监控墙（大屏 6 单元 + 告警流）
        ├── OverviewView.vue          # 2. 总览
        ├── FactorsView.vue           # 3. 因子分析
        ├── BacktestView.vue          # 4. 策略回测（8 策略对比）
        ├── CompareView.vue           # 5. 策略对比（多选叠加）
        ├── ModelVersionsView.vue     # 6. 版本对比（V1→V3.0-E 演进）
        ├── WalkForwardView.vue       # 7. Walk-Forward 可视化
        ├── ValidationView.vue        # 8. 过拟合验证（Holdout 6 列）
        ├── BacktestCustomView.vue    # 9. 信号回测（+5 参数：止损/止盈/Kelly/Vol/Regime）
        ├── EventBacktestView.vue    # 10. 事件回测（FOMC/CPI/Regime 切换）
        ├── SimulatorView.vue         # 11. 仓位模拟器（蒙特卡洛 1000 路径）
        ├── AttributionView.vue      # 12. 资金归因（Brinson 三因素）
        ├── HistoryView.vue           # 13. 历史趋势（prob/ML/sharpe 4 折线）
        ├── TuningView.vue            # 14. 参数调优（V5 6 参数）
        ├── AdjustView.vue           # 15. 人工调整（localStorage 持久化）
        ├── DataView.vue              # 16. 数据管理（250 日表 + CSV 导出）
        └── ExecutionView.vue         # 17. 执行方案（4 步指令 + PDF 周报按钮）
```

## 17 Tab 功能矩阵

| # | Tab | Canvas | 关键功能 |
|---|-----|--------|---------|
| 1 | 监控墙 | 4 | 信号 + 周K线 + 6指标 + 告警流（6 类告警） |
| 2 | 总览 | 2 | 状态卡 + 概率条 + Holdout 三联 |
| 3 | 因子分析 | 1 | TOP10 特征 + 当前快照 12 因子 |
| 4 | 策略回测 | 3 | 8 策略表 + NAV/回撤/雷达 |
| 5 | 策略对比 | 2 | 多选叠加 + 5 指标切换 + 雷达 |
| 6 | 版本对比 | 2 | V1→V3.0-E 演进 + 多因子雷达 |
| 7 | Walk-Forward | 3 | 4 horizon 折线 + 夏普历史 + 命中率对比 |
| 8 | 过拟合验证 | 1 | Holdout 6 列 + 诊断 3 原因 |
| 9 | 信号回测 | 2 | 60天回测 + 5 新参数（止损/止盈/Kelly/Vol/Regime） |
| 10 | 事件回测 | 1 | FOMC/CPI/Regime 切换 4 类事件窗口 |
| 11 | 仓位模拟器 | 2 | 蒙特卡洛 1000 路径 + 95% 置信扇形 + 直方图 |
| 12 | 资金归因 | 2 | Brinson 三因素 + Regime 分布 |
| 13 | 历史趋势 | 4 | prob/regime/ML/sharpe 4 折线 |
| 14 | 参数调优 | 0 | V5 6 参数表单 + 运行日志 |
| 15 | 人工调整 | 0 | Slider + localStorage 持久化 |
| 16 | 数据管理 | 0 | 9 列 250 日表 + 搜索 + CSV 导出 |
| 17 | 执行方案 | 2 | 4 步指令 + 资金规模切换 + PDF 周报按钮 |

**全局功能**：Ctrl+K 命令面板 / 17 Tab 快速跳转 / WS 实时推送 / PWA 离线缓存

## 后端 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 + 数据加载状态 |
| `/api/state` | GET | 全量 dashboard + execution 数据 |
| `/api/history?days=N&regime=X` | GET | 历史信号（按 Regime 过滤） |
| `/api/drift` | GET | 漂移快照 |
| `/api/strategies` | GET | 策略列表 |
| `/api/signals/recent?limit=N` | GET | 最近 N 次信号变化 |
| `/api/db/ingest` | POST | 把当前 dashboard 写入 SQLite |
| `/api/db/history?days=N&regime=X&action=Y` | GET | SQLite 历史信号查询 |
| `/api/db/alerts?days=N&alert_type=X` | GET | 历史告警查询 |
| `/api/db/stats` | GET | 数据库统计 |
| `/api/symbols` | GET | 列出 4 标的（GOLD/SILVER/COPPER/BTC） |
| `/api/symbol/{sym}?days=N` | GET | 拉取标的简化数据（GOLD 全量，其他 yfinance） |
| `/api/report/weekly` | GET | 生成 PDF 周报 |
| `/api/push/feishu` | POST | 推送信号到飞书群 |
| `/api/alerts/subscribe` | POST | 注册告警 webhook |
| `/api/alerts/subscribers` | GET | 列出告警订阅者 |
| `/api/alerts/subscribe?url=X` | DELETE | 取消告警订阅 |
| `/api/v5/run` | POST | 以指定参数跑 V5 脚本 |
| `/ws` | WS | WebSocket 实时推送 |

## cron 任务

| 任务 | 调度 | 推送渠道 | 说明 |
|------|------|---------|------|
| V5 每日运行 + ingest | 周一~五 08:00 (Asia/Shanghai) | 清言 | 跑 V5 脚本 + 写入 SQLite |

## 数据契约

### dashboard_data.json（V5 脚本输出）
- `overview` — 当前状态（金价/Regime/概率/建议）
- `strategies` — 8 策略对比表
- `features` — 特征重要性 TOP12
- `ml_models` — 4 horizon ML 指标
- `current_factors` — 当前因子快照
- `raw_data` — 60 日历史数据
- `v5_holdout` — Holdout 6 月验证
- `v5_regression` — 回归分支 R²/方向准确率
- `v5_feature_count` / `v5_original_feature_count`

### execution_data.json
- `current` — 当前仓位/Regime/概率
- `scenarios` — 3 场景（牛市/熊市/震荡）
- `execution_rules` — 4 步执行指令
- `signal_stats` — 命中率/WF 基准/偏差/仓位系数
- `cost_comparison` — 4 资金规模 × 3 场景成本
- `position_history` — 250 日仓位历史

### drift_history.json（drift_monitor.py 输出）
- 18 条历史快照，每条含：timestamp / ml_metrics / feature_importance_top10 / regime_distribution / current_state / prob_stats / best_sharpe / signal_backtest

## 部署

### 生产环境（用户本地）

1. **前端**：直接打开 `dashboard-vue3.html`（数据已内联，离线可用）
2. **后端**（可选）：
   ```bash
   pip install fastapi uvicorn yfinance
   python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000
   ```
3. **飞书机器人**：
   ```bash
   export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
   export FEISHU_WEBHOOK_SECRET=xxx  # 可选，签名验证
   ```
4. **PWA 安装**：浏览器地址栏右侧"安装"按钮，可装为桌面应用

### 数据流

```
V5 脚本 (gold_factor_v5.py)
  ↓ 输出 dashboard_data.json + execution_data.json
drift_monitor.py
  ↓ 输出 drift_history.json
inject_data.py
  ↓ 内联到 dist/index.html (window.__DASHBOARD_DATA__ 等)
前端 Vue3 应用
  ↓ file:// 协议：直接读 window 全局
  ↓ http:// 协议：fetch + 30s 轮询 + WS 实时推送
用户浏览器
```

## 已知限制

- **沙箱环境**：yfinance 实时拉取超时（F 多标的）/ WebSocket 本地连接被拒 / 这些在生产环境（用户本地）可用
- **V5 脚本参数化**：当前 V5 脚本不支持命令行参数，调优界面通过环境变量传入（脚本需小改读取环境变量）
- **多标的接入**：只 GOLD 跑了完整 V5 模型，其他标的（SILVER/COPPER/BTC）只有简化版数据（价格+MA+Regime），未跑 ML 模型
- **告警 webhook**：内存存储（重启失效），生产应改用 SQLite alerts 表

## 后续方向

- **数据层**：接入新闻情绪（FinBERT）/ 黄金 ETF 持仓 / 央行购金数据
- **模型层**：V5 支持 Regime-conditional 训练窗口 + 多市场状态数据增强
- **部署**：Docker 容器化 + nginx 反向代理 + Let's Encrypt
- **监控**：Prometheus + Grafana 监控 API 健康/SQLite 大小/前端访问量

## 技术栈

- **前端**：Vue 3.5 + Vite 6 + ArcoDesign 2.57 + ECharts 5.5 + vite-plugin-singlefile
- **后端**：FastAPI + uvicorn + SQLite + yfinance
- **PDF**：ReportLab + NotoSerifSC 字体
- **PWA**：manifest.json + Service Worker（双缓存策略）
- **字体**：JetBrains Mono / SF Mono / Noto Serif SC

## 主题色（V7 暖金晨报）

- 背景：`#0e0f11` 暖石墨
- 主色/金价：`#d9a648` 暖金（高光 `#eec170`）
- 正值：`#45b789` 柔绿
- 负值：`#cf6b62` 柔红
- 警告：`#eec170` 金杏

---

生成时间：2026-08-06
版本：V6.0 (Vue3 + ArcoDesign)
作者：Z.AI
