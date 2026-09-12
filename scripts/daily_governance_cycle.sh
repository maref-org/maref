#!/bin/bash
# MAREF 每日治理循环 (Phase Beta B1)
# 每日 UTC 06:00 运行，串联全部治理脚本
# 用法: bash scripts/daily_governance_cycle.sh [--quiet]

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$REPO_ROOT/scripts"
REPORTS="$REPO_ROOT/reports"
LOG_DIR="$REPORTS/daily-logs"
mkdir -p "$LOG_DIR"

TODAY=$(date +%Y-%m-%d)
LOGFILE="$LOG_DIR/governance-cycle-$TODAY.log"
QUIET=false
[ "$1" = "--quiet" ] && QUIET=true

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOGFILE"; }
fail() { log "❌ $1"; echo "❌ $1" >> "$LOG_DIR/failures-$TODAY.log"; }

if $QUIET; then
    exec >> "$LOGFILE" 2>&1
fi

log "========== MAREF 每日治理循环启动 =========="

# Phase 1: 数据闭环
log "Phase 1: 数据闭环"
log "  P0-B 探针采样 (进水口)..."
python3 "$SCRIPTS/probe_sampler.py" >> "$LOGFILE" 2>&1 || fail "P0-B-probe-sampler"

log "  P-02 提案对账..."
python3 "$SCRIPTS/proposal_reconcile.py" >> "$LOGFILE" 2>&1 || fail "P-02"

log "  P-01 翻案抽查..."
python3 "$SCRIPTS/approval_resample.py" >> "$LOGFILE" 2>&1 || fail "P-01"

log "  P-06 置信度实算..."
python3 "$SCRIPTS/confidence_realtime.py" >> "$LOGFILE" 2>&1 || fail "P-06"

log "  P-09 增益口径审计..."
python3 "$SCRIPTS/gain_audit.py" >> "$LOGFILE" 2>&1 || fail "P-09"

# Phase 2: 分析 + 疫苗
log "Phase 2: 分析 + 疫苗"
log "  P-03 审批分层..."
python3 "$SCRIPTS/approval_tier.py" >> "$LOGFILE" 2>&1 || fail "P-03"

log "  P-05 权重分级..."
python3 "$SCRIPTS/domain_weight.py" >> "$LOGFILE" 2>&1 || fail "P-05"

log "  P-07 疫苗管线..."
python3 "$SCRIPTS/vaccine_pipeline/01_extract_patterns.py" >> "$LOGFILE" 2>&1 || fail "P-07-extract"
python3 "$SCRIPTS/vaccine_pipeline/04_compile_vaccines.py" >> "$LOGFILE" 2>&1 || fail "P-07-compile"

# Phase 3: 检测 + SLA
log "Phase 3: 检测 + SLA"
log "  P-04 僵死检测..."
python3 "$SCRIPTS/zombie_agent_escalation.py" >> "$LOGFILE" 2>&1 || fail "P-04"

log "  P-08 SLA 治理..."
python3 "$SCRIPTS/backlog_sla.py" >> "$LOGFILE" 2>&1 || fail "P-08"

# 辅助检查
log "辅助检查"
log "  探针阈值校准..."
python3 "$SCRIPTS/probe_threshold_calibrate.py" >> "$LOGFILE" 2>&1 || fail "probe-calibrate"

log "  校准状态观察..."
python3 "$SCRIPTS/calibration_status.py" >> "$LOGFILE" 2>&1 || fail "calibration-status"

log "  审计健康检查..."
python3 "$SCRIPTS/audit_health_check.py" >> "$LOGFILE" 2>&1 || fail "audit-health"

log "  进化状态检查..."
python3 "$SCRIPTS/evolution_daemon_status.py" >> "$LOGFILE" 2>&1 || fail "evolution-status"

# 晨报
log "  晨报生成..."
python3 "$SCRIPTS/gen_morning_report.py" >> "$LOGFILE" 2>&1 || fail "morning-report"

# 阈值推送
log "  阈值推送..."
python3 "$SCRIPTS/push_thresholds.py" >> "$LOGFILE" 2>&1 || fail "threshold-push"

# 告警推送
log "  告警推送..."
python3 "$SCRIPTS/push_alerts.py" >> "$LOGFILE" 2>&1 || fail "alert-push"

# 提案对账推送
log "  提案对账推送..."
python3 "$SCRIPTS/push_proposal_reconcile.py" >> "$LOGFILE" 2>&1 || fail "proposal-push"

FAIL_COUNT=$(grep -c "❌" "$LOG_DIR/failures-$TODAY.log" 2>/dev/null || echo 0)
log "========== 治理循环完成 | 失败: $FAIL_COUNT =========="

exit 0