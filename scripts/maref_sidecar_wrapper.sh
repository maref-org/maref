#!/bin/bash
#
# MAREF Unified Sidecar Wrapper Script
# 位于内置硬盘，绕过 macOS 对外置硬盘脚本的执行限制
# launchd/systemd 通过此脚本启动 UnifiedSidecar 服务器
#
# Usage: ./maref_sidecar_wrapper.sh [start|stop|status]

set -euo pipefail

# Load environment from ~/.maref.env if available
if [[ -f "${HOME}/.maref.env" ]]; then
    set -a
    source "${HOME}/.maref.env"
    set +a
fi

MAREF_ROOT="${MAREF_PROJECT_ROOT:-$(pwd)}"
PYTHON="${MAREF_ROOT}/.venv/bin/python"
SIDECAR_MODULE="sidecar.server"
HOST="127.0.0.1"
PORT="${MAREF_SIDECAR_PORT:-8099}"
PID_FILE="/tmp/maref_sidecar.pid"
LOG_DIR="${MAREF_ROOT}/logs/sidecar"
mkdir -p "${LOG_DIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/sidecar_${TIMESTAMP}.log"

start() {
    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        echo "[ERROR] Sidecar already running (PID $(cat "${PID_FILE}"))"
        exit 1
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting MAREF Unified Sidecar..." | tee -a "${LOG_FILE}"
    echo "  Host: ${HOST}:${PORT}" | tee -a "${LOG_FILE}"
    echo "  Log:  ${LOG_FILE}" | tee -a "${LOG_FILE}"

    nohup "${PYTHON}" -m "${SIDECAR_MODULE}" \
        --host "${HOST}" \
        --port "${PORT}" \
        >> "${LOG_FILE}" 2>&1 &

    PID=$!
    echo "${PID}" > "${PID_FILE}"
    echo "[OK] Sidecar started with PID ${PID}" | tee -a "${LOG_FILE}"
}

stop() {
    if [[ ! -f "${PID_FILE}" ]]; then
        echo "[WARN] No PID file found"
        return 0
    fi
    PID=$(cat "${PID_FILE}")
    if kill -0 "${PID}" 2>/dev/null; then
        echo "Stopping sidecar (PID ${PID})..."
        kill "${PID}"
        sleep 2
        if kill -0 "${PID}" 2>/dev/null; then
            kill -9 "${PID}" 2>/dev/null || true
        fi
        echo "[OK] Sidecar stopped"
    else
        echo "[WARN] Process ${PID} not running"
    fi
    rm -f "${PID_FILE}"
}

status() {
    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        echo "Sidecar running (PID $(cat "${PID_FILE}"))"
        curl -s "http://${HOST}:${PORT}/api/health" 2>/dev/null || echo "  (not responding)"
    else
        echo "Sidecar not running"
    fi
}

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 1; start ;;
    status)  status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
