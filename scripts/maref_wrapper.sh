#!/bin/bash
#
# MAREF AutoResearch Wrapper
# 此脚本位于内置硬盘，绕过 macOS 对外置硬盘脚本的执行限制
# launchd 通过此脚本调用实际的 run_daily.sh
#
# 环境变量加载优先级:
#   1. ~/.maref.env (用户私有配置，不被 Git 追踪)
#   2. .env 项目根目录 (Git 忽略)
#   3. launchctl 注入 (来自 LaunchAgent)
#

# 步骤 1: 从用户私有配置加载 (最高优先级)
MAREF_USER_ENV="${HOME}/.maref.env"
if [[ -f "${MAREF_USER_ENV}" ]]; then
    set -a
    source "${MAREF_USER_ENV}"
    set +a
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loaded environment from ${MAREF_USER_ENV}"
fi

# 步骤 2: 从项目 .env 加载 (次优先级)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${MAREF_PROJECT_ROOT:-${SCRIPT_DIR}/..}"
PROJECT_ENV="${PROJECT_ROOT}/.env"
if [[ -f "${PROJECT_ENV}" ]]; then
    set -a
    source "${PROJECT_ENV}"
    set +a
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loaded environment from ${PROJECT_ENV}"
fi

# 步骤 3: 设置默认值 (最低优先级，仅当环境变量未设置时)
export MAREF_PROJECT_ROOT="${MAREF_PROJECT_ROOT:-$(pwd)}"
export MAREF_MAILBOX_DIR="${MAREF_MAILBOX_DIR:-${MAREF_PROJECT_ROOT}/mailbox}"
export MAREF_OUTPUT_DIR="${MAREF_OUTPUT_DIR:-${MAREF_MAILBOX_DIR}/research_output}"

# 切换到项目目录并直接运行 Python
cd "${MAREF_PROJECT_ROOT}" || exit 1

PYTHON="${MAREF_PROJECT_ROOT}/.venv/bin/python"
OUTPUT_DIR="${MAREF_OUTPUT_DIR}"
LOG_DIR="${OUTPUT_DIR}/logs"
mkdir -p "${LOG_DIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/autoresearch_${TIMESTAMP}.log"

# 预检
if [[ -z "${DASHSCOPE_API_KEY}" ]]; then
    echo "[ERROR] DASHSCOPE_API_KEY is not set." | tee -a "${LOG_FILE}"
    exit 78
fi

if [[ ! -f "${PYTHON}" ]]; then
    echo "[ERROR] Python not found at ${PYTHON}" | tee -a "${LOG_FILE}"
    exit 78
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting MAREF AutoResearch batch..." | tee -a "${LOG_FILE}"
echo "  Project: ${MAREF_PROJECT_ROOT}" | tee -a "${LOG_FILE}"
echo "  Output:  ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
echo "  Log:     ${LOG_FILE}" | tee -a "${LOG_FILE}"

# 直接运行 Python 模块（绕过 shell 脚本执行限制）
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
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Batch failed with exit code ${EXIT_CODE}." | tee -a "${LOG_FILE}"
fi

# 清理旧日志
find "${LOG_DIR}" -name "autoresearch_*.log" -mtime +30 -delete 2>/dev/null || true

exit ${EXIT_CODE}
