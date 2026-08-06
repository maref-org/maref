#!/bin/bash
# MAREF 定期内存监控脚本 - 由 launchd 调用

PROJECT_DIR="$PROJECT_ROOT/maref-experiments"
MONITOR_SCRIPT="$PROJECT_DIR/scripts/memory_monitor.py"
LOG_FILE="$PROJECT_DIR/scripts/memory_monitor_cron.log"

# 记录执行时间
echo "========================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 定期内存监控执行" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 执行一次性检查
cd "$PROJECT_DIR" && python3 "$MONITOR_SCRIPT" --once >> "$LOG_FILE" 2>&1

# 如果内存使用率超过90%，执行紧急清理
MEMORY_USAGE=$(python3 "$MONITOR_SCRIPT" --once 2>/dev/null | grep "内存使用" | grep -oP '[0-9]+\.?[0-9]*' | head -1)
if [ -n "$MEMORY_USAGE" ]; then
    INTEGER_PART=${MEMORY_USAGE%%.*}
    if [ "$INTEGER_PART" -ge 90 ] 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  内存使用率 ${MEMORY_USAGE}% >= 90%，执行紧急清理" >> "$LOG_FILE"
        bash "$PROJECT_DIR/scripts/emergency_cleanup.sh" >> "$LOG_FILE" 2>&1
    fi
fi

echo "" >> "$LOG_FILE"
