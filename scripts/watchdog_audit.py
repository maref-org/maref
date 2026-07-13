#!/usr/bin/env python3
"""
MAREF v17 watchdog — runs audit_v17.sh every 5 minutes in a loop.
Kill with: kill $(cat /Volumes/1TB-M2/public/maref/reports/watchdog_audit.pid)
"""

import os
import subprocess
import time
from pathlib import Path

AUDIT_SCRIPT = Path("/Volumes/1TB-M2/public/maref/scripts/audit_v17.sh")
PID_FILE = Path("/Volumes/1TB-M2/public/maref/reports/watchdog_audit.pid")
INTERVAL = 300  # 5 minutes


def main() -> None:
    PID_FILE.write_text(str(os.getpid()))
    while True:
        try:
            subprocess.run(
                ["/bin/bash", str(AUDIT_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except Exception as e:
            print(f"[watchdog] audit failed: {e}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
