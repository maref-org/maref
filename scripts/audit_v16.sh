#!/bin/bash
# MAREF v16 Autonomous Loop Auditor
#
# 每 5 分钟审计 v16 自治循环的运行状态，检测异常并发出通知。
# 检测: 进程崩溃、诊断卡顿、失败累积、ruff 回弹、Fix 23 活跃度

set -u

PROJECT_DIR="/Volumes/1TB-M2/public/maref"
LOG_FILE="$PROJECT_DIR/reports/audit_v16.log"
ALERT_LOG="$PROJECT_DIR/reports/audit_v16_alerts.log"
V16_LOG="$PROJECT_DIR/reports/autonomous_48h_v16.log"
V16_PID=34510
DIAG_TIMEOUT_SEC=1500

mkdir -p "$PROJECT_DIR/reports"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

alert() {
    local severity="$1" message="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$severity] $message" >> "$ALERT_LOG"
    log "ALERT [$severity]: $message"
    osascript -e "display notification \"$message\" with title \"MAREF v16 Audit [$severity]\" subtitle \"$(date '+%H:%M:%S')\"" 2>/dev/null || true
}

log "===== audit start ====="

# Check 1: process alive
if ! ps -p "$V16_PID" > /dev/null 2>&1; then
    alert "CRITICAL" "v16 process (PID $V16_PID) is NOT running"
    log "===== audit end (crash) ====="; exit 1
fi
cpu=$(ps -p $V16_PID -o %cpu= 2>/dev/null | tr -d ' ')
log "PID $V16_PID alive (CPU: ${cpu:-?}%)"

# Check 2: cycle progress
[ ! -f "$V16_LOG" ] && { log "no log yet"; log "===== audit end ====="; exit 0; }

cline=$(grep "Starting cycle-" "$V16_LOG" | tail -1)
[ -z "$cline" ] && { log "no cycle found"; log "===== audit end ====="; exit 0; }
cycle=$(echo "$cline" | grep -oE 'cycle-[0-9]+')
ts=$(date -j -f "%Y-%m-%d %H:%M:%S" "$(echo "$cline" | awk '{print $1,$2}')" +%s 2>/dev/null || echo 0)
elapsed=$(( $(date +%s) - ts ))
log "current: $cycle, elapsed: ${elapsed}s"

cyc_lines=$(awk "/Starting $cycle/,0" "$V16_LOG")
if echo "$cyc_lines" | grep -q "Fix 22b:"; then
    log "diagnosis done in $cycle"
else
    [ "$elapsed" -gt "$DIAG_TIMEOUT_SEC" ] && \
        alert "WARNING" "$cycle diagnosis stuck ${elapsed}s (threshold ${DIAG_TIMEOUT_SEC}s)"
fi

# Fix 23 activity
echo "$cyc_lines" | grep -q "Fix 23:" && log "Fix 23 active in $cycle"

# Check 3: failures
lc=$(grep "Cycle cycle-" "$V16_LOG" | tail -1)
[ -n "$lc" ] && {
    cum=$(echo "$lc" | grep -oE 'cumulative: [0-9]+ ok / [0-9]+ fail')
    log "last: $cum"
    fail=$(echo "$lc" | grep -oE '/ [0-9]+ fail' | grep -oE '[0-9]+')
    [ -n "$fail" ] && [ "$fail" -ge 3 ] && alert "CRITICAL" "failures=$fail"
}

# Check 4: ruff rebound
rr=$(grep "Fix 22b: injected ruff hypothesis" "$V16_LOG" | tail -3)
[ -n "$rr" ] && {
    lr=$(echo "$rr" | tail -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    pr=$(echo "$rr" | head -1 | grep -oE '\([0-9]+ errors\)' | grep -oE '[0-9]+')
    [ -n "$lr" ] && [ -n "$pr" ] && {
        log "ruff: $pr → $lr"
        [ $((lr - pr)) -gt 50 ] && alert "WARNING" "ruff rebound +$((lr - pr)) ($pr→$lr)"
    }
}

log "===== audit end (healthy) ====="
exit 0
