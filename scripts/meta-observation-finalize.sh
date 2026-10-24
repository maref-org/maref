#!/bin/sh
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
cd "$ROOT" || exit 2
LOG=".governance/meta/observation-24h-final.log"
JSON=".governance/meta/observation-24h-final.json"
.venv/bin/python scripts/meta_audit_gate.py --all >"$LOG" 2>&1
status=$?
.venv/bin/python - "$status" <<'PY' >"$JSON"
import json
import sys
import time
from pathlib import Path

status = int(sys.argv[1])
try:
    report = json.loads(Path(".governance/meta/meta-monitor-report.json").read_text())
except Exception as exc:
    report = {"read_error": str(exc)}
report["observation_result"] = "PASS" if status == 0 else "FAIL"
report["observation_finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
report["gate_exit_code"] = status
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
exit "$status"
