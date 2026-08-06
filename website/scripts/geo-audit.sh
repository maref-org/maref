#!/usr/bin/env bash
set -euo pipefail

# GEO Audit wrapper for maref.cc
# Uses geo-optimizer-skill (Auriti-Labs v4.14.0+)
# Usage: ./scripts/geo-audit.sh [quick|full|score|json] [url]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
URL="${2:-https://maref.cc}"
MODE="${1:-quick}"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating Python venv..."
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

if ! command -v geo &> /dev/null; then
  echo "Installing geo-optimizer-skill..."
  pip install geo-optimizer-skill
fi

case "$MODE" in
  quick)
    echo "=== GEO Quick Audit: $URL ==="
    geo audit --url "$URL" --format text --verbose
    ;;
  full)
    echo "=== GEO Full Audit: $URL ==="
    geo audit --url "$URL" --format rich --save-history
    echo "---"
    geo access --url "$URL"
    echo "---"
    geo coherence --url "$URL"
    echo "---"
    geo authority --url "$URL"
    ;;
  score)
    echo "=== GEO Score Only: $URL ==="
    geo audit --url "$URL" --format text 2>&1 | grep -E 'Score|GEO|Overall' || true
    ;;
  json)
    echo "=== GEO JSON Report: $URL ==="
    OUTPUT="$PROJECT_DIR/dist/geo-audit-report.json"
    geo audit --url "$URL" --format json --output "$OUTPUT" --save-history
    echo "Report saved to: $OUTPUT"
    ;;
  threshold)
    THRESHOLD="${2:-85}"
    echo "=== GEO Threshold Check (>= $THRESHOLD): $URL ==="
    geo audit --url "$URL" --format text --threshold "$THRESHOLD"
    ;;
  history)
    echo "=== GEO History ==="
    geo history --url "$URL"
    ;;
  *)
    echo "Usage: $0 [quick|full|score|json|threshold|history] [url]"
    echo "  quick     — Quick text audit (default)"
    echo "  full      — Full audit + access + coherence + authority"
    echo "  score     — Score only"
    echo "  json      — JSON report to dist/geo-audit-report.json"
    echo "  threshold — Check if score >= N (default 85)"
    echo "  history   — Show score history"
    exit 1
    ;;
esac
