#!/bin/bash
# GOLD COMMAND V6 — API Server 启动/重启脚本 (macOS 适配版)
# 用法：bash start_api.sh [start|stop|restart|status]
# 默认：start（如已运行则跳过）

cd "$(dirname "$0")/.."

PORT=8000
PID_FILE=/tmp/gold_api_server.pid
LOG_FILE=/tmp/gold_api_server.log

cmd="${1:-start}"

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    # fallback：查进程
    if pgrep -f "gold_model.api_server" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        pgrep -f "gold_model.api_server" | head -1
    fi
}

start() {
    if is_running; then
        echo "[api] already running, pid=$(get_pid)"
        return 0
    fi
    local PY=python3
    if [ -x ".venv/bin/python3" ]; then
        PY=".venv/bin/python3"
    fi
    nohup env PYTHONPATH=src "$PY" -m gold_model.api_server \
        > "$LOG_FILE" 2>&1 < /dev/null &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    sleep 2
    if is_running; then
        echo "[api] started, pid=$pid, log=$LOG_FILE"
    else
        echo "[api] failed to start, check $LOG_FILE"
        tail -20 "$LOG_FILE"
        return 1
    fi
}

stop() {
    if ! is_running; then
        echo "[api] not running"
        rm -f "$PID_FILE"
        return 0
    fi
    local pid=$(get_pid)
    kill "$pid" 2>/dev/null
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$PID_FILE"
    echo "[api] stopped"
}

status() {
    if is_running; then
        echo "[api] running, pid=$(get_pid)"
        if command -v curl >/dev/null; then
            local resp=$(curl -s --max-time 2 "http://localhost:$PORT/api/health")
            echo "[api] health: $resp"
        fi
    else
        echo "[api] not running"
    fi
}

case "$cmd" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "Usage: $0 [start|stop|restart|status]"; exit 1 ;;
esac
