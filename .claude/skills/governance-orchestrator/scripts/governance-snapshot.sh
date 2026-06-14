#!/bin/bash
# governance-snapshot.sh — 创建 git 快照 tag + 检查点
# 用法:
#   governance-snapshot.sh              # 普通快照
#   governance-snapshot.sh checkpoint   # 每日检查点

set -e

ACTION="${1:-snapshot}"
TIMESTAMP=$(date +%Y%m%d-%H%M)

if [ "$ACTION" = "checkpoint" ]; then
  TAG="checkpoint-$(date +%Y%m%d)"
  MSG="每日检查点 $(date)"
else
  TAG="snapshot-$TIMESTAMP"
  MSG="自动快照 $TIMESTAMP"
fi

# 检查是否是 git 仓库
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "❌ 当前目录不是 git 仓库"
  exit 1
fi

# 检查是否有未提交的修改
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "📸 创建快照: $TAG"
  git tag -f "$TAG" HEAD
  echo "✅ 快照已创建: $TAG"
else
  echo "📸 无未提交修改，跳过快照"
fi

# 清理旧快照（保留最近 48 个）
if [ "$ACTION" != "checkpoint" ]; then
  SNAPSHOTS=$(git tag -l 'snapshot-*' | sort -r | tail -n +49)
  if [ -n "$SNAPSHOTS" ]; then
    echo "🧹 清理旧快照..."
    echo "$SNAPSHOTS" | xargs -r git tag -d
  fi
fi
