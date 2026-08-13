"""GOLD COMMAND V6 — 飞书机器人每日推送
每日 8:30 把当日信号 + 仓位建议 + 关键告警推送到飞书群

用法：
  python3 send_to_feishu.py
  # 或通过 API: POST /api/push/feishu

前提：先配置飞书 bot（Feishu 工具）
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime

from gold_model.paths import DASHBOARD_JSON, EXECUTION_JSON

DASHBOARD = DASHBOARD_JSON
EXECUTION = EXECUTION_JSON

# 飞书 webhook URL（通过环境变量或配置文件）
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK_URL', '')
FEISHU_SECRET = os.environ.get('FEISHU_WEBHOOK_SECRET', '')


def build_message():
    """构造飞书 interactive 消息卡片"""
    if not DASHBOARD.exists():
        return None

    with open(DASHBOARD, 'r', encoding='utf-8') as f:
        d = json.load(f)
    ov = d.get('overview', {})

    gold_price = ov.get('当前金价', '--')
    regime = ov.get('当前Regime', '--')
    action = ov.get('建议操作', '--')
    weighted_prob = ov.get('加权集成概率', '--')
    base_date = ov.get('预测基准日', '--')
    prob_5d = ov.get('5日看多概率', '--')
    prob_10d = ov.get('10日看多概率', '--')
    prob_20d = ov.get('20日看多概率', '--')
    prob_60d = ov.get('60日看多概率', '--')

    # 关键策略
    v3e = next((s for s in d.get('strategies', []) if 'V3.0-E' in s.get('策略', '')), {})
    sharpe = v3e.get('夏普', '--')
    max_dd = v3e.get('最大回撤', '--')

    # Holdout
    v5h = d.get('v5_holdout', [])
    v3e_holdout = next((s for s in v5h if 'V3.0-E' in s.get('strategy', '')), {})
    holdout_sharpe = v3e_holdout.get('sharpe', '--')

    # 告警（简单版：命中率告警）
    sb = d.get('signal_stats', {}) or {}
    hit_rate = 'N/A'
    wf_base = 'N/A'
    if not sb:
        # 从 execution_data 取
        exec_path = EXECUTION
        if exec_path.exists():
            with open(exec_path, 'r', encoding='utf-8') as f:
                e = json.load(f)
            sb = e.get('signal_stats', {}) or {}
    hit_rate = sb.get('hit_rate_20d', 'N/A')
    wf_base = sb.get('wf_base', 'N/A')

    # 卡片颜色：根据 Regime
    if '熊' in regime:
        header_color = 'red'
        emoji = '⚠️'
    elif '牛' in regime:
        header_color = 'green'
        emoji = '🚀'
    else:
        header_color = 'orange'
        emoji = '⚖️'

    today = datetime.now().strftime('%Y-%m-%d')
    title = f'{emoji} 黄金V5每日信号 {today}'

    # 构造 interactive 卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": header_color
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**预测基准日**: {base_date}\n**当前金价**: {gold_price}\n**Regime**: {regime}\n**建议操作**: **{action}**"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**多周期概率**\n5D: {prob_5d} / 10D: {prob_10d}\n20D: {prob_20d} / 60D: {prob_60d}\n**加权**: {weighted_prob}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**策略表现**\n夏普(回测): {sharpe} / 最大回撤: {max_dd}\n夏普(Holdout): {holdout_sharpe}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**信号质量**\n20日命中率: {hit_rate} (基准 {wf_base})"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整 Dashboard"},
                        "type": "primary",
                        "url": os.environ.get('DASHBOARD_URL', 'http://127.0.0.1:8000/')
                    }
                ]
            }
        ]
    }
    return card


def send():
    if not FEISHU_WEBHOOK:
        print('[feishu] FEISHU_WEBHOOK_URL not set')
        print('[feishu] Set env: export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
        return 1

    import urllib.request
    import hashlib
    import hmac
    import time

    card = build_message()
    if not card:
        print('[feishu] no dashboard data')
        return 1

    body = {"msg_type": "interactive", "card": card}
    if FEISHU_SECRET:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{FEISHU_SECRET}"
        sign = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
        import base64
        body['timestamp'] = timestamp
        body['sign'] = base64.b64encode(sign).decode()

    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get('StatusCode') == 0 or result.get('code') == 0:
                print(f'[feishu] pushed at {datetime.now().isoformat()}')
                return 0
            else:
                print(f'[feishu] failed: {result}')
                return 1
    except Exception as e:
        print(f'[feishu] error: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(send())
