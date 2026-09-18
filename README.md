# 黄金多因子预测模型（Gold Model）

基于多因子 + 机器学习的黄金价格预测与仓位决策系统：每日自动采集行情与宏观数据，训练集成模型输出上涨概率与建议仓位，并通过 Vue3 仪表盘、PDF 报告、macOS 通知 / 飞书机器人分发结果。

**管道链路**：数据采集（八层 fallback）→ 特征工程（VIF 共线性剔除）→ XGBoost/LightGBM 集成（Purged K-fold + Holdout 纯净验证）→ Regime 仓位策略 → SQLite 持久化 → Vue3 Dashboard / FastAPI / PDF 周报。

## 快速开始

```bash
cd gold_model
python3 -m venv .venv && .venv/bin/pip install -e ".[api,dev]"
bash scripts/start_api.sh start        # 启动 API + 前端 → http://127.0.0.1:8000/dashboard-vue3.html
```

跑最新预测（需联网，约 5-8 分钟）：

```bash
PYTHONPATH=src .venv/bin/python3 -m gold_model.gold_factor_v5
```

## 文档

- `gold_model/README.md` — 完整安装、开发、测试、部署指南
- `gold_model/docs/预测逻辑流程.md` — 预测逻辑流程图与解释（核心知识文件）
- `gold_model/docs/ARCHITECTURE.md` — 架构笔记
- `gold_model/dashboard-vue3/README.md` — 前端 17 个 Tab 功能矩阵与 API 接口表

## 许可

代码公开供学习与研究参考；未附开源许可证（保留所有权利），转载或二次使用请注明出处。
