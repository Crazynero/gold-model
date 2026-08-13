#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根因诊断:模型为什么在熊市失效?
================================
不调参数,不做消融。用数据回答三个问题:
  1. 哪些特征有真实预测力(per-feature IC)?
  2. 特征在牛/熊市的IC是否不同(regime-dependent)?
  3. 60日IC是稳定的还是某段运好(滚动IC)?

跑法: PYTHONPATH=src .venv/bin/python3 tests/diagnose_model.py
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import gold_model.gold_factor_v5 as v5

factors = v5.factors.copy()
feature_cols = v5.feature_cols
bull = v5.bull
bear = v5.bear
range_ = v5.range_

print("=" * 80)
print("根因诊断:模型为什么在熊市失效?")
print("=" * 80)

# ── 1. Per-feature IC (真实预测力,不是XGBoost gain) ──
print("\n[1] 特征IC分析(各特征 vs 60日前瞻收益的Spearman相关)")
print("    IC>0.03=弱有效  IC>0.05=有效  IC<0=反向信号")

ret_60 = factors['未来60日收益']
ret_20 = factors['未来20日收益']

feature_ics = []
for col in feature_cols:
    if col not in factors.columns:
        continue
    s = factors[col]
    valid = s.notna() & ret_60.notna()
    if valid.sum() < 100:
        continue
    ic60, _ = spearmanr(s[valid], ret_60[valid])
    valid20 = s.notna() & ret_20.notna()
    ic20, _ = spearmanr(s[valid20], ret_20[valid20])
    feature_ics.append({'feature': col, 'ic60': ic60, 'ic20': ic20, 'abs_ic60': abs(ic60)})

ic_df = pd.DataFrame(feature_ics).sort_values('abs_ic60', ascending=False)

print(f"\n{'特征':<28} {'60日IC':>8} {'20日IC':>8} {'判断':>12}")
print("-" * 60)
for _, r in ic_df.iterrows():
    judge = '✅有效' if abs(r['ic60']) > 0.05 else ('🟡弱' if abs(r['ic60']) > 0.03 else '❌噪声')
    print(f"{r['feature']:<28} {r['ic60']:>+8.4f} {r['ic20']:>+8.4f} {judge:>12}")

n_effective = (ic_df['abs_ic60'] > 0.05).sum()
n_weak = ((ic_df['abs_ic60'] > 0.03) & (ic_df['abs_ic60'] <= 0.05)).sum()
n_noise = (ic_df['abs_ic60'] <= 0.03).sum()
print(f"\n汇总: {n_effective}个有效(>0.05) + {n_weak}个弱(>0.03) + {n_noise}个噪声(≤0.03) = {len(ic_df)}个特征")

# ── 2. 分Regime的特征IC ──
print("\n\n[2] 分Regime特征IC(牛/熊/震荡下各特征预测力是否不同)")
print("    ★核心问题:如果特征在牛熊IC符号反转,单一模型无法兼顾")

regime_masks = {'牛市': bull, '熊市': bear, '震荡': range_}
regime_ics = []
for col in feature_cols:
    if col not in factors.columns:
        continue
    s = factors[col]
    row = {'feature': col}
    for regime_name, mask in regime_masks.items():
        valid = s.notna() & ret_60.notna() & mask.reindex(s.index).fillna(False)
        if valid.sum() > 30:
            ic, _ = spearmanr(s[valid], ret_60[valid])
            row[regime_name] = ic
        else:
            row[regime_name] = np.nan
    regime_ics.append(row)

regime_df = pd.DataFrame(regime_ics)

# 找IC符号反转的特征(牛市正熊市负,或反之)
print(f"\n{'特征':<28} {'牛市IC':>8} {'熊市IC':>8} {'震荡IC':>8} {'反转?':>8}")
print("-" * 65)
for _, r in regime_df.iterrows():
    bull_ic = r.get('牛市', np.nan)
    bear_ic = r.get('熊市', np.nan)
    range_ic = r.get('震荡', np.nan)
    reversed_ = ''
    if pd.notna(bull_ic) and pd.notna(bear_ic):
        if bull_ic * bear_ic < 0 and (abs(bull_ic) > 0.03 or abs(bear_ic) > 0.03):
            reversed_ = '⚠️反转'
    print(f"{r['feature']:<28} {bull_ic:>+8.4f} {bear_ic:>+8.4f} {range_ic:>+8.4f} {reversed_:>8}")

n_reversed = sum(1 for _, r in regime_df.iterrows()
                 if pd.notna(r.get('牛市', np.nan)) and pd.notna(r.get('熊市', np.nan))
                 and r['牛市'] * r['熊市'] < 0
                 and (abs(r['牛市']) > 0.03 or abs(r['熊市']) > 0.03))
print(f"\n⚠️ IC符号反转的特征: {n_reversed}/{len(regime_df)}个 —— 这些特征在牛熊市预测方向相反")

# ── 3. 60日模型IC的滚动稳定性 ──
print("\n\n[3] 60日预测IC滚动稳定性(每250天窗口)")
print("    判断:60日IC=+0.17是稳定的还是某段牛市运气?")

prob60 = pd.Series(v5.ml_results[60]['probabilities'], index=v5.ml_results[60]['dates'])
prob60 = prob60[~prob60.index.duplicated(keep='last')]
ret60_aligned = ret_60.reindex(prob60.index)

# 滚动250天IC
rolling_window = 250
rolling_ics = []
dates_rolled = []
for i in range(rolling_window, len(prob60)):
    window_probs = prob60.iloc[i-rolling_window:i]
    window_rets = ret60_aligned.iloc[i-rolling_window:i]
    valid = window_probs.notna() & window_rets.notna()
    if valid.sum() > 50:
        ic, _ = spearmanr(window_probs[valid], window_rets[valid])
        rolling_ics.append(ic)
        dates_rolled.append(prob60.index[i])

pos_pct = 0.0  # B3修复: 提前初始化,rolling_ics为空时末段总结不再NameError
if rolling_ics:
    rolling_s = pd.Series(rolling_ics, index=dates_rolled)
    # 分段:前1/3 中1/3 后1/3
    third = len(rolling_s) // 3
    print(f"  滚动IC ({rolling_window}天窗口, {len(rolling_s)}个点):")
    print(f"    全程: 均值={rolling_s.mean():+.4f} 中位={rolling_s.median():+.4f} 标准差={rolling_s.std():.4f}")
    print(f"    前1/3: 均值={rolling_s.iloc[:third].mean():+.4f}")
    print(f"    中1/3: 均值={rolling_s.iloc[third:2*third].mean():+.4f}")
    print(f"    后1/3: 均值={rolling_s.iloc[2*third:].mean():+.4f}  ← 最近")
    # IC为正的占比
    pos_pct = (rolling_s > 0).mean()
    print(f"    IC>0的占比: {pos_pct:.0%}")
    if pos_pct > 0.7:
        print(f"    → 60日IC稳定有效(>70%时间为正)")
    elif pos_pct > 0.5:
        print(f"    → 60日IC不稳定(仅{pos_pct:.0%}时间为正)")
    else:
        print(f"    → 60日IC实际上是噪声(<50%时间为正)")

# ── 4. 分Regime的模型准确率(模型到底在哪里错) ──
print("\n\n[4] 分Regime模型方向准确率(20日+60日,模型到底在哪错)")

for horizon in [20, 60]:
    probs = pd.Series(v5.ml_results[horizon]['probabilities'], index=v5.ml_results[horizon]['dates'])
    probs = probs[~probs.index.duplicated(keep='last')]
    actual_dir = (factors[f'未来{horizon}日收益'] > 0).astype(float).reindex(probs.index)
    pred_dir = (probs > 0.5).astype(float)

    for regime_name, mask in regime_masks.items():
        mask_aligned = mask.reindex(probs.index).fillna(False)
        valid = probs.notna() & actual_dir.notna() & mask_aligned
        if valid.sum() > 10:
            acc = (pred_dir[valid] == actual_dir[valid]).mean()
            # 预测涨的比例
            pred_up = (pred_dir[valid] == 1).mean()
            # 实际涨的比例
            actual_up = actual_dir[valid].mean()
            print(f"  {horizon}日 {regime_name}: ACC={acc:.1%} 预测涨={pred_up:.0%} 实际涨={actual_up:.0%} (共{valid.sum()}天)")
    print()

# ── 5. 综合诊断结论 ──
print("=" * 80)
print("综合诊断结论")
print("=" * 80)
print(f"""
1. 特征质量: {n_effective}个有效(>0.05) / {len(ic_df)}个总特征
   → {'特征质量OK' if n_effective >= 10 else '⚠️ 有效特征太少,特征工程需要改进'}

2. Regime反转: {n_reversed}个特征在牛熊IC反转
   → {'单一模型无法兼顾牛熊' if n_reversed >= 5 else '牛熊特征基本一致'}

3. 60日IC稳定性: {'稳定' if pos_pct > 0.7 else '不稳定'}
   → {'60日信号可靠' if pos_pct > 0.7 else '⚠️ 60日IC可能是某段运好'}

4. 模型在熊市的错误: 看上面的"预测涨 vs 实际涨"对比
   → 如果预测涨>>实际涨,就是多头偏见的确凿证据
""")
