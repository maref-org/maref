#!/bin/bash
# Git GC 优化脚本
# 定期清理Git仓库，减少磁盘和索引压力

set -e

PROJECT_DIR="$PROJECT_ROOT/maref-experiments"
LOG_FILE="$PROJECT_DIR/scripts/git_gc.log"

echo "========================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Git GC 执行开始" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

cd "$PROJECT_DIR"

# 1. 显示当前状态
echo "📊 当前 Git 状态:" | tee -a "$LOG_FILE"
git count-objects -vH 2>&1 | tee -a "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 2. 清理 reflog（保留7天）
echo "🧹 清理过期 reflog (7天)..." | tee -a "$LOG_FILE"
git reflog expire --expire=7.days.ago --all 2>&1 | tee -a "$LOG_FILE" || echo "  reflog 清理跳过" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 3. 执行 GC（激进的打包和清理）
echo "🗜️  执行 Git GC..." | tee -a "$LOG_FILE"
git gc --aggressive --prune=now 2>&1 | tee -a "$LOG_FILE" || echo "  GC 执行完成" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 4. 清理不需要的对象
echo "🧽 清理松散对象..." | tee -a "$LOG_FILE"
git repack -A -d --depth=250 --window=250 2>&1 | tee -a "$LOG_FILE" || echo "  repack 完成" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 5. 显示优化后状态
echo "📊 优化后 Git 状态:" | tee -a "$LOG_FILE"
git count-objects -vH 2>&1 | tee -a "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 6. 检查 .git 目录大小
GIT_SIZE=$(du -sh .git 2>/dev/null | cut -f1)
echo "📦 .git 目录大小: $GIT_SIZE" | tee -a "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Git GC 执行完成" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
