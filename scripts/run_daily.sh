#!/bin/bash
#
# MAREF Complete Daily Evolution Runner — 8-phase autonomous closed loop
#
# Phases:
#   0. Environment check (git, venv, API keys)
#   1. Data collection (SelfObserver + RealMetricsCollector)
#   2. Trend analysis (IterationAnalyzer)
#   3. Hypothesis generation (OptimizerEvolutionBridge)
#   4. Constitution review (ConstitutionHarness)
#   5. Experiment execution (RecursiveEvolutionEngine)
#   6. Result persistence (RoundVault + EvolutionVault)
#   7. Next planning (IterationAnalyzer priority)
#
# Optionally runs:
#   - PERCV research (if DASHSCOPE_API_KEY is set)
#   - RSI loop (if run_rsi_loop.sh exists)
#   - MAS-TS evaluation (if mas-ts is available)
#
# Called by: launchd (macOS), cron, or manually.
#
# Usage:
#   ./run_daily.sh                    # Full pipeline
#   ./run_daily.sh --dry-run          # Dry-run only (no writes)
#   ./run_daily.sh --skip-research    # Skip PERCV research
#   ./run_daily.sh --skip-rsi         # Skip RSI loop
#

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
PYTHON="${VENV_PATH}/bin/python"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ── Parse args ──────────────────────────────────────────────────
DRY_RUN="--dry-run"
SKIP_RESEARCH=false
SKIP_RSI=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN="--dry-run" ;;
        --no-dry-run) DRY_RUN="--no-dry-run" ;;
        --skip-research) SKIP_RESEARCH=true ;;
        --skip-rsi) SKIP_RSI=true ;;
    esac
    shift
done

# ── Load .env ───────────────────────────────────────────────────
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a; source "${PROJECT_ROOT}/.env"; set +a
fi

# ── Directories ─────────────────────────────────────────────────
MAILBOX_DIR="${MAREF_MAILBOX_DIR:-${PROJECT_ROOT}/mailbox}"
OUTPUT_DIR="${MAREF_OUTPUT_DIR:-${MAILBOX_DIR}/research_output}"
LOG_DIR="${OUTPUT_DIR}/logs"
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/evolution_${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"; }
run_phase() {
    local phase="$1" label="$2"
    log "── Phase ${phase}: ${label} ──"
}

# ── Pre-flight ──────────────────────────────────────────────────
log "Starting MAREF Daily Evolution (dry-run=${DRY_RUN})"
log "Project: ${PROJECT_ROOT}"
log "Log:     ${LOG_FILE}"

if [[ ! -f "${PYTHON}" ]]; then
    log "ERROR: Virtual environment not found at ${VENV_PATH}"
    exit 78
fi

cd "${PROJECT_ROOT}"

OVERALL_EXIT=0

# ── Phase 0-7: DailyEvolutionLoop (8 phases in one call) ────────
run_phase "0-7" "Daily Evolution Loop"
if "${PYTHON}" -m maref.evolution.daily_loop \
    ${DRY_RUN} \
    --vault "${PROJECT_ROOT}/.evolution_vault" \
    2>&1 | tee -a "${LOG_FILE}"; then
    log "Daily evolution loop completed successfully"
else
    log "Daily evolution loop exited with code $? (non-fatal)"
fi

# ── Phase 8a: PERCV Research (optional) ─────────────────────────
if [[ "${SKIP_RESEARCH}" != "true" && -n "${DASHSCOPE_API_KEY:-}" ]]; then
    run_phase "8a" "PERCV AutoResearch"
    if "${PYTHON}" -m src.research.continuous_engine \
        --output-dir "${OUTPUT_DIR}" \
        --experiments-per-batch 50 \
        --batch-interval 10 \
        --max-batches 1 \
        --llm-model qwen-plus \
        2>&1 | tee -a "${LOG_FILE}"; then
        log "PERCV research completed"
    else
        log "PERCV research failed (non-fatal)"
    fi
else
    log "Skipping PERCV research (no DASHSCOPE_API_KEY or --skip-research)"
fi

# ── Phase 8b: RSI Loop (optional) ───────────────────────────────
if [[ "${SKIP_RSI}" != "true" && -f "${SCRIPT_DIR}/run_rsi_loop.sh" ]]; then
    run_phase "8b" "RSI Loop"
    if bash "${SCRIPT_DIR}/run_rsi_loop.sh" 2>&1 | tee -a "${LOG_FILE}"; then
        log "RSI loop completed"
    else
        log "RSI loop failed (non-fatal)"
    fi
else
    log "Skipping RSI loop"
fi

# ── Phase 8c: MAS-TS Evaluation (optional) ──────────────────────
if [[ -d "${PROJECT_ROOT}/external/mas_ts" ]]; then
    run_phase "8c" "MAS-TS Evaluation"
    if "${PYTHON}" -m pytest tests/integration/test_platform/ \
        -q --no-header --timeout=60 --no-cov \
        2>&1 | tee -a "${LOG_FILE}"; then
        log "MAS-TS evaluation passed"
    else
        log "MAS-TS evaluation found issues (non-fatal)"
    fi
else
    log "Skipping MAS-TS evaluation (mas_ts not available)"
fi

# ── Report sync ─────────────────────────────────────────────────
if [[ -f "${SCRIPT_DIR}/sync_reports.sh" ]]; then
    bash "${SCRIPT_DIR}/sync_reports.sh" 2>&1 | tee -a "${LOG_FILE}" || true
fi

# ── Cleanup ─────────────────────────────────────────────────────
find "${LOG_DIR}" -name "evolution_*.log" -mtime +30 -delete 2>/dev/null || true

log "Daily evolution complete. Log: ${LOG_FILE}"
exit ${OVERALL_EXIT}
