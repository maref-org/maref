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

# P2-3 双路径收敛：统一运行时审计路径（与 launchd plist 对齐）
# T0-2: 不硬编码机器路径（Leak Detection CI）；解析顺序 env → ~/.maref/runtime_dir.json → repo
if [ -z "${MAREF_RUNTIME_DIR:-}" ] && [ -f "$HOME/.maref/runtime_dir.json" ]; then
    MAREF_RUNTIME_DIR="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("runtime_dir",""))' "$HOME/.maref/runtime_dir.json" 2>/dev/null || true)"
fi
export MAREF_RUNTIME_DIR="${MAREF_RUNTIME_DIR:-$REPO_ROOT}"
export MAREF_AUDIT_PATH="${MAREF_AUDIT_PATH:-$MAREF_RUNTIME_DIR/.governance}"
export MAREF_PROJECT_ROOT="${MAREF_PROJECT_ROOT:-$MAREF_RUNTIME_DIR}"
# Overlay tick 需要完整框架 → 优先 project venv (py3.14)
PY_VENV="$REPO_ROOT/.venv/bin/python3"
if [ -x "$PY_VENV" ]; then
    PY="$PY_VENV"
else
    PY="python3"
fi

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
"$PY" "$SCRIPTS/probe_sampler.py" >> "$LOGFILE" 2>&1 || fail "P0-B-probe-sampler"

# T2-3: 遗留库合并 (PROBE_DB 解析到 RUNTIME 后, REPO 历史库需先并入,
# 否则 confidence/calibrate 读到分裂数据源) + 校准前置 (当日阈值当日用)
log "  T2-3 探针库合并 + 阈值校准..."
"$PY" "$SCRIPTS/probe_db_merge.py" >> "$LOGFILE" 2>&1 || fail "probe-db-merge"
"$PY" "$SCRIPTS/probe_threshold_calibrate.py" >> "$LOGFILE" 2>&1 || fail "probe-calibrate"

log "  P-02 提案对账..."
"$PY" "$SCRIPTS/proposal_reconcile.py" >> "$LOGFILE" 2>&1 || fail "P-02"

log "  P-01 翻案抽查..."
"$PY" "$SCRIPTS/approval_resample.py" >> "$LOGFILE" 2>&1 || fail "P-01"

log "  P-06 置信度实算..."
"$PY" "$SCRIPTS/confidence_realtime.py" >> "$LOGFILE" 2>&1 || fail "P-06"

log "  P-09 增益口径审计..."
"$PY" "$SCRIPTS/gain_audit.py" >> "$LOGFILE" 2>&1 || fail "P-09"

# Phase 2: 分析 + 疫苗
log "Phase 2: 分析 + 疫苗"
log "  P-03 审批分层..."
"$PY" "$SCRIPTS/approval_tier.py" >> "$LOGFILE" 2>&1 || fail "P-03"

log "  P-05 权重分级..."
"$PY" "$SCRIPTS/domain_weight.py" >> "$LOGFILE" 2>&1 || fail "P-05"

log "  Coding Agent 治理注册状态..."
"$PY" "$SCRIPTS/coding_agent_status.py" >> "$LOGFILE" 2>&1 || fail "coding-agent-status"

log "  P-07 疫苗管线..."
"$PY" "$SCRIPTS/vaccine_pipeline/01_extract_patterns.py" >> "$LOGFILE" 2>&1 || fail "P-07-extract"
"$PY" "$SCRIPTS/vaccine_pipeline/04_compile_vaccines.py" >> "$LOGFILE" 2>&1 || fail "P-07-compile"

# Phase 3: 检测 + SLA
log "Phase 3: 检测 + SLA"
log "  P-04 僵死检测..."
"$PY" "$SCRIPTS/zombie_agent_escalation.py" >> "$LOGFILE" 2>&1 || fail "P-04"

log "  P-08 SLA 治理..."
"$PY" "$SCRIPTS/backlog_sla.py" >> "$LOGFILE" 2>&1 || fail "P-08"

# T2-2: 闭环验证依赖 backlog_sla_report (top medium → 提案) 与 coding_agents_status (KPI 证据)
log "  T2-2 治理闭环验证 (提案→部署→观测→固化)..."
"$PY" "$SCRIPTS/governance_loop_validator.py" >> "$LOGFILE" 2>&1 || fail "governance-loop-validator"

# 辅助检查
log "辅助检查"
log "  P2-1/2 RecursiveOverlay 生产 tick (真实 observation)..."
"$PY" "$SCRIPTS/recursive_overlay_tick.py" >> "$LOGFILE" 2>&1 || fail "recursive-overlay-tick"

log "  P1-C 审计生产链心跳..."
"$PY" "$SCRIPTS/audit_heartbeat.py" >> "$LOGFILE" 2>&1 || fail "audit-heartbeat"

log "  校准状态观察..."
"$PY" "$SCRIPTS/calibration_status.py" >> "$LOGFILE" 2>&1 || fail "calibration-status"

log "  校准复核 (对比基线)..."
"$PY" "$SCRIPTS/calibration_review.py" >> "$LOGFILE" 2>&1 || fail "calibration-review"

log "  审计健康检查..."
"$PY" "$SCRIPTS/audit_health_check.py" >> "$LOGFILE" 2>&1 || fail "audit-health"

log "  进化状态检查..."
"$PY" "$SCRIPTS/evolution_daemon_status.py" >> "$LOGFILE" 2>&1 || fail "evolution-status"

# T2-4: 覆盖对账 + 单一自证明报告（晨报 status 与 evidence_gate 依赖其产出）
log "  T2-4 覆盖对账 + 证据报告..."
"$PY" "$SCRIPTS/agent_coverage_reconcile.py" >> "$LOGFILE" 2>&1 || fail "agent-coverage"
"$PY" "$SCRIPTS/gen_evidence_report.py" >> "$LOGFILE" 2>&1 || fail "evidence-report"

# 晨报
log "  晨报生成..."
"$PY" "$SCRIPTS/gen_morning_report.py" >> "$LOGFILE" 2>&1 || fail "morning-report"

# 阈值推送
log "  阈值推送..."
"$PY" "$SCRIPTS/push_thresholds.py" >> "$LOGFILE" 2>&1 || fail "threshold-push"

# 告警推送
log "  告警推送..."
"$PY" "$SCRIPTS/push_alerts.py" >> "$LOGFILE" 2>&1 || fail "alert-push"

# 提案对账推送
log "  提案对账推送..."
"$PY" "$SCRIPTS/push_proposal_reconcile.py" >> "$LOGFILE" 2>&1 || fail "proposal-push"

# T2-4: 统一验收门槛（方案 §6 — 全绿才通过）
log "  T2-4 证据门禁..."
bash "$SCRIPTS/evidence_gate.sh" >> "$LOGFILE" 2>&1 || fail "evidence-gate"

FAIL_COUNT=$(grep -c "❌" "$LOG_DIR/failures-$TODAY.log" 2>/dev/null || echo 0)
log "========== 治理循环完成 | 失败: $FAIL_COUNT =========="

exit 0