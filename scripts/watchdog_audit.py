#!/usr/bin/env python3
"""
MAREF v17 watchdog — runs audit_v17.sh every 5 minutes in a loop.
Kill with: kill $(cat $PROJECT_ROOT/reports/watchdog_audit.pid)
"""

import os
import subprocess
import time
from pathlib import Path

AUDIT_SCRIPT = Path("scripts/audit_v17.sh")
PID_FILE = Path("reports/watchdog_audit.pid")
INTERVAL = 300  # 5 minutes


def main() -> None:
    """Run audit script in a loop. Falls back to meta-monitor if audit script missing."""
    os.makedirs("reports", exist_ok=True)
    pid_dir = Path("reports")
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / "watchdog_audit.pid").write_text(str(os.getpid()))

    meta_monitor_available = True
    try:
        import maref.observability.meta_monitor  # noqa: F401
    except ImportError:
        meta_monitor_available = False

    while True:
        try:
            if AUDIT_SCRIPT.exists():
                subprocess.run(
                    ["/bin/bash", str(AUDIT_SCRIPT)],
                    capture_output=True, text=True, timeout=120,
                )
            elif meta_monitor_available:
                from maref.observability.meta_monitor import run_once
                run_once()
            else:
                print("[watchdog] no audit script or meta-monitor available", flush=True)
        except Exception as e:
            print(f"[watchdog] audit failed: {e}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
