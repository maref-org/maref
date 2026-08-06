#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if ! command -v maref &> /dev/null; then
  echo -e "${RED}[WARN] 'maref' CLI not found in PATH. Install with: pip install -e '.[dev]'${NC}"
fi

if ! curl -sf http://localhost:8000/health &> /dev/null; then
  echo "Starting sidecar on port 8000..."
  maref sidecar --port 8000 &
  SIDECAR_PID=$!
  trap 'echo "Cleaning up..."; kill $SIDECAR_PID 2>/dev/null; exit' EXIT INT TERM
  sleep 2
  if ! kill -0 "$SIDECAR_PID" 2>/dev/null; then
    echo -e "${RED}[FAIL] Sidecar failed to start${NC}"
    exit 1
  fi
fi

if maref demo governed-review --auto-approve; then
  echo -e "${GREEN}[PASS] Governed review completed successfully${NC}"
  exit 0
else
  echo -e "${RED}[FAIL] Governed review encountered errors${NC}"
  exit 1
fi
