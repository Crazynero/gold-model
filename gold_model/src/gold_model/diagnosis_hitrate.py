#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V4模型命中率10%问题诊断脚本
提取WF预测明细，分段分析失效原因
"""
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 复用V4脚本的数据和训练逻辑
# 为了避免完整跑V4（3分钟），我们只跑数据+WF训练部分
print("=" * 60)
print("  V4 命中率问题诊断")
print("=" * 60)

# 导入V4脚本中的变量（通过exec方式获取中间结果）
# 更简单的方式：直接在V4脚本运行时注入诊断代码

# 方案：写一个精简版，只跑WF训练+诊断
import yfinance as yf
import requests
import io
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
import xgboost as xgb
import lightgbm as lgb

# ── 1. 加载数据（复用data_fetcher）──
from gold_model.data_fetcher import fetch_ticker_with_fallback
from gold_model.paths import CHARTS_DIR

TICKERS = {
    'GC=F': '黄金期货', 'GLD': 'GLD基金', 'IAU': 'IAU基金', 'SGOL': 'SGOL基金',
    'DX-Y.NYB': '美元指数', 'TIP': 'TIPS', 'IEF': '名义利率', 'TLT': '20+年国债',
    'SLV': '白银', 'GDX': '金矿股', 'GDXJ': '金矿小盘', 'SIL': '白银矿企',
    '^VIX': 'VIX恐慌', '^GVZ': '黄金VIX', 'NEM': '纽蒙特矿业',
    'EUR=X': '欧元/美元', 'JPY=X': '美元/日元', 'UUP': '美元ETF',
    'HG=F': '铜期货', 'BTC-USD': '比特币', '^VIX9D': 'VIX9D',
    '^IRX': '13周国债', '^FVX': '5年国债', '^TNX': '10年国债', '^TYX': '30年国债',
}

print("\n[1] 数据加载...")
raw = {}
for ticker, name in TICKERS.items():
    s = fetch_ticker_with_fallback(ticker, name, period='5y', verbose=False)
    if s is not None:
        raw[name] = s

# FRED
FRED_SERIES = {
    'DFII10': '实际利率10年', 'DFII5': '实际利率5年',
    'DGS2': '国债2年', 'DGS10': '国债10年', 'DGS30': '国债30年',
    'DFF': '联邦基金利率', 'T10YIE': '通胀预期10年',
}
for sid, name in FRED_SERIES.items():
    try:
        url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and 'html' not in r.text[:50].lower():
            df_f = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
            df_f = df_f.replace('.', np.nan).astype(float)
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=5*365)
            df_f = df_f[df_f.index > cutoff]
            if len(df_f) > 100:
                raw[name] = df_f.iloc[:, 0]
    except:
        pass

df = pd.DataFrame(raw)
print(f"  合并: {df.shape}")

# V4.3关键修复：先过滤掉金价为NaN的行（FRED非交易日），再做后续计算
df = df[df['黄金期货'].notna()].copy()

# ── 2. 构建因子（精简版，只保留关键因子）──
print("\n[2] 因子构建...")
gold = df['黄金期货']

factors = pd.DataFrame(index=df.index)
factors['金价'] = gold
factors['美元指数'] = df['美元指数']
factors['实际利率'] = df['TIPS'] if 'TIPS' in df else df.get('实际利率10年')
factors['名义利率'] = df['名义利率']
factors['VIX'] = df['VIX恐慌']
factors['金矿/黄金'] = df['金矿股'] / gold
factors['白银/黄金'] = df['白银'] / gold
factors['铜金比'] = df['铜期货'] / gold
factors['BTC/黄金'] = df['比特币'] / gold
factors['5日动量'] = gold.pct_change(5)
factors['20日动量'] = gold.pct_change(20)
factors['60日动量'] = gold.pct_change(60)
factors['MA50偏离'] = gold / gold.rolling(50).mean() - 1
factors['MA200偏离'] = gold / gold.rolling(200).mean() - 1
factors['20日波动率'] = gold.pct_change().rolling(20).std() * np.sqrt(252)
factors['60日波动率'] = gold.pct_change().rolling(60).std() * np.sqrt(252)
# V4.3: 新增反转特征——让模型能看到"超买/超跌"
# 用factors['金价']确保index对齐
g = factors['金价']
factors['5日涨幅'] = g.pct_change(5)
factors['20日涨幅'] = g.pct_change(20)
factors['60日涨幅'] = g.pct_change(60)
factors['120日涨幅'] = g.pct_change(120)
factors['20日最大回撤'] = g.rolling(20).apply(lambda x: (x/np.maximum.accumulate(x)-1).min(), raw=True)
factors['相对20日高点'] = g / g.rolling(20).max() - 1
factors['相对60日高点'] = g / g.rolling(60).max() - 1
factors['波动率变化'] = factors['20日波动率'] / factors['20日波动率'].rolling(20).mean() - 1

# Regime (V4.3: 加波动率触发)
ma50 = factors['金价'].rolling(50).mean()
ma200 = factors['金价'].rolling(200).mean()
vol_60 = factors['金价'].pct_change().rolling(60).std() * np.sqrt(250)
vol_rank = vol_60.rolling(252).rank(pct=True)
gold_ret_20d = factors['金价'].pct_change(20)
gold_vs_ma50 = (factors['金价'] - ma50) / ma50

regime = pd.Series('震荡', index=factors.index)
regime[(factors['金价'] > ma200) & (ma50 > ma200)] = '牛市'
regime[(factors['金价'] < ma200) & (ma50 < ma200)] = '熊市'
# V4.3: 急跌加速转熊
fast_bear = (gold_vs_ma50 < -0.03) & (gold_ret_20d < -0.05) & (vol_rank > 0.6)
regime[fast_bear & (regime != '熊市')] = '熊市'
# V4.3: 急涨加速转牛
fast_bull = (gold_vs_ma50 > 0.03) & (gold_ret_20d > 0.05) & (factors['金价'] > ma200)
regime[fast_bull & (regime == '震荡')] = '牛市'
factors['Regime'] = regime

print(f"  因子矩阵: {factors.shape}")
print(f"  Regime分布: {factors['Regime'].value_counts().to_dict()}")

# ── 3. WF训练（20日预测，与V4一致）──
print("\n[3] WF训练（20日预测）...")

PRED_DAYS = 20
feature_cols = [c for c in factors.columns if c not in ['金价', 'Regime']]

# 标签：20日后收益率>0
factors['label_20d'] = (factors['金价'].shift(-PRED_DAYS) > factors['金价']).astype(int)
factors['return_20d'] = factors['金价'].shift(-PRED_DAYS) / factors['金价'] - 1

# 训练数据
data = factors.dropna(subset=feature_cols + ['label_20d', 'return_20d']).copy()
X = data[feature_cols].values
y = data['label_20d'].values
returns = data['return_20d'].values
dates = data.index

print(f"  训练数据: {len(data)}条, {len(feature_cols)}特征")
print(f"  正样本比例: {y.mean():.1%}")

# WF参数（V4.3: 缩短训练窗口350→更快适应市场变化）
TRAIN_WINDOW = 350
TEST_WINDOW = 60
STEP = 30

predictions = []
actuals = []
probabilities = []
pred_returns = []
pred_dates = []
regimes_at_pred = []

start_idx = 0
while start_idx + TRAIN_WINDOW + TEST_WINDOW <= len(X):
    end_train = start_idx + TRAIN_WINDOW
    end_test = start_idx + TRAIN_WINDOW + TEST_WINDOW
    
    X_train = X[start_idx:end_train]
    y_train = y[start_idx:end_train]
    X_test = X[end_train:end_test]
    y_test = y[end_train:end_test]
    
    # 中位数填充
    medians = np.nanmedian(X_train, axis=0)
    X_train = np.where(np.isnan(X_train), medians, X_train)
    X_test = np.where(np.isnan(X_test), medians, X_test)
    
    # 标准化
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # V4.3: 训练（标签平衡+概率校准）
    pos_count = y_train.sum()
    neg_count = len(y_train) - pos_count
    spw = min(neg_count / pos_count if pos_count > 0 else 1.0, 2.0)
    xgb_model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8, random_state=42,
                                   scale_pos_weight=spw,
                                   eval_metric='logloss', verbosity=0)
    lgb_model = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.05,
                                    subsample=0.8, colsample_bytree=0.8, random_state=42,
                                    class_weight={0: spw, 1: 1.0},
                                    verbose=-1)
    xgb_model.fit(X_train_s, y_train)
    lgb_model.fit(X_train_s, y_train)
    
    prob_xgb = xgb_model.predict_proba(X_test_s)[:, 1]
    prob_lgb = lgb_model.predict_proba(X_test_s)[:, 1]
    prob_ens = (prob_xgb + prob_lgb) / 2
    
    # V4.3: Isotonic Regression概率校准
    from sklearn.isotonic import IsotonicRegression
    prob_train_cal = (xgb_model.predict_proba(X_train_s)[:, 1] +
                     lgb_model.predict_proba(X_train_s)[:, 1]) / 2
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(prob_train_cal, y_train)
    prob_ens = iso.predict(prob_ens)
    
    pred_ens = (prob_ens >= 0.5).astype(int)
    
    predictions.extend(pred_ens)
    actuals.extend(y_test)
    probabilities.extend(prob_ens)
    pred_returns.extend(returns[end_train:end_test])
    pred_dates.extend(dates[end_train:end_test])
    regimes_at_pred.extend(data['Regime'].iloc[end_train:end_test].values)
    
    start_idx += STEP

predictions = np.array(predictions)
actuals = np.array(actuals)
probabilities = np.array(probabilities)
pred_returns = np.array(pred_returns)
pred_dates = pd.DatetimeIndex(pred_dates)
regimes_at_pred = np.array(regimes_at_pred)

# 去重
df_wf = pd.DataFrame({
    'date': pred_dates, 'prob': probabilities, 'actual': actuals,
    'return_20d': pred_returns, 'pred': predictions, 'regime': regimes_at_pred,
}).drop_duplicates(subset='date', keep='last').reset_index(drop=True)

print(f"\n  WF预测总数: {len(df_wf)}")
print(f"  整体命中率: {(df_wf['actual'] == df_wf['pred']).mean():.1%}")
print(f"  整体准确率(=命中率): {accuracy_score(df_wf['actual'], df_wf['pred']):.1%}")

# ── 4. 诊断分析 ──
print("\n" + "=" * 60)
print("  诊断分析")
print("=" * 60)

# 4.1 按季度分段命中率
print("\n[4.1] 按季度分段命中率:")
df_wf['quarter'] = df_wf['date'].dt.to_period('Q')
quarterly = df_wf.groupby('quarter').agg(
    count=('actual', 'count'),
    hit_rate=('actual', 'mean'),
    avg_prob=('prob', 'mean'),
    avg_return=('return_20d', 'mean'),
).round(3)
print(quarterly.to_string())
print(f"\n  最近20次: 命中率={df_wf['actual'].tail(20).mean():.1%}")
print(f"  最近10次: 命中率={df_wf['actual'].tail(10).mean():.1%}")

# 4.2 按Regime分段命中率
print("\n[4.2] 按Regime分段命中率:")
regime_stats = df_wf.groupby('regime').agg(
    count=('actual', 'count'),
    hit_rate=('actual', 'mean'),
    avg_prob=('prob', 'mean'),
    avg_return=('return_20d', 'mean'),
).round(3)
print(regime_stats.to_string())

# 4.3 滚动IC走势
print("\n[4.3] 滚动60日IC:")
df_wf['ic_60'] = np.nan
for i in range(60, len(df_wf)):
    window = df_wf.iloc[i-60:i]
    valid = window['return_20d'].notna()
    if valid.sum() > 10:
        ic, _ = stats.spearmanr(window.loc[valid, 'prob'], window.loc[valid, 'return_20d'])
        df_wf.loc[i, 'ic_60'] = ic

print(f"  整体IC: {stats.spearmanr(df_wf['prob'], df_wf['return_20d'])[0]:+.4f}")
print(f"  最近60日IC: {df_wf['ic_60'].iloc[-1]:+.4f}")
print(f"  最近120日IC均值: {df_wf['ic_60'].tail(120).mean():+.4f}")
print(f"  IC由正转负时间点: ", end='')
neg_ic = df_wf[df_wf['ic_60'] < 0]
if len(neg_ic) > 0:
    print(neg_ic['date'].iloc[0].strftime('%Y-%m-%d'))
else:
    print("未转负")

# 4.4 概率分布变化
print("\n[4.4] 概率分布变化:")
print(f"  全程: 均值={df_wf['prob'].mean():.3f}, 标准差={df_wf['prob'].std():.3f}")
print(f"  最近20次: 均值={df_wf['prob'].tail(20).mean():.3f}, 标准差={df_wf['prob'].tail(20).std():.3f}")
print(f"  最近20次概率范围: [{df_wf['prob'].tail(20).min():.3f}, {df_wf['prob'].tail(20).max():.3f}]")

# 4.5 最近20次详细
print("\n[4.5] 最近20次预测明细:")
recent20 = df_wf.tail(20)[['date', 'prob', 'actual', 'pred', 'return_20d', 'regime']].copy()
recent20['date'] = recent20['date'].dt.strftime('%Y-%m-%d')
recent20['correct'] = recent20['actual'] == recent20['pred']
recent20['prob'] = recent20['prob'].round(3)
recent20['return_20d'] = (recent20['return_20d'] * 100).round(2)
print(recent20.to_string(index=False))

# 4.6 标签平衡性
print("\n[4.6] 标签平衡性:")
print(f"  全程正样本比例: {df_wf['actual'].mean():.1%}")
print(f"  最近20次正样本比例: {df_wf['actual'].tail(20).mean():.1%}")
print(f"  最近20次实际20日收益: 均值={df_wf['return_20d'].tail(20).mean()*100:.2f}%, 中位数={df_wf['return_20d'].tail(20).median()*100:.2f}%")

# 4.7 概率阈值分析
print("\n[4.7] 概率阈值 vs 命中率:")
for threshold in [0.4, 0.45, 0.5, 0.55, 0.6, 0.65]:
    subset = df_wf[(df_wf['prob'] >= threshold - 0.025) & (df_wf['prob'] < threshold + 0.025)]
    if len(subset) > 5:
        print(f"  P∈[{threshold-0.025:.3f}, {threshold+0.025:.3f}): n={len(subset):3d}, 命中率={subset['actual'].mean():.1%}, 平均收益={subset['return_20d'].mean()*100:+.2f}%")

# 4.8 高概率段（>0.9）分析
print("\n[4.8] 高概率段(>0.9)分析:")
high = df_wf[df_wf['prob'] > 0.9]
mid = df_wf[(df_wf['prob'] >= 0.6) & (df_wf['prob'] < 0.9)]
low = df_wf[df_wf['prob'] < 0.6]
print(f"  概率>0.9:  n={len(high):3d}, 命中率={high['actual'].mean():.1%}, 平均收益={high['return_20d'].mean()*100:+.2f}%")
print(f"  概率0.6-0.9: n={len(mid):3d}, 命中率={mid['actual'].mean():.1%}, 平均收益={mid['return_20d'].mean()*100:+.2f}%")
print(f"  概率<0.6:  n={len(low):3d}, 命中率={low['actual'].mean():.1%}, 平均收益={low['return_20d'].mean()*100:+.2f}%")
if len(high) > 0:
    print(f"  高概率段时间范围: {high['date'].min().strftime('%Y-%m-%d')} ~ {high['date'].max().strftime('%Y-%m-%d')}")

# ── 5. 可视化 ──
print("\n[5] 生成诊断图表...")
fig, axes = plt.subplots(4, 1, figsize=(14, 16))

# 5.1 滚动命中率
ax = axes[0]
df_wf['hit_60'] = df_wf['actual'].rolling(60).mean()
ax.plot(df_wf['date'], df_wf['hit_60'], color='#3b82f6', linewidth=1.5)
ax.axhline(y=0.5, color='#94a3b8', linestyle='--', alpha=0.5)
ax.axhline(y=df_wf['actual'].mean(), color='#16a34a', linestyle='--', alpha=0.5, label=f'整体基准={df_wf["actual"].mean():.1%}')
ax.set_title('滚动60日命中率', fontsize=14, fontweight='bold')
ax.set_ylabel('命中率')
ax.legend()
ax.grid(True, alpha=0.3)
# 标记最近20次
ax.axvspan(df_wf['date'].iloc[-20], df_wf['date'].iloc[-1], alpha=0.15, color='#dc2626')

# 5.2 滚动IC
ax = axes[1]
ax.plot(df_wf['date'], df_wf['ic_60'], color='#8b5cf6', linewidth=1.5)
ax.axhline(y=0, color='#94a3b8', linestyle='--', alpha=0.5)
ax.set_title('滚动60日IC（Spearman）', fontsize=14, fontweight='bold')
ax.set_ylabel('IC')
ax.grid(True, alpha=0.3)
ax.axvspan(df_wf['date'].iloc[-20], df_wf['date'].iloc[-1], alpha=0.15, color='#dc2626')

# 5.3 概率vs时间
ax = axes[2]
colors = df_wf['actual'].map({1: '#16a34a', 0: '#dc2626'})
ax.scatter(df_wf['date'], df_wf['prob'], c=colors, alpha=0.5, s=15)
ax.axhline(y=0.5, color='#94a3b8', linestyle='--', alpha=0.5)
ax.set_title('WF预测概率 vs 实际方向（绿=对/红=错）', fontsize=14, fontweight='bold')
ax.set_ylabel('看多概率')
ax.grid(True, alpha=0.3)
ax.axvspan(df_wf['date'].iloc[-20], df_wf['date'].iloc[-1], alpha=0.15, color='#dc2626')

# 5.4 按季度命中率柱状图
ax = axes[3]
q_stats = df_wf.groupby('quarter').agg(
    hit_rate=('actual', 'mean'),
    count=('actual', 'count'),
)
q_stats = q_stats[q_stats['count'] >= 5]
ax.bar(range(len(q_stats)), q_stats['hit_rate'], color=['#dc2626' if h < 0.4 else '#f59e0b' if h < 0.55 else '#16a34a' for h in q_stats['hit_rate']])
ax.axhline(y=0.5, color='#94a3b8', linestyle='--', alpha=0.5)
ax.set_title('按季度命中率', fontsize=14, fontweight='bold')
ax.set_ylabel('命中率')
ax.set_xticks(range(len(q_stats)))
ax.set_xticklabels([str(q) for q in q_stats.index], rotation=45, fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig(str(CHARTS_DIR / 'diagnosis_hitrate.png'), dpi=120, bbox_inches='tight')
print("  ✅ diagnosis_hitrate.png")

# ── 6. 结论 ──
print("\n" + "=" * 60)
print("  诊断结论")
print("=" * 60)

# 自动判断失效起始时间
q_stats_full = df_wf.groupby('quarter').agg(
    hit_rate=('actual', 'mean'),
    count=('actual', 'count'),
)
q_stats_full = q_stats_full[q_stats_full['count'] >= 5]
recent_qs = q_stats_full.tail(6)
print(f"\n  最近6个季度命中率:")
for q, row in recent_qs.iterrows():
    print(f"    {q}: {row['hit_rate']:.1%} (n={row['count']:.0f})")

# IC趋势
ic_recent = df_wf['ic_60'].tail(60).mean()
ic_overall = df_wf['ic_60'].mean()
print(f"\n  IC趋势: 整体={ic_overall:+.4f}, 最近60日={ic_recent:+.4f}")

# 最近20次实际收益
recent_returns = df_wf['return_20d'].tail(20)
print(f"\n  最近20次实际20日收益:")
print(f"    均值={recent_returns.mean()*100:+.2f}%, 正收益占比={(recent_returns>0).mean():.0%}")

print("\n" + "=" * 60)
