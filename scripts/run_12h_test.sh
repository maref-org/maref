#!/bin/bash
#
# MAREF 12-hour Autonomous Iteration Test
#
# Runs the full autonomous loop for 12 hours, logging everything.
#
# Usage:
#   bash scripts/run_12h_test.sh                    # 12h dry-run
#   bash scripts/run_12h_test.sh --production        # 12h production (writes + LLM)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${PROJECT_ROOT}/reports/autonomous/${TIMESTAMP}"
LOG_FILE="${PROJECT_ROOT}/reports/autonomous/${TIMESTAMP}/run.log"

mkdir -p "${OUTPUT_DIR}"

MODE="dry-run"
DURATION=12
ARGS="--dry-run"

if [[ "${1:-}" == "--production" ]]; then
    MODE="production"
    ARGS="--production"
    echo "[!] PRODUCTION MODE: real writes + LLM code generation enabled"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting 12h autonomous loop test" | tee -a "${LOG_FILE}"
echo "  Mode:     ${MODE}" | tee -a "${LOG_FILE}"
echo "  Duration: ${DURATION} hours" | tee -a "${LOG_FILE}"
echo "  Output:   ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "  Log:      ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "" | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}"

# Run the autonomous loop
python -m scripts.run_autonomous_loop \
    --duration "${DURATION}" \
    --interval 15 \
    ${ARGS} \
    --output "${OUTPUT_DIR}" \
    2>&1 | tee -a "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 12h autonomous loop test complete" | tee -a "${LOG_FILE}"
echo "  Exit code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"
echo "  Report:    ${OUTPUT_DIR}/final-report.json" | tee -a "${LOG_FILE}"

# Print summary
if [[ -f "${OUTPUT_DIR}/final-report.json" ]]; then
    echo "" | tee -a "${LOG_FILE}"
    echo "=== SUMMARY ===" | tee -a "${LOG_FILE}"
    python3 -c "
import json
with open('${OUTPUT_DIR}/final-report.json') as f:
    r = json.load(f)
print(f'  Wall time:    {r[\"duration_hours\"]:.1f} hours')
print(f'  Cycles:       {r[\"total_cycles\"]}')
print(f'  Successes:    {r[\"successful_cycles\"]}')
print(f'  Failures:     {r[\"failed_cycles\"]}')
print(f'  Adoption:     {r[\"adoption_rate\"]*100:.1f}%')
" | tee -a "${LOG_FILE}"
fi

exit ${EXIT_CODE}
