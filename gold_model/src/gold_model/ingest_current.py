"""GOLD COMMAND V6 — 独立 ingest 脚本
读取 dashboard_data.json + execution_data.json，写入 SQLite
用于 cron 任务调用（不依赖 FastAPI 服务运行）

用法：
  python3 ingest_current.py
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
