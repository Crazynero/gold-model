#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消融实验:多周期集成权重策略对照
================================
目的:用数据回答"砍掉IC为负的周期(尤其20日)到底会让集成变好还是变差"

实验设计:
  - 模型不变(XGB+LGB,同一份walk-forward预测)
  - 数据不变(同一次采集)
  - 策略不变(V3.0-E阈值表)
  - 只改 prob_multi 的权重分配层
  - 对照4种方案,比3个指标(集成IC / 方向ACC / 模拟回测夏普)

方案:
  A. baseline  — 现行IC自适应权重(softmax(IC/0.5),负IC压顶0.15)
  B. drop20    — 砍掉20日(权重置0,其余归一化)
  C. drop_neg  — 砍掉所有IC<0的周期(5/10/20日里IC为负的),其余归一化
  D. equal     — 等权(各0.25),作为随机基准

跑法:
  PYTHONPATH=src .venv/bin/python3 tests/ablation_weights.py
"""
import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# 复用主管道:import 整个模块会跑完全链路(采集→训练→预测)
# 跑完后 ml_results / factors / prob_series / bull / bear / range_ 都在模块命名空间里
import gold_model.gold_factor_v5 as v5

print("\n" + "=" * 70)
print("消融实验:多周期集成权重策略对照")
print("=" * 70)

# ── 从主管道拿中间结果 ──
ml_results = v5.ml_results
factors = v5.factors
PREDICT_DAYS = v5.PREDICT_DAYS  # [5, 10, 20, 60]
prob_series = v5.prob_series    # 20日预测序列(对齐基准)
bull = v5.bull
bear = v5.bear
range_ = v5.range_

# 各周期IC
horizon_ics = np.array([ml_results[d]['ic'] for d in PREDICT_DAYS])
print(f"\n各周期 IC: " + "  ".join(f"{d}日={ml_results[d]['ic']:+.4f}" for d in PREDICT_DAYS))

# 对齐各周期概率序列到20日轴(和主管道1033行完全一致)
prob5_a = pd.Series(ml_results[5]['probabilities'], index=ml_results[5]['dates']).reindex(prob_series.index).ffill()
prob10_a = pd.Series(ml_results[10]['probabilities'], index=ml_results[10]['dates']).reindex(prob_series.index).ffill()
prob60_a = pd.Series(ml_results[60]['probabilities'], index=ml_results[60]['dates']).reindex(prob_series.index).ffill()
prob20_a = prob_series  # 20日本身就是基准轴

probs = {5: prob5_a, 10: prob10_a, 20: prob20_a, 60: prob60_a}

# 实际未来收益(用于算IC和方向ACC)——用20日未来收益作为统一评估标签
actual_ret = factors['未来20日收益'].reindex(prob_series.index)
actual_dir = (actual_ret > 0).astype(float)


# ── 权重方案定义 ──
def make_weights(strategy):
    """返回 {5:w, 10:w, 20:w, 60:w} 归一化权重"""
    ics = {d: ml_results[d]['ic'] for d in PREDICT_DAYS}

    if strategy == 'A_baseline':
        # 复刻主管道1019-1028行
        arr = np.array([ics[d] for d in PREDICT_DAYS])
        scaled = arr / 0.5
        exp = np.exp(scaled - scaled.max())
        w = exp / exp.sum()
        for i, d in enumerate(PREDICT_DAYS):
            if ics[d] < 0 and w[i] > 0.15:
                w[i] = 0.15
        w = w / w.sum()
        return {PREDICT_DAYS[i]: w[i] for i in range(4)}

    elif strategy == 'B_drop20':
        # 砍20日
        w = {d: ics[d] for d in PREDICT_DAYS}
        w[20] = 0  # 置零
        # 其余按IC softmax归一化(不含20)
        rest = {d: max(ics[d], 0.001) for d in PREDICT_DAYS if d != 20}
        arr = np.array([rest[d] for d in rest])
        scaled = arr / 0.5
        exp = np.exp(scaled - scaled.max())
        wr = exp / exp.sum()
        for i, d in enumerate(rest):
            w[d] = wr[i]
        total = sum(w.values())
        return {d: w[d] / total for d in PREDICT_DAYS}

    elif strategy == 'C_drop_neg':
        # 砍所有IC<0的周期
        w = {d: (ics[d] if ics[d] > 0 else 0) for d in PREDICT_DAYS}
        total = sum(w.values())
        if total == 0:  # 全负退化为等权
            return {d: 0.25 for d in PREDICT_DAYS}
        return {d: w[d] / total for d in PREDICT_DAYS}

    elif strategy == 'D_equal':
        return {d: 0.25 for d in PREDICT_DAYS}


# ── Holdout 切分(复刻主管道1154-1156行)──
HOLDOUT_DAYS = getattr(v5, 'HOLDOUT_DAYS', 125)
_holdout_start_idx = len(factors) - HOLDOUT_DAYS
holdout_start_date = factors.index[_holdout_start_idx] if _holdout_start_idx > 0 else factors.index[0]
print(f"\nHoldout切分: 起始日={holdout_start_date.date()} (最近{HOLDOUT_DAYS}天样本外)")


def _metrics_for_slice(pm, mask):
    """对 pm 的 mask 子集算 IC/ACC/夏普/回撤(内部函数,被 evaluate 调用)"""
    pm_s = pm[mask]
    ar_s = actual_ret.reindex(pm_s.index)
    ad_s = actual_dir.reindex(pm_s.index)

    valid = pm_s.notna() & ar_s.notna()
    if valid.sum() < 10:
        return {'ic': float('nan'), 'acc': float('nan'), 'sharpe': 0, 'ann_ret': 0, 'max_dd': 0}
    ic, _ = spearmanr(pm_s[valid], ar_s[valid])
    pred_dir = (pm_s > 0.5).astype(float)
    acc = (pred_dir[valid] == ad_s[valid]).mean()

    # V3.0-E 仓位(复刻1056-1095行)
    bull_s = bull.reindex(pm_s.index).fillna(False)
    bear_s = bear.reindex(pm_s.index).fillna(False)
    range_s = range_.reindex(pm_s.index).fillna(False)
    pos = pd.Series(0.0, index=pm_s.index)
    pos[bull_s & (pm_s > 0.65)] = 1.0
    pos[bull_s & (pm_s > 0.55) & (pm_s <= 0.65)] = 0.6
    pos[bull_s & (pm_s > 0.48) & (pm_s <= 0.55)] = 0.3
    pos[bear_s & (pm_s < 0.35)] = -1.0
    pos[bear_s & (pm_s < 0.45) & (pm_s >= 0.35)] = -0.5
    pos[range_s & (pm_s > 0.60)] = 0.4
    pos[range_s & (pm_s < 0.40)] = -0.3

    gold_ret = factors['金价'].pct_change().reindex(pm_s.index).fillna(0)
    strat_ret = (pos.shift(1) * gold_ret).fillna(0)
    vol_60 = gold_ret.rolling(60).std() * np.sqrt(250)
    vol_aligned = vol_60.reindex(pm_s.index).fillna(0.15)
    strat_ret = strat_ret * (0.15 / vol_aligned).clip(0, 2)

    ann_ret = strat_ret.mean() * 250
    ann_vol = strat_ret.std() * np.sqrt(250)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cum = (1 + strat_ret).cumprod()
    max_dd = ((cum / cum.cummax()) - 1).min()
    return {'ic': ic, 'acc': acc, 'sharpe': sharpe, 'ann_ret': ann_ret, 'max_dd': max_dd}


def evaluate(weights, label):
    """给定权重,同时算全样本 + Holdout 两段指标"""
    pm = sum(weights[d] * probs[d] for d in PREDICT_DAYS)

    full_mask = pd.Series(True, index=pm.index)
    holdout_mask = pm.index >= holdout_start_date

    m_full = _metrics_for_slice(pm, full_mask)
    m_hold = _metrics_for_slice(pm, holdout_mask)

    w_str = "  ".join(f"{d}日={weights[d]:.2f}" for d in PREDICT_DAYS)
    print(f"\n  [{label}]  权重: {w_str}")
    print(f"    全样本:    IC={m_full['ic']:+.4f}  ACC={m_full['acc']:.1%}  夏普={m_full['sharpe']:.2f}  年化={m_full['ann_ret']:+.1%}  回撤={m_full['max_dd']:.1%}")
    print(f"    Holdout:   IC={m_hold['ic']:+.4f}  ACC={m_hold['acc']:.1%}  夏普={m_hold['sharpe']:.2f}  年化={m_hold['ann_ret']:+.1%}  回撤={m_hold['max_dd']:.1%}")
    decay = (1 - m_hold['sharpe'] / m_full['sharpe']) * 100 if m_full['sharpe'] != 0 else float('nan')
    print(f"    夏普衰减:  {decay:.0f}%")
    return {'strategy': label, 'weights': weights, 'full': m_full, 'holdout': m_hold}


# ── 跑4个方案 ──
print("\n── 对照实验开始 ──")
results = []
for strategy, label in [
    ('A_baseline', 'A. 现行IC权重(baseline)'),
    ('B_drop20',   'B. 砍掉20日'),
    ('C_drop_neg', 'C. 砍掉所有IC<0周期'),
    ('D_equal',    'D. 等权(随机基准)'),
]:
    w = make_weights(strategy)
    results.append(evaluate(w, label))

# ── 汇总对比表 ──
print("\n" + "=" * 90)
print("汇总对比(全样本 vs Holdout)")
print("=" * 90)

print("\n▼ 全样本(全部历史,含牛市主导期):")
print(f"{'方案':<28} {'集成IC':>8} {'方向ACC':>8} {'夏普':>7} {'年化':>7} {'回撤':>7}")
print("-" * 75)
for r in results:
    m = r['full']
    print(f"{r['strategy']:<28} {m['ic']:>+8.4f} {m['acc']:>7.1%} {m['sharpe']:>7.2f} {m['ann_ret']:>+6.1%} {m['max_dd']:>7.1%}")

print(f"\n▼ Holdout(近{HOLDOUT_DAYS}天样本外,当前为熊市环境):")
print(f"{'方案':<28} {'集成IC':>8} {'方向ACC':>8} {'夏普':>7} {'年化':>7} {'回撤':>7}")
print("-" * 75)
for r in results:
    m = r['holdout']
    print(f"{r['strategy']:<28} {m['ic']:>+8.4f} {m['acc']:>7.1%} {m['sharpe']:>7.2f} {m['ann_ret']:>+6.1%} {m['max_dd']:>7.1%}")

# ── 结论判定(全样本+Holdout双重验证)──
print("\n" + "=" * 90)
print("结论(必须全样本+Holdout双重验证才可信)")
print("=" * 90)

base = results[0]
drop20 = results[1]
drop_neg = results[2]
equal = results[3]


def _cmp(name, a, b, metric, segment):
    """比较两方案在指定segment的metric,a vs b(baseline)"""
    va = a[segment][metric]
    vb = b[segment][metric]
    diff = va - vb
    better = diff > 0
    arrow = "↑优于" if better else "↓劣于"
    print(f"   {name} {segment:6s} {metric}: {vb:+.4f} → {va:+.4f} ({diff:+.4f}) {arrow} baseline")
    return better


print("\n1) 砍20日 vs baseline:")
for seg in ['full', 'holdout']:
    _cmp("砍20日", drop20, base, 'ic', seg)
    _cmp("砍20日", drop20, base, 'sharpe', seg)
    print()

print("2) 砍所有负IC(方案C) vs baseline:")
c_full_better = _cmp("方案C", drop_neg, base, 'ic', 'full')
c_hold_better = _cmp("方案C", drop_neg, base, 'ic', 'holdout')
print()
c_sharpe_full = _cmp("方案C", drop_neg, base, 'sharpe', 'full')
c_sharpe_hold = _cmp("方案C", drop_neg, base, 'sharpe', 'holdout')

print("\n3) IC自适应权重 vs 等权(验证机制本身):")
_cmp("baseline", base, equal, 'ic', 'full')
_cmp("baseline", base, equal, 'ic', 'holdout')

# ── 关键判定:方案C是否在两段都赢 ──
print("\n── 最终判定 ──")
if c_full_better and c_hold_better:
    print("✅ 方案C(负IC置0)在全样本和Holdout【两段都优于baseline】→ 改动可信,建议落地")
elif c_full_better and not c_hold_better:
    print("⚠️ 方案C全样本优于baseline,但Holdout【未优于】baseline → 全样本优势可能是牛市滤镜,不建议直接落地")
elif not c_full_better:
    print("❌ 方案C全样本也未优于baseline → 砍负IC无益,维持现状")

# Holdout里方案C vs 买入持有(同期)——关键:样本外是否至少跑赢笨办法
print(f"\n── Holdout期间方案C vs 同期持有 ──")
print(f"   方案C Holdout夏普={drop_neg['holdout']['sharpe']:.2f} 年化={drop_neg['holdout']['ann_ret']:+.1%} 回撤={drop_neg['holdout']['max_dd']:.1%}")
print(f"   baseline Holdout夏普={base['holdout']['sharpe']:.2f} 年化={base['holdout']['ann_ret']:+.1%} 回撤={base['holdout']['max_dd']:.1%}")
if drop_neg['holdout']['sharpe'] > base['holdout']['sharpe']:
    print("   → 样本外方案C仍优于baseline(即便绝对夏普为负,相对改进成立)")
else:
    print("   → 样本外方案C不优于baseline,全样本优势确属牛市滤镜")
