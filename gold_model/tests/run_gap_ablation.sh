#!/usr/bin/env bash
# V5.3 GAP 消融实验：GAP=10(历史值, 60日标签有50天泄漏) vs GAP=60(无泄漏)
# 连续跑两次主管道，抓 WF IC / Holdout 夏普 / 最优策略 对比
# 用法: bash tests/run_gap_ablation.sh
set -u
cd "$(dirname "$0")/.."
PY=".venv/bin/python3"
export PYTHONPATH=src

echo "===== [1/2] GAP=10 (基线, 历史默认, 60日标签有泄漏) ====="
V5_PURGE_GAP=10 V5_FEATURE_BLACKLIST=1 V5_REGRESSION_ADJUST=0 V5_SAMPLE_AUGMENT=0 V5_LABEL_MODE=abs \
  "$PY" -m gold_model.gold_factor_v5 > tests/_gap10.log 2>&1
echo "GAP=10 done (exit=$?)"

echo "===== [2/2] GAP=60 (修复, 无标签泄漏) ====="
V5_PURGE_GAP=60 V5_FEATURE_BLACKLIST=1 V5_REGRESSION_ADJUST=0 V5_SAMPLE_AUGMENT=0 V5_LABEL_MODE=abs \
  "$PY" -m gold_model.gold_factor_v5 > tests/_gap60.log 2>&1
echo "GAP=60 done (exit=$?)"

echo "===== 对比表 ====="
for tag in gap10 gap60; do
  f="tests/_${tag}.log"
  echo "--- $tag ---"
  grep -E "日预测: 准确率" "$f" | sed 's/^[[:space:]]*//'
  grep -E "IC自适应权重" "$f" | sed 's/^[[:space:]]*//'
  grep -E "Holdout\(6m\)" "$f" | sed 's/^[[:space:]]*//'
  grep -E "最优策略.*夏普|夏普: " "$f" | tail -3 | sed 's/^[[:space:]]*//'
done
echo "===== 完成 ====="
