#!/usr/bin/env python3
"""进化守护进程状态检查与诊断 (Phase Alpha A2)"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("/Volumes/1TB-M2/public/maref/.evolution_daemon_state.json")
VAULT_DIR = Path("/Volumes/1TB-M2/public/maref/.evolution_vault")
PID_FILE = Path("/tmp/maref-evolution-daemon.pid")


def check_daemon() -> tuple[bool, str, dict]:
    status = {
        "state_file_exists": STATE_FILE.exists(),
        "vault_dir_exists": VAULT_DIR.exists(),
        "pid_file_exists": PID_FILE.exists(),
        "daemon_running": False,
    }

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            status["daemon_running"] = True
        except (OSError, ValueError):
            pass

    if not STATE_FILE.exists():
        return False, "STATE_FILE_MISSING", status

    try:
        state = json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return False, "STATE_FILE_CORRUPT", status

    last_run_str = state.get("last_run", "")
    if not last_run_str:
        return False, "NO_LAST_RUN", status

    last_run = datetime.fromisoformat(last_run_str)
    now = datetime.now(timezone.utc)
    hours_stale = (now - last_run).total_seconds() / 3600

    status.update({
        "last_run": last_run_str,
        "total_runs": state.get("total_runs", 0),
        "failed_runs": state.get("failed_runs", 0),
        "hours_stale": round(hours_stale, 1),
        "days_stale": round(hours_stale / 24, 1),
    })

    if status["daemon_running"]:
        return True, "RUNNING", status
    elif hours_stale < 24:
        return True, "RECENTLY_STOPPED", status
    else:
        return False, f"STALE_{int(hours_stale)}h", status


def main():
    healthy, reason, status = check_daemon()

    print("=" * 60)
    print("进化守护进程状态报告 (Phase Alpha A2)")
    print("=" * 60)
    print(f"\n状态: {reason}")
    print(f"守护进程运行中: {'✅' if status['daemon_running'] else '❌'}")
    print(f"上次运行: {status.get('last_run', 'N/A')}")
    print(f"停滞时长: {status.get('days_stale', 'N/A')} 天")
    print(f"总运行次数: {status.get('total_runs', 'N/A')}")
    print(f"失败次数: {status.get('failed_runs', 'N/A')}")

    if not status["daemon_running"] and status.get("days_stale", 0) > 1:
        print(f"\n⚠️ 进化引擎已停滞 {status.get('days_stale')} 天！")
        print("建议: python3 src/maref/evolution/daemon.py --interval-hours 6 &")

    state_path = "/Volumes/1TB-M2/public/maref/reports/evolution_daemon_status.json"
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "healthy": healthy,
            "reason": reason,
            "status": status,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {state_path}")


if __name__ == "__main__":
    main()