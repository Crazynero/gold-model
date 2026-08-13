"""GOLD COMMAND V6 — FastAPI 后端
提供 dashboard 数据 API + WebSocket 实时推送

启动：
  cd /home/z/my-project/reports/gold_model/dashboard-vue3
  uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload

接口：
  GET  /api/state           — 当前状态（dashboard_data.json 全量）
  GET  /api/history?days=N  — 历史信号（最近N天，默认30）
  GET  /api/drift           — 漂移快照
  GET  /api/health          — 健康检查
  WS   /ws                  — 实时推送金价/信号变更
"""
import json
import asyncio
import time
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from gold_model.db import db

# === 路径 ===
from gold_model.paths import (
    DASHBOARD_JSON, EXECUTION_JSON, DRIFT_HISTORY, WEEKLY_REPORTS_DIR, WEB_DIR,
)

DRIFT_SNAPSHOT = DRIFT_HISTORY

# === 应用 ===
app = FastAPI(
    title="GOLD COMMAND V6 API",
    description="黄金多因子分析命令中心后端",
    version="6.0.0"
)

# CORS：允许任意来源（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 工具函数 ===
def _safe(obj: Any) -> Any:
    """递归过滤 NaN/Infinity（JSON 标准不支持）"""
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj in (float('inf'), float('-inf')):
            return None
    return obj

def _load_json(path: Path) -> Dict:
    """加载 JSON，文件不存在或解析失败返回空对象"""
    try:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] load {path} failed: {e}")
        return {}

def _file_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0

# === 全局缓存 ===
_last_dashboard_mtime = 0
_last_execution_mtime = 0
_dashboard_cache: Dict = {}
_execution_cache: Dict = {}

def _refresh_cache():
    global _last_dashboard_mtime, _last_execution_mtime, _dashboard_cache, _execution_cache
    dm = _file_mtime(DASHBOARD_JSON)
    em = _file_mtime(EXECUTION_JSON)
    if dm != _last_dashboard_mtime:
        _dashboard_cache = _safe(_load_json(DASHBOARD_JSON))
        _last_dashboard_mtime = dm
    if em != _last_execution_mtime:
        _execution_cache = _safe(_load_json(EXECUTION_JSON))
        _last_execution_mtime = em

# === 接口 ===

@app.get("/api/health")
async def health():
    """健康检查"""
    _refresh_cache()
    return {
        "status": "ok",
        "version": "6.0.0",
        "dashboard_loaded": bool(_dashboard_cache),
        "execution_loaded": bool(_execution_cache),
        "dashboard_mtime": datetime.fromtimestamp(_last_dashboard_mtime).isoformat() if _last_dashboard_mtime else None,
        "server_time": datetime.now().isoformat()
    }

@app.get("/api/state")
async def get_state():
    """当前完整状态：dashboard + execution 数据"""
    _refresh_cache()
    return {
        "dashboard": _dashboard_cache,
        "execution": _execution_cache,
        "fetched_at": datetime.now().isoformat(),
        "dashboard_updated_at": datetime.fromtimestamp(_last_dashboard_mtime).isoformat() if _last_dashboard_mtime else None
    }

@app.get("/api/history")
async def get_history(
    days: int = Query(30, ge=1, le=250, description="返回最近N天的历史信号"),
    regime: Optional[str] = Query(None, description="过滤Regime：牛市/熊市/震荡")
):
    """历史信号查询：从 raw_data 取最近N天，可按 Regime 过滤"""
    _refresh_cache()
    raw = _dashboard_cache.get('raw_data', [])
    if not raw:
        return {"data": [], "total": 0, "filter": {"days": days, "regime": regime}}
    
    # 取最近N天（raw_data 为升序，最近的在末尾）
    rows = raw[-days:][::-1]
    if regime:
        rows = [r for r in rows if r.get('Regime') == regime]
    
    return {
        "data": rows,
        "total": len(rows),
        "filter": {"days": days, "regime": regime},
        "fetched_at": datetime.now().isoformat()
    }

@app.get("/api/drift")
async def get_drift():
    """模型漂移快照（DRIFT_HISTORY 顶层是 list，非 {snapshots:...} 结构）"""
    drift = _safe(_load_json(DRIFT_SNAPSHOT))
    if not isinstance(drift, list):
        drift = []
    return {
        "snapshots": drift,
        "count": len(drift),
        "fetched_at": datetime.now().isoformat()
    }

@app.get("/api/strategies")
async def get_strategies():
    """策略对比数据：返回所有策略的 NAV 序列（若有）"""
    _refresh_cache()
    strategies = _dashboard_cache.get('strategies', [])
    return {
        "strategies": strategies,
        "count": len(strategies),
        "fetched_at": datetime.now().isoformat()
    }

@app.get("/api/signals/recent")
async def get_recent_signals(limit: int = Query(10, ge=1, le=100)):
    """最近N次信号变化（从 position_history 找仓位变化的点）
    修复: raw_data 无仓位/概率字段,原实现恒返回空;改读 execution_data 的 position_history。"""
    _refresh_cache()
    ph = _execution_cache.get('position_history', {})
    dates = ph.get('dates', [])
    positions = ph.get('positions', [])
    regimes = ph.get('regimes', [])
    gold_prices = ph.get('gold_prices', [])
    probs = ph.get('probabilities', [])

    signals = []
    # position_history 为升序（早→晚），从最新往回找仓位发生实质变化(≥0.05)的点
    for i in range(len(dates) - 1, 0, -1):
        pos = positions[i] if i < len(positions) else None
        prev = positions[i - 1] if i - 1 < len(positions) else None
        if pos is None or prev is None or abs(pos - prev) < 0.05:
            continue
        signals.append({
            "date": dates[i],
            "position": pos,
            "regime": regimes[i] if i < len(regimes) else '',
            "gold_price": gold_prices[i] if i < len(gold_prices) else None,
            "prob": probs[i] if i < len(probs) else None,
        })
        if len(signals) >= limit:
            break
    return {"signals": signals, "count": len(signals)}


# === SQLite 历史信号查询 (I) ===

@app.post("/api/db/ingest")
async def db_ingest():
    """把当前 dashboard_data + execution_data 写入 SQLite
    V5 脚本跑完后调用此接口持久化本次信号"""
    _refresh_cache()
    if not _dashboard_cache:
        raise HTTPException(500, "dashboard data not loaded")
    try:
        db.init()
        sid = db.insert_signal(_dashboard_cache, _execution_cache)
        return {"signal_id": sid, "ingested_at": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(500, f"ingest failed: {e}")

@app.get("/api/db/history")
async def db_history(
    days: int = Query(30, ge=1, le=3650),
    regime: Optional[str] = Query(None),
    action: Optional[str] = Query(None)
):
    """从 SQLite 查询最近 N 天的信号历史（支持 regime/action 过滤）"""
    db.init()
    rows = db.query_history(days=days, regime=regime, action=action)
    return {
        "count": len(rows),
        "days": days,
        "filter": {"regime": regime, "action": action},
        "data": rows
    }

@app.get("/api/db/alerts")
async def db_alerts(days: int = Query(30, ge=1, le=365), alert_type: Optional[str] = Query(None)):
    """查询 SQLite 中的历史告警"""
    db.init()
    rows = db.query_alerts(days=days, alert_type=alert_type)
    return {"count": len(rows), "data": rows}

@app.get("/api/db/stats")
async def db_stats():
    """SQLite 数据库统计"""
    db.init()
    return db.stats()


# === F: 多标的简化版数据 (白银/铜/BTC) ===

SYMBOL_CONFIG = {
    'GOLD':   {'yf': 'GC=F', 'name': '黄金期货',     'color': '#ffb020'},
    'SILVER': {'yf': 'SI=F', 'name': '白银期货',     'color': '#c0c0c0'},
    'COPPER': {'yf': 'HG=F', 'name': '铜期货',       'color': '#b87333'},
    'BTC':    {'yf': 'BTC-USD', 'name': '比特币',    'color': '#f7931a'}
}

@app.get("/api/symbol/{symbol}")
async def get_symbol_data(symbol: str, days: int = Query(250, ge=30, le=1000)):
    """获取指定标的的简化版数据（价格+MA+Regime）
    GOLD 走完整 V5 数据，其他从 yfinance 实时拉取"""
    sym = symbol.upper()
    if sym not in SYMBOL_CONFIG:
        raise HTTPException(404, f"unknown symbol: {symbol}")
    cfg = SYMBOL_CONFIG[sym]

    # GOLD 直接返回完整 dashboard_data
    if sym == 'GOLD':
        _refresh_cache()
        return {
            "symbol": "GOLD",
            "name": cfg['name'],
            "color": cfg['color'],
            "data_source": "v5_full",
            "overview": _dashboard_cache.get('overview', {}),
            "strategies": _dashboard_cache.get('strategies', []),
            "raw_data": _dashboard_cache.get('raw_data', [])[:days]
        }

    # 其他标的：yfinance 实时拉
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        raise HTTPException(500, "yfinance not installed on server")

    try:
        ticker = yf.Ticker(cfg['yf'])
        hist = ticker.history(period=f"{days + 60}d")  # 多拉60天用于算MA
        if hist.empty:
            raise HTTPException(500, f"yfinance returned empty for {cfg['yf']}")

        # 处理列名
        if isinstance(hist.columns, pd.MultiIndex):
            closes = hist['Close'].iloc[:, 0] if 'Close' in hist.columns else hist.iloc[:, -1]
        else:
            closes = hist['Close'] if 'Close' in hist.columns else hist.iloc[:, -1]

        # 构造 raw_data（与 GOLD 格式对齐）
        raw = []
        prices = []
        for i, (date, close) in enumerate(closes.items()):
            if i >= days:
                break
            prices.append(float(close))
            raw.append({
                "日期": date.strftime("%Y-%m-%d"),
                "金价": f"{close:.4f}",
                # 后续字段填充
            })

        # 反转为升序（早→晚）
        prices.reverse()
        raw.reverse()

        # 计算MA50/200 + Regime
        def ma(p, n):
            r = []
            for i in range(len(p)):
                if i < n - 1:
                    r.append(None)
                    continue
                r.append(sum(p[i-n+1:i+1]) / n)
            return r

        ma50 = ma(prices, 50)
        ma200 = ma(prices, 200)
        for i, r in enumerate(raw):
            r['MA50'] = f"{ma50[i]:.4f}" if ma50[i] else ''
            r['MA200'] = f"{ma200[i]:.4f}" if ma200[i] else ''
            # Regime: 牛市(>MA200 5%+) / 熊市(<MA200 5%+) / 震荡
            if ma200[i] and prices[i] > ma200[i] * 1.05:
                r['Regime'] = '牛市'
            elif ma200[i] and prices[i] < ma200[i] * 0.95:
                r['Regime'] = '熊市'
            else:
                r['Regime'] = '震荡'
            r['20日波动率'] = f"{(prices[max(0,i-20):i+1] and __import__('numpy').std(prices[max(0,i-20):i+1]) / max(1e-9, __import__('numpy').mean(prices[max(0,i-20):i+1])) if i > 0 else 0):.4f}"

        last_price = prices[-1] if prices else 0
        last_regime = raw[-1]['Regime'] if raw else '--'
        last_ma50 = ma50[-1] if ma50[-1] else 0
        last_ma200 = ma200[-1] if ma200[-1] else 0

        overview = {
            "预测基准日": raw[-1]['日期'] if raw else '--',
            "当前金价": f"${last_price:.2f}",
            "MA50": f"${last_ma50:.2f}" if last_ma50 else '--',
            "MA200": f"${last_ma200:.2f}" if last_ma200 else '--',
            "当前Regime": last_regime,
            "60日波动率": '--',
            "建议操作": "数据未接入V5模型" if sym != 'GOLD' else '空仓观望',
            "加权集成概率": 'N/A',
        }

        return {
            "symbol": sym,
            "name": cfg['name'],
            "color": cfg['color'],
            "data_source": "yfinance_realtime",
            "ticker": cfg['yf'],
            "overview": overview,
            "strategies": [],
            "raw_data": raw,
            "note": f"{sym} 数据来自 yfinance 实时拉取，仅含价格+MA+Regime，未跑V5多因子模型"
        }
    except Exception as e:
        raise HTTPException(500, f"fetch {sym} failed: {e}")


@app.get("/api/symbols")
async def list_symbols():
    """列出所有可用标的"""
    return {"symbols": [{"key": k, **v} for k, v in SYMBOL_CONFIG.items()]}


# === M: PDF 周报一键生成 ===

@app.get("/api/report/weekly")
async def generate_weekly_report():
    """生成 PDF 周报，返回文件路径。生产环境用：周一 8:30 cron 调用 + 飞书机器人推送"""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'gold_model.weekly_report'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise HTTPException(500, f"report generation failed: {result.stderr}")
        # 解析输出获取 PDF 路径
        output = result.stdout
        path = None
        for line in output.split('\n'):
            if '[weekly] PDF saved:' in line:
                path = line.split('saved: ')[1].strip()
                break
        if not path:
            path = str(WEEKLY_REPORTS_DIR / f"gold_weekly_{datetime.now().strftime('%Y%m%d')}.pdf")
        return {
            "status": "ok",
            "pdf_path": path,
            "generated_at": datetime.now().isoformat(),
            "stdout": output[-200:] if output else ''
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "report generation timeout (60s)")
    except Exception as e:
        raise HTTPException(500, f"report error: {e}")


# === N: 飞书机器人推送 ===

@app.post("/api/push/feishu")
async def push_feishu():
    """推送当日信号到飞书群。
    前置条件：环境变量 FEISHU_WEBHOOK_URL 已配置。
    生产环境用：每天 8:30 cron 调用"""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'gold_model.send_to_feishu'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}
        )
        ok = result.returncode == 0
        return {
            "status": "ok" if ok else "fail",
            "stdout": result.stdout[-300:],
            "stderr": result.stderr[-300:] if result.stderr else '',
            "pushed_at": datetime.now().isoformat()
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "feishu push timeout (30s)")
    except Exception as e:
        raise HTTPException(500, f"push error: {e}")


# === C: 告警多渠道推送 ===

# 内存中的 webhook 订阅列表（重启失效；生产用 SQLite alerts 表）
_webhooks: List[Dict] = []

@app.post("/api/alerts/subscribe")
async def subscribe_alerts(payload: Dict):
    """注册告警 webhook URL。
    payload: {"url": "https://...", "events": ["hit_rate","regime_shift",...], "name": "my-bot"}
    当 drift_monitor 检测到对应事件时，POST 到 url"""
    url = payload.get('url')
    if not url:
        raise HTTPException(400, "url required")
    sub = {
        "url": url,
        "events": payload.get('events', ['*']),
        "name": payload.get('name', 'unnamed'),
        "created_at": datetime.now().isoformat()
    }
    _webhooks.append(sub)
    return {"status": "ok", "subscription": sub, "total_subscribers": len(_webhooks)}

@app.get("/api/alerts/subscribers")
async def list_subscribers():
    return {"subscribers": _webhooks, "total": len(_webhooks)}

@app.delete("/api/alerts/subscribe")
async def unsubscribe_alerts(url: str):
    global _webhooks
    before = len(_webhooks)
    _webhooks = [w for w in _webhooks if w['url'] != url]
    return {"status": "ok", "removed": before - len(_webhooks)}

async def _notify_webhooks(alert: Dict):
    """告警事件触发时调用——通知所有匹配的订阅者"""
    if not _webhooks:
        return
    import urllib.request
    for sub in _webhooks:
        if '*' in sub['events'] or alert.get('type') in sub['events']:
            try:
                req = urllib.request.Request(
                    sub['url'],
                    data=json.dumps({"alert": alert, "subscriber": sub['name']}).encode(),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                print(f"[webhook] notify {sub['name']} failed: {e}")


# === R: V5 脚本参数调优 ===

from pydantic import BaseModel

class V5TuningParams(BaseModel):
    train_window: int = 500          # 训练窗口（日）——主管道 V5_TRAIN_WINDOW 支持
    purge_gap: int = 60              # Purged K-fold gap——主管道 V5_PURGE_GAP 支持(默认60无泄漏)

@app.post("/api/v5/run")
async def run_v5_with_params(params: V5TuningParams):
    """以指定参数跑 V5 脚本。
    注意：V5 脚本运行时间约 3-5 分钟，请耐心等待。
    返回运行日志 + 关键指标。"""
    try:
        import subprocess
        # 只传主管道真正读取的环境变量(修复:原6个参数仅V5_PURGE_GAP生效,其余5个主管道硬编码)
        env = {
            **os.environ,
            'V5_TRAIN_WINDOW': str(params.train_window),
            'V5_PURGE_GAP': str(params.purge_gap),
        }
        result = subprocess.run(
            [sys.executable, '-m', 'gold_model.gold_factor_v5'],
            capture_output=True, text=True, timeout=600,
            env=env
        )
        # 提取关键指标
        output = result.stdout
        metrics = {}
        for line in output.split('\n'):
            if '最优夏普' in line or 'Sharpe' in line:
                metrics['sharpe_line'] = line.strip()
            if '当前金价' in line:
                metrics['gold_price'] = line.strip()
            if '加权集成' in line:
                metrics['weighted_prob'] = line.strip()
            if 'Regime' in line and '熊' in line or '牛' in line or '震荡' in line:
                metrics['regime'] = line.strip()
        return {
            "status": "ok" if result.returncode == 0 else "fail",
            "params": params.dict(),
            "metrics": metrics,
            "stdout_tail": output[-1500:],
            "stderr_tail": result.stderr[-500:] if result.stderr else '',
            "ran_at": datetime.now().isoformat(),
            "duration_note": "V5 脚本约需 3-5 分钟"
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "V5 run timeout (600s). 脚本可能卡在 yfinance 网络请求")
    except Exception as e:
        raise HTTPException(500, f"v5 run error: {e}")


# === WebSocket 实时推送 ===

class ConnectionManager:
    """WebSocket 连接管理器"""
    def __init__(self):
        self.active: List[WebSocket] = []
    
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] connected, total: {len(self.active)}")
    
    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        print(f"[WS] disconnected, total: {len(self.active)}")
    
    async def broadcast(self, message: Dict):
        """向所有连接广播消息"""
        if not self.active:
            return
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 实时推送端点
    
    推送事件类型：
    - state_update: JSON 文件变更时推送全量状态
    - price_tick: 模拟金价 tick 推送（开发模式）
    - heartbeat: 30s 心跳
    """
    await manager.connect(ws)
    try:
        # 首次连接推送当前状态
        _refresh_cache()
        await ws.send_json({
            "type": "state_update",
            "data": {
                "dashboard": _dashboard_cache,
                "execution": _execution_cache
            },
            "timestamp": datetime.now().isoformat()
        })
        
        # 进入消息循环
        while True:
            # 接收客户端消息（如订阅/退订）
            msg = await ws.receive_text()
            try:
                req = json.loads(msg)
                if req.get("action") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "invalid json"})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        print(f"[WS] error: {e}")
        manager.disconnect(ws)

async def file_watcher():
    """后台任务：监听 JSON 文件变更，变更时广播"""
    while True:
        await asyncio.sleep(2)
        try:
            dm = _file_mtime(DASHBOARD_JSON)
            em = _file_mtime(EXECUTION_JSON)
            if dm != _last_dashboard_mtime or em != _last_execution_mtime:
                _refresh_cache()
                await manager.broadcast({
                    "type": "state_update",
                    "data": {
                        "dashboard": _dashboard_cache,
                        "execution": _execution_cache
                    },
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            print(f"[watcher] error: {e}")

@app.on_event("startup")
async def startup_event():
    """启动时初始化缓存 + 启动文件监听"""
    _refresh_cache()
    asyncio.create_task(file_watcher())
    print(f"[API] started, dashboard_loaded={bool(_dashboard_cache)}")

# === 静态文件托管（生产环境可选用）===
from fastapi.responses import FileResponse

@app.get("/")
async def root():
    """根路径返回 dist/index.html（生产部署用）"""
    idx = WEB_DIR / 'dashboard-vue3.html'
    if idx.exists():
        return FileResponse(idx)
    return {"message": "GOLD COMMAND V6 API", "docs": "/docs"}

@app.get("/{file_path:path}")
async def static_files(file_path: str):
    """托管 web/ 下的静态文件（dashboard_data.json、manifest.json、sw.js 等）
    前端轮询的 JSON 走这里，避免 404 噪音"""
    if not file_path or file_path.startswith('api/') or file_path == 'ws':
        raise HTTPException(404, "Not Found")
    base = WEB_DIR.resolve()
    candidate = (base / file_path).resolve()
    if candidate.is_file() and str(candidate).startswith(str(base)):
        return FileResponse(candidate)
    raise HTTPException(404, "Not Found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
