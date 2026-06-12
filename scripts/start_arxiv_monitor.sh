#!/bin/bash
# Start arXiv endorsement email monitor in the background
# Usage: ./scripts/start_arxiv_monitor.sh [--accounts "email1:server,email2:server"] [--interval 60] [--loops 1440]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/logs/arxiv_monitor_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="$PROJECT_ROOT/.arxiv_monitor.pid"

# Default configuration
INTERVAL=${INTERVAL:-60}
LOOPS=${LOOPS:-1440}  # ~24 hours at 60s interval
CSV_FILE="${CSV_FILE:-docs/arxiv-endorsement-targets.csv}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --accounts)
            export MONITOR_ACCOUNTS="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --loops)
            LOOPS="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if monitor is already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Monitor already running (PID: $OLD_PID)"
        echo "Stop it first: kill $OLD_PID"
        exit 1
    else
        echo "Stale PID file found, removing"
        rm -f "$PID_FILE"
    fi
fi

# Create logs directory
mkdir -p "$PROJECT_ROOT/logs"

# Check environment
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading .env file..."
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
elif [ -f "$HOME/.maref.env" ]; then
    echo "Loading ~/.maref.env file..."
    export $(grep -v '^#' "$HOME/.maref.env" | xargs)
else
    echo "WARNING: No .env or ~/.maref.env found. Monitor will prompt for password."
fi

echo "Starting arXiv endorsement monitor..."
echo "  Interval: ${INTERVAL}s"
echo "  Loops: ${LOOPS} (approximately $(( LOOPS * INTERVAL / 3600 )) hours)"
echo "  CSV targets: ${CSV_FILE}"
echo "  Log file: ${LOG_FILE}"
echo "  Accounts: ${MONITOR_ACCOUNTS:-default}"
echo ""
echo "IMPORTANT: Make sure you have configured:"
echo "  1. IMAP authorization code in .env or ~/.maref.env"
echo "  2. Target emails in ${CSV_FILE}"
echo ""
echo "To check logs: tail -f ${LOG_FILE}"
echo "To stop: kill \$(cat ${PID_FILE})"
echo ""

# Start monitor in background
cd "$PROJECT_ROOT"
nohup python3 scripts/arxiv_endorsement_mailer.py \
    --csv "$CSV_FILE" \
    --monitor \
    --interval "$INTERVAL" \
    --loops "$LOOPS" \
    > "$LOG_FILE" 2>&1 &

MONITOR_PID=$!
echo "$MONITOR_PID" > "$PID_FILE"
echo "Monitor started with PID: $MONITOR_PID"
echo "Waiting 3 seconds to verify it started..."
sleep 3

if kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "Monitor is running successfully"
    echo "Last 5 lines of log:"
    tail -n 5 "$LOG_FILE"
else
    echo "ERROR: Monitor failed to start. Check log:"
    cat "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
