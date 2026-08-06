#!/bin/bash
# MAREF v17 Autonomous Loop Auditor
set -u

PROJECT_DIR="$PROJECT_ROOT"
LOG_FILE="$PROJECT_DIR/reports/audit_v17.log"
ALERT_LOG="$PROJECT_DIR/reports/audit_v17_alerts.log"
V17_LOG="$PROJECT_DIR/reports/autonomous_48h_v17.log"
V17_PID=14129
DIAG_TIMEOUT_SEC=1500

mkdir -p "$PROJECT_DIR/reports"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }
alert() {
    local s="$1" m="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$s] $m" >> "$ALERT_LOG"
    log "ALERT [$s]: $m"
    osascript -e "display notification \"$m\" with title \"MAREF v17 Audit [$s]\" subtitle \"$(date '+%H:%M:%S')\"" 2>/dev/null || true
}

log "===== audit start ====="
ps -p "$V17_PID" > /dev/null 2>&1 || { alert "CRITICAL" "v17 PID $V17_PID DEAD"; exit 1; }
log "PID $V17_PID alive"
[ ! -f "$V17_LOG" ] && { log "no log yet"; log "===== end ====="; exit 0; }

cline=$(grep "Starting cycle-" "$V17_LOG" | tail -1)
[ -z "$cline" ] && { log "no cycle"; log "===== end ====="; exit 0; }
cycle=$(echo "$cline" | grep -oE 'cycle-[0-9]+')
ts=$(date -j -f "%Y-%m-%d %H:%M:%S" "$(echo "$cline" | awk '{print $1,$2}')" +%s 2>/dev/null || echo 0)
elapsed=$(( $(date +%s) - ts ))
log "$cycle elapsed: ${elapsed}s"

cyc_lines=$(awk "/Starting $cycle/,0" "$V17_LOG")
echo "$cyc_lines" | grep -q "Fix 22b:" && log "diagnosis done"
echo "$cyc_lines" | grep -q "Fix 23:" && log "Fix 23 fired"
echo "$cyc_lines" | grep -q "Adopted hypothesis" && log "ADOPTED! 🎉"
echo "$cyc_lines" | grep -q "200 OK" && log "DeepSeek 200 OK"

lc=$(grep "Cycle cycle-" "$V17_LOG" | tail -1)
[ -n "$lc" ] && log "$(echo "$lc" | grep -oE 'cumulative: [0-9]+ ok / [0-9]+ fail')"

rr=$(grep "Fix 22b:" "$V17_LOG" | tail -3)
[ -n "$rr" ] && {
    lr=$(echo "$rr" | tail -1 | grep -oE '\([0-9]+' | grep -oE '[0-9]+')
    pr=$(echo "$rr" | head -1 | grep -oE '\([0-9]+' | grep -oE '[0-9]+')
    [ -n "$lr" ] && [ -n "$pr" ] && log "ruff: ${pr}ev → ${lr}ev"
}

log "===== end (healthy) ====="
exit 0
