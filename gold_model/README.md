# gold_model — 黄金多因子预测模型 V4

数据采集（yfinance + FRED）→ 特征工程（35+ 因子）→ XGBoost/LightGBM 集成 → Regime 仓位策略 → 信号告警 / 漂移监控 → Dashboard 与 PDF 报告。

## 安装

```bash
cd gold_model
pip install -e .          # 或 pip install -e ".[pdf]"（含封面渲染 playwright）
# macOS 前置：brew install libomp（xgboost/lightgbm 依赖）
# 中国大陆网络建议加镜像：-i https://pypi.tuna.tsinghua.edu.cn/simple
```

不安装也可用 `PYTHONPATH=src` 直接运行下文所有 `python3 -m ...` 命令。

## 目录结构

```
gold_model/
├── pyproject.toml
├── src/gold_model/            # Python 包
│   ├── paths.py               # 统一路径配置（所有模块的路径入口）
│   ├── gold_factor_v4.py      # 主管道：采集→建模→图表→JSON输出
│   ├── data_fetcher.py        # 多源数据 fallback（yfinance→新浪→东财→腾讯外汇→FRED→代理因子）
│   ├── fomc_calendar.py       # FOMC 议息日历（多级fallback+缓存）
│   ├── cpi_calendar.py        # CPI 发布日历（多级fallback+缓存）
│   ├── signal_alert.py        # 异常信号检测（Regime切换/仓位变化/概率穿越）
│   ├── drift_monitor.py       # 模型漂移监控（7类漂移检测）
│   ├── diagnosis_hitrate.py   # 命中率诊断
│   ├── web_server.py          # 本地 Dashboard 静态服务器
│   └── execution_plan/        # 仓位管理方案与 PDF 报告生成
│       ├── signal_analysis.py
│       ├── generate_charts.py
│       ├── generate_cover.py  # 需 playwright
│       ├── generate_pdf.py
│       └── assets/cover.html
├── web/                       # 前端 Dashboard（index.html + JSON 数据）
├── data/                      # 缓存与状态（fomc_cache / cpi_cache / drift_history / signal_alert_state）
├── outputs/                   # 生成物（charts_v4 / execution_plan / reports）
└── docs/
```

## 常用命令

```bash
python3 -m gold_model.gold_factor_v4            # 跑主管道（需联网，约2-3分钟）
python3 -m gold_model.signal_alert              # 检测异常信号（--dry-run 测试格式）
python3 -m gold_model.drift_monitor             # 漂移检测（--verbose 详细输出）
python3 -m gold_model.web_server 8000           # 启动 Dashboard → http://127.0.0.1:8000
python3 -m gold_model.execution_plan.signal_analysis   # 仓位方案分析（→ analysis.json）
python3 -m gold_model.execution_plan.generate_charts   # 方案图表
python3 -m gold_model.execution_plan.generate_pdf      # 方案正文 PDF
python3 -m gold_model.execution_plan.generate_cover    # 方案封面 PDF（playwright）
python3 -m gold_model.execution_plan.merge_pdf         # 合并封面+正文 → 最终方案PDF
```

## 定时任务（launchd）

`scripts/daily_signal_check.sh` 每日跑主管道+信号告警，有告警时弹 macOS 通知：

```bash
python3 -m venv .venv && .venv/bin/pip install -e .     # 首次：主管道依赖装进 .venv
bash scripts/install_launchd.sh                          # 注入项目路径并加载（周二~六 22:30）
```

日志在 `logs/`（按天滚动）。卸载：`bash scripts/install_launchd.sh --uninstall`。

## 冒烟测试

```bash
pip install -e ".[dev]"                                   # 含 pytest
PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q      # 8 个用例：paths/日历/JSON契约/采集链
```

## 约定

- 所有路径集中在 `src/gold_model/paths.py`，**不要在脚本里写绝对路径**。
- 前端只读 `web/` 下的 `dashboard_data.json` / `execution_data.json`，由主管道写入。
- `data/` 下的缓存与状态文件是跨运行的状态，改管道代码时保持其 schema 兼容。
- 图表与报告输出到 `outputs/`，可随时删除重建。
