# gold_model — 黄金多因子预测模型 V5

数据采集（八层 fallback）→ 特征工程（VIF 共线性剔除）→ XGBoost/LightGBM 集成（Purged K-fold + Holdout 纯净验证）→ Regime 仓位策略 → SQLite 持久化 → Vue3 Dashboard + FastAPI 后端 + PDF 报告 + 信号告警。

V5 相对 V4 的建模改进：VIF 共线性剔除（41→25-30 特征）、最近 6 月 Holdout 纯净 OOS 验证、Regime-aware 自适应训练窗口（高波动 250 日/低波动 500 日）、Purged K-fold（gap=10 消除标签泄漏）、收益幅度回归分支。V4 主管道保留为 `gold_factor_v4.py` 参考。

## 功能概览

- **每日预测**：上涨概率（5/10/20/60 日）、Regime 判定（牛/熊/震荡）、建议仓位与 4 步执行指令
- **Vue3 仪表盘**：17 个 Tab（监控墙/回测/事件分析/蒙特卡洛模拟/资金归因等），支持中英文、离线单文件、API 实时模式
- **报告与告警**：PDF 周报、仓位管理方案 PDF、异常信号 macOS 通知、飞书机器人推送
- **运维监控**：模型漂移监控（7 类检测）、命中率诊断、SQLite 历史信号库

## 安装

```bash
cd gold_model
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev]"   # api=FastAPI 后端, dev=pytest；再加 pdf 含 playwright 封面渲染
# macOS 前置：brew install libomp（xgboost/lightgbm 依赖）
# 中国大陆网络建议加镜像：-i https://pypi.tuna.tsinghua.edu.cn/simple
```

不安装也可用 `PYTHONPATH=src` 直接运行下文所有 `python3 -m ...` 命令。前端开发另需 Node.js 18+。

## 目录结构

```
gold_model/
├── pyproject.toml
├── src/gold_model/            # Python 包
│   ├── paths.py               # 统一路径配置（所有模块的路径入口）
│   ├── gold_factor_v5.py      # V5 主管道：采集→建模→Holdout验证→图表→JSON→public/同步→SQLite直写
│   ├── gold_factor_v4.py      # V4 参考备份
│   ├── data_fetcher.py        # 多源数据 fallback（yfinance→新浪→东财→新浪期货→腾讯外汇→CBOE→FRED→代理因子）
│   ├── fomc_calendar.py       # FOMC 议息日历（多级fallback+缓存）
│   ├── cpi_calendar.py        # CPI 发布日历（多级fallback+缓存）
│   ├── signal_alert.py        # 异常信号检测（Regime切换/仓位变化/概率穿越/V5 Holdout摘要）
│   ├── drift_monitor.py       # 模型漂移监控（7类漂移检测）
│   ├── diagnosis_hitrate.py   # 命中率诊断
│   ├── api_server.py          # FastAPI 后端（/api/state /api/db/history /ws 等，自带 web/ 静态托管）
│   ├── db.py                  # SQLite 历史信号持久化（gold_signals.db）
│   ├── ingest_current.py      # [已弃用] V5 已直写 SQLite，仅作失败时的手动 fallback
│   ├── weekly_report.py       # PDF 周报生成器（ReportLab）
│   ├── send_to_feishu.py      # 飞书机器人推送（webhook 走环境变量）
│   ├── web_server.py          # 纯静态 Dashboard 服务器（无 API 的轻量方案）
│   └── execution_plan/        # 仓位管理方案与 PDF 报告生成
│       ├── signal_analysis.py / generate_charts.py / generate_pdf.py
│       ├── generate_cover.py  # 需 playwright
│       └── assets/cover.html
├── dashboard-vue3/            # Vue3 + ArcoDesign 前端源码（Vite 构建，17 Tab，详见其 README）
├── web/                       # 前端产物与数据（dashboard-vue3.html 单文件成品 / JSON 数据）
├── data/                      # 缓存与状态（fomc_cache / cpi_cache / drift_history / gold_signals.db / signal_alert_state）
├── outputs/                   # 生成物（charts_v5 / weekly_reports / execution_plan / reports）
├── scripts/                   # 运维脚本（每日任务 / launchd 安装 / API 启停）
├── tests/                     # pytest 冒烟测试
└── docs/                      # 文档（见下方「文档索引」）
```

## 文档索引

按角色选读：

| 角色 | 先读这份 | 这份讲什么 |
|---|---|---|
| **产品经理** | [`产品设计白皮书.md`](docs/产品设计白皮书.md) | 设计者视角：预测逻辑全链路、可靠程度（含实时指标诚实评估）、理论依据与参考文献、各节点数据来源、指标字典、演进史与弯路 |
| **终端用户** | [`用户使用说明书.md`](docs/用户使用说明书.md) | 不懂技术也能上手：每天 5 分钟决策流程、19 个 Tab 逐个讲解、核心指标速查表、FAQ、风险提示 |
| **开发者/继任者** | [`开发设计文档.md`](docs/开发设计文档.md) | 系统总纲：架构拓扑、前后端交互契约、八层数据源、模块清单、指标字典（含义+计算+来源）、构建部署、接手指南、已知陷阱 |

技术参考（按需查阅）：

| 文档 | 内容 |
|---|---|
| [`预测逻辑流程.md`](docs/预测逻辑流程.md) | ML 算法核心知识文件：mermaid 全链路 + 各阶段详解（数据/因子/标签/WF训练/集成/仓位/输出） |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 架构决策记录：为什么选 Vue3/单文件/Arco、ChartBox 设计、SQLite 层、Brinson 归因等 |
| [`功能点与问题清单.md`](docs/功能点与问题清单.md) | 功能全景 + 现存问题分级（P0/P1/P2）+ 预测价值诚实评估 |
| [`DASHBOARD_DESIGN.md`](docs/DASHBOARD_DESIGN.md) | 前端设计规范 |

## 运行与启动

### 1. 跑预测管道（数据生产者）

```bash
PYTHONPATH=src .venv/bin/python3 -m gold_model.gold_factor_v5   # 需联网，约 5-8 分钟
```

一次运行完成三件事：写 `web/*.json` → 同步 `dashboard-vue3/public/` → 直写 SQLite 历史库。

### 2. 启动前端 + API（推荐）

```bash
bash scripts/start_api.sh start     # 启动/重启；stop/status 同参
# → http://127.0.0.1:8000/dashboard-vue3.html
```

前端会自动探测 API：在线时状态栏显示 `API:ON`（实时数据 + WS 推送 + SQLite 历史），离线时回退到页面内联的静态数据。

### 3. 纯静态方式（无后端）

直接双击 `web/dashboard-vue3.html`（数据已内联，离线可用），或：

```bash
PYTHONPATH=src .venv/bin/python3 -m gold_model.web_server 8000
```

## 前端开发

```bash
cd dashboard-vue3
npm install
npm run dev          # 开发服 http://localhost:5173（读 public/ 下 JSON 或 API）
npm run build        # 单文件构建到 dist/index.html
PYTHONPATH=../src python3 inject_data.py            # 内联最新数据 + 复制 PWA 资源
cp dist/index.html ../web/dashboard-vue3.html       # 部署到 web/
```

日常数据刷新（不重新构建）用 `inject_data.py --refresh`，每日任务已自动执行。

## 常用命令

```bash
python3 -m gold_model.signal_alert              # 检测异常信号（--dry-run 测试格式）
python3 -m gold_model.drift_monitor             # 漂移检测（--verbose 详细输出）
python3 -m gold_model.weekly_report             # 生成 PDF 周报
python3 -m gold_model.send_to_feishu            # 推送信号到飞书（需 FEISHU_WEBHOOK_URL）
python3 -m gold_model.execution_plan.signal_analysis   # 仓位方案分析（→ analysis.json）
python3 -m gold_model.execution_plan.generate_charts   # 方案图表
python3 -m gold_model.execution_plan.generate_pdf      # 方案正文 PDF
python3 -m gold_model.execution_plan.generate_cover    # 方案封面 PDF（playwright）
python3 -m gold_model.execution_plan.merge_pdf         # 合并封面+正文 → 最终方案PDF
```

## 测试

```bash
PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q    # 8 个冒烟用例：paths/日历/JSON契约/采集链
```

改管道代码后另需验证：`python3 -m compileall -q src` 语法检查，并重跑主管道确认 `web/*.json`、图表、PDF 产物数值合理、中文渲染正常。

## 部署（每日自动运行）

`scripts/daily_signal_check.sh` 每日跑主管道 + 前端数据刷新 + 信号告警，有告警时弹 macOS 通知。由 launchd 驱动（周二~六 22:30）：

```bash
bash scripts/install_launchd.sh                  # 注入项目路径并加载
bash scripts/install_launchd.sh --uninstall      # 卸载
```

日志在 `logs/`（按天滚动）。飞书推送需设置环境变量 `FEISHU_WEBHOOK_URL`。

## 常见问题

- **东财/新浪接口限流或超时**：正常现象，`data_fetcher.py` 有八层 fallback 自动降级，日志会标注实际命中源。
- **yfinance 在中国大陆不可直连**：fallback 链会自动切到国内源，无需配置代理。
- **xgboost/lightgbm 报错 `libomp`**：macOS 先 `brew install libomp`。
- **前端显示旧数据**：纯静态模式读的是内联快照，跑主管道或 `inject_data.py --refresh` 后刷新；API 模式检查状态栏是否 `API:ON`。
- **PDF 中文乱码/方块**：中文字体链为 macOS `PingFang SC/STHeiti` → Linux `Noto Serif SC`，Linux 需装 Noto 中文字体。

## 约定

- 所有路径集中在 `src/gold_model/paths.py`，**不要在脚本里写绝对路径**。
- 前端只读 `web/` 下的 `dashboard_data.json` / `execution_data.json`，由主管道写入。
- `data/` 下的缓存与状态文件是跨运行的状态，改管道代码时保持其 schema 兼容。
- 图表与报告输出到 `outputs/`，可随时删除重建。
- 不要提交 API Key / Webhook 等凭据，一律走环境变量。
