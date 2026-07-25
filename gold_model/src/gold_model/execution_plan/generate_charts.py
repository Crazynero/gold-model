#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成信号频率分析图表"""

import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Hiragino Sans GB', 'Noto Sans SC', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from gold_model.paths import EXECUTION_PLAN_DIR, ANALYSIS_JSON

OUT_DIR = str(EXECUTION_PLAN_DIR / 'charts')
os.makedirs(OUT_DIR, exist_ok=True)

# 加载数据
with open(str(ANALYSIS_JSON), 'r') as f:
    analysis = json.load(f)

pos_df = pd.read_csv(str(EXECUTION_PLAN_DIR / 'position_series.csv'), parse_dates=['date'])
pos_df = pos_df.dropna(subset=['position'])

stats = analysis['signal_stats']
costs = analysis['cost_comparison']

# 配色
C_ACCENT = '#288fb1'
C_GREEN = '#548235'
C_RED = '#C00000'
C_YELLOW = '#BF9000'
C_MUTED = '#7b776f'
C_LIGHT = '#e5e3df'

# ═══════════════════════════════════════════════════════════════════
# 图1: 仓位分布饼图
# ═══════════════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(8, 5))
labels = list(stats['仓位分布'].keys())
sizes = list(stats['仓位分布'].values())
colors_pie = [C_MUTED, C_LIGHT, C_ACCENT, C_GREEN, C_YELLOW, C_RED]
# 过滤掉为0的
filtered = [(l, s, c) for l, s, c in zip(labels, sizes, colors_pie) if s > 0]
labels, sizes, colors_pie = zip(*filtered)

wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors_pie,
    autopct='%1.1f%%', startangle=90, textprops={'fontsize': 10})
for t in autotexts:
    t.set_fontsize(9)
ax.set_title('V4模型仓位分布 (2022.12~2026.06)', fontsize=13, fontweight='bold', pad=15)
plt.tight_layout()
plt.savefig(f'{OUT_DIR}/position_distribution.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ position_distribution.png")

# ═══════════════════════════════════════════════════════════════════
# 图2: 仓位时间序列
# ═══════════════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(12, 4))
colors_pos = [C_GREEN if p > 0 else C_RED if p < 0 else C_MUTED for p in pos_df['position']]
ax.bar(pos_df['date'], pos_df['position'], color=colors_pos, width=1.5, alpha=0.7)
ax.axhline(y=0, color='black', linewidth=0.5)
ax.axhline(y=1.0, color=C_GREEN, linewidth=0.5, linestyle='--', alpha=0.5)
ax.axhline(y=-1.0, color=C_RED, linewidth=0.5, linestyle='--', alpha=0.5)
ax.fill_between(pos_df['date'], 0, pos_df['position'], where=pos_df['position'] > 0,
                color=C_GREEN, alpha=0.3, label='多头')
ax.fill_between(pos_df['date'], 0, pos_df['position'], where=pos_df['position'] < 0,
                color=C_RED, alpha=0.3, label='空头')
ax.set_title('V3.0-E仓位信号时间序列', fontsize=13, fontweight='bold')
ax.set_ylabel('仓位', fontsize=11)
ax.legend(loc='upper right', fontsize=9)
ax.set_ylim(-1.8, 1.8)
plt.tight_layout()
plt.savefig(f'{OUT_DIR}/position_timeseries.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ position_timeseries.png")

# ═══════════════════════════════════════════════════════════════════
# 图3: 成本对比柱状图
# ═══════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# 左图：不同资金规模下的年化成本（%）
capitals = [100000, 500000, 1000000, 5000000]
cap_labels = ['10万', '50万', '100万', '500万']
modes = ['纯ETF', '纯期货', 'ETF+期货分层']
colors_bar = [C_ACCENT, C_GREEN, C_YELLOW]

n_years = len(pos_df) / 250
x = np.arange(len(capitals))
width = 0.25

for i, mode in enumerate(modes):
    rates = []
    for cap in capitals:
        c = costs[str(cap)][mode]
        usd_cap = cap / 7.2
        ann_cost = c['总成本'] / n_years
        rate = ann_cost / usd_cap * 100
        rates.append(rate)
    axes[0].bar(x + i * width, rates, width, label=mode, color=colors_bar[i])

axes[0].set_xlabel('资金规模 (人民币)', fontsize=11)
axes[0].set_ylabel('年化成本率 (%)', fontsize=11)
axes[0].set_title('不同资金规模下的年化成本对比', fontsize=12, fontweight='bold')
axes[0].set_xticks(x + width)
axes[0].set_xticklabels(cap_labels)
axes[0].legend(fontsize=9)
axes[0].grid(axis='y', alpha=0.3)

# 右图：100万资金下成本结构分解
cap_key = '1000000'
etf_cost = costs[cap_key]['纯ETF']
fut_cost = costs[cap_key]['纯期货']
hybrid = costs[cap_key]['ETF+期货分层']

categories = ['纯ETF', '纯期货', 'ETF+期货\n分层']
commission = [etf_cost['总佣金'], fut_cost['总佣金'], hybrid['ETF成本']['总佣金'] + hybrid['期货成本']['总佣金']]
mgmt = [etf_cost.get('总管理费', 0), fut_cost.get('保证金机会成本', 0),
        hybrid['ETF成本'].get('总管理费', 0) + hybrid['期货成本'].get('保证金机会成本', 0)]

axes[1].bar(categories, commission, 0.5, label='佣金', color=C_ACCENT)
axes[1].bar(categories, mgmt, 0.5, bottom=commission, label='管理费/保证金成本', color=C_LIGHT)
axes[1].set_ylabel('成本 ($)', fontsize=11)
axes[1].set_title('100万资金成本结构分解', fontsize=12, fontweight='bold')
axes[1].legend(fontsize=9)
axes[1].grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig(f'{OUT_DIR}/cost_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ cost_comparison.png")

# ═══════════════════════════════════════════════════════════════════
# 图4: 月度调仓频率
# ═══════════════════════════════════════════════════════════════════

monthly = pos_df.set_index('date')['position'].diff().abs()
monthly = monthly[monthly > 0].resample('M').count()

fig, ax = plt.subplots(figsize=(12, 4))
colors_m = [C_RED if v > 20 else C_YELLOW if v > 15 else C_GREEN for v in monthly.values]
ax.bar(monthly.index, monthly.values, color=colors_m, width=20)
ax.axhline(y=monthly.mean(), color=C_ACCENT, linestyle='--', linewidth=1, label=f'月均{monthly.mean():.1f}次')
ax.set_title('月度调仓次数分布', fontsize=13, fontweight='bold')
ax.set_ylabel('调仓次数', fontsize=11)
ax.legend(fontsize=9)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(f'{OUT_DIR}/monthly_rebalance.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ monthly_rebalance.png")

# ═══════════════════════════════════════════════════════════════════
# 图5: 三层执行架构流程图
# ═══════════════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(10, 6))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis('off')

# 模型信号层
from matplotlib.patches import FancyBboxPatch
box1 = FancyBboxPatch((1, 8), 8, 1.5, boxstyle="round,pad=0.1", facecolor=C_ACCENT, edgecolor='none', alpha=0.9)
ax.add_patch(box1)
ax.text(5, 8.75, 'V4模型信号 (41因子 × 多周期集成)', ha='center', va='center', fontsize=12, fontweight='bold', color='white')

# 箭头
ax.annotate('', xy=(5, 7.3), xytext=(5, 8),
            arrowprops=dict(arrowstyle='->', color=C_MUTED, lw=2))

# 三层架构
# ETF底仓层
box2 = FancyBboxPatch((0.5, 5), 2.8, 2, boxstyle="round,pad=0.1", facecolor=C_GREEN, edgecolor='none', alpha=0.85)
ax.add_patch(box2)
ax.text(1.9, 6.5, 'ETF底仓层', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
ax.text(1.9, 6.0, '518880', ha='center', va='center', fontsize=10, color='white')
ax.text(1.9, 5.5, '60-70%资金', ha='center', va='center', fontsize=9, color='white')

# 期货战术层
box3 = FancyBboxPatch((3.6, 5), 2.8, 2, boxstyle="round,pad=0.1", facecolor=C_YELLOW, edgecolor='none', alpha=0.85)
ax.add_patch(box3)
ax.text(5, 6.5, '期货战术层', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
ax.text(5, 6.0, 'COMEX GC=F', ha='center', va='center', fontsize=10, color='white')
ax.text(5, 5.5, '30-40%资金', ha='center', va='center', fontsize=9, color='white')

# 现金层
box4 = FancyBboxPatch((6.7, 5), 2.8, 2, boxstyle="round,pad=0.1", facecolor=C_MUTED, edgecolor='none', alpha=0.85)
ax.add_patch(box4)
ax.text(8.1, 6.5, '现金层', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
ax.text(8.1, 6.0, '货币基金', ha='center', va='center', fontsize=10, color='white')
ax.text(8.1, 5.5, '0-10%资金', ha='center', va='center', fontsize=9, color='white')

# 箭头连接
for x in [1.9, 5, 8.1]:
    ax.annotate('', xy=(x, 5), xytext=(x, 5.8),
                arrowprops=dict(arrowstyle='->', color=C_MUTED, lw=1.5))

# 底部说明
ax.text(1.9, 4.5, '月均1.7次调仓\n大调仓≥0.3', ha='center', va='center', fontsize=9, color=C_GREEN)
ax.text(5, 4.5, '月均14次调仓\n任何仓位变化', ha='center', va='center', fontsize=9, color=C_YELLOW)
ax.text(8.1, 4.5, '保证金追加\n+申购缓冲', ha='center', va='center', fontsize=9, color=C_MUTED)

# 成本标注
ax.text(1.9, 3.5, '万一佣金\n免印花税\n0.6%/年管理费', ha='center', va='center', fontsize=8,
        bbox=dict(boxstyle='round,pad=0.3', facecolor=C_LIGHT, edgecolor='none'))
ax.text(5, 3.5, '$3/手佣金\n20倍杠杆\n无管理费', ha='center', va='center', fontsize=8,
        bbox=dict(boxstyle='round,pad=0.3', facecolor=C_LIGHT, edgecolor='none'))
ax.text(8.1, 3.5, '2-2.5%\n年化收益\n随时可取', ha='center', va='center', fontsize=8,
        bbox=dict(boxstyle='round,pad=0.3', facecolor=C_LIGHT, edgecolor='none'))

# 标题
ax.text(5, 9.5, 'ETF + 期货 三层执行架构', ha='center', va='center', fontsize=14, fontweight='bold', color='#1e1d1b')

plt.tight_layout()
plt.savefig(f'{OUT_DIR}/execution_architecture.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ execution_architecture.png")

# ═══════════════════════════════════════════════════════════════════
# 图6: 持仓时长分布
# ═══════════════════════════════════════════════════════════════════

pos_series = pos_df.set_index('date')['position']
pos_changes = pos_series.diff().fillna(0) != 0
change_idx = np.where(pos_changes.values)[0]
hold_periods = np.diff(change_idx) if len(change_idx) > 1 else [0]

fig, ax = plt.subplots(figsize=(8, 4))
bins = [0, 1, 2, 3, 5, 10, 20, 30]
counts, edges, patches = ax.hist(hold_periods, bins=bins, color=C_ACCENT, edgecolor='white', alpha=0.8)
ax.set_title('持仓时长分布 (天数)', fontsize=13, fontweight='bold')
ax.set_xlabel('持仓天数', fontsize=11)
ax.set_ylabel('频次', fontsize=11)
ax.axvline(x=np.median(hold_periods), color=C_RED, linestyle='--', linewidth=1.5, label=f'中位数: {np.median(hold_periods):.0f}天')
ax.legend(fontsize=9)
ax.grid(axis='y', alpha=0.3)

# 标注
for i, (c, e) in enumerate(zip(counts, edges)):
    if c > 0:
        ax.text(e + (edges[i+1]-e)/2, c + 5, f'{int(c)}', ha='center', fontsize=9)

plt.tight_layout()
plt.savefig(f'{OUT_DIR}/holding_period.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ holding_period.png")

print("\n全部图表生成完成。")
