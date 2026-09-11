#!/usr/bin/env python3
"""进化触发端点 (Phase Delta D5) — 供飞轮调度器触发进化轮次"""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

EVOLUTION_DAEMON = "/Volumes/1TB-M2/public/maref/src/maref/evolution/daemon.py"


def trigger_evolution_run():
    print(f"[{datetime.now(timezone.utc).isoformat()}] 触发进化运行...")
    try:
        result = subprocess.run(
            [sys.executable, EVOLUTION_DAEMON, "--dry-run", "--max-runs", "1", "--real-writes"],
            capture_output=True, text=True, timeout=120,
        )
        ok = result.returncode == 0
        print(f"  {'✅' if ok else '❌'} exit={result.returncode}")
        if result.stdout:
            print(result.stdout[:500])
        if result.stderr:
            print("  stderr:", result.stderr[:300])
        return ok
    except subprocess.TimeoutExpired:
        print("  ❌ 超时 (120s)")
        return False
    except FileNotFoundError:
        print("  ❌ 进化守护进程脚本不存在")
        return False


if __name__ == "__main__":
    trigger_evolution_run()