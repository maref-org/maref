#!/usr/bin/env bash
# 治理证据门禁入口。默认 P0；传 --all 追加治理质量指标。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
if [ -n "${MAREF_PYTHON:-}" ]; then
    PY="$MAREF_PYTHON"
elif [ -x ".venv/bin/python3" ]; then
    PY=".venv/bin/python3"
else
    PY="python3"
fi
exec "$PY" scripts/evidence_gate.py "$@"
