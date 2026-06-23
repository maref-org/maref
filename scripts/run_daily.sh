#!/bin/bash
#
# MAREF AutoResearch Daily Runner
#
# This script is designed to be called by launchd (macOS) or cron.
# It runs one batch of continuous autoresearch experiments with LLM analysis.
#
# Usage:
#   ./run_daily.sh
#
# Environment:
#   DASHSCOPE_API_KEY  - Required. 阿里云百炼 API Key.
#   MAREF_OUTPUT_DIR   - Optional. Output directory for reports.
#   MAREF_MAILBOX_DIR  - Optional. Mailbox directory for synced reports.
#

# NOTE: Do NOT use "set -e" here — launchd needs to capture all exit codes
# and we want logs to be written even on partial failure.
set -uo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
PYTHON="${VENV_PATH}/bin/python"

# Load .env file if present (so launchd jobs also pick up the API key)
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Default mailbox directory: uses MAREF_MAILBOX_DIR env var, or falls back to project_root/mailbox
MAILBOX_DIR="${MAREF_MAILBOX_DIR:-${PROJECT_ROOT}/mailbox}"

# Default output directory (uses mailbox dir if MAREF_OUTPUT_DIR not set)
OUTPUT_DIR="${MAREF_OUTPUT_DIR:-${MAILBOX_DIR}/research_output}"
LOG_DIR="${OUTPUT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# Also ensure project-level logs dir exists for launchd stdout/stderr
PROJECT_LOG_DIR="${PROJECT_ROOT}/research_output/logs"
mkdir -p "${PROJECT_LOG_DIR}" 2>/dev/null || true

# Log file with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/autoresearch_${TIMESTAMP}.log"

# --- Pre-flight checks (log but do NOT exit early) ---
PREFLIGHT_OK=true

# Check API key
if [[ -z "${DASHSCOPE_API_KEY:-}" ]]; then
    echo "[ERROR] DASHSCOPE_API_KEY is not set." | tee -a "${LOG_FILE}"
    echo "Please set your 阿里云百炼 API key:" | tee -a "${LOG_FILE}"
    echo "  export DASHSCOPE_API_KEY='your-key-here'" | tee -a "${LOG_FILE}"
    PREFLIGHT_OK=false
fi

# Check Python environment
if [[ ! -f "${PYTHON}" ]]; then
    echo "[ERROR] Virtual environment not found at ${VENV_PATH}" | tee -a "${LOG_FILE}"
    echo "Please create it first:" | tee -a "${LOG_FILE}"
    echo "  python3 -m venv ${VENV_PATH}" | tee -a "${LOG_FILE}"
    echo "  source ${VENV_PATH}/bin/activate && pip install -r requirements.txt" | tee -a "${LOG_FILE}"
    PREFLIGHT_OK=false
fi

if [[ "${PREFLIGHT_OK}" != "true" ]]; then
    echo "[ERROR] Pre-flight checks failed. Exiting." | tee -a "${LOG_FILE}"
    exit 78
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting MAREF AutoResearch batch..." | tee -a "${LOG_FILE}"
echo "  Project: ${PROJECT_ROOT}" | tee -a "${LOG_FILE}"
echo "  Output:  ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "  Log:     ${LOG_FILE}" | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running MAREF daily recursive evolution dry-run..." | tee -a "${LOG_FILE}"
"${PYTHON}" -m maref.evolution.daily_loop \
    --dry-run \
    --vault "${PROJECT_ROOT}/.evolution_vault" \
    2>&1 | tee -a "${LOG_FILE}" || true

# Run one batch (max-batches=1)
"${PYTHON}" -m src.research.continuous_engine \
    --output-dir "${OUTPUT_DIR}" \
    --experiments-per-batch 50 \
    --batch-interval 10 \
    --max-batches 1 \
    --llm-model qwen-plus \
    2>&1 | tee -a "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Batch completed successfully." | tee -a "${LOG_FILE}"

    # Sync reports to project-level research_output for backup
    if [[ -f "${SCRIPT_DIR}/sync_reports.sh" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Syncing reports..." | tee -a "${LOG_FILE}"
        bash "${SCRIPT_DIR}/sync_reports.sh" 2>&1 | tee -a "${LOG_FILE}" || true
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Batch failed with exit code ${EXIT_CODE}." | tee -a "${LOG_FILE}"
fi

# Cleanup old logs (keep last 30 days)
find "${LOG_DIR}" -name "autoresearch_*.log" -mtime +30 -delete 2>/dev/null || true

exit ${EXIT_CODE}
