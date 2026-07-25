#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V4模型信号频率分析 → ETF+期货组合仓位方案
==========================================
分析V4模型的换手率、持仓周期、信号变化频率
设计ETF(518880)+COMEX期货(GC=F)两层执行框架
"""

import warnings
warnings.filterwarnings('ignore')

import os, sys, json, numpy as np, pandas as pd
from gold_model.paths import ANALYSIS_JSON, EXECUTION_PLAN_DIR
import yfinance as yf, requests, io
from datetime import datetime, timedelta
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
import xgboost as xgb
import lightgbm as lgb

# ═══════════════════════════════════════════════════════════════════
# 1. 数据采集（复用V4逻辑）
# ═══════════════════════════════════════════════════════════════════

print("=" * 60)
print("  V4信号频率分析 → ETF+期货执行方案")
print("=" * 60)

TICKERS = {
    'GC=F': '黄金期货', 'GLD': 'GLD基金', 'IAU': 'IAU基金', 'SGOL': 'SGOL基金',
    'DX-Y.NYB': '美元指数', 'TIP': 'TIPS(实际利率替代)', 'IEF': '7-10年国债(名义利率替代)',
    'TLT': '20+年国债', 'SLV': '白银', 'GDX': '金矿股', 'GDXJ': '金矿小盘',
    'SIL': '白银矿企', '^VIX': 'VIX恐慌', '^GVZ': '黄金VIX', 'NEM': '纽蒙特矿业',
    'EUR=X': '欧元/美元', 'JPY=X': '美元/日元', 'UUP': '美元指数ETF',
    'HG=F': '铜期货', 'BTC-USD': '比特币', '^VIX9D': 'VIX9D',
    '^IRX': '13周国债', '^FVX': '5年国债', '^TNX': '10年国债', '^TYX': '30年国债',
}

FRED_SERIES = {
    'DFII10': '10年实际利率(FRED)', 'DFII5': '5年实际利率(FRED)',
    'DGS2': '2年国债收益率(FRED)', 'DGS10': '10年国债收益率(FRED)',
    'DGS30': '30年国债收益率(FRED)', 'DFF': '联邦基金利率(FRED)',
    'T10YIE': '10年通胀预期(FRED)',
}

print("\n[1] 数据采集...")
raw = {}
for ticker, name in TICKERS.items():
    try:
        d = yf.download(ticker, period='5y', progress=False, auto_adjust=False)
        if len(d) > 100:
            if isinstance(d.columns, pd.MultiIndex):
                col = 'Adj Close' if ('Adj Close', ticker) in d.columns else 'Close'
                s = d[col][ticker] if ticker in d[col] else d[col].iloc[:, 0]
            else:
                s = d['Adj Close'] if 'Adj Close' in d.columns else d['Close']
            s.name = name
            raw[name] = s
    except:
        pass

for sid, name in FRED_SERIES.items():
    try:
        url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and 'html' not in r.text[:50].lower():
            df_fred = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
            df_fred.columns = [name]
            df_fred = df_fred.replace('.', np.nan).astype(float)
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=5*365)
            df_fred = df_fred[df_fred.index > cutoff]
            if len(df_fred) > 100:
                s = df_fred[name]
                s.name = name
                raw[name] = s
    except:
        pass

df = pd.DataFrame(raw).dropna(how='all')

# ═══════════════════════════════════════════════════════════════════
# 2. 因子构建（复用V4逻辑，精简版）
# ═══════════════════════════════════════════════════════════════════

print("[2] 因子构建...")
gold = df['黄金期货'].dropna()

f_real_rate = df['TIPS(实际利率替代)']
f_dxy = df['美元指数']
f_nominal_rate = df['7-10年国债(名义利率替代)']
f_inflation = df['TIPS(实际利率替代)'] / df['7-10年国债(名义利率替代)']
f_vix = df['VIX恐慌']
f_gdx_gold = df['金矿股'] / df['黄金期货']
f_silver_gold = df['白银'] / df['黄金期货']
f_gvz = df['黄金VIX']
etp_holdings = df['GLD基金'] + df['IAU基金'] + df['SGOL基金']
f_cb_proxy = etp_holdings.pct_change(60)
f_miner_ratio = df['金矿股'] / df['白银矿企']
f_usd_jpy = df['美元/日元']
f_gold_nem = df['黄金期货'] / df['纽蒙特矿业']
f_ma200_dev = gold / gold.rolling(200).mean() - 1
f_ma_cross = np.where(gold.rolling(50).mean() > gold.rolling(200).mean(), 1, -1)
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
f_real_x_dxy = f_real_rate * f_dxy
f_vix_x_infl = f_vix * f_inflation
f_gdx_x_vix = f_gdx_gold * f_vix
f_vol_change = f_vol_20d.pct_change(10)
f_mom_accel = f_mom_20d - f_mom_20d.shift(10)
f_gold_ma_ratio = gold / gold.rolling(250).mean()

f_real_rate_10y = df['10年实际利率(FRED)'] if '10年实际利率(FRED)' in df else pd.Series(np.nan, index=df.index)
f_real_rate_5y = df['5年实际利率(FRED)'] if '5年实际利率(FRED)' in df else pd.Series(np.nan, index=df.index)
f_fed_rate = df['联邦基金利率(FRED)'] if '联邦基金利率(FRED)' in df else pd.Series(np.nan, index=df.index)
f_infl_exp_10y = df['10年通胀预期(FRED)'] if '10年通胀预期(FRED)' in df else pd.Series(np.nan, index=df.index)
f_2s10s = (df['10年国债收益率(FRED)'] - df['2年国债收益率(FRED)']) if '10年国债收益率(FRED)' in df and '2年国债收益率(FRED)' in df else pd.Series(np.nan, index=df.index)
f_5s30s = (df['30年国债收益率(FRED)'] - df['5年国债收益率(FRED)']) if '30年国债收益率(FRED)' in df and '5年国债收益率(FRED)' in df else pd.Series(np.nan, index=df.index)
f_curve_invert = (f_2s10s < 0).astype(float)
f_copper_gold = df['铜期货'] / df['黄金期货'] if '铜期货' in df else pd.Series(np.nan, index=df.index)
f_btc = df['比特币'] if '比特币' in df else pd.Series(np.nan, index=df.index)
f_btc_gold = df['比特币'] / df['黄金期货'] if '比特币' in df and '黄金期货' in df else pd.Series(np.nan, index=df.index)
f_vix_9d = df['VIX9D'] if 'VIX9D' in df else pd.Series(np.nan, index=df.index)
f_vix_term_spread = df['VIX恐慌'] / df['VIX9D'] if 'VIX9D' in df else pd.Series(np.nan, index=df.index)

FOMC_DATES = pd.to_datetime([
    '2021-01-27','2021-03-17','2021-04-28','2021-06-16','2021-07-28','2021-09-22','2021-11-03','2021-12-15',
    '2022-01-26','2022-03-16','2022-05-04','2022-06-15','2022-07-27','2022-09-21','2022-11-02','2022-12-14',
    '2023-02-01','2023-03-22','2023-05-03','2023-06-14','2023-07-26','2023-09-20','2023-11-01','2023-12-13',
    '2024-01-31','2024-03-20','2024-05-01','2024-06-12','2024-07-31','2024-09-18','2024-11-07','2024-12-18',
    '2025-01-29','2025-03-19','2025-04-30','2025-06-18','2025-07-30','2025-09-17','2025-10-29','2025-12-10',
    '2026-01-28','2026-03-18','2026-04-29','2026-06-17','2026-07-29','2026-09-16','2026-10-28','2026-12-09',
])
CPI_DATES = []
for year in range(2021, 2027):
    for month in range(1, 13):
        for day in [10, 11, 12, 13, 14, 15, 16]:
            try:
                d = pd.Timestamp(year=year, month=month, day=day)
                if d.weekday() in [1, 2, 3]:
                    CPI_DATES.append(d)
                    break
            except:
                pass
CPI_DATES = pd.DatetimeIndex(CPI_DATES)

fomc_dates = FOMC_DATES.sort_values()
def days_to_next_event(date, event_dates):
    future = event_dates[event_dates >= date]
    if len(future) > 0:
        return (future[0] - date).days
    return 30

f_days_to_fomc = pd.Series(0.0, index=gold.index)
f_days_to_cpi = pd.Series(0.0, index=gold.index)
for d in gold.index:
    f_days_to_fomc[d] = days_to_next_event(d, fomc_dates)
    f_days_to_cpi[d] = days_to_next_event(d, CPI_DATES)
f_fomc_week = (f_days_to_fomc <= 3).astype(float)
f_cpi_week = (f_days_to_cpi <= 2).astype(float)
f_real_x_fed = f_real_rate_10y * f_fed_rate if f_real_rate_10y.notna().sum() > 0 else pd.Series(np.nan, index=df.index)
f_copper_x_vix = f_copper_gold * f_vix if f_copper_gold.notna().sum() > 0 else pd.Series(np.nan, index=df.index)
f_curve_x_dxy = f_2s10s * f_dxy if f_2s10s.notna().sum() > 0 else pd.Series(np.nan, index=df.index)

factors = pd.DataFrame({
    '金价': gold, '实际利率(TIP)': f_real_rate, '美元指数': f_dxy,
    '名义利率(IEF)': f_nominal_rate, '通胀预期(TIP/IEF)': f_inflation,
    'VIX恐慌': f_vix, '金矿/黄金': f_gdx_gold, '白银/黄金': f_silver_gold,
    '黄金VIX': f_gvz, '央行购金代理(ETP)': f_cb_proxy, '金矿/银矿': f_miner_ratio,
    '美元/日元': f_usd_jpy, '金/纽蒙特': f_gold_nem, 'MA200偏离': f_ma200_dev,
    'MA交叉信号': f_ma_cross, '20日动量': f_mom_20d, '60日动量': f_mom_60d,
    '20日波动率': f_vol_20d, '60日波动率': f_vol_60d, 'RSI14': f_rsi,
    '实际利率×美元': f_real_x_dxy, 'VIX×通胀预期': f_vix_x_infl, '金矿×VIX': f_gdx_x_vix,
    '波动率变化': f_vol_change, '动量加速度': f_mom_accel, '金价/长期均线': f_gold_ma_ratio,
    '10年实际利率': f_real_rate_10y, '5年实际利率': f_real_rate_5y,
    '联邦基金利率': f_fed_rate, '10年通胀预期': f_infl_exp_10y,
    '2s10s利差': f_2s10s, '5s30s利差': f_5s30s, '曲线倒挂信号': f_curve_invert,
    '铜金比': f_copper_gold, 'BTC/黄金': f_btc_gold, 'VIX期限结构': f_vix_term_spread,
    '距FOMC天数': f_days_to_fomc, 'FOMC周': f_fomc_week,
    '距CPI天数': f_days_to_cpi, 'CPI周': f_cpi_week,
    '实际利率×Fed利率': f_real_x_fed, '铜金比×VIX': f_copper_x_vix, '曲线×美元': f_curve_x_dxy,
})
factors = factors.dropna(how='all')
factors['MA交叉信号'] = factors['MA交叉信号'].fillna(0)
fred_cols = ['10年实际利率','5年实际利率','联邦基金利率','10年通胀预期',
             '2s10s利差','5s30s利差','曲线倒挂信号','铜金比','BTC/黄金','VIX期限结构']
for col in fred_cols:
    if col in factors.columns:
        factors[col] = factors[col].ffill()
for col in ['实际利率×Fed利率', '铜金比×VIX', '曲线×美元']:
    if col in factors.columns:
        factors[col] = factors[col].ffill()
factors['距FOMC天数'] = factors['距FOMC天数'].fillna(30)
factors['距CPI天数'] = factors['距CPI天数'].fillna(15)
factors['FOMC周'] = factors['FOMC周'].fillna(0)
factors['CPI周'] = factors['CPI周'].fillna(0)

# 标签
PREDICT_DAYS = [5, 10, 20, 60]
for n in PREDICT_DAYS:
    factors[f'未来{n}日收益'] = factors['金价'].pct_change(n).shift(-n)
    factors[f'未来{n}日涨跌'] = (factors[f'未来{n}日收益'] > 0).astype(int)

# Regime
ma200 = factors['金价'].rolling(200).mean()
ma50 = factors['金价'].rolling(50).mean()
vol_60 = factors['金价'].pct_change().rolling(60).std() * np.sqrt(250)
regime = pd.Series('震荡', index=factors.index)
regime[(factors['金价'] > ma200) & (ma50 > ma200)] = '牛市'
regime[(factors['金价'] < ma200) & (ma50 < ma200)] = '熊市'

# ═══════════════════════════════════════════════════════════════════
# 3. Walk-Forward训练（复用V4逻辑）
# ═══════════════════════════════════════════════════════════════════

print("[3] Walk-Forward训练...")
feature_cols = [c for c in factors.columns if c not in
    ['金价', 'Regime', '高波动', 'MA200', 'MA50',
     '未来5日收益','未来10日收益','未来20日收益','未来60日收益',
     '未来5日涨跌','未来10日涨跌','未来20日涨跌','未来60日涨跌']]

ml_results = {}
TRAIN_WINDOW = 500
TEST_WINDOW = 60
STEP = 30

for pred_days in PREDICT_DAYS:
    target_col = f'未来{pred_days}日涨跌'
    ret_col = f'未来{pred_days}日收益'
    X = factors[feature_cols].copy()
    y = factors[target_col].copy()
    rets = factors[ret_col].copy()
    predictions, actuals, probabilities, pred_returns, pred_dates = [], [], [], [], []
    start_idx = TRAIN_WINDOW
    while start_idx + TEST_WINDOW <= len(X):
        end_idx = start_idx + TEST_WINDOW
        train_mask = slice(max(0, start_idx - TRAIN_WINDOW), start_idx)
        test_mask = slice(start_idx, end_idx)
        X_train = X.iloc[train_mask].copy()
        y_train = y.reindex(X_train.index)
        valid_train = y_train.notna()
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        train_medians = X_train.median()
        X_train = X_train.fillna(train_medians)
        X_test = X.iloc[test_mask].copy()
        y_test = y.reindex(X_test.index)
        valid_test = y_test.notna()
        X_test = X_test[valid_test]
        y_test = y_test[valid_test]
        X_test = X_test.fillna(train_medians)
        if len(X_train) < 100 or len(X_test) < 10:
            start_idx += STEP
            continue
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)
        model_xgb = xgb.XGBClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            random_state=42, use_label_encoder=False,
            eval_metric='logloss', verbosity=0)
        model_xgb.fit(X_train_s, y_train)
        model_lgb = lgb.LGBMClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            random_state=42, verbose=-1)
        model_lgb.fit(X_train_s, y_train)
        prob_xgb = model_xgb.predict_proba(X_test_s)[:, 1]
        prob_lgb = model_lgb.predict_proba(X_test_s)[:, 1]
        prob_ens = (prob_xgb + prob_lgb) / 2
        pred_ens = (prob_ens > 0.5).astype(int)
        predictions.extend(pred_ens)
        actuals.extend(y_test.values)
        probabilities.extend(prob_ens)
        pred_returns.extend(rets.reindex(X_test.index).values)
        pred_dates.extend(X_test.index)
        start_idx += STEP

    predictions = np.array(predictions)
    actuals = np.array(actuals)
    probabilities = np.array(probabilities)
    pred_returns = np.array(pred_returns)
    valid = ~np.isnan(pred_returns) & ~np.isnan(actuals.astype(float))
    df_tmp = pd.DataFrame({
        'prob': probabilities[valid],
        'date': [pred_dates[i] for i in range(len(pred_dates)) if valid[i]],
    })
    df_tmp = df_tmp.drop_duplicates(subset='date', keep='last')
    ml_results[pred_days] = {
        'probabilities': df_tmp['prob'].values,
        'dates': df_tmp['date'].tolist(),
    }
    acc = accuracy_score(actuals[valid], predictions[valid])
    print(f"  {pred_days}日: acc={acc:.1%}, 样本={valid.sum()}")

# ═══════════════════════════════════════════════════════════════════
# 4. 构建V3.0-E仓位序列 + 信号频率分析
# ═══════════════════════════════════════════════════════════════════

print("\n[4] 仓位序列 + 信号频率分析...")

pred20 = ml_results[20]
prob_series = pd.Series(pred20['probabilities'], index=pred20['dates'])
prob_series = prob_series[~prob_series.index.duplicated(keep='last')]
regime_aligned = regime.reindex(prob_series.index).fillna('震荡')
gold_returns = factors['金价'].pct_change().reindex(prob_series.index)

prob5_s = pd.Series(ml_results[5]['probabilities'], index=ml_results[5]['dates'])
prob10_s = pd.Series(ml_results[10]['probabilities'], index=ml_results[10]['dates'])
prob60_s = pd.Series(ml_results[60]['probabilities'], index=ml_results[60]['dates'])
prob5_aligned = prob5_s.reindex(prob_series.index).ffill()
prob10_aligned = prob10_s.reindex(prob_series.index).ffill()
prob60_aligned = prob60_s.reindex(prob_series.index).ffill()
prob_multi = 0.15 * prob5_aligned + 0.25 * prob10_aligned + 0.40 * prob_series + 0.20 * prob60_aligned

bull = regime_aligned == '牛市'
bear = regime_aligned == '熊市'
range_ = regime_aligned == '震荡'
pm = prob_multi

v3e_pos = pd.Series(0.0, index=prob_series.index)
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

# Vol targeting
target_vol = 0.15
realized_vol = gold_returns.rolling(20).std() * np.sqrt(250)
vol_scalar = target_vol / realized_vol
vol_scalar = vol_scalar.clip(0, 2)
v3e_pos = v3e_pos * vol_scalar
v3e_pos = v3e_pos.clip(-1.5, 1.5)

# ═══════════════════════════════════════════════════════════════════
# 5. 信号频率统计（核心分析）
# ═══════════════════════════════════════════════════════════════════

print("\n[5] 信号频率统计...")

pos = v3e_pos.dropna()
pos_changes = pos.diff().fillna(0) != 0
change_dates = pos.index[pos_changes]

# 仓位变化统计
n_changes = pos_changes.sum()
n_days = len(pos)
avg_hold_days = n_days / max(n_changes, 1)

# 按变化幅度分类
pos_diff = pos.diff().abs()
major_change = (pos_diff >= 0.5).sum()  # 大调仓
minor_change = ((pos_diff > 0) & (pos_diff < 0.5)).sum()  # 小调仓
no_change = (pos_diff == 0).sum()

# 持仓时长分布
hold_periods = []
change_idx = np.where(pos_changes.values)[0]
if len(change_idx) > 1:
    for i in range(len(change_idx) - 1):
        hold_periods.append(change_idx[i+1] - change_idx[i])
hold_periods = np.array(hold_periods) if hold_periods else np.array([0])

# 仓位分布
pos_buckets = {
    '空仓 (0)': ((pos == 0)).sum(),
    '轻仓多 (0-0.5)': ((pos > 0) & (pos <= 0.5)).sum(),
    '半仓多 (0.5-0.8)': ((pos > 0.5) & (pos <= 0.8)).sum(),
    '满仓多 (>0.8)': ((pos > 0.8)).sum(),
    '轻仓空 (-0.5-0)': ((pos < 0) & (pos >= -0.5)).sum(),
    '半仓空 (<-0.5)': ((pos < -0.5)).sum(),
}

# 月度调仓次数
monthly_changes = pd.Series(pos_changes.astype(int), index=pos.index).resample('M').sum()

# Regime下仓位分布
regime_pos_stats = {}
for r in ['牛市', '熊市', '震荡']:
    mask = regime_aligned == r
    if mask.sum() > 0:
        regime_pos_stats[r] = {
            '天数': int(mask.sum()),
            '平均仓位': float(pos[mask].mean()),
            '仓位标准差': float(pos[mask].std()),
            '空仓占比': float((pos[mask] == 0).mean()),
            '满仓占比': float((pos[mask] > 0.8).mean()),
        }

stats = {
    '分析区间': f"{pos.index[0].date()} ~ {pos.index[-1].date()}",
    '总交易日': int(n_days),
    '总调仓次数': int(n_changes),
    '平均持仓天数': float(avg_hold_days),
    '大调仓(≥50%)': int(major_change),
    '小调仓(<50%)': int(minor_change),
    '无变化天数': int(no_change),
    '持仓天数_中位数': float(np.median(hold_periods)) if len(hold_periods) > 0 else 0,
    '持仓天数_P25': float(np.percentile(hold_periods, 25)) if len(hold_periods) > 0 else 0,
    '持仓天数_P75': float(np.percentile(hold_periods, 75)) if len(hold_periods) > 0 else 0,
    '持仓天数_最长': int(hold_periods.max()) if len(hold_periods) > 0 else 0,
    '月均调仓次数': float(monthly_changes.mean()),
    '调仓最多月': int(monthly_changes.max()),
    '调仓最少月': int(monthly_changes.min()),
    '仓位分布': {k: int(v) for k, v in pos_buckets.items()},
    'Regime统计': regime_pos_stats,
    '当前Regime': str(regime.iloc[-1]),
    '当前仓位': float(pos.iloc[-1]),
    '当前概率': float(pm.iloc[-1]),
}

print(f"  分析区间: {stats['分析区间']}")
print(f"  总调仓次数: {stats['总调仓次数']}")
print(f"  平均持仓天数: {stats['平均持仓天数']:.1f}")
print(f"  大调仓(≥50%): {stats['大调仓(≥50%)']}")
print(f"  小调仓(<50%): {stats['小调仓(<50%)']}")
print(f"  月均调仓: {stats['月均调仓次数']:.1f}次")
print(f"  持仓天数 P50: {stats['持仓天数_中位数']:.0f}, P75: {stats['持仓天数_P75']:.0f}")
print(f"  仓位分布:")
for k, v in pos_buckets.items():
    pct = v / n_days * 100
    print(f"    {k}: {v}天 ({pct:.1f}%)")
print(f"\n  Regime统计:")
for r, s in regime_pos_stats.items():
    print(f"    {r}: {s['天数']}天, 均仓{s['平均仓位']:.2f}, 空仓{s['空仓占比']:.1%}")

# ═══════════════════════════════════════════════════════════════════
# 6. ETF+期货执行方案设计
# ═══════════════════════════════════════════════════════════════════

print("\n[6] ETF+期货执行方案设计...")

# 成本参数
ETF_COMMISSION = 0.0001  # 万一
ETF_MGMT_FEE = 0.006  # 0.6%/年
FUTURES_COMMISSION = 3  # $/手
FUTURES_MARGIN = 0.05  # 5%保证金≈20倍杠杆
GC_CONTRACT_SIZE = 100  # 100盎司/手

current_gold = float(factors['金价'].iloc[-1])
print(f"  当前金价: ${current_gold:.2f}")

# 方案设计：分层执行
# 底仓层 (ETF): 承载60-70%的资金，低频调仓
# 战术层 (期货): 承载30-40%的资金，高频调仓

# 根据信号频率计算最优分层
# 大调仓频率低(月均X次)→ETF执行
# 小调仓频率高(月均Y次)→期货执行

# 回测两种执行方式的成本
def calc_etf_cost(position_series, capital, gold_price):
    """ETF执行成本"""
    # 每次调仓的交易成本
    changes = position_series.diff().fillna(0).abs()
    # 每次调仓的交易额
    trade_value = changes * capital
    # 佣金成本
    commission = trade_value * ETF_COMMISSION
    # 管理费(按持仓时间)
    mgmt_fee = position_series.abs() * capital * ETF_MGMT_FEE / 250
    total_commission = commission.sum()
    total_mgmt = mgmt_fee.sum()
    return {
        '总佣金': float(total_commission),
        '总管理费': float(total_mgmt),
        '总成本': float(total_commission + total_mgmt),
        '日均成本': float((total_commission + total_mgmt) / len(position_series)),
    }

def calc_futures_cost(position_series, capital, gold_price):
    """期货执行成本"""
    changes = position_series.diff().fillna(0).abs()
    # 期货需要的合约数（杠杆后）
    # 假设资本100万，金价$2000，1手=100盎司=$200,000
    # 1倍仓位 = capital / (GC_CONTRACT_SIZE * gold_price) 手
    contracts_per_unit = capital / (GC_CONTRACT_SIZE * gold_price)
    n_contracts = changes * contracts_per_unit
    # 佣金 $3/手
    commission = n_contracts * FUTURES_COMMISSION
    # 无管理费，但有保证金占用成本（机会成本）
    margin_used = position_series.abs() * capital * FUTURES_MARGIN
    # 保证金机会成本（按货币基金2%算）
    margin_cost = margin_used * 0.02 / 250
    total_commission = commission.sum()
    total_margin = margin_cost.sum()
    return {
        '总佣金': float(total_commission),
        '保证金机会成本': float(total_margin),
        '总成本': float(total_commission + total_margin),
        '日均成本': float((total_commission + total_margin) / len(position_series)),
    }

# 分层执行成本
def calc_hybrid_cost(position_series, capital, gold_price, etf_ratio=0.65):
    """ETF+期货分层执行"""
    etf_capital = capital * etf_ratio
    fut_capital = capital * (1 - etf_ratio)
    
    # ETF层：只承载大调仓（仓位变化≥0.3的部分）
    etf_pos = position_series.copy()
    # 小变化归零（ETF只做大仓位调整）
    small_changes = position_series.diff().abs() < 0.3
    # ETF仓位 = 信号的平滑版
    etf_pos = position_series.rolling(5).mean().clip(-1.5, 1.5)
    
    # 期货层：总仓位 - ETF仓位
    fut_pos = position_series - etf_pos
    
    etf_cost = calc_etf_cost(etf_pos, etf_capital, gold_price)
    fut_cost = calc_futures_cost(fut_pos, fut_capital, gold_price)
    
    return {
        'ETF成本': etf_cost,
        '期货成本': fut_cost,
        '总成本': etf_cost['总成本'] + fut_cost['总成本'],
        '日均成本': (etf_cost['日均成本'] + fut_cost['日均成本']),
    }

# 模拟不同资金规模
capitals = [100_000, 500_000, 1_000_000, 5_000_000]  # ¥10万~500万
cost_comparison = {}
for cap in capitals:
    # 换算：人民币资金→美元黄金仓位
    usd_cap = cap / 7.2  # 假设汇率7.2
    etf_only = calc_etf_cost(v3e_pos, usd_cap, current_gold)
    fut_only = calc_futures_cost(v3e_pos, usd_cap, current_gold)
    hybrid = calc_hybrid_cost(v3e_pos, usd_cap, current_gold, etf_ratio=0.65)
    cost_comparison[cap] = {
        '纯ETF': etf_only,
        '纯期货': fut_only,
        'ETF+期货分层': hybrid,
    }

print("\n  成本对比（年化）:")
for cap, costs in cost_comparison.items():
    n_years = len(v3e_pos) / 250
    print(f"\n  资金: ¥{cap:,.0f} (≈${cap/7.2:,.0f})")
    for mode, c in costs.items():
        if isinstance(c, dict) and '总成本' in c:
            ann_cost = c['总成本'] / n_years
            pct = ann_cost / (cap / 7.2) * 100
            print(f"    {mode}: 年化${ann_cost:,.0f} ({pct:.2f}%/年)")
        elif isinstance(c, dict) and 'ETF成本' in c:
            ann_cost = c['总成本'] / n_years
            pct = ann_cost / (cap / 7.2) * 100
            print(f"    {mode}: 年化${ann_cost:,.0f} ({pct:.2f}%/年)")

# ═══════════════════════════════════════════════════════════════════
# 7. 最优执行路径设计
# ═══════════════════════════════════════════════════════════════════

print("\n[7] 最优执行路径设计...")

# 根据信号特征设计执行规则
execution_rules = {
    '底仓层(ETF 518880)': {
        '资金占比': '60-70%',
        '调仓触发': '仓位变化≥0.3 或 Regime切换',
        '调仓频率': f'月均{major_change / (len(v3e_pos) / 250 * 12):.1f}次',
        '目标': '承载核心仓位，降低交易成本',
        '操作': '按V3.0-E仓位信号×0.65执行',
        '佣金': '万一，免印花税',
        '持有成本': '0.6%/年管理费',
    },
    '战术层(COMEX GC=F)': {
        '资金占比': '30-40%',
        '调仓触发': '任何仓位变化',
        '调仓频率': f'月均{n_changes / (len(v3e_pos) / 250 * 12):.1f}次',
        '目标': '精细调仓，杠杆增强收益',
        '操作': '按(总仓位 - ETF仓位)执行',
        '佣金': '$3/手',
        '杠杆': '约20倍',
    },
    '现金层': {
        '资金占比': '0-10%',
        '用途': '保证金追加 + ETF申购赎回缓冲',
        '收益': '货币基金2-2.5%',
    },
}

# 情景化执行手册
scenarios = []
# 牛市满仓场景
scenarios.append({
    '场景': '牛市+高概率(P>0.65)',
    '模型仓位': '100%',
    'ETF执行': '65%（底仓满配）',
    '期货执行': '35%（战术增强）',
    '操作': 'ETF买入518880至65%→期货开多35%→总仓位100%',
    '注意事项': '期货杠杆部分需严格止损',
})

# 牛市半仓场景
scenarios.append({
    '场景': '牛市+中概率(0.55<P≤0.65)',
    '模型仓位': '60%',
    'ETF执行': '39%（底仓部分）',
    '期货执行': '21%（战术部分）',
    '操作': 'ETF持有39%→期货调整至21%多→总仓位60%',
    '注意事项': '可考虑期货部分减仓而非ETF',
})

# 空仓场景
scenarios.append({
    '场景': '牛市+低概率(P≤0.48) 或 震荡市',
    '模型仓位': '0%',
    'ETF执行': '0%（清仓）',
    '期货执行': '0%（平仓）',
    '操作': 'ETF全部卖出→期货平仓→转入货币基金',
    '注意事项': 'ETF T+0可当天进出',
})

# 熊市做空场景
scenarios.append({
    '场景': '熊市+低概率(P<0.35)',
    '模型仓位': '-100%（做空）',
    'ETF执行': '0%（ETF不能做空）',
    '期货执行': '-100%（全部期货做空）',
    '操作': 'ETF清仓→期货开空100%→纯空头',
    '注意事项': '做空只用期货，ETF无法做空',
})

# 止损场景
scenarios.append({
    '场景': '止损触发(回撤>8%)',
    '模型仓位': '强制空仓3天',
    'ETF执行': '立即清仓',
    '期货执行': '立即平仓',
    '操作': '两腿同时平仓→等待3天→重新建仓',
    '注意事项': '期货滑点更小，优先平期货',
})

print("\n  执行规则:")
for layer, rules in execution_rules.items():
    print(f"\n  【{layer}】")
    for k, v in rules.items():
        print(f"    {k}: {v}")

print("\n  情景执行手册:")
for s in scenarios:
    print(f"\n  ▶ {s['场景']}")
    print(f"    模型仓位: {s['模型仓位']}")
    print(f"    ETF: {s['ETF执行']} | 期货: {s['期货执行']}")
    print(f"    操作: {s['操作']}")

# ═══════════════════════════════════════════════════════════════════
# 8. 保存分析结果
# ═══════════════════════════════════════════════════════════════════

print("\n[8] 保存分析结果...")

# 保存仓位序列供后续使用
pos_df = pd.DataFrame({
    'date': v3e_pos.index,
    'position': v3e_pos.values,
    'probability': pm.reindex(v3e_pos.index).values,
    'regime': regime_aligned.reindex(v3e_pos.index).values,
    'gold_price': factors['金价'].reindex(v3e_pos.index).values,
    'gold_return': gold_returns.reindex(v3e_pos.index).values,
})
pos_df.to_csv(str(EXECUTION_PLAN_DIR / 'position_series.csv'), index=False)

# 保存统计结果
output = {
    'signal_stats': stats,
    'cost_comparison': {
        str(k): {
            mode: {kk: float(vv) if isinstance(vv, (int, float, np.number)) else 
                   ({kkk: float(vvv) if isinstance(vvv, (int, float, np.number)) else vvv 
                     for kkk, vvv in vv.items()} if isinstance(vv, dict) else vv)
                   for kk, vv in v.items()}
            for mode, v in costs.items()
        }
        for k, costs in cost_comparison.items()
    },
    'execution_rules': execution_rules,
    'scenarios': scenarios,
    'current': {
        'gold_price': current_gold,
        'regime': str(regime.iloc[-1]),
        'position': float(v3e_pos.iloc[-1]),
        'probability': float(pm.iloc[-1]),
        'ma200': float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else current_gold,
        'ma50': float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else current_gold,
        'vol_60d': float(vol_60.iloc[-1]) if pd.notna(vol_60.iloc[-1]) else 0.15,
    },
}

with open(str(ANALYSIS_JSON), 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print("  ✅ position_series.csv")
print("  ✅ analysis.json")
print(f"\n  当前状态: Regime={output['current']['regime']}, 仓位={output['current']['position']:.2f}, 概率={output['current']['probability']:.1%}")
print("\n  分析完成，可生成PDF报告。")
