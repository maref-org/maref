#!/bin/bash
# MAREF v15 Autonomous Loop Auditor
#
# 每 5 分钟审计 v15 自治循环的运行状态，检测异常并发出 macOS 通知。
#
# 检测的异常:
#   1. 进程崩溃 (PID 55803 不存在)
#   2. 诊断阶段卡顿 (>25 分钟无 Fix 22b/22c/23 日志)
#   3. 循环失败连续累积 (consecutive_failures >= 3)
#   4. ruff 错误回弹 (>50 新增)
#   5. Fix 23 是否活跃 (LLM ruff proposal 产出率)
#
# 正常状态静默退出; 异常时调用 osascript 发系统通知 + 写告警日志。

set -u

PROJECT_DIR="/Volumes/1TB-M2/public/maref"
LOG_FILE="$PROJECT_DIR/reports/audit_v15.log"
ALERT_LOG="$PROJECT_DIR/reports/audit_v15_alerts.log"
V15_LOG="$PROJECT_DIR/reports/autonomous_48h_v15.log"
V15_PID=55803

# Diagnosis 阶段超时阈值 (秒) — 基于 v14 实测 ~18m, +40% = 25m
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
    osascript -e "display notification \"$message\" with title \"MAREF v15 Audit [$severity]\" subtitle \"$(date '+%H:%M:%S')\"" 2>/dev/null || true
}

log "===== audit start ====="

# ── Check 1: 进程是否存在 ──
if ! ps -p "$V15_PID" > /dev/null 2>&1; then
    alert "CRITICAL" "v15 process (PID $V15_PID) is NOT running — loop has crashed"
    log "===== audit end (crash detected) ====="
    exit 1
fi
log "PID $V15_PID alive (CPU: $(ps -p $V15_PID -o %cpu= 2>/dev/null | tr -d ' ')% )"

# ── Check 2: 当前 cycle 阶段 & 诊断卡顿 ──
V15_LOG="$PROJECT_DIR/reports/autonomous_48h_v15.log"
if [ ! -f "$V15_LOG" ]; then
    log "v15 log not yet created (startup in progress)"
    log "===== audit end (no log) ====="
    exit 0
fi

current_cycle_line=$(grep "Starting cycle-" "$V15_LOG" | tail -1)
if [ -z "$current_cycle_line" ]; then
    log "no cycle start line found yet"
    log "===== audit end (no cycle) ====="
    exit 0
fi
current_cycle=$(echo "$current_cycle_line" | grep -oE 'cycle-[0-9]+')
cycle_start_ts=$(date -j -f "%Y-%m-%d %H:%M:%S" "$(echo "$current_cycle_line" | awk '{print $1, $2}')" +%s 2>/dev/null || echo 0)
now_ts=$(date +%s)
elapsed=$((now_ts - cycle_start_ts))

log "current cycle: $current_cycle, elapsed: ${elapsed}s"

# 检查 Fix 22b 是否在当前 cycle 内出现
cycle_lines=$(awk "/Starting $current_cycle/,0" "$V15_LOG")
if echo "$cycle_lines" | grep -q "Fix 22b: injected"; then
    log "Fix 22b already triggered in $current_cycle — diagnosis done"
else
    if [ "$elapsed" -gt "$DIAG_TIMEOUT_SEC" ]; then
        alert "WARNING" "$current_cycle diagnosis stage stuck for ${elapsed}s (>${DIAG_TIMEOUT_SEC}s threshold) — possible hang"
    else
        log "$current_cycle diagnosis in progress (${elapsed}s / ${DIAG_TIMEOUT_SEC}s)"
    fi
fi

# ── Fix 23 活跃度监测 ──
if echo "$cycle_lines" | grep -q "Fix 23: LLM ruff fix for"; then
    log "Fix 23 active in $current_cycle — LLM ruff proposal deployed"
elif echo "$cycle_lines" | grep -q "Adopted hypothesis"; then
    # adopted means apply_fn was called — check if it was ruff-related
    if echo "$cycle_lines" | grep -q "ruff"; then
        log "Fix 23 may have contributed to adopted ruff hypothesis"
    fi
fi

# ── Check 3: cumulative failure tracking ──
last_complete=$(grep "Cycle cycle-" "$V15_LOG" | tail -1)
if [ -n "$last_complete" ]; then
    cum=$(echo "$last_complete" | grep -oE 'cumulative: [0-9]+ ok / [0-9]+ fail')
    log "last cycle: $cum"
    fail_count=$(echo "$last_complete" | grep -oE '/ [0-9]+ fail' | grep -oE '[0-9]+')
    if [ -n "$fail_count" ] && [ "$fail_count" -ge 3 ]; then
        alert "CRITICAL" "consecutive failures reached $fail_count — circuit breaker should trip soon"
    fi
fi

# ── Check 4: ruff 错误回弹检测 ──
recent_ruff=$(grep "Fix 22b: injected ruff hypothesis" "$V15_LOG" | tail -3)
if [ -n "$recent_ruff" ]; then
    last_ruff=$(echo "$recent_ruff" | tail -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    prev_ruff=$(echo "$recent_ruff" | head -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    if [ -n "$last_ruff" ] && [ -n "$prev_ruff" ]; then
        log "ruff trajectory: prev=$prev_ruff → last=$last_ruff"
        rebound=$((last_ruff - prev_ruff))
        if [ "$rebound" -gt 50 ]; then
            alert "WARNING" "ruff error rebound: +$rebound (prev=$prev_ruff → now=$last_ruff) — possible regression from LLM edits"
        fi
    fi
fi

log "===== audit end (healthy) ====="
exit 0
