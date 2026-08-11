#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阈值校准实验:为超额收益标签(方案B)寻找最优仓位阈值
=====================================================
目的:方案B(超额收益标签)已让Holdout IC转正(+0.162),但Holdout夏普仍负(-1.70),
     因为V3.0-E仓位阈值(0.65/0.55/0.48)是为"绝对涨跌"标定的。

严谨性原则:
  - 阈值搜索只在【训练期】(排除Holdout)上做,避免在Holdout上过拟合
  - Holdout作为纯样本外验证,搜索时完全不碰
  - 对比3种配置,看净效果

3种配置对比:
  1. baseline: 方案A标签 + 现行阈值(0.65/0.55/0.48)  ← 当前生产环境
  2. B+旧阈值: 方案B标签 + 现行阈值                  ← 只改标签,不调阈值(上一轮结果)
  3. B+新阈值: 方案B标签 + 校准阈值                  ← 标签+阈值都改

搜索策略(分步,避免组合爆炸):
  V3.0-E每个Regime有多个档位,但核心参数是"满仓阈值"和"空仓阈值"。
  简化搜索:每个Regime只搜2个参数(entry=开仓阈值,exit=平仓阈值)
  - 牛市: entry(满仓) / neutral(空仓线,牛市默认不空)
  - 熊市: entry_short(满仓空) / neutral(平仓线)
  - 震荡: entry(轻仓多) / entry_short(轻仓空)

跑法: PYTHONPATH=src .venv/bin/python3 tests/ablation_thresholds.py
"""
import sys
import numpy as np
import pandas as pd
from itertools import product
from scipy.stats import spearmanr

# 复用主管道(会跑完整管道拿到factors/feature_cols/bull/bear/range_)
import sys, os
import numpy as np
import pandas as pd
from itertools import product
from scipy.stats import spearmanr
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, accuracy_score

import gold_model.gold_factor_v5 as v5

factors = v5.factors.copy()
feature_cols = v5.feature_cols
PREDICT_DAYS = v5.PREDICT_DAYS
bull = v5.bull
bear = v5.bear
range_ = v5.range_
TRAIN_WINDOW = v5.TRAIN_WINDOW
TEST_WINDOW = v5.TEST_WINDOW
STEP = v5.STEP
GAP = v5.GAP
REGIME_CONDITIONAL = v5.REGIME_CONDITIONAL
regime_series_all = factors['Regime'] if 'Regime' in factors else None
gold_ret_raw = factors['金价'].pct_change()


# ── 标签构建(只构建方案B)──
def build_labels_excess(n_list):
    """超额收益标签(方案B):未来N日收益 > 滚动250日均值收益×N"""
    labels = {}
    for n in n_list:
        ret_n = factors['金价'].pct_change(n).shift(-n)
        rolling_mean_ret = gold_ret_raw.rolling(250).mean() * n
        label = (ret_n > rolling_mean_ret.shift(-n)).astype(float)
        labels[n] = (label, ret_n)
    return labels


# ── Walk-Forward训练(复刻主管道,标签可替换)──
def walk_forward(labeled_data, pred_days):
    label_col, ret_col = labeled_data[pred_days]
    X = factors[feature_cols].copy()
    y = label_col.reindex(X.index)
    rets = ret_col.reindex(X.index)
    regime_s = regime_series_all

    predictions, actuals, probabilities, pred_dates = [], [], [], []
    start_idx = TRAIN_WINDOW
    while start_idx + TEST_WINDOW <= len(X):
        end_idx = start_idx + TEST_WINDOW
        train_end = start_idx - GAP
        train_start = max(0, train_end - TRAIN_WINDOW)
        X_train = X.iloc[train_start:train_end].copy()
        y_train = y.reindex(X_train.index)

        if REGIME_CONDITIONAL and regime_s is not None:
            test_regimes = regime_s.iloc[start_idx:end_idx].dropna()
            if len(test_regimes) > 0:
                target_regime = test_regimes.mode().iloc[0] if len(test_regimes.mode()) > 0 else '震荡'
                train_regimes = regime_s.reindex(X_train.index)
                regime_mask = (train_regimes == target_regime)
                if regime_mask.sum() >= 100:
                    X_train = X_train[regime_mask]
                    y_train = y_train[regime_mask]

        valid_train = y_train.notna()
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        train_medians = X_train.median()
        X_train = X_train.fillna(train_medians)

        X_test = X.iloc[start_idx:end_idx].copy()
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

        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        spw = min(neg_count / pos_count if pos_count > 0 else 1.0, 2.0)

        model_xgb = xgb.XGBClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            scale_pos_weight=spw, random_state=42,
            use_label_encoder=False, eval_metric='logloss', verbosity=0)
        model_xgb.fit(X_train_s, y_train)

        model_lgb = lgb.LGBMClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.15, reg_lambda=1.5,
            class_weight={0: spw, 1: 1.0}, random_state=42, verbose=-1)
        model_lgb.fit(X_train_s, y_train)

        prob_ens = (model_xgb.predict_proba(X_test_s)[:, 1] +
                    model_lgb.predict_proba(X_test_s)[:, 1]) / 2
        prob_train_cal = (model_xgb.predict_proba(X_train_s)[:, 1] +
                          model_lgb.predict_proba(X_train_s)[:, 1]) / 2
        iso = IsotonicRegression(out_of_bounds='clip')
        iso.fit(prob_train_cal, y_train.values)
        prob_ens = iso.predict(prob_ens)
        pred_ens = (prob_ens > 0.5).astype(int)

        predictions.extend(pred_ens)
        actuals.extend(y_test.values)
        probabilities.extend(prob_ens)
        pred_dates.extend(X_test.index)
        start_idx += STEP

    dates = pd.Index(pred_dates)
    probs_s = pd.Series(probabilities, index=dates)
    probs_s = probs_s[~probs_s.index.duplicated(keep='last')]
    rets_s = ret_col.reindex(probs_s.index)
    actuals_s = pd.Series(actuals, index=dates)
    actuals_s = actuals_s[~actuals_s.index.duplicated(keep='last')]

    valid = probs_s.notna() & rets_s.notna()
    if valid.sum() > 10:
        ic, _ = spearmanr(probs_s[valid], rets_s[valid])
        acc = accuracy_score(actuals_s[valid], (probs_s[valid] > 0.5).astype(int))
        try:
            auc = roc_auc_score(actuals_s[valid], probs_s[valid])
        except Exception:
            auc = 0.5
    else:
        ic, acc, auc = 0, 0, 0.5
    return {'dates': dates, 'probabilities': probs_s, 'ic': ic, 'acc': acc, 'auc': auc}

print("\n" + "=" * 80)
print("阈值校准实验:为超额收益标签寻找最优仓位阈值")
print("=" * 80)

HOLDOUT_DAYS = 125
holdout_start_date = factors.index[len(factors) - HOLDOUT_DAYS]
train_end_date = holdout_start_date  # 训练期截止 = Holdout起始
print(f"训练期(阈值搜索): ~{train_end_date.date()}")
print(f"Holdout(验证): {holdout_start_date.date()} ~ 末尾")


# ── 步骤1: 跑方案B的walk-forward训练(复用ablation_labels的函数) ──
print("\n[1] 训练方案B(超额收益标签)的4周期模型...")
labeled_B = build_labels_excess(PREDICT_DAYS)
ml_res_B = {}
for n in PREDICT_DAYS:
    r = walk_forward(labeled_B, n)
    ml_res_B[n] = r
    print(f"  {n}日: IC={r['ic']:+.4f} ACC={r['acc']:.1%}")

# 集成概率(IC自适应权重)
ics_B = np.array([ml_res_B[d]['ic'] for d in PREDICT_DAYS])
temp = 0.5
scaled = ics_B / temp
exp_v = np.exp(scaled - scaled.max())
weights_B = exp_v / exp_v.sum()
for i in range(len(ics_B)):
    if ics_B[i] < 0 and weights_B[i] > 0.15:
        weights_B[i] = 0.15
weights_B = weights_B / weights_B.sum()

base_idx = ml_res_B[20]['probabilities'].index
prob_multi_B = pd.Series(0.0, index=base_idx)
for i, d in enumerate(PREDICT_DAYS):
    p = ml_res_B[d]['probabilities'].reindex(base_idx).ffill().fillna(0.5)
    prob_multi_B += weights_B[i] * p

gold_ret = factors['金价'].pct_change().reindex(base_idx).fillna(0)
vol_60 = gold_ret.rolling(60).std() * np.sqrt(250)
vol_aligned = vol_60.reindex(base_idx).fillna(0.15)
vol_scalar = (0.15 / vol_aligned).clip(0, 2)

actual_ret_20 = factors['未来20日收益'].reindex(base_idx)
bull_a = bull.reindex(base_idx).fillna(False)
bear_a = bear.reindex(base_idx).fillna(False)
range_a = range_.reindex(base_idx).fillna(False)

# 也准备方案A的集成概率(用主管道已有的结果)
print("\n[1b] 同时获取方案A(baseline)集成概率...")
ics_A = np.array([v5.ml_results[d]['ic'] for d in PREDICT_DAYS])
scaled_A = ics_A / temp
exp_A = np.exp(scaled_A - scaled_A.max())
weights_A = exp_A / exp_A.sum()
for i in range(len(ics_A)):
    if ics_A[i] < 0 and weights_A[i] > 0.15:
        weights_A[i] = 0.15
weights_A = weights_A / weights_A.sum()

prob20_A = pd.Series(v5.ml_results[20]['probabilities']).reindex(base_idx).ffill()
prob5_A = pd.Series(v5.ml_results[5]['probabilities']).reindex(base_idx).ffill()
prob10_A = pd.Series(v5.ml_results[10]['probabilities']).reindex(base_idx).ffill()
prob60_A = pd.Series(v5.ml_results[60]['probabilities']).reindex(base_idx).ffill()
prob_multi_A = sum(weights_A[i] * [prob5_A, prob10_A, prob20_A, prob60_A][i]
                   for i in range(4))


# ── 步骤2: 定义仓位策略函数(参数化阈值)──
def strategy_returns(pm, bull_th, bear_th, range_th, pos_size=1.0, short_size=1.0):
    """
    参数化V3.0-E仓位策略
    bull_th: (entry_full, entry_half, entry_light) 牛市开仓阈值
    bear_th: (entry_short_full, entry_short_half) 熊市做空阈值
    range_th: (entry_long, entry_short) 震荡市开仓阈值
    返回: 策略日收益Series
    """
    pos = pd.Series(0.0, index=pm.index)
    bf, hf, lf = bull_th   # 满仓/半仓/轻仓
    bsf, bsh = bear_th     # 满仓空/半仓空
    rl, rs = range_th      # 震荡多/空

    pos[bull_a & (pm > bf)] = pos_size
    pos[bull_a & (pm > hf) & (pm <= bf)] = pos_size * 0.6
    pos[bull_a & (pm > lf) & (pm <= hf)] = pos_size * 0.3
    # 牛市不做空

    pos[bear_a & (pm < (1-bsf))] = -short_size      # 概率<(1-满仓空阈值)→满仓空
    pos[bear_a & (pm < (1-bsh)) & (pm >= (1-bsf))] = -short_size * 0.5  # 半仓空

    pos[range_a & (pm > rl)] = pos_size * 0.4
    pos[range_a & (pm < (1-rs))] = -short_size * 0.3

    strat_ret = (pos.shift(1) * gold_ret).fillna(0)
    strat_ret = strat_ret * vol_scalar
    return strat_ret, pos


def calc_metrics(strat_ret):
    ann_ret = strat_ret.mean() * 250
    ann_vol = strat_ret.std() * np.sqrt(250)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cum = (1 + strat_ret).cumprod()
    max_dd = ((cum / cum.cummax()) - 1).min()
    return {'sharpe': sharpe, 'ann_ret': ann_ret, 'max_dd': max_dd}


# ── 步骤3: 在训练期搜索最优阈值(只用在train期数据)──
print("\n[2] 在训练期搜索方案B最优阈值...")

# 现行阈值(baseline)
bull_default = (0.65, 0.55, 0.48)
bear_default = (0.65, 0.55)   # 概率<0.35满仓空,<0.45半仓空
range_default = (0.60, 0.60)

# 搜索空间(围绕默认值展开)
bull_entries = [(0.55, 0.48, 0.42), (0.60, 0.50, 0.42), (0.65, 0.55, 0.48),
                (0.55, 0.45, 0.40), (0.60, 0.50, 0.45), (0.50, 0.45, 0.40)]
bear_entries = [(0.55, 0.50), (0.60, 0.55), (0.65, 0.55), (0.50, 0.45), (0.55, 0.45)]
range_entries = [(0.55, 0.55), (0.50, 0.50), (0.60, 0.60), (0.52, 0.52)]

# 训练期mask
train_mask = base_idx < holdout_start_date

best_sharpe = -999
best_th = None
best_train_metrics = None
count = 0
total = len(bull_entries) * len(bear_entries) * len(range_entries)
print(f"  搜索空间: {total} 组合")

for bull_th, bear_th, range_th in product(bull_entries, bear_entries, range_entries):
    count += 1
    strat_ret, _ = strategy_returns(prob_multi_B, bull_th, bear_th, range_th)
    train_ret = strat_ret[train_mask]
    m = calc_metrics(train_ret)
    if m['sharpe'] > best_sharpe:
        best_sharpe = m['sharpe']
        best_th = (bull_th, bear_th, range_th)
        best_train_metrics = m

print(f"  训练期最优: 夏普={best_train_metrics['sharpe']:.2f} 年化={best_train_metrics['ann_ret']:+.1%} 回撤={best_train_metrics['max_dd']:.1%}")
print(f"  最优阈值: 牛市={best_th[0]} 熊市={best_th[1]} 震荡={best_th[2]}")


# ── 步骤4: Holdout纯样本外验证 ──
print("\n[3] Holdout样本外验证(搜索时未碰这段数据)...")

configs = [
    ('1.baseline(A标签+旧阈值)', prob_multi_A, bull_default, bear_default, range_default),
    ('2.B标签+旧阈值', prob_multi_B, bull_default, bear_default, range_default),
    ('3.B标签+校准阈值', prob_multi_B, best_th[0], best_th[1], best_th[2]),
]

holdout_mask = base_idx >= holdout_start_date

print(f"\n{'配置':<32} {'训练期夏普':>10} {'训练期年化':>10} {'Holdout夏普':>11} {'Holdout年化':>11} {'Holdout回撤':>11}")
print("-" * 96)
for label, pm, bt, brt, rt in configs:
    strat_ret, pos = strategy_returns(pm, bt, brt, rt)
    m_train = calc_metrics(strat_ret[train_mask])
    m_hold = calc_metrics(strat_ret[holdout_mask])
    pos_ratio_hold = (pos[holdout_mask] != 0).mean()
    print(f"{label:<32} {m_train['sharpe']:>10.2f} {m_train['ann_ret']:>+9.1%} {m_hold['sharpe']:>11.2f} {m_hold['ann_ret']:>+10.1%} {m_hold['max_dd']:>10.1%}")

# ── 步骤5: 方案B的Holdout IC再确认 ──
print("\n[4] Holdout IC 确认(方案B vs A):")
for label, pm in [('A标签', prob_multi_A), ('B标签', prob_multi_B)]:
    pm_h = pm[holdout_mask]
    ar_h = actual_ret_20.reindex(pm_h.index)
    valid = pm_h.notna() & ar_h.notna()
    ic, _ = spearmanr(pm_h[valid], ar_h[valid])
    print(f"  {label} Holdout IC = {ic:+.4f}")

# ── 结论 ──
print("\n" + "=" * 80)
print("结论")
print("=" * 80)
print("""
判断标准:
  - 配置3(B标签+校准阈值)的Holdout夏普如果 > 配置1(baseline)的Holdout夏普,
    则"改标签+调阈值"整体有效,值得考虑落地。
  - 但Holdout只有125天,任何结论都需更长样本验证。
  - 训练期夏普高不代表Holdout好(过拟合风险),重点看Holdout列。
""")

# 自动判定
strat_1, _ = strategy_returns(prob_multi_A, bull_default, bear_default, range_default)
strat_3, _ = strategy_returns(prob_multi_B, best_th[0], best_th[1], best_th[2])
h1 = calc_metrics(strat_1[holdout_mask])
h3 = calc_metrics(strat_3[holdout_mask])
print(f"Holdout夏普对比: baseline={h1['sharpe']:.2f}  vs  B+校准阈值={h3['sharpe']:.2f}")
if h3['sharpe'] > h1['sharpe']:
    print(f"✅ B+校准阈值 Holdout夏普优于baseline (+{h3['sharpe']-h1['sharpe']:.2f}) → 方向正确")
    if h3['sharpe'] > 0:
        print(f"✅✅ Holdout夏普转正! → 方案B+校准阈值值得落地验证")
    else:
        print(f"⚠️  Holdout夏普仍为负({h3['sharpe']:.2f}),但比baseline好 → 方向对,需进一步优化")
else:
    print(f"❌ B+校准阈值 Holdout夏普不优于baseline → 阈值校准未能弥补,需重新审视")
