#!/bin/bash
# 安装 launchd 定时任务：把当前项目路径注入 plist 模板并加载
# 用法: bash scripts/install_launchd.sh   （卸载: bash scripts/install_launchd.sh --uninstall）
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$PROJECT_DIR/scripts/com.goldmodel.daily-signal.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.goldmodel.daily-signal.plist"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "已卸载: $PLIST_DST"
  exit 0
fi

sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"
echo "已安装并加载: $PLIST_DST（周二~六 22:30 自动运行）"
