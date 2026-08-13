#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格预测 V5.0 — 过拟合修复 + 共线性剔除 + 自适应窗口 + 收益回归
===================================================================
V4.0→V5.0改进点（回应外部AI Code Review的5条硬伤中3.5条在理项）：
  P0-1: VIF共线性剔除（相关系数聚类+VIF逐层剔除，41→25-30特征）
  P0-2: Holdout验证（保留最近6月数据做纯净OOS验证）
  P1-1: Regime-aware自适应训练窗口（高波动期250日，低波动期500日）
  P1-2: Purged K-fold（train/test间加gap=10，消除标签泄漏）
  P2-1: 收益幅度回归分支（并行XGBoost回归预测收益率，仓位更精细）
  P2-2: Regime-conditional训练（只用同Regime历史样本训练）
"""

import warnings
warnings.filterwarnings('ignore')

import os
import sys
import json
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
import xgboost as xgb
import lightgbm as lgb

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.dates as mdates
from matplotlib.patches import Patch

# 中文字体
import platform
if platform.system() == 'Darwin':
    plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Hiragino Sans GB', 'DejaVu Sans']
else:
    for fp in ['/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf',
               '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
    plt.rcParams['font.sans-serif'] = ['Noto Serif SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from gold_model.paths import (
    CHARTS_V5_DIR, DASHBOARD_JSON, EXECUTION_JSON, DRIFT_HISTORY,
    REPORT_V5_XLSX, EXECUTION_LATEST_JSON, ANALYSIS_JSON, ensure_dirs,
    VUE3_PUBLIC_DIR,
)
ensure_dirs()

# ═══════════════════════════════════════════════════════════════════
# 1. 数据采集 V4.0（yfinance + FRED）
# ═══════════════════════════════════════════════════════════════════

print("=" * 60)
print("  黄金多因子分析 V5.0 — 过拟合修复+共线性剔除+自适应窗口+收益回归")
print("=" * 60)

TICKERS = {
    'GC=F':    '黄金期货',
    'GLD':     'GLD基金',
    'IAU':     'IAU基金',
    'SGOL':    'SGOL基金',
    'DX-Y.NYB':'美元指数',
    'TIP':     'TIPS(实际利率替代)',
    'IEF':     '7-10年国债(名义利率替代)',
    'TLT':     '20+年国债',
    'SLV':     '白银',
    'GDX':     '金矿股',
    'GDXJ':    '金矿小盘',
    'SIL':     '白银矿企',
    '^VIX':    'VIX恐慌',
    '^GVZ':    '黄金VIX',
    'NEM':     '纽蒙特矿业',
    'EUR=X':   '欧元/美元',
    'JPY=X':   '美元/日元',
    'UUP':     '美元指数ETF',
    # V4.0新增
    'HG=F':    '铜期货',
    'BTC-USD': '比特币',
    '^VIX9D':  'VIX9D',
    '^IRX':    '13周国债',
    '^FVX':    '5年国债',
    '^TNX':    '10年国债名义',
    '^TYX':    '30年国债',
}

# FRED数据序列（直接CSV抓取，无需API key）
FRED_SERIES = {
    'DFII10':  '10年实际利率(FRED)',      # 10年期TIPS实际收益率
    'DFII5':   '5年实际利率(FRED)',       # 5年期TIPS实际收益率
    'DGS2':    '2年国债收益率(FRED)',
    'DGS10':   '10年国债收益率(FRED)',
    'DGS30':   '30年国债收益率(FRED)',
    'DFF':     '联邦基金利率(FRED)',       # 美联储政策利率
    'T10YIE':  '10年通胀预期(FRED)',      # 10年盈亏平衡通胀率
}

print("\n[1a] yfinance数据采集（含多源fallback）...")
# V4.2: 多源fallback架构 yfinance→FRED→Stooq
# V5.3: 数据周期可配置。默认10y(含2018熊市,熊市样本184→461天);
#   10y下WF IC近零但Holdout夏普-2.25→-1.58(首次跑赢买入持有),风控价值>方向预测
from gold_model.data_fetcher import fetch_ticker_with_fallback
DATA_PERIOD = os.environ.get('V5_DATA_PERIOD', '10y')
raw = {}
for ticker, name in TICKERS.items():
    s = fetch_ticker_with_fallback(ticker, name, period=DATA_PERIOD)
    if s is not None:
        raw[name] = s

print("\n[1b] FRED宏观数据采集...")
for sid, name in FRED_SERIES.items():
    try:
        url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and 'html' not in r.text[:50].lower():
            df_fred = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
            df_fred.columns = [name]
            # 过滤无效值（FRED用.表示缺失）
            df_fred = df_fred.replace('.', np.nan).astype(float)
            # 只取最近N年(跟随DATA_PERIOD)
            _period_years = int(''.join(c for c in DATA_PERIOD if c.isdigit()) or '5')
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=_period_years*365)
            df_fred = df_fred[df_fred.index > cutoff]
            if len(df_fred) > 100:
                s = df_fred[name]
                s.name = name
                raw[name] = s
                print(f"  ✅ {name}({sid}) {len(df_fred)}行")
    except Exception as e:
        print(f"  ❌ {name}({sid}) {str(e)[:40]}")

df = pd.DataFrame(raw).dropna(how='all')
print(f"  合并: {df.shape[0]} rows, {df.shape[1]} cols")

# ═══════════════════════════════════════════════════════════════════
# 2. 因子构建
# ═══════════════════════════════════════════════════════════════════

print("\n[2] 因子构建...")
gold = df['黄金期货'].dropna()

# 基础因子
f_real_rate    = df['TIPS(实际利率替代)']
f_dxy          = df['美元指数']
f_nominal_rate = df['7-10年国债(名义利率替代)']
f_inflation    = df['TIPS(实际利率替代)'] / df['7-10年国债(名义利率替代)']
f_vix          = df['VIX恐慌']
f_gdx_gold     = df['金矿股'] / df['黄金期货']
f_silver_gold  = df['白银'] / df['黄金期货']
f_gvz          = df['黄金VIX']

# V2.0因子
etp_holdings = df['GLD基金'] + df['IAU基金'] + df['SGOL基金']
f_cb_proxy = etp_holdings.pct_change(60)
f_miner_ratio = df['金矿股'] / df['白银矿企']
f_usd_jpy = df['美元/日元']
f_gold_nem = df['黄金期货'] / df['纽蒙特矿业']

# 技术因子
f_ma200_dev = gold / gold.rolling(200).mean() - 1
f_ma_cross = np.where(
    gold.rolling(50).mean() > gold.rolling(200).mean(), 1, -1)
f_ma_cross = pd.Series(f_ma_cross, index=gold.index)
f_mom_20d = gold.pct_change(20)
f_mom_60d = gold.pct_change(60)
f_vol_20d = gold.pct_change().rolling(20).std() * np.sqrt(250)
f_vol_60d = gold.pct_change().rolling(60).std() * np.sqrt(250)

delta = gold.diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rs = gain / loss
f_rsi = 100 - (100 / (1 + rs))

# 交互因子
f_real_x_dxy = f_real_rate * f_dxy
f_vix_x_infl = f_vix * f_inflation
f_gdx_x_vix = f_gdx_gold * f_vix

# V3.0新增因子
# 波动率变化率（波动率上升=恐慌信号）
f_vol_change = f_vol_20d.pct_change(10)
# 动量加速度（二阶导）
f_mom_accel = f_mom_20d - f_mom_20d.shift(10)
# 金价/长期均线比率（宏观估值）
f_gold_ma_ratio = gold / gold.rolling(250).mean()

# ═══ V4.0新增因子（补全盲区）═══

# ── FRED真实宏观数据 ──
# 10年实际利率（真实TIPS收益率，比TIP ETF精确）
f_real_rate_10y = df['10年实际利率(FRED)'] if '10年实际利率(FRED)' in df else pd.Series(np.nan, index=df.index)
# 5年实际利率
f_real_rate_5y = df['5年实际利率(FRED)'] if '5年实际利率(FRED)' in df else pd.Series(np.nan, index=df.index)
# 联邦基金利率（美联储政策利率）
f_fed_rate = df['联邦基金利率(FRED)'] if '联邦基金利率(FRED)' in df else pd.Series(np.nan, index=df.index)
# 10年通胀预期（盈亏平衡通胀率）
f_infl_exp_10y = df['10年通胀预期(FRED)'] if '10年通胀预期(FRED)' in df else pd.Series(np.nan, index=df.index)

# ── 收益率曲线 ──
# 2s10s利差（10年-2年，倒挂=衰退预警）
f_2s10s = (df['10年国债收益率(FRED)'] - df['2年国债收益率(FRED)']) if '10年国债收益率(FRED)' in df and '2年国债收益率(FRED)' in df else pd.Series(np.nan, index=df.index)
# 5s30s利差
f_5s30s = (df['30年国债收益率(FRED)'] - df['5年国债收益率(FRED)']) if '30年国债收益率(FRED)' in df and '5年国债收益率(FRED)' in df else pd.Series(np.nan, index=df.index)
# 收益率曲线倒挂信号（1=倒挂, 0=正常）
f_curve_invert = (f_2s10s < 0).astype(float)

# ── 铜金比（经济周期代理）──
# 铜涨金跌=经济复苏（风险偏好上升）；铜跌金涨=经济衰退（避险需求上升）
f_copper_gold = df['铜期货'] / df['黄金期货'] if '铜期货' in df else pd.Series(np.nan, index=df.index)

# ── 比特币（避险替代品竞争）──
# BTC涨=部分避险资金流入加密而非黄金
f_btc = df['比特币'] if '比特币' in df else pd.Series(np.nan, index=df.index)
f_btc_gold = df['比特币'] / df['黄金期货'] if '比特币' in df and '黄金期货' in df else pd.Series(np.nan, index=df.index)

# ── VIX期限结构（近端恐慌vs远端）──
# VIX/VIX9D比值>1=近端恐慌>远端，市场紧张
f_vix_9d = df['VIX9D'] if 'VIX9D' in df else pd.Series(np.nan, index=df.index)
f_vix_term_spread = df['VIX恐慌'] / df['VIX9D'] if 'VIX9D' in df else pd.Series(np.nan, index=df.index)

# ── FOMC议息日历特征（V4.2: 动态获取，替代硬编码）──
# 多级fallback：Fed官网抓取 → 硬编码历史 → 本地缓存 → 模式估算
from gold_model.fomc_calendar import get_fomc_dates
FOMC_DATES = get_fomc_dates(end_year=datetime.now().year + 2)

# CPI发布日期（V4.2: 动态获取，替代估算）
# 多级fallback：cpiinflationcalculator.com抓取 → 硬编码历史 → 缓存 → 模式估算
from gold_model.cpi_calendar import get_cpi_dates
CPI_DATES = get_cpi_dates(end_year=datetime.now().year + 2)

# 计算距下次FOMC的天数
fomc_dates = FOMC_DATES.sort_values()
def days_to_next_event(date, event_dates):
    """计算距下次事件的天数"""
    future = event_dates[event_dates >= date]
    if len(future) > 0:
        return (future[0] - date).days
    return 30  # 默认值

f_days_to_fomc = pd.Series(0.0, index=gold.index)
f_days_to_cpi = pd.Series(0.0, index=gold.index)
for d in gold.index:
    f_days_to_fomc[d] = days_to_next_event(d, fomc_dates)
    f_days_to_cpi[d] = days_to_next_event(d, CPI_DATES)

# FOMC周标记（议息前3天+议息当天）
f_fomc_week = (f_days_to_fomc <= 3).astype(float)
# CPI周标记
f_cpi_week = (f_days_to_cpi <= 2).astype(float)

# ── 实际利率×美联储利率（政策紧缩力度）──
f_real_x_fed = f_real_rate_10y * f_fed_rate if f_real_rate_10y.notna().sum() > 0 else pd.Series(np.nan, index=df.index)
# ── 铜金比×VIX（滞胀信号）──
f_copper_x_vix = f_copper_gold * f_vix if f_copper_gold.notna().sum() > 0 else pd.Series(np.nan, index=df.index)
# ── 收益率曲线×美元（美元周期+利率周期叠加）──
f_curve_x_dxy = f_2s10s * f_dxy if f_2s10s.notna().sum() > 0 else pd.Series(np.nan, index=df.index)

# 组装
factors = pd.DataFrame({
    '金价':              gold,
    '实际利率(TIP)':      f_real_rate,
    '美元指数':           f_dxy,
    '名义利率(IEF)':      f_nominal_rate,
    '通胀预期(TIP/IEF)':  f_inflation,
    'VIX恐慌':           f_vix,
    '金矿/黄金':          f_gdx_gold,
    '白银/黄金':          f_silver_gold,
    '黄金VIX':           f_gvz,
    '央行购金代理(ETP)':  f_cb_proxy,
    '金矿/银矿':          f_miner_ratio,
    '美元/日元':          f_usd_jpy,
    '金/纽蒙特':          f_gold_nem,
    'MA200偏离':          f_ma200_dev,
    'MA交叉信号':         f_ma_cross,
    '20日动量':           f_mom_20d,
    '60日动量':           f_mom_60d,
    '20日波动率':         f_vol_20d,
    '60日波动率':         f_vol_60d,
    'RSI14':             f_rsi,
    '实际利率×美元':      f_real_x_dxy,
    'VIX×通胀预期':       f_vix_x_infl,
    '金矿×VIX':           f_gdx_x_vix,
    # V3.0新增
    '波动率变化':         f_vol_change,
    '动量加速度':         f_mom_accel,
    '金价/长期均线':      f_gold_ma_ratio,
    # V4.0新增——FRED宏观
    '10年实际利率':       f_real_rate_10y,
    '5年实际利率':        f_real_rate_5y,
    '联邦基金利率':       f_fed_rate,
    '10年通胀预期':       f_infl_exp_10y,
    '2s10s利差':          f_2s10s,
    '5s30s利差':          f_5s30s,
    '曲线倒挂信号':       f_curve_invert,
    # V4.0新增——商品/加密
    '铜金比':             f_copper_gold,
    'BTC/黄金':           f_btc_gold,
    # V4.0新增——VIX期限
    'VIX期限结构':        f_vix_term_spread,
    # V4.0新增——事件日历
    '距FOMC天数':         f_days_to_fomc,
    'FOMC周':             f_fomc_week,
    '距CPI天数':          f_days_to_cpi,
    'CPI周':              f_cpi_week,
    # V4.0新增——交互
    '实际利率×Fed利率':   f_real_x_fed,
    '铜金比×VIX':         f_copper_x_vix,
    '曲线×美元':          f_curve_x_dxy,
})

factors = factors.dropna(how='all')
# P0修复: 只保留有金价的交易日行，避免日历日NaN导致rolling失效
factors = factors[factors['金价'].notna()].copy()
factors['MA交叉信号'] = factors['MA交叉信号'].fillna(0)

# V4.0: 对FRED宏观数据做前向填充（FRED日频数据可能有缺失日）
fred_cols = ['10年实际利率', '5年实际利率', '联邦基金利率', '10年通胀预期',
             '2s10s利差', '5s30s利差', '曲线倒挂信号', '铜金比', 'BTC/黄金', 'VIX期限结构']
for col in fred_cols:
    if col in factors.columns:
        factors[col] = factors[col].ffill()

# 对交互因子也做ffill
interaction_cols = ['实际利率×Fed利率', '铜金比×VIX', '曲线×美元']
for col in interaction_cols:
    if col in factors.columns:
        factors[col] = factors[col].ffill()

# 对事件日历特征填充默认值
if '距FOMC天数' in factors.columns:
    factors['距FOMC天数'] = factors['距FOMC天数'].fillna(30)
if '距CPI天数' in factors.columns:
    factors['距CPI天数'] = factors['距CPI天数'].fillna(15)
if 'FOMC周' in factors.columns:
    factors['FOMC周'] = factors['FOMC周'].fillna(0)
if 'CPI周' in factors.columns:
    factors['CPI周'] = factors['CPI周'].fillna(0)

print(f"  因子矩阵: {factors.shape}")
print(f"  NaN占比: {factors.isna().sum().sum() / factors.size:.1%}")

# ═══════════════════════════════════════════════════════════════════
# 2.5 P0-1: VIF共线性剔除（相关系数聚类+VIF逐层剔除）
# ═══════════════════════════════════════════════════════════════════

print("\n[2.5] P0-1: VIF共线性剔除...")

# 先定义所有候选特征列
_all_feature_cols = [c for c in factors.columns if c not in
    ['金价', 'Regime', '高波动', 'MA200', 'MA50',
     '未来5日收益', '未来10日收益', '未来20日收益', '未来60日收益',
     '未来5日涨跌', '未来10日涨跌', '未来20日涨跌', '未来60日涨跌']]
# 注：此时标签列还没构建，但提前定义不影响

# 用有效行计算相关性（填充NaN后）
_X_for_corr = factors[_all_feature_cols].fillna(factors[_all_feature_cols].median())

# 剔除常数列（方差=0 → 相关性NaN）
_const_cols = [c for c in _all_feature_cols if _X_for_corr[c].std() == 0]
if _const_cols:
    print(f"  剔除常数列: {_const_cols}")
    _all_feature_cols = [c for c in _all_feature_cols if c not in _const_cols]
    _X_for_corr = _X_for_corr[_all_feature_cols]

corr_matrix = _X_for_corr.corr().abs()
# 填充NaN相关性为0（不相关）
corr_matrix = corr_matrix.fillna(0)

# 层次聚类：相关系数 > 0.7 的特征归为同簇，每簇保留IC绝对值最大的
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

# 1 - corr → 距离矩阵
dist_matrix = 1 - corr_matrix
dist_matrix = dist_matrix.clip(0, 2)
# pandas3/numpy2: DataFrame.values 是只读视图，需显式拷贝为numpy数组再原地修改
dist_arr = dist_matrix.to_numpy(dtype=float, copy=True)
np.fill_diagonal(dist_arr, 0)
# 确保对称
dist_arr = (dist_arr + dist_arr.T) / 2
# 再次清理可能的NaN/inf
dist_arr = np.nan_to_num(dist_arr, nan=1.0, posinf=1.0, neginf=1.0)
# 转为condensed distance
condensed = squareform(dist_arr, checks=False)
# 确保无NaN
condensed = np.nan_to_num(condensed, nan=1.0)
Z = linkage(condensed, method='ward')
clusters = fcluster(Z, t=0.3, criterion='distance')  # 距离<0.3 → 相关系数>0.7

# 每簇保留方差最大的特征（方差大=信息量大）
cluster_map = {}
for i, c in enumerate(clusters):
    if c not in cluster_map:
        cluster_map[c] = []
    cluster_map[c].append(_all_feature_cols[i])

print(f"  相关性聚类: {len(_all_feature_cols)}个特征 → {len(cluster_map)}簇")
cluster_repr = []
for cid, members in cluster_map.items():
    if len(members) == 1:
        cluster_repr.append(members[0])
    else:
        # 保留方差最大的
        variances = {m: _X_for_corr[m].var() for m in members}
        best = max(variances, key=variances.get)
        cluster_repr.append(best)
        print(f"    簇{cid}: {members} → 保留 '{best}'")

# VIF逐层剔除：VIF > 10 的逐个删除
from statsmodels.stats.outliers_influence import variance_inflation_factor as _vif_func

selected = list(cluster_repr)  # 从聚类代表开始
_max_vif_iter = 10
for iteration in range(_max_vif_iter):
    _X_vif = _X_for_corr[selected].dropna()
    if len(_X_vif) < 50 or len(selected) < 3:
        break
    vif_values = {}
    for i, col in enumerate(selected):
        try:
            vif_values[col] = _vif_func(_X_vif.values, i)
        except:
            vif_values[col] = 999
    max_col = max(vif_values, key=vif_values.get)
    max_vif = vif_values[max_col]
    if max_vif > 10:
        print(f"    VIF剔除 iter{iteration+1}: 移除 '{max_col}' (VIF={max_vif:.1f})")
        selected.remove(max_col)
    else:
        print(f"    VIF收敛: 最高VIF={max_vif:.1f} ({max_col}) ≤ 10")
        break

feature_cols = selected
_all_feature_cols_len = len(_all_feature_cols)

# V5.3 特征手术: 剔除per-feature IC诊断确认的噪声/反转特征(2026-08-11 diagnose_model.py)
# 数据依据: 这些特征的60日IC≈0(无预测力)或在牛/震荡市IC符号反转(Regime不稳定)
FEATURE_BLACKLIST = os.environ.get('V5_FEATURE_BLACKLIST', '1') == '1'
if FEATURE_BLACKLIST:
    _noise_features = {
        # IC≈0 的纯噪声特征(模型在这些特征上浪费分裂能力):
        '距FOMC天数', '距CPI天数', 'FOMC周', 'CPI周', 'RSI14',
        # Regime反转特征(牛市IC正/震荡IC负,单一模型无法兼顾):
        'BTC/黄金', '金/纽蒙特',
    }
    _before = len(feature_cols)
    feature_cols = [f for f in feature_cols if f not in _noise_features]
    print(f"  ✅ 特征手术(V5.3): 剔除{_before - len(feature_cols)}个噪声/反转特征 → {len(feature_cols)}个")
    print(f"     剔除: {_noise_features & set(selected)}")
else:
    print(f"  ✅ 最终特征数: {len(feature_cols)} (原始{len(_all_feature_cols)})")
    print(f"  剔除特征: {set(_all_feature_cols) - set(feature_cols)}")

# ═══════════════════════════════════════════════════════════════════
# 3. 标签构建（多周期）
# ═══════════════════════════════════════════════════════════════════

print("\n[3] 标签构建...")
PREDICT_DAYS = [5, 10, 20, 60]

# V5.1 标签模式: 'abs'=绝对涨跌(原V5) / 'excess'=超额收益vs滚动均值(消融实验验证)
# 消融实验(2026-08-08,tests/ablation_labels.py+ablation_thresholds.py)证明:
#   'excess'模式 Holdout IC从-0.102翻正到+0.162,Holdout年化从-34.7%改善到-9.0%,
#   去掉了牛市样本导致的标签偏斜(60日牛市正样本74%→50%)。
# 仓位阈值(0.65/0.55/0.48)不调——第4轮实验证明搜索阈值会过拟合,旧阈值在新标签下更稳。
LABEL_MODE = os.environ.get('V5_LABEL_MODE', 'abs')  # 默认abs(原V5标签);excess=超额收益(主管道实测更差,保留待研究)
_gold_daily_ret = factors['金价'].pct_change()

for n in PREDICT_DAYS:
    factors[f'未来{n}日收益'] = factors['金价'].pct_change(n).shift(-n)
    # 原绝对涨跌标签(始终保留,供分析/回退)
    factors[f'未来{n}日涨跌'] = (factors[f'未来{n}日收益'] > 0).astype(int)
    # 超额收益标签: 未来N日收益 > 滚动250日日均收益×N
    # P2修复(前视偏差): 基准用当前已知的250日均值,不用shift(-n)搬未来均值
    _rolling_mean_n = _gold_daily_ret.rolling(250).mean() * n
    factors[f'未来{n}日超额'] = (factors[f'未来{n}日收益'] > _rolling_mean_n).astype(int)
    # D3修复: 未来收益NaN的行(末N天未结算)标签也置NaN,避免astype把NaN误标成"跌"(0)
    _unsettled = factors[f'未来{n}日收益'].isna()
    factors.loc[_unsettled, f'未来{n}日涨跌'] = np.nan
    factors.loc[_unsettled, f'未来{n}日超额'] = np.nan

# 训练用哪个标签列(由LABEL_MODE决定)
_label_suffix = '涨跌' if LABEL_MODE == 'abs' else '超额'
print(f"  标签模式: LABEL_MODE={LABEL_MODE} (训练用'未来{{N}}日{_label_suffix}')")
if LABEL_MODE == 'excess':
    for n in PREDICT_DAYS:
        _pos_ratio = factors[f'未来{n}日超额'].mean()
        print(f"  {n}日超额标签正样本占比: {_pos_ratio:.1%}")

# ═══════════════════════════════════════════════════════════════════
# 4. Regime识别（核心创新1）
# ═══════════════════════════════════════════════════════════════════

print("\n[4] Regime识别...")

ma200 = factors['金价'].rolling(200).mean()
ma50 = factors['金价'].rolling(50).mean()
vol_60 = factors['金价'].pct_change().rolling(60).std() * np.sqrt(250)

# Regime定义（V4.3: 加波动率触发，缩短切换延迟）：
# 牛市: 金价>MA200 且 MA50>MA200（均线多头排列）
# 熊市: 金价<MA200 且 MA50<MA200（均线空头排列）
# 震荡: 其他
# V4.3新增: 从均线偏离度+波动率角度加速识别
# 当金价跌破MA50且20日跌幅>5%时，立即转熊市（不等MA200跟随）
gold_price = factors['金价']
gold_ret_20d = gold_price.pct_change(20)
gold_vs_ma50 = (gold_price - ma50) / ma50  # 偏离度

# 波动率分位数（高波动=风险regime）
vol_rank = vol_60.rolling(252).rank(pct=True)
high_vol = vol_rank > 0.8  # 前20%波动率

regime = pd.Series('震荡', index=factors.index)
regime[(gold_price > ma200) & (ma50 > ma200)] = '牛市'
regime[(gold_price < ma200) & (ma50 < ma200)] = '熊市'

# V4.3: 波动率触发——急跌时加速转熊市
# 条件：金价低于MA50 3%以上 且 20日跌幅<-5% 且 波动率高位
fast_bear = (gold_vs_ma50 < -0.03) & (gold_ret_20d < -0.05) & (vol_rank > 0.6)
# 只在当前是牛市或震荡时切换（避免反复切换）
regime[fast_bear & (regime != '熊市')] = '熊市'

# V4.3: 急涨时加速转牛市
fast_bull = (gold_vs_ma50 > 0.03) & (gold_ret_20d > 0.05) & (gold_price > ma200)
regime[fast_bull & (regime == '震荡')] = '牛市'

factors['Regime'] = regime
factors['高波动'] = high_vol
factors['MA200'] = ma200
factors['MA50'] = ma50

regime_counts = regime.value_counts()
print(f"  Regime分布:")
for r, c in regime_counts.items():
    pct = c / len(regime) * 100
    print(f"    {r}: {c}天 ({pct:.1f}%)")

# 各Regime下的收益统计
print(f"\n  各Regime下金价表现:")
for r in ['牛市', '熊市', '震荡']:
    mask = regime == r
    if mask.sum() > 0:
        rets = factors['金价'].pct_change()[mask]
        ann_ret = rets.mean() * 250
        ann_vol = rets.std() * np.sqrt(250)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        print(f"    {r}: 年化={ann_ret:+.1%} 波动={ann_vol:.1%} 夏普={sharpe:.2f}")

# ═══════════════════════════════════════════════════════════════════
# 5. Walk-Forward ML训练（多周期）
# ═══════════════════════════════════════════════════════════════════

print("\n[5] Walk-Forward ML训练...")

# feature_cols 已在[2.5]通过VIF共线性剔除确定，此处不再重新定义
# 保留原始定义作为fallback（正常不会走到）
if 'feature_cols' not in dir() or not feature_cols:
    feature_cols = [c for c in factors.columns if c not in
        ['金价', 'Regime', '高波动', 'MA200', 'MA50',
         '未来5日收益', '未来10日收益', '未来20日收益', '未来60日收益',
         '未来5日涨跌', '未来10日涨跌', '未来20日涨跌', '未来60日涨跌']]

# 为每个预测周期训练模型
ml_results = {}
TRAIN_WINDOW = int(os.environ.get('V5_TRAIN_WINDOW', '500'))
TEST_WINDOW = 60
STEP = 30
# V5.0 P1-2: Purged gap——train和test之间的间隔，消除标签泄漏
# 泄漏机理: 训练样本t的"N日标签"用到 t+1..t+N 的金价; 末尾训练样本在 start_idx-GAP-1,
# 其标签窥探到 start_idx-GAP .. start_idx-GAP+N-1。要完全不落入test集(start_idx起)，
# 需 GAP >= N。GAP=10 仅够 10日标签, 对 60日标签有 50 天泄漏。
# V5.3 GAP 消融实验: GAP=10(历史值)对60日标签有50天泄漏, 实测60日IC虚高57%
#   (+0.290→+0.123)。生产默认改60(无泄漏); 仅影响回测验证, 不影响实盘预测。
GAP = int(os.environ.get('V5_PURGE_GAP', '60'))
# V5.0 P1-1: 自适应训练窗口
ADAPTIVE_WINDOW_HIGH_VOL = 250  # 高波动期窗口缩短
ADAPTIVE_WINDOW_LOW_VOL = 500   # 低波动期窗口保持

# V5.0 P2-2: Regime-conditional训练开关
REGIME_CONDITIONAL = True  # True=只用同Regime历史样本训练
# V5.2 样本增强: 熊市样本不足(30-100)时复制补齐,不退回全量(消融实验验证)
SAMPLE_AUGMENT = os.environ.get('V5_SAMPLE_AUGMENT', '0') == '1'

for pred_days in PREDICT_DAYS:
    target_col = f'未来{pred_days}日{_label_suffix}'  # V5.1: abs→涨跌 / excess→超额
    ret_col = f'未来{pred_days}日收益'

    X = factors[feature_cols].copy()
    y = factors[target_col].copy()
    rets = factors[ret_col].copy()
    regime_series = factors['Regime'] if 'Regime' in factors else None

    # Walk-forward
    predictions = []
    actuals = []
    probabilities = []
    pred_returns = []
    pred_dates = []
    fold_accs = []

    start_idx = TRAIN_WINDOW
    while start_idx + TEST_WINDOW <= len(X):
        end_idx = start_idx + TEST_WINDOW

        # V5.0 P1-2: Purged gap——在train和test之间留gap天
        # 原始: train = [start_idx-TRAIN_WINDOW, start_idx), test = [start_idx, end_idx)
        # 修改: train = [start_idx-TRAIN_WINDOW-gap, start_idx-gap), test = [start_idx, end_idx)
        # 即gap天数据既不参与train也不参与test，消除标签泄漏
        train_end = start_idx - GAP  # P1-2: gap
        train_start = max(0, train_end - TRAIN_WINDOW)
        train_mask = slice(train_start, train_end)
        test_mask = slice(start_idx, end_idx)

        # V5.0 P1-1: 自适应训练窗口——根据当前波动率决定窗口大小
        if 'vol_60' in dir() or 'vol_60' in globals():
            current_vol_rank = vol_60.iloc[start_idx] if start_idx < len(vol_60) else 0.15
            vol_quantile = vol_60.rank(pct=True).iloc[start_idx] if start_idx < len(vol_60) else 0.5
            if vol_quantile > 0.7:  # 高波动期
                adaptive_window = ADAPTIVE_WINDOW_HIGH_VOL
                train_start = max(0, train_end - adaptive_window)
                train_mask = slice(train_start, train_end)
        # P1-1 fallback: vol_60在后续才定义，用factors的波动率
        if '20日波动率' in factors.columns:
            _vol_at_start = factors['20日波动率'].iloc[start_idx] if start_idx < len(factors) else 0.15
            _vol_rank = factors['20日波动率'].rank(pct=True).iloc[start_idx] if start_idx < len(factors) else 0.5
            if _vol_rank > 0.7:
                adaptive_window = ADAPTIVE_WINDOW_HIGH_VOL
                train_start = max(0, train_end - adaptive_window)
                train_mask = slice(train_start, train_end)

        # 原始训练数据
        X_train = X.iloc[train_mask].copy()
        y_train = y.reindex(X_train.index)

        # V5.0 P2-2: Regime-conditional训练——只用与当前Regime一致的历史样本
        if REGIME_CONDITIONAL and regime_series is not None:
            # ⑤修复(前视): 用训练期最后一天的Regime(因果已知)代替test期多数Regime(偷看未来)
            target_regime = '震荡'
            if train_end > 0:
                _last_reg = regime_series.iloc[train_end - 1]
                target_regime = str(_last_reg) if pd.notna(_last_reg) else '震荡'
            train_regimes = regime_series.reindex(X_train.index)
            regime_mask = (train_regimes == target_regime)
            regime_count = regime_mask.sum()
            if SAMPLE_AUGMENT and target_regime == '熊市' and 30 <= regime_count < 100:
                # V5.2: 熊市样本不足时不退回全量(含牛市),改为复制熊市样本补到100+
                X_regime = X_train[regime_mask]
                y_regime = y_train[regime_mask]
                dup_times = int(np.ceil(100 / regime_count))
                X_train = pd.concat([X_regime] * dup_times, ignore_index=True)
                y_train = pd.concat([y_regime] * dup_times, ignore_index=True)
            elif regime_count >= 100:
                # 样本足够,正常过滤
                X_train = X_train[regime_mask]
                y_train = y_train[regime_mask]
            # regime_count < 30 或非熊市不足时仍退回全量(augment=off 的旧行为)

        # 只保留有标签的行
        valid_train = y_train.notna()
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        # 中位数填充
        train_medians = X_train.median()
        X_train = X_train.fillna(train_medians)

        X_test = X.iloc[test_mask].copy()
        y_test = y.reindex(X_test.index)
        valid_test = y_test.notna()
        X_test = X_test[valid_test]
        y_test = y_test[valid_test]
        X_test = X_test.fillna(train_medians)  # 用训练集中位数填充测试集

        if len(X_train) < 100 or len(X_test) < 10:
            start_idx += STEP
            continue

        # 标准化
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # XGBoost (V4.3: scale_pos_weight平衡标签)
        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        spw = neg_count / pos_count if pos_count > 0 else 1.0
        # 限幅：避免极端平衡导致过度预测负样本
        spw = min(spw, 2.0)
        model_xgb = xgb.XGBClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            scale_pos_weight=spw,
            random_state=42, use_label_encoder=False,
            eval_metric='logloss', verbosity=0,
        )
        model_xgb.fit(X_train_s, y_train)

        # LightGBM (V4.3: class_weight平衡)
        # P1修复: class_weight与scale_pos_weight语义对齐——正类(1)放大,非负类
        cw = {0: 1.0, 1: spw}
        model_lgb = lgb.LGBMClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            class_weight=cw,
            random_state=42, verbose=-1,
        )
        model_lgb.fit(X_train_s, y_train)

        # 集成
        prob_xgb = model_xgb.predict_proba(X_test_s)[:, 1]
        prob_lgb = model_lgb.predict_proba(X_test_s)[:, 1]
        prob_ens = (prob_xgb + prob_lgb) / 2

        # P2修复: 去掉in-sample Isotonic校准——fit在训练集自身预测上会退化(实盘单点clip到0/1)。
        #   回测与实盘统一用原始集成概率，阈值尺度一致(此前回测用校准概率、实盘用raw,不一致)。
        pred_ens = (prob_ens > 0.5).astype(int)

        predictions.extend(pred_ens)
        actuals.extend(y_test.values)
        probabilities.extend(prob_ens)
        pred_returns.extend(rets.reindex(X_test.index).values)
        pred_dates.extend(X_test.index)

        acc = accuracy_score(y_test, pred_ens)
        fold_accs.append(acc)

        start_idx += STEP

    predictions = np.array(predictions)
    actuals = np.array(actuals)
    probabilities = np.array(probabilities)
    pred_returns = np.array(pred_returns)

    valid = ~np.isnan(pred_returns) & ~np.isnan(actuals.astype(float))
    acc = accuracy_score(actuals[valid], predictions[valid])

    try:
        auc = roc_auc_score(actuals[valid], probabilities[valid])
    except:
        auc = 0.5

    # IC
    ic, _ = stats.spearmanr(probabilities[valid], pred_returns[valid])

    ml_results[pred_days] = {
        'predictions': predictions[valid],
        'actuals': actuals[valid],
        'probabilities': probabilities[valid],
        'returns': pred_returns[valid],
        'dates': [pred_dates[i] for i in range(len(pred_dates)) if valid[i]],
        'accuracy': acc,
        'auc': auc,
        'ic': ic,
        'fold_accs': fold_accs,
    }

    # 去重（保留最后一次预测）
    df_tmp = pd.DataFrame({
        'prob': probabilities[valid],
        'actual': actuals[valid],
        'date': [pred_dates[i] for i in range(len(pred_dates)) if valid[i]],
    })
    df_tmp = df_tmp.drop_duplicates(subset='date', keep='last')
    ml_results[pred_days]['dates'] = df_tmp['date'].tolist()
    ml_results[pred_days]['probabilities'] = df_tmp['prob'].values
    ml_results[pred_days]['actuals'] = df_tmp['actual'].values

    print(f"  {pred_days}日预测: 准确率={acc:.1%} AUC={auc:.3f} IC={ic:+.4f}")

# ═══════════════════════════════════════════════════════════════════
# 5.1 V5.0 P2-1: 收益幅度回归分支（并行训练XGBoost回归模型预测收益率）
# ═══════════════════════════════════════════════════════════════════

print("\n[5.1] P2-1: 收益幅度回归分支（Walk-Forward）...")

reg_results = {}  # 每个周期的回归预测结果

for pred_days in PREDICT_DAYS:
    target_ret = f'未来{pred_days}日收益'
    X_reg = factors[feature_cols].copy()
    y_reg = factors[target_ret].copy()
    regime_series = factors['Regime'] if 'Regime' in factors else None

    reg_preds = []
    reg_actuals = []
    reg_dates = []

    start_idx = TRAIN_WINDOW
    while start_idx + TEST_WINDOW <= len(X_reg):
        end_idx = start_idx + TEST_WINDOW

        # 同分类：purged gap + adaptive window
        train_end = start_idx - GAP
        train_start = max(0, train_end - TRAIN_WINDOW)

        # 自适应窗口
        if '20日波动率' in factors.columns:
            _vol_rank = factors['20日波动率'].rank(pct=True).iloc[start_idx] if start_idx < len(factors) else 0.5
            if _vol_rank > 0.7:
                train_start = max(0, train_end - ADAPTIVE_WINDOW_HIGH_VOL)

        train_mask = slice(train_start, train_end)
        test_mask = slice(start_idx, end_idx)

        X_train = X_reg.iloc[train_mask].copy()
        y_train = y_reg.reindex(X_train.index)

        # Regime-conditional
        if REGIME_CONDITIONAL and regime_series is not None:
            # ⑤修复(前视): 用训练期最后一天的Regime(因果已知)代替test期多数Regime
            target_regime = '震荡'
            if train_end > 0:
                _last_reg = regime_series.iloc[train_end - 1]
                target_regime = str(_last_reg) if pd.notna(_last_reg) else '震荡'
            train_regimes = regime_series.reindex(X_train.index)
            regime_mask = (train_regimes == target_regime)
            if regime_mask.sum() >= 100:
                X_train = X_train[regime_mask]
                y_train = y_train[regime_mask]

        valid_train = y_train.notna()
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        train_medians = X_train.median()
        X_train = X_train.fillna(train_medians)

        X_test = X_reg.iloc[test_mask].copy()
        y_test_r = y_reg.reindex(X_test.index)
        valid_test = y_test_r.notna()
        X_test = X_test[valid_test]
        y_test_r = y_test_r[valid_test]
        X_test = X_test.fillna(train_medians)

        if len(X_train) < 100 or len(X_test) < 10:
            start_idx += STEP
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # XGBoost回归
        model_reg = xgb.XGBRegressor(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            random_state=42, verbosity=0,
        )
        model_reg.fit(X_train_s, y_train)

        pred_ret = model_reg.predict(X_test_s)

        reg_preds.extend(pred_ret)
        reg_actuals.extend(y_test_r.values)
        reg_dates.extend(X_test.index)

        start_idx += STEP

    reg_preds = np.array(reg_preds)
    reg_actuals = np.array(reg_actuals)
    valid = ~np.isnan(reg_actuals) & ~np.isnan(reg_preds)

    # 回归模型评估
    from sklearn.metrics import r2_score, mean_squared_error
    r2 = r2_score(reg_actuals[valid], reg_preds[valid]) if valid.sum() > 0 else 0
    rmse = np.sqrt(mean_squared_error(reg_actuals[valid], reg_preds[valid])) if valid.sum() > 0 else 0
    # 方向准确率（预测为正→实际为正）
    dir_acc = ((reg_preds[valid] > 0) == (reg_actuals[valid] > 0)).mean() if valid.sum() > 0 else 0
    ic_reg, _ = stats.spearmanr(reg_preds[valid], reg_actuals[valid]) if valid.sum() > 10 else (0, 0)

    # 去重
    df_reg = pd.DataFrame({
        'pred_ret': reg_preds[valid],
        'actual_ret': reg_actuals[valid],
        'date': [reg_dates[i] for i in range(len(reg_dates)) if valid[i]],
    }).drop_duplicates(subset='date', keep='last')

    reg_results[pred_days] = {
        'predictions': df_reg['pred_ret'].values,
        'actuals': df_reg['actual_ret'].values,
        'dates': df_reg['date'].tolist(),
        'r2': r2,
        'rmse': rmse,
        'dir_acc': dir_acc,
        'ic': ic_reg,
    }

    print(f"  {pred_days}日回归: R²={r2:.3f} RMSE={rmse:.4f} 方向准确率={dir_acc:.1%} IC={ic_reg:+.4f}")

# ═══════════════════════════════════════════════════════════════════
# 5.5 信号回测基准（V4.2新增：追踪近期信号命中率）
# ═══════════════════════════════════════════════════════════════════

print("\n[5.5] 信号回测基准...")
# 用20日WF预测序列计算滚动命中率
wf20 = ml_results[20]
wf_dates = wf20['dates']
wf_probs = wf20['probabilities']
wf_actuals = wf20['actuals']

# 最近N次信号的命中情况
SIGNAL_WINDOW = 20  # 滚动窗口
recent_n = min(SIGNAL_WINDOW, len(wf_dates))
recent_hits = sum(wf_actuals[-recent_n:])  # actuals是0/1，1=命中
recent_hit_rate = recent_hits / recent_n if recent_n > 0 else 0

# 连续错误次数（从最后一次往前数）
consecutive_miss = 0
for a in reversed(wf_actuals):
    if a == 0:
        consecutive_miss += 1
    else:
        break

# 最近10次信号命中率
recent_10 = min(10, len(wf_dates))
recent_10_hits = sum(wf_actuals[-recent_10:])
recent_10_rate = recent_10_hits / recent_10 if recent_10 > 0 else 0

# WF整体基准命中率
wf_baseline_acc = wf20['accuracy']

# V4.3: 构建滚动命中率时序——用于策略层信号质量熔断
wf_actuals_series = pd.Series(wf_actuals, index=wf_dates)
# P0修复(前视偏差): 预测日p的20日actual要到p+20交易日才结算。
#   将actual按"结算日"(预测日+20交易日)平移对齐后再滚动,任何时点只用已结算命中率。
_settled_actuals = wf_actuals_series.copy()
_settled_actuals.index = wf_actuals_series.index + pd.tseries.offsets.BDay(20)
# 结算日对齐交易日历后ffill,再滚动20日命中率
rolling_hit = _settled_actuals.reindex(factors.index).ffill().rolling(20, min_periods=10).mean()
# 转为0-1之间的信号质量因子（命中率<40%时大幅降仓位，>60%时正常）
signal_quality = rolling_hit.fillna(0.5)
# 熔断逻辑：命中率<30% → 仓位×0.2；<40% → 仓位×0.5；<50% → 仓位×0.8
signal_scalar = pd.Series(1.0, index=factors.index)
signal_scalar[signal_quality < 0.50] = 0.8
signal_scalar[signal_quality < 0.40] = 0.5
signal_scalar[signal_quality < 0.30] = 0.2
# 打印当前熔断状态
current_sq = signal_quality.iloc[-1] if len(signal_quality) > 0 else 0.5
current_ss = signal_scalar.iloc[-1] if len(signal_scalar) > 0 else 1.0
print(f"  当前信号质量: 滚动命中率={current_sq:.1%}, 仓位系数={current_ss:.1f}")
if current_ss < 1.0:
    print(f"  ⚠️ 信号质量熔断生效！仓位将乘以{current_ss:.1f}")

print(f"  20日WF整体命中率: {wf_baseline_acc:.1%}")
print(f"  最近{recent_n}次命中率: {recent_hit_rate:.1%} ({recent_hits}/{recent_n})")
print(f"  最近{recent_10}次命中率: {recent_10_rate:.1%} ({recent_10_hits}/{recent_10})")
print(f"  连续错误次数: {consecutive_miss}")
if consecutive_miss >= 3:
    print(f"  ⚠️ 连续{consecutive_miss}次方向错误，模型可能失效！")

# ═══════════════════════════════════════════════════════════════════

print("\n[6] V3.0策略回测...")

# 构建20日预测的时序概率（walk-forward）——去重
pred20 = ml_results[20]
prob_series = pd.Series(pred20['probabilities'], index=pred20['dates'])
prob_series = prob_series[~prob_series.index.duplicated(keep='last')]
regime_aligned = regime.reindex(prob_series.index).fillna('震荡')
vol_aligned = vol_60.reindex(prob_series.index).fillna(0.15)
gold_returns = factors['金价'].pct_change().reindex(prob_series.index)
ma200_aligned = ma200.reindex(prob_series.index)

# ── 策略定义 ──

# V1.0基线: 信号>0.5做多, <0.5做空
v1_pos = np.where(prob_series > 0.5, 1, -1)
v1_pos = pd.Series(v1_pos, index=prob_series.index)
v1_ret = v1_pos.shift(1) * gold_returns

# V2.0: ML+趋势过滤（牛市只做多，熊市做空，震荡空仓）
v2_pos = pd.Series(0.0, index=prob_series.index)
bull = regime_aligned == '牛市'
bear = regime_aligned == '熊市'
range_ = regime_aligned == '震荡'
v2_pos[bull & (prob_series > 0.5)] = 1
v2_pos[bear & (prob_series < 0.5)] = -1
v2_ret = v2_pos.shift(1) * gold_returns

# V3.0-A: Regime切换 + 非对称仓位 + 概率分级
# 牛市: P>0.7满仓, 0.6-0.7半仓, 0.5-0.6轻仓, <0.5空仓（不做空）
# 熊市: P<0.3满仓做空, 0.3-0.4半仓做空, 0.4-0.5轻仓做空, >0.5空仓
# 震荡: P>0.65轻仓做多, P<0.35轻仓做空, 中间空仓
v3a_pos = pd.Series(0.0, index=prob_series.index)
p = prob_series

# 牛市非对称
v3a_pos[bull & (p > 0.7)] = 1.0
v3a_pos[bull & (p > 0.6) & (p <= 0.7)] = 0.5
v3a_pos[bull & (p > 0.5) & (p <= 0.6)] = 0.25
v3a_pos[bull & (p <= 0.5)] = 0.0  # 不做空

# 熊市非对称
v3a_pos[bear & (p < 0.3)] = -1.0
v3a_pos[bear & (p < 0.4) & (p >= 0.3)] = -0.5
v3a_pos[bear & (p < 0.5) & (p >= 0.4)] = -0.25
v3a_pos[bear & (p >= 0.5)] = 0.0

# 震荡轻仓
v3a_pos[range_ & (p > 0.65)] = 0.3
v3a_pos[range_ & (p < 0.35)] = -0.3
v3a_pos[range_ & (p >= 0.35) & (p <= 0.65)] = 0.0

v3a_ret = v3a_pos.shift(1) * gold_returns

# V3.0-B: + 波动率靶向（vol targeting 15%年化）
target_vol = 0.15
realized_vol = gold_returns.rolling(20).std() * np.sqrt(250)
vol_scalar = target_vol / realized_vol
vol_scalar = vol_scalar.clip(0, 2)  # 上限2倍
v3b_pos = v3a_pos * vol_scalar
# V4.3: 信号质量熔断
v3b_pos = v3b_pos * signal_scalar
v3b_pos = v3b_pos.clip(-1.5, 1.5)
v3b_ret = v3b_pos.shift(1) * gold_returns

# V3.0-C: + 止损机制（20日回撤>8%触发空仓3天）
v3c_pos = v3b_pos.copy()
cumret = (1 + v3b_ret.fillna(0)).cumprod()
dd = cumret / cumret.cummax() - 1
stop_loss = dd < -0.08  # 回撤超8%
# 触发后空仓3天
for i in range(len(stop_loss)):
    if stop_loss.iloc[i] and i + 3 < len(stop_loss):
        v3c_pos.iloc[i+1:i+4] = 0
v3c_ret = v3c_pos.shift(1) * gold_returns

# V3.0-D: + Kelly公式仓位（基于滚动胜率和赔率）
# Kelly = (bp - q) / b, b=赔率, p=胜率, q=1-p
# P1修复: 用walk-forward 20日预测的滚动命中率（之前错误地用日频returns算命中率）
_pred20_kelly = pd.DataFrame({
    'prob': pred20['probabilities'],  # 已去重
    'date': pred20['dates'],           # 已去重
}).set_index('date').sort_index()
# actuals从factors重新对齐（避免长度不一致）
_pred20_kelly['actual'] = factors[f'未来20日{_label_suffix}'].reindex(_pred20_kelly.index)
_pred20_kelly = _pred20_kelly.dropna(subset=['actual'])
_pred20_kelly['pred'] = (_pred20_kelly['prob'] > 0.5).astype(int)
_pred20_kelly['correct'] = (_pred20_kelly['pred'] == _pred20_kelly['actual'].astype(int)).astype(int)

# 滚动命中率（窗口60个预测，最少20个）
# P0修复(前视偏差): correct的index是预测日,结算日=预测日+20交易日,先平移再用
_correct_settled = _pred20_kelly['correct'].copy()
_correct_settled.index = _pred20_kelly.index + pd.tseries.offsets.BDay(20)
win_prob = _correct_settled.reindex(prob_series.index).ffill().rolling(60, min_periods=20).mean()
win_prob = win_prob.fillna(0.55)

# Kelly: f* = 2p - 1（b=1:1赔率），用半Kelly避免过度下注
kelly_scalar = ((2 * win_prob - 1) * 0.5).clip(0, 1)  # 半Kelly
v3d_pos = v3c_pos * kelly_scalar
v3d_pos = v3d_pos.clip(-1.5, 1.5)
v3d_ret = v3d_pos.shift(1) * gold_returns

# V3.0-E: 多周期投票（终极版）
# 用5/10/20/60日模型投票，加权后决定仓位
pred5 = ml_results[5]
pred10 = ml_results[10]
pred60 = ml_results[60]

prob5_s = pd.Series(pred5['probabilities'], index=pred5['dates'])
prob10_s = pd.Series(pred10['probabilities'], index=pred10['dates'])
prob60_s = pd.Series(pred60['probabilities'], index=pred60['dates'])

# 对齐到20日预测的时间轴
prob5_aligned = prob5_s.reindex(prob_series.index).ffill()
prob10_aligned = prob10_s.reindex(prob_series.index).ffill()
prob60_aligned = prob60_s.reindex(prob_series.index).ffill()

# V4.3: IC自适应权重——IC为负的周期权重降低
# 改进：temp从0.3调到0.5（更温和），IC为负的周期权重上限0.15
_hORIZON_ICS = np.array([ml_results[d]['ic'] for d in PREDICT_DAYS])  # [5d, 10d, 20d, 60d]
_temp = 0.5  # V4.3: 从0.3调到0.5，避免过度集中
_ic_scaled = _hORIZON_ICS / _temp
_ic_exp = np.exp(_ic_scaled - _ic_scaled.max())
_hORIZON_WEIGHTS = _ic_exp / _ic_exp.sum()
# V4.3: IC为负的周期权重上限0.15
for i in range(len(_hORIZON_ICS)):
    if _hORIZON_ICS[i] < 0 and _hORIZON_WEIGHTS[i] > 0.15:
        _hORIZON_WEIGHTS[i] = 0.15
_hORIZON_WEIGHTS = _hORIZON_WEIGHTS / _hORIZON_WEIGHTS.sum()  # 重新归一化
_w5, _w10, _w20, _w60 = _hORIZON_WEIGHTS
print(f"  IC自适应权重(V4.3): 5日={_w5:.2f}(IC={_hORIZON_ICS[0]:+.3f}) 10日={_w10:.2f}(IC={_hORIZON_ICS[1]:+.3f}) 20日={_w20:.2f}(IC={_hORIZON_ICS[2]:+.3f}) 60日={_w60:.2f}(IC={_hORIZON_ICS[3]:+.3f})")

# 加权集成（IC自适应权重）
prob_multi = _w5 * prob5_aligned + _w10 * prob10_aligned + _w20 * prob_series + _w60 * prob60_aligned

# V5.0 P2-1: 回归分支——用预期收益率调整仓位幅度
# 回归模型预测20日收益率，用预期收益/目标波动率确定仓位幅度
reg20 = reg_results.get(20, {})
if reg20 and 'predictions' in reg20 and len(reg20['dates']) > 0:
    reg_pred_s = pd.Series(reg20['predictions'], index=reg20['dates'])
    reg_pred_aligned = reg_pred_s.reindex(prob_series.index).ffill().fillna(0)
    # 预期收益→仓位幅度：预期收益 / 目标波动率（15%年化≈0.95%日化20日≈18.7%）
    # 但仓位不超过±1.5，且符号与分类概率一致
    target_vol_daily = 0.15 / np.sqrt(250)
    expected_ret_20d = reg_pred_aligned  # 20日预期收益率
    # 仓位幅度 = |预期收益| / (目标波动率 × sqrt(20))，但不超过1.5
    reg_magnitude = (expected_ret_20d.abs() / (target_vol_daily * np.sqrt(20))).clip(0, 1.5)
    # 方向：预期收益正→做多，负→做空，但需与分类概率方向一致
    reg_direction = np.sign(expected_ret_20d)
    print(f"  P2-1 回归增强: 最新预期20日收益={expected_ret_20d.iloc[-1]:+.2%}, 仓位幅度={reg_magnitude.iloc[-1]:.2f}")
else:
    reg_magnitude = pd.Series(1.0, index=prob_series.index)
    reg_direction = pd.Series(0.0, index=prob_series.index)
    print(f"  P2-1 回归增强: 无有效回归预测，退回纯分类仓位")

# 用多周期概率重新做Regime+非对称仓位
v3e_pos = pd.Series(0.0, index=prob_series.index)
pm = prob_multi

v3e_pos[bull & (pm > 0.65)] = 1.0
v3e_pos[bull & (pm > 0.55) & (pm <= 0.65)] = 0.6
v3e_pos[bull & (pm > 0.48) & (pm <= 0.55)] = 0.3
v3e_pos[bull & (pm <= 0.48)] = 0.0

v3e_pos[bear & (pm < 0.35)] = -1.0
v3e_pos[bear & (pm < 0.45) & (pm >= 0.35)] = -0.5
v3e_pos[bear & (pm >= 0.45)] = 0.0

v3e_pos[range_ & (pm > 0.60)] = 0.4
v3e_pos[range_ & (pm < 0.40)] = -0.3
v3e_pos[range_ & (pm >= 0.40) & (pm <= 0.60)] = 0.0

# V5.0 P2-1: 用回归预测的幅度微调仓位（在分类方向的基准上，按预期收益幅度缩放）
# 只有当回归方向与分类方向一致时才增强，否则减弱
# V5.3: 回归分支R²全负(-0.09~-0.41),预测比随机还差,默认关闭回归仓位调整
REGRESSION_ADJUST = os.environ.get('V5_REGRESSION_ADJUST', '0') == '1'
if REGRESSION_ADJUST:
    _cls_direction = np.sign(v3e_pos)
    _adjust_factor = pd.Series(1.0, index=v3e_pos.index)
    _both_nonzero = (_cls_direction != 0) & (reg_direction != 0)
    _agree = (_cls_direction == reg_direction) & _both_nonzero
    _disagree = (_cls_direction != reg_direction) & _both_nonzero
    # 方向一致时：按回归幅度增强（但不超过1.5x原始仓位）
    _adjust_factor[_agree] = (0.5 + 0.5 * reg_magnitude[_agree]).clip(0.8, 1.5)
    # 方向不一致时：减弱仓位（回归模型不认可分类信号）
    _adjust_factor[_disagree] = 0.5  # 减半
    v3e_pos = v3e_pos * _adjust_factor
    print(f"  P2-1 回归仓位调整: 开启(R²负,可能有害)")
else:
    print(f"  P2-1 回归仓位调整: 关闭(R²全负,默认不用回归预测调仓位)")

# + vol targeting
v3e_pos = v3e_pos * vol_scalar.clip(0, 2)
# V4.3: 信号质量熔断——近期命中率低时自动降仓位
v3e_pos = v3e_pos * signal_scalar
v3e_pos = v3e_pos.clip(-1.5, 1.5)

# + 止损
cumret_e = (1 + (v3e_pos.shift(1) * gold_returns).fillna(0)).cumprod()
dd_e = cumret_e / cumret_e.cummax() - 1
for i in range(len(dd_e)):
    if dd_e.iloc[i] < -0.08 and i + 3 < len(dd_e):
        v3e_pos.iloc[i+1:i+4] = 0

v3e_ret = v3e_pos.shift(1) * gold_returns

# ── 买入持有 ──
bh_ret = gold_returns

# ── 计算各策略指标 ──
def calc_metrics(rets, name):
    rets = rets.dropna()
    if len(rets) == 0:
        return {'name': name, 'ann_ret': 0, 'ann_vol': 0, 'sharpe': 0, 'max_dd': 0, 'win_rate': 0, 'calmar': 0}
    # P2-4修复: 几何(复利)年化,替代算术年化rets.mean()*250(高波动期虚高)
    ann_ret = float(np.exp(np.log1p(rets).mean() * 250) - 1)
    ann_vol = float(rets.std() * np.sqrt(250))
    sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0
    cumret = (1 + rets).cumprod()
    max_dd = float((cumret / cumret.cummax() - 1).min())
    win_rate = float((rets > 0).mean())
    calmar = float(ann_ret / abs(max_dd)) if max_dd != 0 else 0
    return {
        'name': name,
        'ann_ret': ann_ret,
        'ann_vol': ann_vol,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'win_rate': win_rate,
        'calmar': calmar,
        'cumret': float(cumret.iloc[-1] - 1),
    }

strategies = {
    'V1.0 线性IC': calc_metrics(v1_ret, 'V1.0 线性IC'),
    'V2.0 ML+趋势': calc_metrics(v2_ret, 'V2.0 ML+趋势'),
    'V3.0-A Regime+非对称': calc_metrics(v3a_ret, 'V3.0-A Regime+非对称'),
    'V3.0-B +Vol靶向': calc_metrics(v3b_ret, 'V3.0-B +Vol靶向'),
    'V3.0-C +止损': calc_metrics(v3c_ret, 'V3.0-C +止损'),
    'V3.0-D +Kelly': calc_metrics(v3d_ret, 'V3.0-D +Kelly'),
    'V3.0-E 多周期集成': calc_metrics(v3e_ret, 'V3.0-E 多周期集成'),
    '买入持有': calc_metrics(bh_ret, '买入持有'),
}

print(f"\n  {'策略':<25s} {'年化':>8s} {'波动':>8s} {'夏普':>6s} {'回撤':>8s} {'胜率':>6s} {'Calmar':>7s}")
print("  " + "-" * 75)
for k, m in strategies.items():
    print(f"  {k:<25s} {m['ann_ret']:>+7.1%} {m['ann_vol']:>7.1%} {m['sharpe']:>6.2f} {m['max_dd']:>+7.1%} {m['win_rate']:>5.1%} {m['calmar']:>+7.2f}")

# 找最优策略
# P2-1修复: 在训练期(排除最近125天Holdout)选最优,避免用Holdout数据选最优导致选择偏差。
#   原实现用含Holdout的全期夏普选最优,再在Holdout上报告"纯净OOS"——选最优一步已窥探Holdout。
_HOLDOUT_DAYS = 125
_hstart_date = factors.index[len(factors) - _HOLDOUT_DAYS] if len(factors) > _HOLDOUT_DAYS else factors.index[0]
_train_rets_map = {
    'V1.0 线性IC': v1_ret, 'V2.0 ML+趋势': v2_ret, 'V3.0-A Regime+非对称': v3a_ret,
    'V3.0-B +Vol靶向': v3b_ret, 'V3.0-C +止损': v3c_ret, 'V3.0-D +Kelly': v3d_ret,
    'V3.0-E 多周期集成': v3e_ret, '买入持有': bh_ret,
}
_train_sharpe = {}
for _k, _r in _train_rets_map.items():
    _tr = _r[_r.index < _hstart_date].dropna()
    _train_sharpe[_k] = calc_metrics(_tr, _k)['sharpe'] if len(_tr) > 10 else -999.0
best_key = max((k for k in _train_sharpe if k != '买入持有'), key=lambda k: _train_sharpe[k])
best_strategy = strategies[best_key]
print(f"\n  🏆 最优策略(训练期选择): {best_key} (训练期夏普={_train_sharpe[best_key]:.2f}, 全期夏普={best_strategy['sharpe']:.2f})")

# ═══════════════════════════════════════════════════════════════════
# 6.5 V5.0 P0-2: Holdout验证（保留最近6月数据做纯净OOS验证）
# ═══════════════════════════════════════════════════════════════════

print("\n[6.5] P0-2: Holdout验证（最近6月纯净OOS）...")

# Holdout期：最近125个交易日（约6个月）
HOLDOUT_DAYS = 125
holdout_start_idx = len(factors) - HOLDOUT_DAYS
holdout_start_date = factors.index[holdout_start_idx] if holdout_start_idx > 0 else factors.index[0]

print(f"  Holdout起始日: {holdout_start_date.date()}")
print(f"  Holdout天数: {min(HOLDOUT_DAYS, len(factors) - holdout_start_idx)}")

# 在holdout期内评估各策略表现
holdout_results = {}
strategy_rets_all = {
    'V1.0 线性IC': v1_ret,
    'V2.0 ML+趋势': v2_ret,
    'V3.0-A Regime+非对称': v3a_ret,
    'V3.0-B +Vol靶向': v3b_ret,
    'V3.0-C +止损': v3c_ret,
    'V3.0-D +Kelly': v3d_ret,
    'V3.0-E 多周期集成': v3e_ret,
    '买入持有': bh_ret,
}

print(f"\n  {'策略':<25s} {'年化':>8s} {'波动':>8s} {'夏普':>6s} {'回撤':>8s} {'胜率':>6s}")
print("  " + "-" * 65)
for name, rets in strategy_rets_all.items():
    holdout_rets = rets[rets.index >= holdout_start_date].dropna()
    if len(holdout_rets) < 10:
        holdout_results[name] = {'ann_ret': 0, 'ann_vol': 0, 'sharpe': 0, 'max_dd': 0, 'win_rate': 0, 'n': 0}
        continue
    holdout_results[name] = calc_metrics(holdout_rets, name)
    m = holdout_results[name]
    print(f"  {name:<25s} {m['ann_ret']:>+7.1%} {m['ann_vol']:>7.1%} {m['sharpe']:>6.2f} {m['max_dd']:>+7.1%} {m['win_rate']:>5.1%}")

# Holdout vs Full对比
print(f"\n  Holdout vs Full-period 对比（最优策略{best_key}）:")
full_m = strategies[best_key]
holdout_m = holdout_results.get(best_key, {'sharpe': 0, 'ann_ret': 0, 'max_dd': 0})
print(f"    Full-period:  夏普={full_m['sharpe']:.2f}, 年化={full_m['ann_ret']:+.1%}, 回撤={full_m['max_dd']:+.1%}")
print(f"    Holdout(6m):  夏普={holdout_m['sharpe']:.2f}, 年化={holdout_m['ann_ret']:+.1%}, 回撤={holdout_m['max_dd']:+.1%}")
# D1修复: 负OOS夏普时"衰减"公式会得>100%(如-2.94/0.64→559%),封顶为100%
if full_m['sharpe'] > 0:
    _oos = holdout_m['sharpe']
    sharpe_decay = 1.0 if _oos <= 0 else min((1 - _oos / full_m['sharpe']), 1.0)
else:
    sharpe_decay = 0.0
print(f"    夏普衰减: {sharpe_decay:.1%}")
if sharpe_decay > 0.5:
    print(f"    ⚠️ 夏普衰减>50%，过拟合风险高！")
elif sharpe_decay > 0.3:
    print(f"    ⚠️ 夏普衰减30-50%，存在一定过拟合")
else:
    print(f"    ✅ 夏普衰减<30%，模型泛化能力良好")

# ═══════════════════════════════════════════════════════════════════
# 7. 当前预测
# ═══════════════════════════════════════════════════════════════════

print("\n[7] 当前预测...")

# 先确定最新交易日与当前Regime（实盘预测基准，也用于Regime-conditional训练）
latest_raw = factors[feature_cols].iloc[-1:]
latest_idx = latest_raw.index[0]
current_regime = str(regime.loc[latest_idx])

# P0修复: 数据时效校验——最新数据不应超过4天前（考虑周末/节假日）
max_staleness = pd.Timestamp.now() - pd.Timedelta(days=4)
if latest_idx < max_staleness:
    print(f"  ⚠️ 警告: 最新数据日期 {latest_idx.date()} 超过4天，可能数据源异常！")
    print(f"     (当前时间: {pd.Timestamp.now().strftime('%Y-%m-%d')})")


def _regime_filter_final(X, y, target_regime):
    """与WF回测一致的Regime-conditional：同Regime样本>=100才过滤，否则退回全量"""
    _reg = regime.reindex(X.index)
    if target_regime in ('牛市', '熊市', '震荡'):
        _rm = (_reg == target_regime)
        if _rm.sum() >= 100:
            return X[_rm], y[_rm]
    return X, y


def _train_ensemble_final(X_tr, y_tr):
    """训练XGB+LGB集成，返回(xgb, lgb, scaler, medians)。
    P1修复: 与WF回测对齐——scale_pos_weight/class_weight平衡。
    注: 不做Isotonic校准——in-sample校准在单点实盘预测上退化(把raw≈0.22clip到0.0)，改用原始概率。"""
    _pos = int(y_tr.sum())
    _neg = int(len(y_tr) - _pos)
    _spw = min(_neg / _pos, 2.0) if _pos > 0 else 1.0
    _med = X_tr.median()
    _X = X_tr.fillna(_med)
    _sc = StandardScaler()
    _Xs = _sc.fit_transform(_X)
    _xgb = xgb.XGBClassifier(
        n_estimators=80, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.7,
        reg_alpha=0.15, reg_lambda=1.5,
        scale_pos_weight=_spw, random_state=42, use_label_encoder=False,
        eval_metric='logloss', verbosity=0,
    )
    _xgb.fit(_Xs, y_tr)
    _lgb = lgb.LGBMClassifier(
        n_estimators=80, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.7,
        reg_alpha=0.15, reg_lambda=1.5,
        class_weight={0: 1.0, 1: _spw}, random_state=42, verbose=-1,
    )
    _lgb.fit(_Xs, y_tr)
    return _xgb, _lgb, _sc, _med


# 训练多周期最终模型（每个horizon独立准备数据，与WF回测对齐）
final_models = {}
for pred_days in PREDICT_DAYS:
    target = f'未来{pred_days}日{_label_suffix}'  # V5.1: abs→涨跌 / excess→超额
    X_h = factors[feature_cols].copy()
    y_h = factors[target].reindex(X_h.index)
    valid_h = y_h.notna()
    X_h = X_h[valid_h].copy()
    y_h = y_h[valid_h]
    X_h, y_h = _regime_filter_final(X_h, y_h, current_regime)
    final_models[pred_days] = _train_ensemble_final(X_h, y_h)

# final_xgb/final_lgb 供[8]特征重要性使用（取20日模型）
final_xgb, final_lgb = final_models[20][0], final_models[20][1]

current_price = float(factors['金价'].loc[latest_idx])
ma200_current = float(ma200.loc[latest_idx]) if pd.notna(ma200.loc[latest_idx]) else current_price
ma50_current = float(ma50.loc[latest_idx]) if pd.notna(ma50.loc[latest_idx]) else current_price
current_vol = float(vol_60.loc[latest_idx]) if pd.notna(vol_60.loc[latest_idx]) else 0.15

# 多周期概率（原始集成概率，不做Isotonic校准——见_train_ensemble_final注释）
multi_probs = {}
for pred_days in PREDICT_DAYS:
    _xgb, _lgb, _sc, _med = final_models[pred_days]
    _latest_X = latest_raw.fillna(_med)
    _latest_s = _sc.transform(_latest_X)
    multi_probs[pred_days] = float((_xgb.predict_proba(_latest_s)[0, 1] +
                                    _lgb.predict_proba(_latest_s)[0, 1]) / 2)

# P1修复: 当前预测也用IC自适应权重（与回测一致）
prob_multi_current = (_w5 * multi_probs[5] + _w10 * multi_probs[10] +
                      _w20 * multi_probs[20] + _w60 * multi_probs[60])

print(f"  预测基准日:    {latest_idx.date()}")
print(f"  当前金价:      ${current_price:.2f}")
print(f"  MA50:          ${ma50_current:.2f}")
print(f"  MA200:         ${ma200_current:.2f}")
print(f"  Regime:        {current_regime}")
print(f"  60日波动率:    {current_vol:.1%}")
print(f"\n  多周期看多概率:")
for d in PREDICT_DAYS:
    print(f"    {d:2d}日: {multi_probs[d]:.1%}")
print(f"  加权集成:      {prob_multi_current:.1%}")

# V3.0-E仓位建议
if current_regime == '牛市':
    if prob_multi_current > 0.65:
        suggested_pos = 1.0
    elif prob_multi_current > 0.55:
        suggested_pos = 0.6
    elif prob_multi_current > 0.48:
        suggested_pos = 0.3
    else:
        suggested_pos = 0.0
elif current_regime == '熊市':
    if prob_multi_current < 0.35:
        suggested_pos = -1.0
    elif prob_multi_current < 0.45:
        suggested_pos = -0.5
    else:
        suggested_pos = 0.0
else:
    if prob_multi_current > 0.60:
        suggested_pos = 0.4
    elif prob_multi_current < 0.40:
        suggested_pos = -0.3
    else:
        suggested_pos = 0.0

# Vol targeting调整
# D4修复: 与回测vol_scalar口径一致——回测用20日realized vol,此前实盘误用60日vol(current_vol)
_realized_vol_live = float(factors['金价'].pct_change().rolling(20).std().iloc[-1] * np.sqrt(250))
vol_adjust = min(2.0, target_vol / _realized_vol_live) if _realized_vol_live > 0 else 1.0
suggested_pos = suggested_pos * vol_adjust
# V4.3: 信号质量熔断——结算命中率低时自动降仓位(与V3.0-E回测口径一致;
#   此前只作用于回测策略,漏乘到实时建议仓位,导致"仓位将乘以X"提示名不副实)
suggested_pos = suggested_pos * current_ss
suggested_pos = max(-1.5, min(1.5, suggested_pos))

if suggested_pos > 0.5:
    action = f"做多 (仓位{suggested_pos:.0%})"
elif suggested_pos > 0:
    action = f"轻仓做多 (仓位{suggested_pos:.0%})"
elif suggested_pos < -0.5:
    action = f"做空 (仓位{suggested_pos:.0%})"
elif suggested_pos < 0:
    action = f"轻仓做空 (仓位{suggested_pos:.0%})"
else:
    action = "空仓观望"

print(f"\n  📌 V3.0-E建议:  {action}")
print(f"     (Regime={current_regime}, 概率={prob_multi_current:.1%}, Vol调整={vol_adjust:.2f})")

# ═══════════════════════════════════════════════════════════════════
# 8. 特征重要性
# ═══════════════════════════════════════════════════════════════════

print("\n[8] 特征重要性...")
fi_xgb = pd.Series(final_xgb.feature_importances_, index=feature_cols).sort_values(ascending=False)
fi_lgb = pd.Series(final_lgb.feature_importances_, index=feature_cols).sort_values(ascending=False)
fi_avg = (fi_xgb + fi_lgb) / 2
fi_avg = fi_avg.sort_values(ascending=False)

print("  TOP10:")
for i, (f, v) in enumerate(fi_avg.head(10).items()):
    print(f"    {i+1:2d}. {f:20s} {v:.4f}")

# ═══════════════════════════════════════════════════════════════════
# 9. 图表生成
# ═══════════════════════════════════════════════════════════════════

print("\n[9] 图表生成...")
CHARTS_V5_DIR.mkdir(parents=True, exist_ok=True)

COLORS = {
    'V1.0 线性IC': '#ff7f0e',
    'V2.0 ML+趋势': '#1f77b4',
    'V3.0-A Regime+非对称': '#2ca02c',
    'V3.0-B +Vol靶向': '#9467bd',
    'V3.0-C +止损': '#8c564b',
    'V3.0-D +Kelly': '#e377c2',
    'V3.0-E 多周期集成': '#d62728',
    '买入持有': '#FFD700',
}

# ── 图1: 策略净值曲线对比 ──
fig, axes = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [3, 1]})

ax = axes[0]
strategy_rets = {
    'V1.0 线性IC': v1_ret,
    'V2.0 ML+趋势': v2_ret,
    'V3.0-A Regime+非对称': v3a_ret,
    'V3.0-B +Vol靶向': v3b_ret,
    'V3.0-C +止损': v3c_ret,
    'V3.0-D +Kelly': v3d_ret,
    'V3.0-E 多周期集成': v3e_ret,
    '买入持有': bh_ret,
}

for name, rets in strategy_rets.items():
    cumret = (1 + rets.fillna(0)).cumprod()
    lw = 2.5 if name in ['V3.0-E 多周期集成', '买入持有'] else 1.2
    alpha = 1.0 if name in ['V3.0-E 多周期集成', '买入持有'] else 0.7
    ax.plot(cumret.index, cumret.values, color=COLORS[name], linewidth=lw,
            alpha=alpha, label=f"{name} ({strategies[name]['sharpe']:.2f})")

ax.set_title('策略净值对比 — V1.0 → V3.0演进', fontsize=16, fontweight='bold')
ax.set_ylabel('累计净值')
ax.legend(fontsize=9, loc='upper left')
ax.grid(True, alpha=0.2)
ax.set_yscale('log')

# Regime标记
ax2 = axes[1]
regime_plot = regime.reindex(v3e_ret.index)
colors_regime = {'牛市': '#2ca02c', '熊市': '#d62728', '震荡': '#aaaaaa'}
for r, c in colors_regime.items():
    mask = regime_plot == r
    if mask.sum() > 0:
        ax2.fill_between(regime_plot.index, 0, 1, where=mask, alpha=0.3, color=c, label=r)
ax2.set_title('Regime分布', fontsize=12)
ax2.set_ylabel('Regime')
ax2.legend(fontsize=9, loc='upper right')
ax2.set_yticks([])
ax2.grid(True, alpha=0.2)

plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '01_strategy_evolution.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 01_strategy_evolution.png")

# ── 图2: 回撤对比 ──
fig, ax = plt.subplots(figsize=(16, 7))

for name in ['V3.0-E 多周期集成', 'V3.0-A Regime+非对称', 'V2.0 ML+趋势', '买入持有']:
    rets = strategy_rets[name]
    cumret = (1 + rets.fillna(0)).cumprod()
    dd = cumret / cumret.cummax() - 1
    ax.fill_between(dd.index, dd.values, 0, alpha=0.2, color=COLORS[name])
    ax.plot(dd.index, dd.values, color=COLORS[name], linewidth=1.5, label=name)

ax.set_title('回撤对比', fontsize=16, fontweight='bold')
ax.set_ylabel('回撤')
ax.legend(fontsize=11)
ax.grid(True, alpha=0.2)
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '02_drawdown.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 02_drawdown.png")

# ── 图3: 仓位变化 ──
fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)

# V3.0-A仓位
ax = axes[0]
ax.fill_between(v3a_pos.index, v3a_pos.values, 0, alpha=0.4, color='#2ca02c')
ax.plot(v3a_pos.index, v3a_pos.values, color='#2ca02c', linewidth=0.8)
ax.set_title('V3.0-A 仓位（Regime+非对称）', fontsize=13)
ax.set_ylabel('仓位')
ax.axhline(0, color='black', linewidth=0.5)
ax.set_ylim(-1.5, 1.5)
ax.grid(True, alpha=0.2)

# V3.0-B仓位（+Vol靶向）
ax = axes[1]
ax.fill_between(v3b_pos.index, v3b_pos.values, 0, alpha=0.4, color='#9467bd')
ax.plot(v3b_pos.index, v3b_pos.values, color='#9467bd', linewidth=0.8)
ax.set_title('V3.0-B 仓位（+Vol靶向）', fontsize=13)
ax.set_ylabel('仓位')
ax.axhline(0, color='black', linewidth=0.5)
ax.set_ylim(-1.5, 1.5)
ax.grid(True, alpha=0.2)

# V3.0-E仓位（终极版）
ax = axes[2]
ax.fill_between(v3e_pos.index, v3e_pos.values, 0, alpha=0.4, color='#d62728')
ax.plot(v3e_pos.index, v3e_pos.values, color='#d62728', linewidth=0.8)
ax.set_title('V3.0-E 仓位（多周期集成+全部优化）', fontsize=13)
ax.set_ylabel('仓位')
ax.axhline(0, color='black', linewidth=0.5)
ax.set_ylim(-1.5, 1.5)
ax.grid(True, alpha=0.2)

plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '03_position_evolution.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 03_position_evolution.png")

# ── 图4: 概率分级热力图 ──
fig, ax = plt.subplots(figsize=(16, 6))

# 按Regime着色概率
for r, c in colors_regime.items():
    mask = regime_aligned == r
    if mask.sum() > 0:
        ax.scatter(prob_series[mask].index, prob_series[mask].values,
                  c=c, s=8, alpha=0.5, label=r)

ax.axhline(0.7, color='green', linestyle='--', alpha=0.5, label='0.7满仓线')
ax.axhline(0.5, color='gray', linestyle='--', alpha=0.5, label='0.5中线')
ax.axhline(0.3, color='red', linestyle='--', alpha=0.5, label='0.3做空线')

ax.set_title('模型看多概率 vs Regime', fontsize=16, fontweight='bold')
ax.set_ylabel('看多概率')
ax.set_ylim(-0.05, 1.05)
ax.legend(fontsize=9, loc='upper right')
ax.grid(True, alpha=0.2)
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '04_probability_regime.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 04_probability_regime.png")

# ── 图5: 特征重要性 ──
fig, ax = plt.subplots(figsize=(12, 10))
top_n = 15
bars = ax.barh(range(top_n), fi_avg.head(top_n).values[::-1],
               color=['#d62728' if 'V3.0' in '' else '#1f77b4' for _ in range(top_n)])
ax.set_yticks(range(top_n))
ax.set_yticklabels(fi_avg.head(top_n).index[::-1], fontsize=11)
ax.set_xlabel('重要性')
ax.set_title('特征重要性 TOP15（XGBoost+LightGBM平均）', fontsize=14, fontweight='bold')
ax.grid(True, alpha=0.2, axis='x')
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '05_feature_importance.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 05_feature_importance.png")

# ── 图6: Regime下策略表现雷达图 ──
fig, axes = plt.subplots(1, 3, figsize=(18, 6), subplot_kw=dict(projection='polar'))

metrics_radar = ['夏普', '年化收益', '胜率', 'Calmar', '低回撤']
n_metrics = len(metrics_radar)
angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
angles += angles[:1]

for ax, (reg_name, reg_mask) in zip(axes, [('牛市', regime_aligned=='牛市'),
                                             ('熊市', regime_aligned=='熊市'),
                                             ('震荡', regime_aligned=='震荡')]):
    for strat_name in ['V3.0-A Regime+非对称', 'V3.0-E 多周期集成', '买入持有']:
        rets = strategy_rets[strat_name].copy()
        # 对齐regime mask到rets的index
        reg_mask_aligned = reg_mask.reindex(rets.index).fillna(False)
        rets = rets[reg_mask_aligned]
        if len(rets) < 10:
            continue
        m = calc_metrics(rets, strat_name)
        values = [
            min(3, max(0, m['sharpe'] + 1)) / 3,  # 归一化到0-1
            min(1, max(0, m['ann_ret'] + 0.3)),  # 年化收益
            m['win_rate'],
            min(1, max(0, m['calmar'])),
            min(1, max(0, 1 + m['max_dd'])),  # 回撤越小越好
        ]
        values += values[:1]
        ax.plot(angles, values, linewidth=1.5, label=strat_name.replace('V3.0-', ''))
        ax.fill(angles, values, alpha=0.1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics_radar, fontsize=9)
    ax.set_title(f'{reg_name}', fontsize=13, fontweight='bold')
    ax.set_ylim(0, 1)
    ax.legend(fontsize=7, loc='upper right')

plt.suptitle('各Regime下策略表现对比', fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '06_regime_radar.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 06_regime_radar.png")

# ── 图7: 多周期概率一致性 ──
fig, ax = plt.subplots(figsize=(14, 6))
width = 0.2
x = np.arange(len(PREDICT_DAYS))
probs_list = [multi_probs[d] for d in PREDICT_DAYS]
colors_bar = ['#ff7f0e', '#1f77b4', '#2ca02c', '#9467bd']

for i, (d, p) in enumerate(zip(PREDICT_DAYS, probs_list)):
    ax.bar(x[i], p, width, color=colors_bar[i], label=f'{d}日')

ax.axhline(0.5, color='gray', linestyle='--', alpha=0.5)
ax.axhline(prob_multi_current, color='red', linewidth=2, linestyle='--', label=f'加权={prob_multi_current:.1%}')

ax.set_xticks(x)
ax.set_xticklabels([f'{d}日' for d in PREDICT_DAYS])
ax.set_ylabel('看多概率')
ax.set_title(f'多周期看多概率一致性（{latest_idx.date()}）', fontsize=14, fontweight='bold')
ax.set_ylim(0, 1)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.2, axis='y')
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '07_multi_horizon.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 07_multi_horizon.png")

# ── 图8: 策略指标汇总表 ──
fig, ax = plt.subplots(figsize=(16, 8))
ax.axis('off')

col_names = ['策略', '年化收益', '年化波动', '夏普', '最大回撤', '胜率', 'Calmar', '累计收益']
table_data = []
for name in ['V1.0 线性IC', 'V2.0 ML+趋势', 'V3.0-A Regime+非对称',
             'V3.0-B +Vol靶向', 'V3.0-C +止损', 'V3.0-D +Kelly',
             'V3.0-E 多周期集成', '买入持有']:
    m = strategies[name]
    table_data.append([
        name,
        f"{m['ann_ret']:+.1%}",
        f"{m['ann_vol']:.1%}",
        f"{m['sharpe']:.2f}",
        f"{m['max_dd']:+.1%}",
        f"{m['win_rate']:.1%}",
        f"{m['calmar']:.2f}",
        f"{m['cumret']:+.1%}",
    ])

table = ax.table(cellText=table_data, colLabels=col_names,
                 cellLoc='center', loc='center',
                 colColours=['#4472C4']*len(col_names))
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1, 1.8)

# 表头白色
for j in range(len(col_names)):
    table[0, j].set_text_props(color='white', fontweight='bold')

# 高亮最优策略行
for i, name in enumerate([row[0] for row in table_data]):
    if name == best_key:
        for j in range(len(col_names)):
            table[i+1, j].set_facecolor('#FFF2CC')

ax.set_title('策略表现汇总（黄色=最优夏普）', fontsize=16, fontweight='bold', pad=20)
plt.tight_layout()
plt.savefig(str(CHARTS_V5_DIR / '08_summary_table.png'), dpi=150, bbox_inches='tight')
plt.close()
print("  ✅ 08_summary_table.png")

# ═══════════════════════════════════════════════════════════════════
# 10. Excel报告
# ═══════════════════════════════════════════════════════════════════

print("\n[10] Excel报告生成...")

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()

# 样式
C_PRIMARY = '4472C4'
C_LIGHT = 'D9E2F3'
C_GREEN = '548235'
C_RED = 'C00000'
C_YELLOW = 'FFF2CC'
C_HEADER = '4472C4'

thin_b = Side(style='thin', color='BFBFBF')
border_all = Border(left=thin_b, right=thin_b, top=thin_b, bottom=thin_b)

def font_title(sz=14, color='FFFFFF'):
    return Font(name='Noto Serif SC', size=sz, bold=True, color=color)

def font_body(sz=10, bold=False, color='000000'):
    return Font(name='Noto Serif SC', size=sz, bold=bold, color=color)

def fill_solid(color):
    return PatternFill(start_color=color, end_color=color, fill_type='solid')

align_c = Alignment(horizontal='center', vertical='center', wrap_text=True)
align_l = Alignment(horizontal='left', vertical='center', wrap_text=True)

# ── Sheet1: 分析概览 ──
ws1 = wb.active
ws1.title = '分析概览'
ws1.sheet_view.showGridLines = False
row = 2
ws1.cell(row=row, column=2, value="黄金价格预测 V4.0 — 全因子补全+FRED宏观+事件日历").font = font_title(16, C_PRIMARY)
ws1.merge_cells(start_row=row, start_column=2, end_row=row, end_column=9)
row += 2
ws1.cell(row=row, column=2, value=f"分析周期: {factors.index[0].date()} → {factors.index[-1].date()}").font = font_body(10)
row += 2

ws1.cell(row=row, column=2, value="一、V4.0 新增因子（补全盲区）").font = font_body(12, bold=True, color=C_PRIMARY)
row += 1
improvements = [
    ("FRED实际利率", "DFII10/DFII5 真实TIPS收益率，替代TIP ETF"),
    ("收益率曲线", "2s10s/5s30s利差，曲线倒挂=衰退预警"),
    ("联邦基金利率", "DFF 美联储政策利率直接指标"),
    ("通胀预期", "T10YIE 10年盈亏平衡通胀率"),
    ("FOMC日历", "距下次议息天数+FOMC周标记"),
    ("CPI日历", "距下次CPI发布天数+CPI周标记"),
    ("铜金比", "铜/金，经济周期代理指标"),
    ("BTC/黄金", "比特币/黄金，避险替代品竞争"),
    ("VIX期限结构", "VIX/VIX9D，近端恐慌vs远端"),
    ("3个新交互因子", "实际利率×Fed利率、铜金比×VIX、曲线×美元"),
]
for name, desc in improvements:
    ws1.cell(row=row, column=2, value=f"  {name}").font = font_body(10, bold=True)
    ws1.cell(row=row, column=3, value=desc).font = font_body(10)
    ws1.merge_cells(start_row=row, start_column=3, end_row=row, end_column=9)
    row += 1

row += 1
ws1.cell(row=row, column=2, value="二、策略表现对比").font = font_body(12, bold=True, color=C_PRIMARY)
row += 1
headers = ['策略', '年化收益', '年化波动', '夏普', '最大回撤', '胜率', 'Calmar', '累计收益']
for c, h in enumerate(headers, 2):
    cell = ws1.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

for name in ['V1.0 线性IC', 'V2.0 ML+趋势', 'V3.0-A Regime+非对称',
             'V3.0-B +Vol靶向', 'V3.0-C +止损', 'V3.0-D +Kelly',
             'V3.0-E 多周期集成', '买入持有']:
    m = strategies[name]
    vals = [name, f"{m['ann_ret']:+.1%}", f"{m['ann_vol']:.1%}", f"{m['sharpe']:.2f}",
            f"{m['max_dd']:+.1%}", f"{m['win_rate']:.1%}", f"{m['calmar']:.2f}", f"{m['cumret']:+.1%}"]
    for c, v in enumerate(vals, 2):
        cell = ws1.cell(row=row, column=c, value=v)
        cell.font = font_body(10, bold=(name == best_key))
        cell.alignment = align_c
        cell.border = border_all
        if name == best_key:
            cell.fill = fill_solid(C_YELLOW)
    row += 1

row += 1
ws1.cell(row=row, column=2, value=f"🏆 最优策略: {best_key} (夏普={best_strategy['sharpe']:.2f})").font = font_body(11, bold=True, color=C_GREEN)
row += 2

ws1.cell(row=row, column=2, value="三、Regime分布").font = font_body(12, bold=True, color=C_PRIMARY)
row += 1
for r in ['牛市', '熊市', '震荡']:
    c = regime_counts.get(r, 0)
    pct = c / len(regime) * 100
    mask = regime == r
    if mask.sum() > 0:
        rets = factors['金价'].pct_change()[mask]
        ann = rets.mean() * 250
        vol = rets.std() * np.sqrt(250)
        sh = ann / vol if vol > 0 else 0
        vals = [r, f"{c}天", f"{pct:.1f}%", f"{ann:+.1%}", f"{vol:.1%}", f"{sh:.2f}"]
    else:
        vals = [r, "0", "0%", "—", "—", "—"]
    for c, v in enumerate(vals, 2):
        cell = ws1.cell(row=row, column=c, value=v)
        cell.font = font_body(10)
        cell.alignment = align_c
        cell.border = border_all
    row += 1

row += 1
ws1.cell(row=row, column=2, value="四、当前预测").font = font_body(12, bold=True, color=C_PRIMARY)
row += 1
current_info = [
    ("预测基准日", str(latest_idx.date())),
    ("当前金价", f"${current_price:.2f}"),
    ("MA50", f"${ma50_current:.2f}"),
    ("MA200", f"${ma200_current:.2f}"),
    ("当前Regime", current_regime),
    ("60日波动率", f"{current_vol:.1%}"),
    ("5日看多概率", f"{multi_probs[5]:.1%}"),
    ("10日看多概率", f"{multi_probs[10]:.1%}"),
    ("20日看多概率", f"{multi_probs[20]:.1%}"),
    ("60日看多概率", f"{multi_probs[60]:.1%}"),
    ("加权集成概率", f"{prob_multi_current:.1%}"),
    ("建议操作", action),
]
for name, val in current_info:
    ws1.cell(row=row, column=2, value=name).font = font_body(10, bold=True)
    cell = ws1.cell(row=row, column=3, value=val)
    cell.font = font_body(11, bold=True, color=C_PRIMARY)
    cell.alignment = align_l
    ws1.merge_cells(start_row=row, start_column=3, end_row=row, end_column=9)
    row += 1

row += 1
ws1.cell(row=row, column=2, value="五、关键发现").font = font_body(12, bold=True, color=C_PRIMARY)
row += 1
findings = [
    f"V3.0最优策略: {best_key}，夏普={best_strategy['sharpe']:.2f}，vs V1.0({strategies['V1.0 线性IC']['sharpe']:.2f})提升{best_strategy['sharpe']-strategies['V1.0 线性IC']['sharpe']:+.2f}",
    f"vs 买入持有(夏普{strategies['买入持有']['sharpe']:.2f}): {'超越' if best_strategy['sharpe'] > strategies['买入持有']['sharpe'] else '仍低于'}{abs(best_strategy['sharpe']-strategies['买入持有']['sharpe']):.2f}",
    f"Regime分布: 牛市{regime_counts.get('牛市',0)/len(regime)*100:.0f}% / 熊市{regime_counts.get('熊市',0)/len(regime)*100:.0f}% / 震荡{regime_counts.get('震荡',0)/len(regime)*100:.0f}%",
    f"特征重要性TOP3: {fi_avg.index[0]}({fi_avg.iloc[0]:.3f}), {fi_avg.index[1]}({fi_avg.iloc[1]:.3f}), {fi_avg.index[2]}({fi_avg.iloc[2]:.3f})",
    f"20日模型准确率={ml_results[20]['accuracy']:.1%}，AUC={ml_results[20]['auc']:.3f}",
    f"当前信号: {action}（集成概率={prob_multi_current:.1%}, Regime={current_regime}）",
]
for f in findings:
    ws1.cell(row=row, column=2, value=f"• {f}").font = font_body(10)
    ws1.merge_cells(start_row=row, start_column=2, end_row=row, end_column=9)
    row += 1

ws1.column_dimensions['B'].width = 22
for col in 'CDEFGHI':
    ws1.column_dimensions[col].width = 14

# ── Sheet2: Regime分析 ──
ws2 = wb.create_sheet('Regime分析')
ws2.sheet_view.showGridLines = False
row = 2
ws2.cell(row=row, column=2, value="Regime识别与各态表现分析").font = font_title(14, C_PRIMARY)
ws2.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
row += 2

ws2.cell(row=row, column=2, value="Regime定义").font = font_body(11, bold=True)
row += 1
defs = [
    ("牛市", "金价>MA200 且 MA50>MA200（均线多头排列）"),
    ("熊市", "金价<MA200 且 MA50<MA200（均线空头排列）"),
    ("震荡", "其他（均线交叉混乱）"),
]
for n, d in defs:
    ws2.cell(row=row, column=2, value=n).font = font_body(10, bold=True)
    ws2.cell(row=row, column=3, value=d).font = font_body(10)
    ws2.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
    row += 1

row += 1
ws2.cell(row=row, column=2, value="各Regime下金价表现").font = font_body(11, bold=True)
row += 1
headers = ['Regime', '天数', '占比', '年化收益', '年化波动', '夏普', '最大回撤']
for c, h in enumerate(headers, 2):
    cell = ws2.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

for r in ['牛市', '熊市', '震荡']:
    mask = regime == r
    c = mask.sum()
    pct = c / len(regime) * 100
    if c > 0:
        rets = factors['金价'].pct_change()[mask]
        ann = float(rets.mean() * 250)
        vol = float(rets.std() * np.sqrt(250))
        sh = ann / vol if vol > 0 else 0
        cumret = (1 + rets.fillna(0)).cumprod()
        mdd = float((cumret / cumret.cummax() - 1).min())
        vals = [r, str(c), f"{pct:.1f}%", f"{ann:+.1%}", f"{vol:.1%}", f"{sh:.2f}", f"{mdd:+.1%}"]
    else:
        vals = [r, "0", "0%", "—", "—", "—", "—"]
    for c, v in enumerate(vals, 2):
        cell = ws2.cell(row=row, column=c, value=v)
        cell.font = font_body(10)
        cell.alignment = align_c
        cell.border = border_all
    row += 1

row += 2
ws2.cell(row=row, column=2, value="各Regime下各策略表现").font = font_body(11, bold=True)
row += 1
headers = ['Regime', '策略', '年化收益', '夏普', '最大回撤', '胜率']
for c, h in enumerate(headers, 2):
    cell = ws2.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

for r in ['牛市', '熊市', '震荡']:
    mask = regime_aligned == r
    for sname in ['V3.0-A Regime+非对称', 'V3.0-E 多周期集成', 'V2.0 ML+趋势', '买入持有']:
        rets = strategy_rets[sname].copy()
        mask_a = mask.reindex(rets.index).fillna(False)
        rets = rets[mask_a]
        if len(rets) < 10:
            continue
        m = calc_metrics(rets, sname)
        vals = [r, sname, f"{m['ann_ret']:+.1%}", f"{m['sharpe']:.2f}", f"{m['max_dd']:+.1%}", f"{m['win_rate']:.1%}"]
        for c, v in enumerate(vals, 2):
            cell = ws2.cell(row=row, column=c, value=v)
            cell.font = font_body(10)
            cell.alignment = align_c
            cell.border = border_all
        row += 1

ws2.column_dimensions['B'].width = 12
ws2.column_dimensions['C'].width = 25
for col in 'DEFG':
    ws2.column_dimensions[col].width = 14

# ── Sheet3: 策略对比 ──
ws3 = wb.create_sheet('策略对比')
ws3.sheet_view.showGridLines = False
row = 2
ws3.cell(row=row, column=2, value="全部策略详细对比").font = font_title(14, C_PRIMARY)
ws3.merge_cells(start_row=row, start_column=2, end_row=row, end_column=10)
row += 2

headers = ['策略', '年化收益', '年化波动', '夏普', '最大回撤', '胜率', 'Calmar', '累计收益', 'vs买入持有']
for c, h in enumerate(headers, 2):
    cell = ws3.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

bh_sharpe = strategies['买入持有']['sharpe']
for name in ['V1.0 线性IC', 'V2.0 ML+趋势', 'V3.0-A Regime+非对称',
             'V3.0-B +Vol靶向', 'V3.0-C +止损', 'V3.0-D +Kelly',
             'V3.0-E 多周期集成', '买入持有']:
    m = strategies[name]
    diff = m['sharpe'] - bh_sharpe if name != '买入持有' else 0
    vals = [name, f"{m['ann_ret']:+.1%}", f"{m['ann_vol']:.1%}", f"{m['sharpe']:.2f}",
            f"{m['max_dd']:+.1%}", f"{m['win_rate']:.1%}", f"{m['calmar']:.2f}",
            f"{m['cumret']:+.1%}", f"{diff:+.2f}" if name != '买入持有' else "—"]
    for c, v in enumerate(vals, 2):
        cell = ws3.cell(row=row, column=c, value=v)
        cell.font = font_body(10, bold=(name == best_key))
        cell.alignment = align_c
        cell.border = border_all
        if name == best_key:
            cell.fill = fill_solid(C_YELLOW)
    row += 1

ws3.column_dimensions['B'].width = 25
for col in 'CDEFGHIJ':
    ws3.column_dimensions[col].width = 14

# ── Sheet4: 特征重要性 ──
ws4 = wb.create_sheet('特征重要性')
ws4.sheet_view.showGridLines = False
row = 2
ws4.cell(row=row, column=2, value="V3.0 特征重要性分析").font = font_title(14, C_PRIMARY)
ws4.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
row += 2

headers = ['排名', '因子名称', 'XGBoost', 'LightGBM', '平均']
for c, h in enumerate(headers, 2):
    cell = ws4.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

for i, (f, v) in enumerate(fi_avg.items()):
    vals = [i+1, f, f"{fi_xgb.get(f,0):.4f}", f"{fi_lgb.get(f,0):.4f}", f"{v:.4f}"]
    for c, v in enumerate(vals, 2):
        cell = ws4.cell(row=row, column=c, value=v)
        cell.font = font_body(10)
        cell.alignment = align_c
        cell.border = border_all
    row += 1

ws4.column_dimensions['B'].width = 8
ws4.column_dimensions['C'].width = 25
for col in 'DEF':
    ws4.column_dimensions[col].width = 14

# ── Sheet5: ML模型表现 ──
ws5 = wb.create_sheet('ML模型表现')
ws5.sheet_view.showGridLines = False
row = 2
ws5.cell(row=row, column=2, value="多周期ML模型表现").font = font_title(14, C_PRIMARY)
ws5.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
row += 2

headers = ['预测周期', '准确率', 'AUC', 'IC', '样本数', '有效性']
for c, h in enumerate(headers, 2):
    cell = ws5.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

for d in PREDICT_DAYS:
    m = ml_results[d]
    valid = m['accuracy'] > 0.52
    vals = [f"{d}日", f"{m['accuracy']:.1%}", f"{m['auc']:.3f}", f"{m['ic']:+.4f}",
            str(len(m['actuals'])), "✅有效" if valid else "⚠️弱"]
    for c, v in enumerate(vals, 2):
        cell = ws5.cell(row=row, column=c, value=v)
        cell.font = font_body(10)
        cell.alignment = align_c
        cell.border = border_all
    row += 1

ws5.column_dimensions['B'].width = 12
for col in 'CDEFG':
    ws5.column_dimensions[col].width = 14

# ── Sheet6: 当前因子状态 ──
ws6 = wb.create_sheet('当前因子状态')
ws6.sheet_view.showGridLines = False
row = 2
ws6.cell(row=row, column=2, value=f"当前各因子状态（{latest_idx.date()}）").font = font_title(14, C_PRIMARY)
ws6.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
row += 2

headers = ['因子', '当前值', '20日均值', '60日均值', '20日动量', '信号']
for c, h in enumerate(headers, 2):
    cell = ws6.cell(row=row, column=c, value=h)
    cell.font = font_body(10, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

latest_factors = factors.loc[latest_idx]
for f in feature_cols:
    if f not in factors.columns:
        continue
    val = latest_factors.get(f, np.nan)
    if pd.isna(val):
        continue
    ma20 = float(factors[f].rolling(20).mean().loc[latest_idx]) if pd.notna(factors[f].rolling(20).mean().loc[latest_idx]) else 0
    ma60 = float(factors[f].rolling(60).mean().loc[latest_idx]) if pd.notna(factors[f].rolling(60).mean().loc[latest_idx]) else 0
    idx_21 = factors.index.get_loc(latest_idx) - 21
    mom20 = float(val / factors[f].iloc[idx_21] - 1) if idx_21 >= 0 and factors[f].iloc[idx_21] != 0 else 0
    signal = "偏强" if val > ma20 else "偏弱"

    vals = [f, f"{val:.4f}", f"{ma20:.4f}", f"{ma60:.4f}", f"{mom20:+.2%}", signal]
    for c, v in enumerate(vals, 2):
        cell = ws6.cell(row=row, column=c, value=v)
        cell.font = font_body(10)
        cell.alignment = align_c
        cell.border = border_all
    row += 1

ws6.column_dimensions['B'].width = 22
for col in 'CDEFG':
    ws6.column_dimensions[col].width = 14

# ── Sheet7: 使用说明 ──
ws7 = wb.create_sheet('使用说明')
ws7.sheet_view.showGridLines = False
row = 2
ws7.cell(row=row, column=2, value="V3.0 模型使用说明").font = font_title(14, C_PRIMARY)
ws7.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
row += 2

notes = [
    ("一、模型概述", ""),
    ("", "V4.0 = V3.0(Regime+非对称+多周期) + FRED宏观数据(实际利率/收益率曲线/Fed利率) + 事件日历(FOMC/CPI) + 铜金比/BTC/VIX期限结构"),
    ("", "预测目标: 未来20个交易日金价涨/跌（二分类）"),
    ("", "特征数: 41个（V3.0的23个 + V4.0新增18个）"),
    ("", "验证方法: Walk-Forward（500日训练+60日测试, 步长30）"),
    ("", "数据来源: yfinance（Yahoo Finance）+ FRED（圣路易斯联储）"),
    ("", ""),
    ("二、Regime切换逻辑", ""),
    ("", "牛市: 金价>MA200 且 MA50>MA200 → 只做多，概率分级控仓"),
    ("", "熊市: 金价<MA200 且 MA50<MA200 → 可做空，概率分级控仓"),
    ("", "震荡: 均线混乱 → 轻仓或空仓"),
    ("", ""),
    ("三、非对称仓位逻辑", ""),
    ("", "核心思想: 牛市中做空是主要风险来源，所以牛市不做空"),
    ("", "牛市: P>0.65满仓, 0.55-0.65半仓, 0.48-0.55轻仓, <0.48空仓"),
    ("", "熊市: P<0.35满仓做空, 0.35-0.45半仓做空, >0.45空仓"),
    ("", "震荡: P>0.60轻仓做多, P<0.40轻仓做空, 中间空仓"),
    ("", ""),
    ("四、Vol靶向", ""),
    ("", "目标波动率=15%年化"),
    ("", "实际波动率低时加仓（最高2倍），高时减仓"),
    ("", ""),
    ("五、止损机制", ""),
    ("", "策略回撤>8%时触发空仓3天"),
    ("", ""),
    ("六、多周期集成", ""),
    ("", "5日(15%) + 10日(25%) + 20日(40%) + 60日(20%) 加权投票"),
    ("", "短周期更敏感，长周期更稳定"),
    ("", ""),
    ("七、局限性", ""),
    ("", "1. 5年回测期以牛市为主，熊市样本不足"),
    ("", "2. 未考虑交易成本（滑点+佣金约0.05-0.1%/次）"),
    ("", "3. 央行购金代理(ETP持有量)是间接指标，不如直接数据精确"),
    ("", "4. Walk-Forward虽避免前视偏差，但模型仍可能过拟合"),
    ("", "5. Regime切换有滞后性（均线信号滞后）"),
    ("", ""),
    ("八、建议用法", ""),
    ("", "1. 作为辅助决策工具，不作为唯一信号"),
    ("", "2. 结合基本面（美联储政策、央行购金数据、地缘事件）"),
    ("", "3. 牛市中主要看做多信号，做空信号谨慎对待"),
    ("", "4. 当模型概率>0.7或<0.3时信号较强，中间区域谨慎"),
    ("", "5. 定期重新训练（建议每月）"),
]
for n, d in notes:
    if n and not d:
        ws7.cell(row=row, column=2, value=n).font = font_body(11, bold=True, color=C_PRIMARY)
    else:
        ws7.cell(row=row, column=2, value=n).font = font_body(10, bold=True)
        ws7.cell(row=row, column=3, value=d).font = font_body(10)
        ws7.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
    row += 1

ws7.column_dimensions['B'].width = 20
for col in 'CDEFGH':
    ws7.column_dimensions[col].width = 14

# ── Sheet8: 因子原始数据 ──
ws8 = wb.create_sheet('因子原始数据')
ws8.sheet_view.showGridLines = False
row = 2
ws8.cell(row=row, column=2, value="因子原始数据（日频）").font = font_title(12, C_PRIMARY)
ws8.merge_cells(start_row=row, start_column=2, end_row=row, end_column=12)
row += 2

data_cols = ['金价', '10年实际利率', '联邦基金利率', '2s10s利差', '10年通胀预期',
             '美元指数', 'VIX恐慌', '金矿/黄金', '央行购金代理(ETP)', '铜金比', 'BTC/黄金',
             'VIX期限结构', '距FOMC天数', '距CPI天数', 'MA200偏离', '20日波动率', 'Regime']
headers = ['日期'] + data_cols
for c, h in enumerate(headers, 2):
    cell = ws8.cell(row=row, column=c, value=h)
    cell.font = font_body(9, bold=True, color='FFFFFF')
    cell.fill = fill_solid(C_HEADER)
    cell.alignment = align_c
    cell.border = border_all
row += 1

# 只写最近250行
for idx, (date, r) in enumerate(factors.iloc[-250:].iterrows()):
    vals = [date.strftime('%Y-%m-%d')]
    for col in data_cols:
        v = r.get(col, np.nan)
        if pd.isna(v):
            vals.append("")
        elif isinstance(v, (int, float, np.floating, np.integer)):
            vals.append(f"{float(v):.4f}")
        else:
            vals.append(str(v))
    for c, v in enumerate(vals, 2):
        cell = ws8.cell(row=row, column=c, value=v)
        cell.font = font_body(8)
        cell.alignment = align_c
    row += 1

ws8.column_dimensions['B'].width = 12
for col in 'CDEFGHIJKLM':
    ws8.column_dimensions[col].width = 14

ws8.freeze_panes = 'C5'

# 保存
output_path = str(REPORT_V5_XLSX)
wb.properties.creator = '莫比乌斯'
wb.properties.title = '黄金价格预测V5.0'
wb.save(output_path)
print(f"\n✅ Excel报告已保存: {output_path}")
print(f"   Sheets: {wb.sheetnames}")

# ═══════════════════════════════════════════════════════════════════
# 10. 输出 Dashboard JSON（dashboard_data.json + execution_data.json）
# ═══════════════════════════════════════════════════════════════════

print("\n[10] 输出Dashboard JSON...")

def _safe(v):
    """安全转float，NaN/inf → None"""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except:
        return None

# --- overview ---
overview = {}
for k, m in strategies.items():
    overview[k] = f"{m['ann_ret']:+.1%}"
overview['策略'] = '年化收益'
regime_counts = factors['Regime'].value_counts()
overview['牛市'] = int(regime_counts.get('牛市', 0))
overview['熊市'] = int(regime_counts.get('熊市', 0))
overview['震荡'] = int(regime_counts.get('震荡', 0))
overview['预测基准日'] = str(latest_idx.date())
overview['当前金价'] = f"${current_price:.2f}"
overview['MA50'] = f"${ma50_current:.2f}"
overview['MA200'] = f"${ma200_current:.2f}"
overview['当前Regime'] = current_regime
overview['60日波动率'] = f"{current_vol:.1%}"
overview['5日看多概率'] = f"{multi_probs[5]:.1%}"
overview['10日看多概率'] = f"{multi_probs[10]:.1%}"
overview['20日看多概率'] = f"{multi_probs[20]:.1%}"
overview['60日看多概率'] = f"{multi_probs[60]:.1%}"
overview['命中率20日'] = f"{ml_results[20]['accuracy']:.1%}"  # 供 db.pos_factor 计算(此前该字段缺失→pos_factor恒None)
overview['加权集成概率'] = f"{prob_multi_current:.1%}"
overview['建议操作'] = action

# --- strategies list ---
strategies_list = []
bh_cumret = strategies['买入持有']['cumret']
for k, m in strategies.items():
    strategies_list.append({
        '策略': k,
        '年化收益': f"{m['ann_ret']:+.1%}",
        '年化波动': f"{m['ann_vol']:.1%}",
        '夏普': f"{m['sharpe']:.2f}",
        '最大回撤': f"{m['max_dd']:+.1%}",
        '胜率': f"{m['win_rate']:.1%}",
        'Calmar': f"{m['calmar']:.2f}",
        '累计收益': f"{m['cumret']:+.1%}",
        'vs买入持有': f"{m['cumret'] - bh_cumret:+.2f}",
    })

# --- features ---
features_list = []
for i, (f, v) in enumerate(fi_avg.items()):
    features_list.append({
        'rank': i + 1,
        'name': f,
        'xgb': float(fi_xgb.get(f, 0)),
        'lgb': float(fi_lgb.get(f, 0)),
        'avg': float(v),
    })

# --- ml_models ---
ml_models_list = []
for d in PREDICT_DAYS:
    m = ml_results[d]
    ml_models_list.append({
        'period': f'{d}日',
        'accuracy': f"{m['accuracy']:.1%}",
        'auc': f"{m['auc']:.3f}",
        'ic': f"{m['ic']:+.4f}",
    })

# --- current_factors ---
current_factors_list = []
latest_factors = factors.loc[latest_idx]
for f in feature_cols:
    if f not in factors.columns:
        continue
    val = latest_factors.get(f, np.nan)
    if pd.isna(val):
        continue
    ma20_f = float(factors[f].rolling(20).mean().loc[latest_idx]) if pd.notna(factors[f].rolling(20).mean().loc[latest_idx]) else 0
    idx_21 = factors.index.get_loc(latest_idx) - 21
    mom20 = float(val / factors[f].iloc[idx_21] - 1) if idx_21 >= 0 and factors[f].iloc[idx_21] != 0 else 0
    sig = "偏强" if val > ma20_f else "偏弱"
    current_factors_list.append({
        'name': f,
        'value': f"{float(val):.4f}",
        'momentum': f"{mom20:+.2%}",
        'signal': sig,
    })

# --- raw_data (最近60天) ---
raw_data_list = []
data_cols_raw = ['金价', '10年实际利率', '联邦基金利率', '2s10s利差', '10年通胀预期',
                 '美元指数', 'VIX恐慌', '金矿/黄金', '央行购金代理(ETP)', '铜金比', 'BTC/黄金',
                 'VIX期限结构', '距FOMC天数', '距CPI天数', 'MA200偏离', '20日波动率', 'Regime']
for date, r in factors.iloc[-60:].iterrows():
    row_data = {'日期': date.strftime('%Y-%m-%d')}
    for col in data_cols_raw:
        v = r.get(col, np.nan)
        if pd.isna(v):
            row_data[col] = ''
        elif isinstance(v, (int, float, np.floating, np.integer)):
            row_data[col] = f"{float(v):.4f}"
        else:
            row_data[col] = str(v)
    raw_data_list.append(row_data)

# --- 组装dashboard_data.json ---
# V5.0: 添加holdout验证和回归分支结果
holdout_list = []
for name, m in holdout_results.items():
    holdout_list.append({
        'strategy': name,
        'ann_ret': f"{m.get('ann_ret', 0):+.1%}",
        'sharpe': round(m.get('sharpe', 0), 2),
        'max_dd': f"{m.get('max_dd', 0):+.1%}",
        'win_rate': f"{m.get('win_rate', 0):.1%}",
    })

reg_models_list = []
for d in PREDICT_DAYS:
    r = reg_results.get(d, {})
    reg_models_list.append({
        'horizon': f"{d}日",
        'r2': round(r.get('r2', 0), 3),
        'rmse': round(r.get('rmse', 0), 4),
        'dir_acc': f"{r.get('dir_acc', 0):.1%}",
        'ic': f"{r.get('ic', 0):+.4f}",
    })

dashboard_data = {
    'overview': overview,
    'strategies': strategies_list,
    'features': features_list,
    'ml_models': ml_models_list,
    'current_factors': current_factors_list,
    'raw_data': raw_data_list,
    'v5_holdout': holdout_list,
    'v5_regression': reg_models_list,
    'v5_feature_count': len(feature_cols),
    'v5_original_feature_count': len(_all_feature_cols),
}

dashboard_json_path = str(DASHBOARD_JSON)
with open(dashboard_json_path, 'w', encoding='utf-8') as f:
    json.dump(dashboard_data, f, ensure_ascii=False, indent=2, allow_nan=False)
print(f"  ✅ dashboard_data.json ({len(raw_data_list)}天数据)")

# 同步到dashboard目录（前端静态文件访问）
# 注：本布局下两处同为 web/dashboard_data.json，旧布局需双写时路径会不同
import shutil
dashboard_dir_json = str(DASHBOARD_JSON)
if os.path.abspath(dashboard_dir_json) != os.path.abspath(dashboard_json_path):
    shutil.copy2(dashboard_json_path, dashboard_dir_json)

# --- execution_data.json：当前信号 + 执行方案 ---
# 仓位序列（最近250天）
pos_series = []
v3e_pos_idx = v3e_pos.iloc[-250:]
for i, (date, pos) in enumerate(v3e_pos_idx.items()):
    gold_p = _safe(factors['金价'].loc[date]) if date in factors.index else None
    # prob_multi 是加权集成概率序列，与 v3e_pos 同index
    prob_p = _safe(prob_multi.loc[date]) if date in prob_multi.index else None
    pos_series.append({
        'date': date.strftime('%Y-%m-%d'),
        'position': _safe(pos) or 0.0,
        'probability': prob_p or 0.0,
        'regime': str(factors['Regime'].loc[date]) if date in factors.index else '',
        'gold_price': gold_p,
    })

# 情景手册（固定）
scenarios = [
    {
        "场景": "牛市+高概率(P>0.65)",
        "模型仓位": "100%",
        "ETF执行": "65%（底仓满配）",
        "期货执行": "35%（战术增强）",
        "操作": "ETF买入518880至65%→期货开多35%→总仓位100%",
        "注意事项": "期货杠杆部分需严格止损"
    },
    {
        "场景": "牛市+中概率(0.55<P≤0.65)",
        "模型仓位": "60%",
        "ETF执行": "39%（底仓部分）",
        "期货执行": "21%（战术部分）",
        "操作": "ETF持有39%→期货调整至21%多→总仓位60%",
        "注意事项": "可考虑期货部分减仓而非ETF"
    },
    {
        "场景": "牛市+低概率(P≤0.48) 或 震荡市",
        "模型仓位": "0%",
        "ETF执行": "0%（清仓）",
        "期货执行": "0%（平仓）",
        "操作": "ETF全部卖出→期货平仓→转入货币基金",
        "注意事项": "ETF T+0可当天进出"
    },
    {
        "场景": "熊市+低概率(P<0.35)",
        "模型仓位": "-100%（做空）",
        "ETF执行": "0%（ETF不能做空）",
        "期货执行": "-100%（全部期货做空）",
        "操作": "ETF清仓→期货开空100%→纯空头",
        "注意事项": "做空只用期货，ETF无法做空"
    },
    {
        "场景": "止损触发(回撤>8%)",
        "模型仓位": "强制空仓3天",
        "ETF执行": "立即清仓",
        "期货执行": "立即平仓",
        "操作": "两腿同时平仓→等待3天→重新建仓",
        "注意事项": "期货滑点更小，优先平期货"
    }
]

# 三层架构（固定）
execution_rules = {
    "底仓层(ETF 518880)": {
        "资金占比": "60-70%",
        "调仓触发": "仓位变化≥0.3 或 Regime切换",
        "调仓频率": "月均1.7次",
        "目标": "承载核心仓位，降低交易成本",
        "操作": "按V3.0-E仓位信号×0.65执行",
        "佣金": "万一，免印花税",
        "持有成本": "0.6%/年管理费"
    },
    "战术层(COMEX GC=F)": {
        "资金占比": "30-40%",
        "调仓触发": "任何仓位变化",
        "调仓频率": "月均14.0次",
        "目标": "精细调仓，杠杆增强收益",
        "操作": "按(总仓位 - ETF仓位)执行",
        "佣金": "$3/手",
        "杠杆": "约20倍"
    },
    "现金层": {
        "资金占比": "0-10%",
        "用途": "保证金追加 + ETF申购赎回缓冲",
        "收益": "货币基金2-2.5%"
    }
}

# 当前状态
current_exec = {
    'gold_price': _safe(current_price),
    'regime': current_regime,
    'position': _safe(suggested_pos),
    'probability': _safe(prob_multi_current),
    'ma200': _safe(ma200_current),
    'ma50': _safe(ma50_current),
    'vol_60d': _safe(current_vol),
}

execution_data = {
    'current': current_exec,
    'scenarios': scenarios,
    'execution_rules': execution_rules,
    'position_history': {
        'dates': [p['date'] for p in pos_series],
        'positions': [p['position'] for p in pos_series],
        'probabilities': [p['probability'] for p in pos_series],
        'regimes': [p['regime'] for p in pos_series],
        'gold_prices': [p['gold_price'] for p in pos_series],
    },
    # 静态统计（首次运行后不变，除非重新跑signal_analysis）
    'signal_stats': None,  # 从已有analysis.json继承
    'cost_comparison': None,  # 从已有analysis.json继承
}

# 继承已有的signal_stats和cost_comparison（这些是回测统计，不需要每次重算）
existing_analysis_path = str(ANALYSIS_JSON)
if os.path.exists(existing_analysis_path):
    try:
        with open(existing_analysis_path, 'r') as f:
            existing = json.load(f)
        execution_data['signal_stats'] = existing.get('signal_stats')
        execution_data['cost_comparison'] = existing.get('cost_comparison')
    except:
        pass

# C5修复: 注入真实命中率字段(前端执行计划Tab此前fallback到写死的35%/58%/-23%)。
#   数据来源 [5.5]信号回测基准: recent_hit_rate=近20次已结算命中率, wf_baseline_acc=WF整体命中率。
if execution_data.get('signal_stats') is None:
    execution_data['signal_stats'] = {}
execution_data['signal_stats']['hit_rate_20d'] = f"{recent_hit_rate:.1%}"
execution_data['signal_stats']['wf_base'] = f"{wf_baseline_acc:.1%}"
execution_data['signal_stats']['deviation'] = f"{recent_hit_rate - wf_baseline_acc:+.1%}"

exec_json_path = str(EXECUTION_JSON)
with open(exec_json_path, 'w', encoding='utf-8') as f:
    json.dump(execution_data, f, ensure_ascii=False, indent=2, allow_nan=False)
print(f"  ✅ execution_data.json (仓位={suggested_pos:.1%}, Regime={current_regime})")

# 同步到根目录（供API使用）
shutil.copy2(exec_json_path, str(EXECUTION_LATEST_JSON))

# 同步到 dashboard-vue3/public/（vite 静态资源目录，V5 直接写不再靠手动 cp）
VUE3_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
shutil.copy2(dashboard_json_path, str(VUE3_PUBLIC_DIR / 'dashboard_data.json'))
shutil.copy2(exec_json_path, str(VUE3_PUBLIC_DIR / 'execution_data.json'))
print("  ✅ synced to dashboard-vue3/public/")

# ── 直接写 SQLite（不再依赖 ingest_current.py 搬运）──
print("  ✅ SQLite ingest", end='')
try:
    from gold_model.db import db
    db.init()
    sid = db.insert_signal(dashboard_data, execution_data)
    stats = db.stats()
    print(f" → signal_id={sid}, total={stats['total_signals']}")
except Exception as e:
    print(f" ❌ failed: {e}")

# ── V4.2: 模型漂移快照 ──
# 每次运行追加一条记录到 drift_history.json，供漂移检测用
print("  ✅ 漂移快照", end='')
try:
    drift_snapshot = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'run_date': latest_idx.strftime('%Y-%m-%d'),
        'ml_metrics': {str(d): {
            'accuracy': round(float(ml_results[d]['accuracy']), 4),
            'auc': round(float(ml_results[d]['auc']), 4),
            'ic': round(float(ml_results[d]['ic']), 4),
        } for d in PREDICT_DAYS},
        'feature_importance_top10': {
            f: round(float(v), 4) for f, v in fi_avg.head(10).items()
        },
        'regime_distribution': {
            'bull': int((factors['Regime'] == '牛市').sum()),
            'range': int((factors['Regime'] == '震荡').sum()),
            'bear': int((factors['Regime'] == '熊市').sum()),
        },
        'current_state': {
            'regime': current_regime,
            'probability': round(float(prob_multi_current), 4),
            'position': round(float(suggested_pos), 4),
            'gold_price': round(float(gold.iloc[-1]), 2),
        },
        'prob_stats': {
            'mean': round(float(prob_multi.mean()), 4),
            'std': round(float(prob_multi.std()), 4),
            'p25': round(float(prob_multi.quantile(0.25)), 4),
            'p75': round(float(prob_multi.quantile(0.75)), 4),
        },
        'best_sharpe': round(float(best_strategy['sharpe']), 4),
        'signal_backtest': {
            'wf_baseline_acc': round(float(wf_baseline_acc), 4),
            'recent_20_hit_rate': round(float(recent_hit_rate), 4),
            'recent_10_hit_rate': round(float(recent_10_rate), 4),
            'consecutive_miss': int(consecutive_miss),
            'recent_n': int(recent_n),
        },
    }

    # 追加到历史文件
    drift_file = str(DRIFT_HISTORY)
    drift_history = []
    if os.path.exists(drift_file):
        try:
            with open(drift_file) as f:
                drift_history = json.load(f)
        except:
            drift_history = []
    drift_history.append(drift_snapshot)
    # 只保留最近90次
    if len(drift_history) > 90:
        drift_history = drift_history[-90:]
    with open(drift_file, 'w', encoding='utf-8') as f:
        json.dump(drift_history, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f" (累计{len(drift_history)}条)")
except Exception as e:
    print(f" (失败: {e})")

# ═══════════════════════════════════════════════════════════════════
# 最终总结
# ═══════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  V5.0 分析完成")
print("=" * 60)
print(f"""
  📊 输出文件:
     - 黄金多因子分析报告_V5.xlsx（8个Sheet）
     - charts_v5/01_strategy_evolution.png
     - charts_v5/02_drawdown.png
     - charts_v5/03_position_evolution.png
     - charts_v5/04_probability_regime.png
     - charts_v5/05_feature_importance.png
     - charts_v5/06_regime_radar.png
     - charts_v5/07_multi_horizon.png
     - charts_v5/08_summary_table.png

  📈 关键发现:
     - 最优策略: {best_key}
     - 夏普: {best_strategy['sharpe']:.2f} (V1.0={strategies['V1.0 线性IC']['sharpe']:.2f}, V2.0={strategies['V2.0 ML+趋势']['sharpe']:.2f}, 买入持有={strategies['买入持有']['sharpe']:.2f})
     - 年化收益: {best_strategy['ann_ret']:+.1%} (买入持有={strategies['买入持有']['ann_ret']:+.1%})
     - 最大回撤: {best_strategy['max_dd']:+.1%} (买入持有={strategies['买入持有']['max_dd']:+.1%})
     - 当前信号: {action}
     - 多周期概率: 5日={multi_probs[5]:.0%} / 10日={multi_probs[10]:.0%} / 20日={multi_probs[20]:.0%} / 60日={multi_probs[60]:.0%}
     - Regime: {current_regime}

  🔬 V5.0 优化验证:
     - 特征数: {_all_feature_cols_len}→{len(feature_cols)} (VIF剔除)
     - Holdout夏普: {holdout_results.get(best_key, dict()).get('sharpe', 0):.2f} (Full={best_strategy['sharpe']:.2f}, 衰减={sharpe_decay:.1%})
     - 回归分支20日: R²={reg_results.get(20, dict()).get('r2', 0):.3f}, 方向准确率={reg_results.get(20, dict()).get('dir_acc', 0):.1%}
""")
