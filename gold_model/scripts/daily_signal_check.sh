#!/bin/bash
# 黄金V4 每日信号检测：主管道 → 信号告警 → macOS 通知
# 由 launchd 定时调用（周二~六 22:30），也可手动执行
set -u

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_$(date +%Y%m%d).log"

# 优先用项目 venv（依赖装在这里），否则回退系统 python3
PY="$PROJECT_DIR/.venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"
export PYTHONPATH="$PROJECT_DIR/src"

{
  echo "===== $(date '+%F %T') 开始 (python: $PY) ====="

  "$PY" -m gold_model.gold_factor_v4
  echo "主管道退出码: $?"

  ALERT_OUT="$("$PY" -m gold_model.signal_alert 2>&1)"
  ALERT_RC=$?
  echo "$ALERT_OUT"
  echo "signal_alert退出码: $ALERT_RC"

  if [ "$ALERT_RC" -eq 1 ]; then
    DETAIL="$(echo "$ALERT_OUT" | grep -m1 -E '🔴|🟠|🟡' | cut -c1-80)"
    /usr/bin/osascript -e "display notification \"${DETAIL:-检测到异常信号，详见日志}\" with title \"黄金V4信号告警\" sound name \"Glass\"" || true
  fi

  echo "===== $(date '+%F %T') 结束 ====="
} >> "$LOG" 2>&1

exit 0
