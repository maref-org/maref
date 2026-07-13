#!/bin/bash
# MAREF v14 Autonomous Loop Auditor
#
# 定期审计 v14 自治循环的运行状态，检测异常并发出 macOS 通知。
# 由 launchd 或 cron 调用，建议每 5 分钟执行一次。
#
# 检测的异常:
#   1. 进程崩溃 (PID 78986 不存在)
#   2. 诊断阶段卡顿 (>25 分钟无 Fix 22b/22c 日志)
#   3. 循环失败连续累积 (consecutive_failures >= 3)
#   4. ruff 错误回弹 (上次修复后本 cycle 又出现 >50 个新 ruff 错误 → 可能引入回归)
#
# 正常状态静默退出; 异常时调用 osascript 发系统通知 + 写告警日志。

set -u

PROJECT_DIR="/Volumes/1TB-M2/public/maref"
LOG_FILE="$PROJECT_DIR/reports/audit_v14.log"
ALERT_LOG="$PROJECT_DIR/reports/audit_v14_alerts.log"
V14_LOG="$PROJECT_DIR/reports/autonomous_48h_v14.log"
V14_PID=78986

# Diagnosis 阶段超时阈值 (秒) — 基于 v14 Cycle 1/2 实测 18m, +40% 缓冲 = 25m
DIAG_TIMEOUT_SEC=1500

mkdir -p "$PROJECT_DIR/reports"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

alert() {
    local severity="$1"
    local message="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$severity] $message" >> "$ALERT_LOG"
    log "ALERT [$severity]: $message"
    # macOS 系统通知 (失败也不中断审计)
    osascript -e "display notification \"$message\" with title \"MAREF v14 Audit [$severity]\" subtitle \"$(date '+%H:%M:%S')\"" 2>/dev/null || true
}

log "===== audit start ====="

# ── Check 1: 进程是否存在 ──
if ! ps -p "$V14_PID" > /dev/null 2>&1; then
    alert "CRITICAL" "v14 process (PID $V14_PID) is NOT running — loop has crashed"
    log "===== audit end (crash detected) ====="
    exit 1
fi
log "PID $V14_PID alive (CPU: $(ps -p $V14_PID -o %cpu= 2>/dev/null | tr -d ' ')% )"

# ── Check 2: 当前 cycle 阶段 & 诊断卡顿 ──
if [ ! -f "$V14_LOG" ]; then
    alert "WARNING" "v14 log file missing: $V14_LOG"
    log "===== audit end (no log) ====="
    exit 0
fi

# 提取当前 cycle 启动时间 (最后一个 "Starting cycle-NNNN" 行)
current_cycle_line=$(grep "Starting cycle-" "$V14_LOG" | tail -1)
if [ -z "$current_cycle_line" ]; then
    alert "WARNING" "no cycle start line found in v14 log"
    log "===== audit end (no cycle) ====="
    exit 0
fi
current_cycle=$(echo "$current_cycle_line" | grep -oE 'cycle-[0-9]+')
cycle_start_ts=$(date -j -f "%Y-%m-%d %H:%M:%S" "$(echo "$current_cycle_line" | awk '{print $1, $2}')" +%s 2>/dev/null || echo 0)
now_ts=$(date +%s)
elapsed=$((now_ts - cycle_start_ts))
log "current cycle: $current_cycle, elapsed: ${elapsed}s"

# 检查 Fix 22b 是否在当前 cycle 内出现
cycle_lines=$(awk "/Starting $current_cycle/,0" "$V14_LOG")
if echo "$cycle_lines" | grep -q "Fix 22b: injected"; then
    log "Fix 22b already triggered in $current_cycle — diagnosis done"
else
    # 诊断阶段尚未完成 → 检查是否超时
    if [ "$elapsed" -gt "$DIAG_TIMEOUT_SEC" ]; then
        alert "WARNING" "$current_cycle diagnosis stage stuck for ${elapsed}s (>${DIAG_TIMEOUT_SEC}s threshold) — possible hang"
    else
        log "$current_cycle diagnosis in progress (${elapsed}s / ${DIAG_TIMEOUT_SEC}s)"
    fi
fi

# ── Check 3: cumulative failure tracking ──
# 从 cycle 结束日志提取 cumulative: N ok / M fail
last_complete=$(grep "Cycle cycle-" "$V14_LOG" | tail -1)
if [ -n "$last_complete" ]; then
    cum=$(echo "$last_complete" | grep -oE 'cumulative: [0-9]+ ok / [0-9]+ fail')
    log "last cycle: $cum"
    # 提取 fail 数
    fail_count=$(echo "$last_complete" | grep -oE '/ [0-9]+ fail' | grep -oE '[0-9]+')
    if [ -n "$fail_count" ] && [ "$fail_count" -ge 3 ]; then
        alert "CRITICAL" "consecutive failures reached $fail_count — circuit breaker should trip soon"
    fi
fi

# ── Check 4: ruff 错误回弹检测 (潜在回归) ──
# 对比最近两个 cycle 的 ruff 错误数
recent_ruff=$(grep "Fix 22b: injected ruff hypothesis" "$V14_LOG" | tail -3)
if [ -n "$recent_ruff" ]; then
    last_ruff=$(echo "$recent_ruff" | tail -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    prev_ruff=$(echo "$recent_ruff" | head -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    if [ -n "$last_ruff" ] && [ -n "$prev_ruff" ]; then
        log "ruff trajectory: prev=$prev_ruff → last=$last_ruff"
        # 如果本 cycle ruff 错误比上 cycle 多 50+ → 回归
        rebound=$((last_ruff - prev_ruff))
        if [ "$rebound" -gt 50 ]; then
            alert "WARNING" "ruff error rebound: +$rebound (prev=$prev_ruff → now=$last_ruff) — possible regression from LLM edits"
        fi
    fi
fi

log "===== audit end (healthy) ====="
exit 0
