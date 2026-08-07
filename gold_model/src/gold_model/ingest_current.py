"""GOLD COMMAND V6 — 独立 ingest 脚本 [DEPRECATED 2026-08-07]

⚠️ 已弃用：V5 脚本 (gold_factor_v5.py) 现在直接在末尾调用 db.insert_signal()，
   写 JSON + 同步 public/ + 写 SQLite 三步合一，无需再跑此脚本。
   保留此文件仅作 fallback：如果 V5 脚本 SQLite 写入失败，可手动跑一次补救。

用法（仅 fallback 场景）：
  python3 -m gold_model.ingest_current
"""
import sys
import json
from pathlib import Path

from gold_model.paths import DASHBOARD_JSON, EXECUTION_JSON

DASHBOARD = DASHBOARD_JSON
EXECUTION = EXECUTION_JSON

from gold_model.db import db

def main():
    if not DASHBOARD.exists() or not EXECUTION.exists():
        print(f'[ingest] JSON not found: {DASHBOARD.exists()}/{EXECUTION.exists()}')
        return 1

    with open(DASHBOARD, 'r', encoding='utf-8') as f:
        dashboard = json.load(f)
    with open(EXECUTION, 'r', encoding='utf-8') as f:
        execution = json.load(f)

    db.init()
    sid = db.insert_signal(dashboard, execution)
    stats = db.stats()
    print(f'[ingest] OK signal_id={sid}, total={stats["total_signals"]}, latest={stats["latest"]}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
