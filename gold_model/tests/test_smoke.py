#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：路径配置 / JSON契约 / 缓存schema / 数据源映射一致性（无需网络）"""
import json

import pandas as pd
import pytest

from gold_model import paths


# ── paths ──
def test_ensure_dirs_idempotent():
    paths.ensure_dirs()
    for d in (paths.DATA_DIR, paths.WEB_DIR, paths.CHARTS_DIR,
              paths.EXECUTION_PLAN_DIR, paths.REPORTS_DIR):
        assert d.is_dir(), f"目录不存在: {d}"


def test_paths_under_project_root():
    for p in (paths.DATA_DIR, paths.WEB_DIR, paths.OUTPUTS_DIR):
        assert paths.PROJECT_ROOT in p.parents


# ── 前端 JSON 契约（allow_nan / 必备字段）──
def _load_strict(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f, parse_constant=lambda x: pytest.fail(f"{path.name} 含非法JSON值: {x}"))


def test_dashboard_json_contract():
    d = _load_strict(paths.DASHBOARD_JSON)
    for key in ('overview', 'strategies', 'features', 'ml_models', 'current_factors', 'raw_data'):
        assert key in d, f"dashboard_data.json 缺字段: {key}"
    assert len(d['raw_data']) > 0


def test_execution_json_contract():
    d = _load_strict(paths.EXECUTION_JSON)
    for key in ('current', 'scenarios', 'execution_rules', 'position_history'):
        assert key in d, f"execution_data.json 缺字段: {key}"
    cur = d['current']
    assert -1.5 <= cur['position'] <= 1.5, f"仓位异常: {cur['position']}"  # 熊市做空为合法输出(v3e clip ±1.5)
    assert 0 <= cur['probability'] <= 1, f"概率异常: {cur['probability']}"


# ── 缓存/状态文件 schema ──
def test_calendar_caches():
    for cache in (paths.FOMC_CACHE, paths.CPI_CACHE):
        with open(cache, encoding='utf-8') as f:
            d = json.load(f)
        assert isinstance(d, dict) and len(d) > 0, f"{cache.name} 为空"


def test_drift_history_schema():
    with open(paths.DRIFT_HISTORY, encoding='utf-8') as f:
        history = json.load(f)
    assert isinstance(history, list) and len(history) > 0
    sb = history[-1].get('signal_backtest')
    if sb:  # V4.3.1起应含市场上涨占比诊断字段
        for key in ('wf_baseline_acc', 'recent_20_hit_rate', 'consecutive_miss'):
            assert key in sb


# ── 数据源映射一致性 ──
def test_fetcher_mappings():
    from gold_model.data_fetcher import (
        TICKER_NAMES, FRED_ALTERNATIVES, PROXY_FALLBACK, EASTMONEY_MARKET_HINT,
    )
    for t in FRED_ALTERNATIVES:
        assert t in TICKER_NAMES, f"FRED映射的ticker未知: {t}"
    for t, (proxy, scale) in PROXY_FALLBACK.items():
        assert t in TICKER_NAMES
        # 代理目标无需进入TICKER_NAMES（如CPER只作铜期货代理），但必须可获取
        assert proxy in TICKER_NAMES or proxy in EASTMONEY_MARKET_HINT, f"代理目标不可获取: {proxy}"
        assert scale > 0, f"{t} 代理缩放异常: {scale}"
    for t, mkt in EASTMONEY_MARKET_HINT.items():
        assert mkt in (105, 106, 107), f"{t} 东财market非法: {mkt}"


# ── 信号告警状态文件 ──
def test_signal_alert_state():
    with open(paths.SIGNAL_ALERT_STATE, encoding='utf-8') as f:
        state = json.load(f)
    assert 'regime' in state and 'position' in state
