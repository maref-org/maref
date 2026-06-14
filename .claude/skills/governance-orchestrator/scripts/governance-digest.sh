#!/bin/bash
# governance-digest.sh — 生成多 Agent 决策队列 Digest
# 用法: governance-digest.sh [agent-name]
#       不带参数则生成全局 Digest

set -e

GOV_DIR=".governance/queue"
NOW=$(date +%Y%m%d_%H%M)

if [ $# -gt 0 ]; then
  AGENT="$1"
  QUEUE_DIR="$GOV_DIR/$AGENT/pending"
  if [ ! -d "$QUEUE_DIR" ]; then
    echo "Agent '$AGENT' 队列目录不存在"
    exit 1
  fi
  echo "【P1 批量确认 - $AGENT】"
  echo "生成时间: $(date)"
  echo "━━━━━━━━━━━━━━━━━━━━━━"
  for f in "$QUEUE_DIR"/*.json; do
    [ -f "$f" ] || continue
    python3 -c "
import json
d=json.load(open('$f'))
print(f'{d.get(\"id\",\"?\")}')
print(f'  操作: {d.get(\"technical\",\"?\")}')
print(f'  业务影响: {d.get(\"impact\",\"?\")}')
print(f'  回滚: {d.get(\"rollback\",\"?\")}')
print(f'  [同意] [拒绝]')
print()
"
  done
  echo "【一键操作】[全部同意] [全部拒绝]"
else
  echo "=== 全局 Digest $(date) ==="
  echo ""
  for agent_dir in "$GOV_DIR"/*/; do
    agent=$(basename "$agent_dir")
    [ "$agent" = "_global-digest" ] && continue
    pending="$agent_dir/pending"
    count=$(find "$pending" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    echo "Agent: $agent — $count 项待确认"
  done
  echo ""
  echo "使用 governance-digest.sh <agent-name> 查看详情"
fi
