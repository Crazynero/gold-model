#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型漂移检测器
对比最近一次运行 vs 历史基线，检测模型退化/数据分布偏移

用法：
  python3 drift_monitor.py              # 检测一次
  python3 drift_monitor.py --verbose    # 详细输出
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from gold_model.paths import DRIFT_HISTORY

DRIFT_FILE = DRIFT_HISTORY

# ── 漂移阈值定义 ──
THRESHOLDS = {
    'accuracy_drop_60d': 0.05,    # 60日准确率下降5个百分点
    'ic_drop_60d': 0.05,          # 60日IC下降0.05
    'auc_drop_60d': 0.03,         # 60日AUC下降0.03
    'prob_mean_shift': 0.08,      # 概率均值偏移0.08
    'prob_std_change': 0.05,      # 概率标准差变化0.05
    'feature_rank_change': 3,     # TOP5特征排名变化≥3位
    'regime_dist_shift': 0.10,    # Regime分布偏移10%
    'sharpe_drop': 0.20,          # 最优夏普下降0.20
}


def load_drift_history():
    """加载漂移历史"""
    if not os.path.exists(DRIFT_FILE):
        return []
    try:
        with open(DRIFT_FILE) as f:
            return json.load(f)
    except:
        return []


def detect_drift(history, verbose=False):
    """
    检测漂移，返回告警列表
    每条告警: {'severity': '🟢/🟠/🔴', 'category': str, 'desc': str, 'detail': str}
    """
    alerts = []
    
    if len(history) < 2:
        if verbose:
            print(f"  历史记录不足2条({len(history)})，无法检测漂移")
        return alerts
    
    latest = history[-1]
    # 使用前N条作为基线（最多取前10条，避免太老的数据）
    baseline_n = min(10, len(history) - 1)
    baseline_records = history[:baseline_n]
    
    if verbose:
        print(f"  最新运行: {latest['timestamp']} (数据日: {latest['run_date']})")
        print(f"  基线: 前{baseline_n}条记录")
    
    # ── 1. ML指标漂移 ──
    for horizon in ['5', '10', '20', '60']:
        if horizon not in latest.get('ml_metrics', {}):
            continue
        
        latest_m = latest['ml_metrics'][horizon]
        
        # 计算基线均值
        baseline_accs = [r['ml_metrics'][horizon]['accuracy'] for r in baseline_records if horizon in r.get('ml_metrics', {})]
        baseline_ics = [r['ml_metrics'][horizon]['ic'] for r in baseline_records if horizon in r.get('ml_metrics', {})]
        baseline_aucs = [r['ml_metrics'][horizon]['auc'] for r in baseline_records if horizon in r.get('ml_metrics', {})]
        
        if not baseline_accs:
            continue
        
        baseline_acc = sum(baseline_accs) / len(baseline_accs)
        baseline_ic = sum(baseline_ics) / len(baseline_ics)
        baseline_auc = sum(baseline_aucs) / len(baseline_aucs)
        
        # 准确率下降
        acc_drop = baseline_acc - latest_m['accuracy']
        if acc_drop > THRESHOLDS['accuracy_drop_60d']:
            sev = '🔴' if acc_drop > 0.10 else '🟠'
            alerts.append({
                'severity': sev,
                'category': f'{horizon}日准确率下降',
                'desc': f'{horizon}日预测准确率从{baseline_acc:.1%}降至{latest_m["accuracy"]:.1%} (Δ-{acc_drop:.1%})',
                'detail': f'基线均值={baseline_acc:.4f}, 当前={latest_m["accuracy"]:.4f}',
            })
        
        # IC下降
        ic_drop = baseline_ic - latest_m['ic']
        if ic_drop > THRESHOLDS['ic_drop_60d']:
            sev = '🔴' if ic_drop > 0.10 else '🟠'
            alerts.append({
                'severity': sev,
                'category': f'{horizon}日IC衰减',
                'desc': f'{horizon}日IC从{baseline_ic:+.4f}降至{latest_m["ic"]:+.4f} (Δ-{ic_drop:.4f})',
                'detail': f'基线均值={baseline_ic:.4f}, 当前={latest_m["ic"]:.4f}',
            })
        
        # AUC下降
        auc_drop = baseline_auc - latest_m['auc']
        if auc_drop > THRESHOLDS['auc_drop_60d']:
            sev = '🔴' if auc_drop > 0.06 else '🟠'
            alerts.append({
                'severity': sev,
                'category': f'{horizon}日AUC下降',
                'desc': f'{horizon}日AUC从{baseline_auc:.3f}降至{latest_m["auc"]:.3f} (Δ-{auc_drop:.3f})',
                'detail': f'基线均值={baseline_auc:.4f}, 当前={latest_m["auc"]:.4f}',
            })
    
    # ── 2. 概率分布偏移 ──
    latest_ps = latest.get('prob_stats', {})
    baseline_means = [r.get('prob_stats', {}).get('mean', 0.5) for r in baseline_records if 'prob_stats' in r]
    baseline_stds = [r.get('prob_stats', {}).get('std', 0.2) for r in baseline_records if 'prob_stats' in r]
    
    if baseline_means and latest_ps:
        baseline_mean = sum(baseline_means) / len(baseline_means)
        baseline_std = sum(baseline_stds) / len(baseline_stds)
        
        mean_shift = abs(latest_ps['mean'] - baseline_mean)
        if mean_shift > THRESHOLDS['prob_mean_shift']:
            sev = '🟠' if mean_shift < 0.15 else '🔴'
            direction = '偏多' if latest_ps['mean'] > baseline_mean else '偏空'
            alerts.append({
                'severity': sev,
                'category': '概率分布偏移',
                'desc': f'加权概率均值从{baseline_mean:.1%}→{latest_ps["mean"]:.1%} (Δ{mean_shift:.1%}，{direction})',
                'detail': f'基线均值={baseline_mean:.4f}, 当前={latest_ps["mean"]:.4f}',
            })
        
        std_change = abs(latest_ps['std'] - baseline_std)
        if std_change > THRESHOLDS['prob_std_change']:
            sev = '🟢'
            direction = '收敛' if latest_ps['std'] < baseline_std else '发散'
            alerts.append({
                'severity': sev,
                'category': '概率波动变化',
                'desc': f'概率标准差从{baseline_std:.1%}→{latest_ps["std"]:.1%} (Δ{std_change:.1%}，{direction})',
                'detail': f'基线std={baseline_std:.4f}, 当前={latest_ps["std"]:.4f}',
            })
    
    # ── 3. 特征重要性排名变化 ──
    latest_fi = latest.get('feature_importance_top10', {})
    if baseline_records and latest_fi:
        # 取基线第一条的特征重要性作为参考
        baseline_fi = baseline_records[0].get('feature_importance_top10', {})
        if baseline_fi:
            # 比较TOP5特征的排名变化
            latest_top5 = list(latest_fi.keys())[:5]
            baseline_top5 = list(baseline_fi.keys())[:5]
            
            rank_changes = []
            for i, f in enumerate(latest_top5):
                if f in baseline_top5:
                    old_rank = baseline_top5.index(f)
                    change = old_rank - i  # 正数=上升，负数=下降
                    if abs(change) >= THRESHOLDS['feature_rank_change']:
                        rank_changes.append(f'{f}: #{old_rank+1}→#{i+1}')
                else:
                    rank_changes.append(f'{f}: 新进TOP5')
            
            if rank_changes:
                alerts.append({
                    'severity': '🟢',
                    'category': '特征重要性排名变化',
                    'desc': f'TOP5特征排名变动: {"; ".join(rank_changes)}',
                    'detail': f'基线TOP5: {", ".join(baseline_top5[:5])} → 最新TOP5: {", ".join(latest_top5[:5])}',
                })
    
    # ── 4. Regime分布偏移 ──
    latest_regime = latest.get('regime_distribution', {})
    if baseline_records and latest_regime:
        baseline_regimes = [r.get('regime_distribution', {}) for r in baseline_records if 'regime_distribution' in r]
        if baseline_regimes:
            total_baseline = {'bull': 0, 'range': 0, 'bear': 0}
            for r in baseline_regimes:
                for k in total_baseline:
                    total_baseline[k] += r.get(k, 0)
            n = len(baseline_regimes)
            baseline_pct = {k: v / (n * sum(total_baseline.values()) / n) if sum(total_baseline.values()) > 0 else 0 for k, v in total_baseline.items()}
            
            latest_total = sum(latest_regime.values())
            if latest_total > 0:
                latest_pct = {k: v / latest_total for k, v in latest_regime.items()}
                
                for regime_name, cn in [('bull', '牛市'), ('range', '震荡'), ('bear', '熊市')]:
                    shift = abs(latest_pct.get(regime_name, 0) - baseline_pct.get(regime_name, 0))
                    if shift > THRESHOLDS['regime_dist_shift']:
                        alerts.append({
                            'severity': '🟢',
                            'category': f'Regime分布偏移',
                            'desc': f'{cn}占比: 基线{baseline_pct.get(regime_name, 0):.1%} → 最新{latest_pct.get(regime_name, 0):.1%} (Δ{shift:.1%})',
                            'detail': f'基线: 牛{baseline_pct.get("bull", 0):.1%}/震{baseline_pct.get("range", 0):.1%}/熊{baseline_pct.get("bear", 0):.1%}',
                        })
                        break  # 只报一个
    
    # ── 5. 夏普下降 ──
    latest_sharpe = latest.get('best_sharpe', 0)
    baseline_sharpes = [r.get('best_sharpe', 0) for r in baseline_records if 'best_sharpe' in r]
    if baseline_sharpes:
        baseline_sharpe = sum(baseline_sharpes) / len(baseline_sharpes)
        sharpe_drop = baseline_sharpe - latest_sharpe
        if sharpe_drop > THRESHOLDS['sharpe_drop']:
            sev = '🟠' if sharpe_drop < 0.40 else '🔴'
            alerts.append({
                'severity': sev,
                'category': '策略夏普下降',
                'desc': f'最优夏普从{baseline_sharpe:.2f}降至{latest_sharpe:.2f} (Δ-{sharpe_drop:.2f})',
                'detail': f'基线均值={baseline_sharpe:.4f}, 当前={latest_sharpe:.4f}',
            })
    
    return alerts


def format_drift_report(alerts, latest, history):
    """格式化漂移报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    lines = []
    lines.append(f"📊 模型漂移检测报告 ({now})")
    lines.append("=" * 50)
    lines.append("")
    
    if not alerts:
        lines.append("✅ 未检测到显著漂移，模型运行稳定")
    else:
        # 按严重度排序
        sev_order = {'🔴': 0, '🟠': 1, '🟢': 2}
        alerts_sorted = sorted(alerts, key=lambda x: sev_order.get(x['severity'], 3))
        
        for a in alerts_sorted:
            lines.append(f"{a['severity']} {a['category']}")
            lines.append(f"  {a['desc']}")
            lines.append("")
    
    lines.append("📋 当前模型状态:")
    ml = latest.get('ml_metrics', {})
    for h in ['5', '10', '20', '60']:
        if h in ml:
            m = ml[h]
            lines.append(f"  {h:>3s}日: 准确率={m['accuracy']:.1%} AUC={m['auc']:.3f} IC={m['ic']:+.4f}")
    
    cs = latest.get('current_state', {})
    if cs:
        lines.append(f"  当前: Regime={cs['regime']} 概率={cs['probability']:.1%} 仓位={cs['position']:.0%}")
    
    lines.append(f"  历史记录: {len(history)}条")
    lines.append("")
    
    return '\n'.join(lines)


def run(verbose=False):
    """主函数：检测漂移并输出报告"""
    history = load_drift_history()
    
    if len(history) < 2:
        print(f"[DRIFT] 历史记录不足2条({len(history)})，至少需要2次运行才能检测漂移")
        if len(history) == 1:
            print(f"  当前: {history[0]['timestamp']}, Regime={history[0]['current_state']['regime']}")
        return None
    
    if verbose:
        print(f"[DRIFT] 加载历史: {len(history)}条")
    
    alerts = detect_drift(history, verbose=verbose)
    latest = history[-1]
    
    report = format_drift_report(alerts, latest, history)
    print(report)
    
    # 返回告警（供signal_alert集成用）
    return alerts if alerts else None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='模型漂移检测')
    parser.add_argument('--verbose', action='store_true', help='详细输出')
    args = parser.parse_args()
    
    run(verbose=args.verbose)
