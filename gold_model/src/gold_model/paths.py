#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一路径配置 — 所有模块从这里取路径，不再硬编码绝对路径"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent  # src/gold_model -> 项目根

DATA_DIR = PROJECT_ROOT / 'data'          # 缓存与状态（fomc_cache / drift_history 等）
WEB_DIR = PROJECT_ROOT / 'web'            # 前端 Dashboard 及其 JSON 数据
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'    # 所有生成的报告/图表
CHARTS_DIR = OUTPUTS_DIR / 'charts_v4'
CHARTS_V5_DIR = OUTPUTS_DIR / 'charts_v5'
WEEKLY_REPORTS_DIR = OUTPUTS_DIR / 'weekly_reports'
EXECUTION_PLAN_DIR = OUTPUTS_DIR / 'execution_plan'
REPORTS_DIR = OUTPUTS_DIR / 'reports'
VUE3_PUBLIC_DIR = PROJECT_ROOT / 'dashboard-vue3' / 'public'  # vite dev/build 静态资源目录

# 常用文件
FOMC_CACHE = DATA_DIR / 'fomc_cache.json'
CPI_CACHE = DATA_DIR / 'cpi_cache.json'
PRICE_CACHE = DATA_DIR / 'price_cache.csv'   # 合并后因子源数据缓存（采集全挂时回退用）
COT_CACHE_DIR = DATA_DIR / 'cot_cache'       # CFTC COT 年度压缩包解压缓存（按年）
DRIFT_HISTORY = DATA_DIR / 'drift_history.json'
SIGNAL_ALERT_STATE = DATA_DIR / 'signal_alert_state.json'
GOLD_SIGNALS_DB = DATA_DIR / 'gold_signals.db'
DASHBOARD_JSON = WEB_DIR / 'dashboard_data.json'
EXECUTION_JSON = WEB_DIR / 'execution_data.json'
REPORT_V5_XLSX = REPORTS_DIR / '黄金多因子分析报告_V5.xlsx'
EXECUTION_LATEST_JSON = OUTPUTS_DIR / 'execution_data_latest.json'
ANALYSIS_JSON = EXECUTION_PLAN_DIR / 'analysis.json'

ASSETS_DIR = PACKAGE_DIR / 'execution_plan' / 'assets'


def ensure_dirs():
    for d in (DATA_DIR, WEB_DIR, CHARTS_DIR, CHARTS_V5_DIR, WEEKLY_REPORTS_DIR,
              EXECUTION_PLAN_DIR, REPORTS_DIR, COT_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
