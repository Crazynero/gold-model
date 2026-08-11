#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标签消融实验:绝对涨跌 vs 超额收益
==================================
目的:用数据回答"改标签定义(从绝对涨跌改成超额收益)能否解决多头偏见"

背景:消融实验(权重层)已证明 Holdout 所有方案 IC 全负,根因在模型层多头偏见。
     训练样本牛市占64%,标签"涨=1"天然是多数类。

实验设计:
  - 数据不变(同一次采集,factors完全一致)
  - 特征不变(同一批VIF剪枝后的25个特征)
  - Regime不变(同一套bull/bear/range_)
  - 训练框架不变(XGB+LGB walk-forward,同参数)
  - 只改标签定义这一个变量

标签方案:
  A. abs_return    — 现行:未来N日收益>0=1(绝对涨跌) ← baseline
  B. excess_mean   — 超额:未来N日收益 - 滚动250日均值收益 > 0 = 1
  C. excess_zero   — 严格中性:未来N日收益 > 0 但只在非牛市标1(去牛市beta) ——对照组

评估:
  - 4个周期各算 IC / ACC
  - 集成IC/ACC(用方案B的IC自适应权重)
  - V3.0-E策略在全样本+Holdout的夏普
  - ★关键:Holdout(熊市)的IC是否转正

注意:超额收益标签改变了策略语义(预测的是alpha而非涨跌),
      V3.0-E的仓位阈值表是为"绝对涨跌概率"设计的。
      这里先用相同阈值做初步对比,若IC显著改善再调阈值。

跑法:
  PYTHONPATH=src .venv/bin/python3 tests/ablation_labels.py
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression

# 复用主管道:import 会跑完全链路,拿到 factors / feature_cols / Regime / bull/bear/range_
import gold_model.gold_factor_v5 as v5

print("\n" + "=" * 80)
print("标签消融实验:绝对涨跌 vs 超额收益")
print("=" * 80)

# ── 从主管道拿数据 ──
factors = v5.factors.copy()
feature_cols = v5.feature_cols
PREDICT_DAYS = v5.PREDICT_DAYS  # [5,10,20,60]
bull = v5.bull
bear = v5.bear
range_ = v5.range_
TRAIN_WINDOW = v5.TRAIN_WINDOW
TEST_WINDOW = v5.TEST_WINDOW
STEP = v5.STEP
GAP = v5.GAP
REGIME_CONDITIONAL = v5.REGIME_CONDITIONAL
regime_series_all = factors['Regime'] if 'Regime' in factors else None

# 金价收益序列(用于算超额收益标签)
gold_ret = factors['金价'].pct_change()
HOLDOUT_DAYS = 125
holdout_start_date = factors.index[len(factors) - HOLDOUT_DAYS]
print(f"Holdout起始: {holdout_start_date.date()}")

# ── 标签构建函数 ──
def build_labels(scheme):
    """返回 {n: (label_series, ret_series)} 标签+收益"""
    labels = {}
    for n in PREDICT_DAYS:
        ret_n = factors['金价'].pct_change(n).shift(-n)  # 未来N日收益
        if scheme == 'A_abs':
            # 现行:绝对涨跌
            label = (ret_n > 0).astype(float)
        elif scheme == 'B_excess_mean':
            # 超额收益:未来N日收益 - 过去250日滚动均值N日收益
            rolling_mean_ret = gold_ret.rolling(250).mean() * n  # 日均×N天 ≈ N日期望收益
            label = (ret_n > rolling_mean_ret.shift(-n)).astype(float)
        elif scheme == 'C_excess_demean':
            # 去均值:未来N日收益减去全样本均值(简化版市场中性)
            mean_ret_n = ret_n.mean()
            label = (ret_n > mean_ret_n).astype(float)
        labels[n] = (label, ret_n)
    return labels

# ── Walk-Forward 训练(复刻主管道,但标签可替换)──
def walk_forward(labeled_data, pred_days):
    """对指定周期跑walk-forward,返回 {dates, probabilities, actuals, ic, acc, auc}"""
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
        train_mask = slice(train_start, train_end)
        test_mask = slice(start_idx, end_idx)

        X_train = X.iloc[train_mask].copy()
        y_train = y.reindex(X_train.index)

        # Regime-conditional(复刻主管道)
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

        # Isotonic校准
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
    actuals_arr = np.array(actuals)
    rets_s = ret_col.reindex(dates)

    # 去重(测试窗口重叠)
    probs_s = probs_s[~probs_s.index.duplicated(keep='last')]
    rets_s = rets_s[~rets_s.index.duplicated(keep='last')]
    actuals_aligned = pd.Series(actuals_arr, index=dates)
    actuals_aligned = actuals_aligned[~actuals_aligned.index.duplicated(keep='last')]

    valid = probs_s.notna() & rets_s.notna()
    if valid.sum() > 10:
        from sklearn.metrics import roc_auc_score, accuracy_score
        ic, _ = spearmanr(probs_s[valid], rets_s[valid])
        acc = accuracy_score(actuals_aligned[valid], (probs_s[valid] > 0.5).astype(int))
        try:
            auc = roc_auc_score(actuals_aligned[valid], probs_s[valid])
        except Exception:
            auc = 0.5
    else:
        ic, acc, auc = 0, 0, 0.5

    return {'dates': dates, 'probabilities': probs_s, 'ic': ic, 'acc': acc, 'auc': auc}


# ── 集成 + 策略评估(复刻消融实验的评估框架)──
def evaluate_scheme(scheme, label_name, all_results):
    """算集成IC/ACC/夏普,全样本+Holdout"""
    # IC自适应权重(复刻主管道)
    ics = np.array([all_results[d]['ic'] for d in PREDICT_DAYS])
    temp = 0.5
    scaled = ics / temp
    exp_v = np.exp(scaled - scaled.max())
    weights = exp_v / exp_v.sum()
    for i in range(len(ics)):
        if ics[i] < 0 and weights[i] > 0.15:
            weights[i] = 0.15
    weights = weights / weights.sum()

    # 对齐到20日轴
    base = all_results[20]['probabilities'].index
    prob_multi = pd.Series(0.0, index=base)
    for i, d in enumerate(PREDICT_DAYS):
        p = all_results[d]['probabilities'].reindex(base).ffill().fillna(0.5)
        prob_multi += weights[i] * p

    # 实际收益(统一用20日)
    actual_ret = factors['未来20日收益'].reindex(base)

    def _slice_metrics(mask):
        pm = prob_multi[mask]
        ar = actual_ret.reindex(pm.index)
        valid = pm.notna() & ar.notna()
        if valid.sum() < 10:
            return {'ic': float('nan'), 'sharpe': 0, 'max_dd': 0, 'pos_ratio': 0}
        ic, _ = spearmanr(pm[valid], ar[valid])
        # V3.0-E策略
        bull_s = bull.reindex(pm.index).fillna(False)
        bear_s = bear.reindex(pm.index).fillna(False)
        range_s = range_.reindex(pm.index).fillna(False)
        pos = pd.Series(0.0, index=pm.index)
        pos[bull_s & (pm > 0.65)] = 1.0
        pos[bull_s & (pm > 0.55) & (pm <= 0.65)] = 0.6
        pos[bull_s & (pm > 0.48) & (pm <= 0.55)] = 0.3
        pos[bear_s & (pm < 0.35)] = -1.0
        pos[bear_s & (pm < 0.45) & (pm >= 0.35)] = -0.5
        pos[range_s & (pm > 0.60)] = 0.4
        pos[range_s & (pm < 0.40)] = -0.3
        g_ret = factors['金价'].pct_change().reindex(pm.index).fillna(0)
        s_ret = (pos.shift(1) * g_ret).fillna(0)
        vol60 = g_ret.rolling(60).std() * np.sqrt(250)
        s_ret = s_ret * (0.15 / vol60.reindex(pm.index).fillna(0.15)).clip(0, 2)
        ann_ret = s_ret.mean() * 250
        ann_vol = s_ret.std() * np.sqrt(250)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        cum = (1 + s_ret).cumprod()
        max_dd = ((cum / cum.cummax()) - 1).min()
        pos_ratio = (pos != 0).mean()
        return {'ic': ic, 'sharpe': sharpe, 'max_dd': max_dd, 'ann_ret': ann_ret, 'pos_ratio': pos_ratio}

    full_mask = pd.Series(True, index=base)
    hold_mask = base >= holdout_start_date
    m_full = _slice_metrics(full_mask)
    m_hold = _slice_metrics(hold_mask)

    print(f"\n  [{label_name}]")
    w_str = "  ".join(f"{d}日={weights[i]:.2f}(IC={ics[i]:+.3f})" for i, d in enumerate(PREDICT_DAYS))
    print(f"    权重: {w_str}")
    print(f"    全样本:  IC={m_full['ic']:+.4f}  夏普={m_full['sharpe']:.2f}  年化={m_full['ann_ret']:+.1%}  回撤={m_full['max_dd']:.1%}  持仓占比={m_full['pos_ratio']:.0%}")
    print(f"    Holdout: IC={m_hold['ic']:+.4f}  夏普={m_hold['sharpe']:.2f}  年化={m_hold['ann_ret']:+.1%}  回撤={m_hold['max_dd']:.1%}  持仓占比={m_hold['pos_ratio']:.0%}")
    return {'scheme': label_name, 'ics': ics.tolist(), 'full': m_full, 'holdout': m_hold}


# ── 跑3种标签方案 ──
schemes = [
    ('A_abs',         'A. 绝对涨跌(现行baseline)'),
    ('B_excess_mean', 'B. 超额收益(vs滚动均值)'),
    ('C_excess_demean','C. 超额收益(vs全样本均值)'),
]

print("\n开始训练(每种标签×4周期 = 12次walk-forward)...")
all_scheme_results = []
for scheme_key, scheme_label in schemes:
    print(f"\n>>> 标签方案: {scheme_label}")
    labeled = build_labels(scheme_key)

    # 打印标签分布(关键诊断)
    for n in PREDICT_DAYS:
        lbl = labeled[n][0]
        pos_ratio = lbl.mean()
        # 按Regime看分布
        for regime_name in ['牛市', '熊市', '震荡']:
            mask = factors['Regime'] == regime_name
            regime_pos = lbl[mask].mean()
            print(f"  {n}日标签 {regime_name}: 正样本占比={regime_pos:.1%}(共{mask.sum()}天)")
        print(f"  {n}日标签 全样本: 正样本占比={pos_ratio:.1%}")

    # 4周期训练
    ml_res = {}
    for n in PREDICT_DAYS:
        r = walk_forward(labeled, n)
        ml_res[n] = r
        print(f"  {n}日: IC={r['ic']:+.4f} ACC={r['acc']:.1%} AUC={r['auc']:.3f}")

    result = evaluate_scheme(scheme_key, scheme_label, ml_res)
    result['per_horizon'] = {n: {'ic': ml_res[n]['ic'], 'acc': ml_res[n]['acc'], 'auc': ml_res[n]['auc']} for n in PREDICT_DAYS}
    all_scheme_results.append(result)

# ── 汇总对比 ──
print("\n" + "=" * 80)
print("汇总对比")
print("=" * 80)

print("\n▼ 各周期 IC 对比:")
print(f"{'标签方案':<32} {'5日':>8} {'10日':>8} {'20日':>8} {'60日':>8}")
for r in all_scheme_results:
    ics = r['per_horizon']
    print(f"{r['scheme']:<32} {ics[5]['ic']:>+8.4f} {ics[10]['ic']:>+8.4f} {ics[20]['ic']:>+8.4f} {ics[60]['ic']:>+8.4f}")

print(f"\n▼ 集成 IC + 策略夏普 (全样本 vs Holdout):")
print(f"{'标签方案':<32} {'全样本IC':>9} {'HoldoutIC':>10} {'全样本夏普':>10} {'Holdout夏普':>11} {'Holdout年化':>11}")
for r in all_scheme_results:
    print(f"{r['scheme']:<32} {r['full']['ic']:>+9.4f} {r['holdout']['ic']:>+10.4f} {r['full']['sharpe']:>10.2f} {r['holdout']['sharpe']:>11.2f} {r['holdout']['ann_ret']:>+10.1%}")

# ── 结论 ──
print("\n" + "=" * 80)
print("结论")
print("=" * 80)
base = all_scheme_results[0]
for r in all_scheme_results[1:]:
    print(f"\n{r['scheme']} vs {base['scheme']}:")
    for seg, seg_name in [('full', '全样本'), ('holdout', 'Holdout')]:
        ic_diff = r[seg]['ic'] - base[seg]['ic']
        sharpe_diff = r[seg]['sharpe'] - base[seg]['sharpe']
        ic_arrow = "↑" if ic_diff > 0 else "↓"
        sharpe_arrow = "↑" if sharpe_diff > 0 else "↓"
        print(f"  {seg_name}: IC {base[seg]['ic']:+.4f}→{r[seg]['ic']:+.4f}({ic_diff:+.4f}{ic_arrow})  夏普 {base[seg]['sharpe']:.2f}→{r[seg]['sharpe']:.2f}({sharpe_diff:+.2f}{sharpe_arrow})")

# ★ 核心判定:Holdout IC是否转正
print("\n── 核心判定 ──")
best_holdout = max(all_scheme_results, key=lambda x: x['holdout']['ic'])
print(f"Holdout IC 最优: {best_holdout['scheme']} (IC={best_holdout['holdout']['ic']:+.4f}, 夏普={best_holdout['holdout']['sharpe']:.2f})")
if best_holdout['holdout']['ic'] > 0:
    print("✅ 至少一种标签方案 Holdout IC 转正 → 改标签有效,值得进一步优化阈值")
else:
    print("❌ 所有标签方案 Holdout IC 仍为负 → 改标签不足以解决多头偏见,需结合样本层治理")
