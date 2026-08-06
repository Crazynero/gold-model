"""GOLD COMMAND V6 — SQLite 历史信号持久化
存储每次 V5 脚本运行结果，支持任意天数查询

用法：
  from gold_model.db import db
  db.init()
  db.insert_signal(dashboard_data, execution_data)  # 每次 V5 跑完调用
  rows = db.query_history(days=30, regime='熊市')   # 查询历史
"""
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from gold_model.paths import GOLD_SIGNALS_DB

DB_PATH = GOLD_SIGNALS_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,                    -- V5 脚本运行时间 (ISO8601)
    base_date TEXT NOT NULL,                -- 预测基准日 (前一交易日)
    gold_price REAL,
    regime TEXT,
    position REAL,
    weighted_prob REAL,
    prob_5d REAL,
    prob_10d REAL,
    prob_20d REAL,
    prob_60d REAL,
    v3e_sharpe REAL,
    v3e_max_dd REAL,
    v3e_annual_ret REAL,
    v3e_win_rate REAL,
    holdout_sharpe REAL,
    holdout_decay REAL,
    signal_action TEXT,
    hit_rate_20d REAL,
    wf_base REAL,
    pos_factor REAL,
    dashboard_json TEXT,                    -- 完整 dashboard_data.json 内容
    execution_json TEXT                     -- 完整 execution_data.json 内容
);

CREATE INDEX IF NOT EXISTS idx_signals_base_date ON signals(base_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_regime ON signals(regime);
CREATE INDEX IF NOT EXISTS idx_signals_run_at ON signals(run_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerted_at TEXT NOT NULL,
    alert_type TEXT NOT NULL,               -- drift / signal / data_quality
    severity TEXT NOT NULL,                -- high / medium / low
    title TEXT,
    detail TEXT,
    metric_value REAL,
    baseline_value REAL
);

CREATE INDEX IF NOT EXISTS idx_alerts_alerted_at ON alerts(alerted_at DESC);
"""


class DBHelper:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self):
        """初始化数据库表"""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def insert_signal(self, dashboard: Dict, execution: Dict) -> int:
        """插入一条信号记录"""
        ov = dashboard.get('overview', {})
        v3e = next((s for s in dashboard.get('strategies', []) if s.get('策略', '').startswith('V3.0-E')), {})
        holdout = next((s for s in dashboard.get('v5_holdout', []) if 'V3.0-E' in s.get('strategy', '')), {})
        ss = execution.get('signal_stats', {})
        cur = execution.get('current', {})

        # 解析概率字段（"59.6%" → 0.596, "-6.9%" → -0.069, "2.44" → 2.44）
        def parse_pct(v):
            if v is None: return None
            s = str(v).strip()
            has_percent = '%' in s
            s = s.replace('%', '').replace('+', '')
            try:
                n = float(s)
                return n / 100 if has_percent else n  # 只对带%的除100
            except: return None

        # decay
        full_sharpe = parse_pct(v3e.get('夏普'))
        if full_sharpe is None: full_sharpe = 0
        oos_sharpe = holdout.get('sharpe')
        decay = None
        if oos_sharpe is not None and full_sharpe > 0:
            decay = (1 - oos_sharpe / full_sharpe) * 100

        # pos_factor
        hit_rate = parse_pct(ss.get('hit_rate_20d') or ov.get('命中率20日'))
        wf_base = parse_pct(ss.get('wf_base') or '0.58')
        pos_factor = None
        if hit_rate is not None and wf_base is not None:
            dev = hit_rate - wf_base
            if dev < -0.25: pos_factor = 0.2
            elif dev < -0.15: pos_factor = 0.5
            elif dev < -0.05: pos_factor = 0.8
            else: pos_factor = 1.0

        cursor = self.conn.execute("""
            INSERT INTO signals (
                run_at, base_date, gold_price, regime, position, weighted_prob,
                prob_5d, prob_10d, prob_20d, prob_60d,
                v3e_sharpe, v3e_max_dd, v3e_annual_ret, v3e_win_rate,
                holdout_sharpe, holdout_decay,
                signal_action, hit_rate_20d, wf_base, pos_factor,
                dashboard_json, execution_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            str(ov.get('预测基准日', '')),
            float(ov.get('当前金价', '0').replace('$', '').replace(',', '')) if ov.get('当前金价') else None,
            str(ov.get('当前Regime', '')),
            float(cur.get('position', 0)) if cur.get('position') is not None else None,
            parse_pct(ov.get('加权集成概率')),
            parse_pct(ov.get('5日看多概率')),
            parse_pct(ov.get('10日看多概率')),
            parse_pct(ov.get('20日看多概率')),
            parse_pct(ov.get('60日看多概率')),
            parse_pct(v3e.get('夏普')),
            parse_pct(v3e.get('最大回撤')),
            parse_pct(v3e.get('年化收益')),
            parse_pct(v3e.get('胜率')),
            oos_sharpe,
            decay,
            str(ov.get('建议操作', '')),
            hit_rate,
            wf_base,
            pos_factor,
            json.dumps(dashboard, ensure_ascii=False),
            json.dumps(execution, ensure_ascii=False)
        ))
        self.conn.commit()
        return cursor.lastrowid

    def insert_alert(self, alert_type: str, severity: str, title: str, detail: str,
                     metric_value: float = None, baseline_value: float = None) -> int:
        cursor = self.conn.execute("""
            INSERT INTO alerts (alerted_at, alert_type, severity, title, detail,
                                metric_value, baseline_value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(), alert_type, severity, title, detail,
            metric_value, baseline_value
        ))
        self.conn.commit()
        return cursor.lastrowid

    def query_history(self, days: int = 30, regime: Optional[str] = None,
                      action: Optional[str] = None,
                      start: Optional[str] = None, end: Optional[str] = None) -> List[Dict]:
        """查询历史信号"""
        where_parts = []
        params = []
        if start:
            where_parts.append("run_at >= ?")
            params.append(start)
        if end:
            where_parts.append("run_at <= ?")
            params.append(end)
        else:
            where_parts.append("run_at >= ?")
            params.append((datetime.now() - timedelta(days=days)).isoformat())
        if regime:
            where_parts.append("regime = ?")
            params.append(regime)
        if action:
            where_parts.append("signal_action LIKE ?")
            params.append(f"%{action}%")

        sql = "SELECT * FROM signals"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        sql += " ORDER BY run_at DESC"

        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def query_alerts(self, days: int = 7, alert_type: Optional[str] = None) -> List[Dict]:
        where = ["alerted_at >= ?"]
        params = [(datetime.now() - timedelta(days=days)).isoformat()]
        if alert_type:
            where.append("alert_type = ?")
            params.append(alert_type)
        sql = "SELECT * FROM alerts WHERE " + " AND ".join(where) + " ORDER BY alerted_at DESC"
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def stats(self) -> Dict:
        """数据库统计"""
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM signals")
        total = cur.fetchone()['c']
        cur = self.conn.execute("SELECT MIN(run_at) AS s, MAX(run_at) AS e FROM signals")
        r = cur.fetchone()
        return {
            'total_signals': total,
            'earliest': r['s'],
            'latest': r['e'],
            'db_path': str(self.path)
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

# 单例
db = DBHelper()
