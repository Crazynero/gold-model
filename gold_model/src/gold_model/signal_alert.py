#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金V4 异常信号检测器
检测Regime切换/仓位大幅变化/概率穿越阈值，触发时推送消息

用法：
  python3 signal_alert.py              # 检测一次
  python3 signal_alert.py --dry-run    # 用模拟数据测试消息格式
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# 路径设置
from gold_model.paths import EXECUTION_JSON, DASHBOARD_JSON, SIGNAL_ALERT_STATE

STATE_FILE = SIGNAL_ALERT_STATE  # 上次状态

# ── 触发条件定义 ──
TRIGGERS = {
    'regime_switch': {
        'desc': 'Regime切换（牛/震/熊）',
        'severity': '🔴 高',
    },
    'position_change_large': {
        'desc': '仓位变化≥0.3',
        'severity': '🟠 中高',
        'threshold': 0.3,
    },
    'prob_cross_up_065': {
        'desc': '加权概率上穿0.65（看多信号增强）',
        'severity': '🟢 中',
        'threshold': 0.65,
    },
    'prob_cross_down_035': {
        'desc': '加权概率下穿0.35（看空信号增强）',
        'severity': '🟢 中',
        'threshold': 0.35,
    },
    'prob_cross_up_070': {
        'desc': '加权概率上穿0.70（强看多）',
        'severity': '🔴 高',
        'threshold': 0.70,
    },
    'prob_cross_down_030': {
        'desc': '加权概率下穿0.30（强看空）',
        'severity': '🔴 高',
        'threshold': 0.30,
    },
}


def load_current_data():
    """加载V4最新输出"""
    try:
        with open(EXECUTION_JSON) as f:
            exec_data = json.load(f)
        with open(DASHBOARD_JSON) as f:
            dash_data = json.load(f)
        return exec_data, dash_data
    except FileNotFoundError as e:
        print(f"[ALERT] JSON文件不存在: {e}")
        print(f"  execution: {EXECUTION_JSON}")
        print(f"  dashboard: {DASHBOARD_JSON}")
        return None, None
    except json.JSONDecodeError as e:
        print(f"[ALERT] JSON解析失败: {e}")
        return None, None


def load_prev_state():
    """加载上次状态"""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(state):
    """保存当前状态"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def detect_signals(current, prev):
    """
    检测异常信号
    返回: (alerts列表, new_state字典)
    """
    alerts = []
    
    cur_regime = current.get('regime', '未知')
    cur_pos = current.get('position', 0.0)
    cur_prob = current.get('probability', 0.5)
    
    new_state = {
        'regime': cur_regime,
        'position': cur_pos,
        'probability': cur_prob,
        'timestamp': datetime.now().isoformat(),
    }
    
    if prev is None:
        # 首次运行，不触发任何信号，只记录状态
        return alerts, new_state
    
    prev_regime = prev.get('regime', cur_regime)
    prev_pos = prev.get('position', cur_pos)
    prev_prob = prev.get('probability', cur_prob)
    
    # 1. Regime切换
    if cur_regime != prev_regime:
        alerts.append({
            'type': 'regime_switch',
            'severity': TRIGGERS['regime_switch']['severity'],
            'title': f"Regime切换: {prev_regime} → {cur_regime}",
            'detail': f"市场状态发生切换，策略行为将改变",
        })
    
    # 2. 仓位变化≥0.3
    pos_delta = abs(cur_pos - prev_pos)
    if pos_delta >= TRIGGERS['position_change_large']['threshold']:
        direction = '加仓' if cur_pos > prev_pos else '减仓'
        alerts.append({
            'type': 'position_change_large',
            'severity': TRIGGERS['position_change_large']['severity'],
            'title': f"仓位大幅{direction}: {prev_pos:.0%} → {cur_pos:.0%} (Δ{pos_delta:.0%})",
            'detail': f"仓位变化达到{pos_delta:.0%}，超过0.3阈值",
        })
    
    # 3. 概率穿越0.65（上穿）
    if prev_prob < 0.65 <= cur_prob:
        alerts.append({
            'type': 'prob_cross_up_065',
            'severity': TRIGGERS['prob_cross_up_065']['severity'],
            'title': f"概率上穿0.65: {prev_prob:.1%} → {cur_prob:.1%}",
            'detail': "看多信号增强，接近建仓阈值",
        })
    
    # 4. 概率穿越0.35（下穿）
    if prev_prob > 0.35 >= cur_prob:
        alerts.append({
            'type': 'prob_cross_down_035',
            'severity': TRIGGERS['prob_cross_down_035']['severity'],
            'title': f"概率下穿0.35: {prev_prob:.1%} → {cur_prob:.1%}",
            'detail': "看空信号增强，接近做空阈值",
        })
    
    # 5. 概率穿越0.70（强看多上穿）
    if prev_prob < 0.70 <= cur_prob:
        alerts.append({
            'type': 'prob_cross_up_070',
            'severity': TRIGGERS['prob_cross_up_070']['severity'],
            'title': f"概率上穿0.70: {prev_prob:.1%} → {cur_prob:.1%}",
            'detail': "强看多信号，建议关注建仓机会",
        })
    
    # 6. 概率穿越0.30（强看空下穿）
    if prev_prob > 0.30 >= cur_prob:
        alerts.append({
            'type': 'prob_cross_down_030',
            'severity': TRIGGERS['prob_cross_down_030']['severity'],
            'title': f"概率下穿0.30: {prev_prob:.1%} → {cur_prob:.1%}",
            'detail': "强看空信号，建议关注下行风险",
        })
    
    return alerts, new_state


def format_message(alerts, current, dash_overview):
    """格式化推送消息"""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    lines = [f"📊 黄金V4信号告警 ({now_str})"]
    lines.append("=" * 40)
    
    for a in alerts:
        lines.append(f"\n{a['severity']} {a['title']}")
        lines.append(f"  {a['detail']}")
    
    # 当前状态摘要
    lines.append("\n" + "=" * 40)
    lines.append("📋 当前状态:")
    lines.append(f"  Regime: {current.get('regime', '?')}")
    lines.append(f"  仓位: {current.get('position', 0):.0%}")
    lines.append(f"  加权概率: {current.get('probability', 0):.1%}")
    lines.append(f"  金价: ${current.get('gold_price', 0):.0f}")
    
    # 多周期概率
    if dash_overview:
        for key in ['5日看多概率', '10日看多概率', '20日看多概率', '60日看多概率']:
            if key in dash_overview:
                lines.append(f"  {key}: {dash_overview[key]}")
        if '建议操作' in dash_overview:
            lines.append(f"  建议: {dash_overview['建议操作']}")
    
    return '\n'.join(lines)


def run(dry_run=False):
    """主入口"""
    if dry_run:
        # 用模拟数据测试消息格式
        mock_current = {
            'regime': '熊市',
            'position': 0.0,
            'probability': 0.462,
            'gold_price': 4051.4,
        }
        mock_prev = {
            'regime': '震荡',
            'position': 0.5,
            'probability': 0.68,
        }
        mock_overview = {
            '5日看多概率': '58.4%',
            '10日看多概率': '49.4%',
            '20日看多概率': '59.5%',
            '60日看多概率': '32.0%',
            '建议操作': '空仓观望',
        }
        alerts, _ = detect_signals(mock_current, mock_prev)
        msg = format_message(alerts, mock_current, mock_overview)
        print(msg)
        return
    
    # 正式运行
    exec_data, dash_data = load_current_data()
    if exec_data is None:
        return
    
    current = exec_data.get('current', {})
    if not current:
        print("[ALERT] execution_data.json中没有current字段")
        return
    
    # 提取overview
    dash_overview = {}
    if dash_data and 'overview' in dash_data:
        ov = dash_data['overview']
        if isinstance(ov, dict):
            dash_overview = ov
    
    prev = load_prev_state()
    alerts, new_state = detect_signals(current, prev)
    
    # V4.2: 集成漂移检测
    drift_alerts = []
    try:
        from gold_model.drift_monitor import load_drift_history, detect_drift
        history = load_drift_history()
        if len(history) >= 2:
            raw_drift = detect_drift(history, verbose=False)
            # 统一格式：转换为signal alert格式
            for d in raw_drift:
                drift_alerts.append({
                    'severity': d.get('severity', '🟡'),
                    'title': f"漂移·{d.get('category', '?')}: {d.get('desc', '')}",
                    'detail': d.get('detail', ''),
                })
    except Exception as e:
        if os.environ.get('ALERT_DEBUG'):
            print(f"[DRIFT] 漂移检测失败: {e}")
    
    # V4.2: 信号回测基准检测
    signal_alerts = []
    try:
        if len(history) >= 1:
            latest = history[-1]
            sb = latest.get('signal_backtest', {})
            if sb:
                wf_base = sb.get('wf_baseline_acc', 0.6)
                r20 = sb.get('recent_20_hit_rate', 0.5)
                r10 = sb.get('recent_10_hit_rate', 0.5)
                consec = sb.get('consecutive_miss', 0)
                
                # 连续3次方向错误 → 模型可能失效
                if consec >= 3:
                    signal_alerts.append({
                        'severity': '🔴 高',
                        'title': f"信号·连续{consec}次方向错误",
                        'detail': f"模型可能失效，建议暂停跟单并检查最近市场结构变化",
                    })
                
                # 最近20次命中率 < 40% → 严重失效
                if r20 < 0.40:
                    signal_alerts.append({
                        'severity': '🔴 高',
                        'title': f"信号·近期命中率严重偏低: {r20:.0%}",
                        'detail': f"最近20次信号仅{int(r20*20)}/20命中，WF基准={wf_base:.0%}，偏差{r20-wf_base:+.0%}",
                    })
                # 最近20次命中率比WF基准低15%+ 但未到40%以下
                elif r20 < wf_base - 0.15:
                    signal_alerts.append({
                        'severity': '🟠 中高',
                        'title': f"信号·近期命中率下降: {r20:.0%} (基准{wf_base:.0%})",
                        'detail': f"最近20次命中率比WF整体低{(wf_base-r20):.0%}，模型处于不利周期",
                    })
                
                # 最近10次命中率 < 50%
                if r10 < 0.50 and r20 >= 0.40:
                    signal_alerts.append({
                        'severity': '🟡 中',
                        'title': f"信号·近10次命中率偏弱: {r10:.0%}",
                        'detail': f"最近10次信号{int(r10*10)}/10命中，短期表现不佳",
                    })
    except Exception as e:
        if os.environ.get('ALERT_DEBUG'):
            print(f"[SIGNAL-BT] 信号回测检测失败: {e}")
    
    all_alerts = alerts + drift_alerts + signal_alerts
    
    if all_alerts:
        msg = format_message(all_alerts, current, dash_overview)
        print(msg)
        save_state(new_state)
        return msg
    else:
        # 无告警，只保存状态
        save_state(new_state)
        is_first = prev is None
        extra_status = ""
        if drift_alerts:
            extra_status += f", 漂移{len(drift_alerts)}项"
        if signal_alerts:
            extra_status += f", 信号{len(signal_alerts)}项"
        # 附加信号回测摘要
        try:
            sb = history[-1].get('signal_backtest', {})
            if sb:
                extra_status += f", 近20命中{sb['recent_20_hit_rate']:.0%}"
        except:
            pass
        if is_first:
            print(f"[ALERT] 首次运行，状态已记录: Regime={new_state['regime']}, 仓位={new_state['position']:.0%}, 概率={new_state['probability']:.1%}{extra_status}")
        else:
            print(f"[ALERT] 无异常信号。当前: Regime={new_state['regime']}, 仓位={new_state['position']:.0%}, 概率={new_state['probability']:.1%}{extra_status}")
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='黄金V4异常信号检测')
    parser.add_argument('--dry-run', action='store_true', help='用模拟数据测试消息格式')
    args = parser.parse_args()
    
    result = run(dry_run=args.dry_run)
    if result:
        # 有告警时退出码=1，cron任务据此推送
        sys.exit(0)
    else:
        sys.exit(0)
