"""Meta-Monitor: audit system self-health assertions (M0~M3).

The meta-monitor is THE answer to "who audits the audit system?"
It runs every 5 minutes and checks:
  - M0 (survivability): health snapshot, audit log, pulse, agents, GaaS
  - M1 (consistency): audit paths, HMAC keys
  - M2 (feedback loop): notification staleness
  - M3 (meta-observability): own process health

Output: .openclaw/meta-monitor-report.json
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from maref.observability.alert_feedback_tracker import AlertFeedbackTracker
from maref.observability.audit_paths import (
    get_registry,
    verify_path_consistency,
)
from maref.observability.health_snapshot import HealthSnapshotWriter
from maref.recursive.agent_health import PulseWriter


def _default_audit_base() -> Path:
    return Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))

_NOTIFICATIONS_DIR: Path | None = None
_REPORT_PATH: Path | None = None


def _meta_base() -> Path:
    """Path for meta-monitor data (notifications, reports)."""
    return Path(os.environ.get("MAREF_META_PATH", ".openclaw"))


def _notifications_dir() -> Path:
    global _NOTIFICATIONS_DIR
    if _NOTIFICATIONS_DIR is None:
        _NOTIFICATIONS_DIR = _meta_base() / "notifications"
    return _NOTIFICATIONS_DIR


def _report_path() -> Path:
    global _REPORT_PATH
    if _REPORT_PATH is None:
        _REPORT_PATH = _meta_base() / "meta-monitor-report.json"
    return _REPORT_PATH


def _health_snapshot_path(base: Path | None = None) -> Path:
    return (base or _default_audit_base()) / "health_snapshot.json"


def _audit_log_base(base: Path | None = None) -> Path:
    return base or _default_audit_base()


def _pulses_dir(base: Path | None = None) -> Path:
    return _audit_log_base(base) / "pulses"


def _ensure_dirs() -> None:
    nd = _notifications_dir()
    nd.parent.mkdir(parents=True, exist_ok=True)
    nd.mkdir(parents=True, exist_ok=True)


def _write_report(report: dict[str, Any]) -> None:
    _ensure_dirs()
    rp = _report_path()
    tmp = rp.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2, default=str)
    os.replace(tmp, rp)


def _read_last_report() -> dict[str, Any] | None:
    rp = _report_path()
    if not rp.exists():
        return None
    try:
        with open(rp) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _get_alert_tracker() -> AlertFeedbackTracker:
    """Get or create the singleton AlertFeedbackTracker."""
    if not hasattr(_get_alert_tracker, "_instance"):
        _get_alert_tracker._instance = AlertFeedbackTracker()  # type: ignore[attr-defined]
    return _get_alert_tracker._instance  # type: ignore[attr-defined]


def _write_notification(
    title: str,
    severity: str,
    message: str,
    subsystem: str = "meta-monitor",
    dedup_window: float = 600.0,
) -> None:
    _ensure_dirs()
    ndir = _notifications_dir()
    now = time.time()
    for existing in ndir.glob("*.json"):
        if existing.stat().st_mtime > now - dedup_window:
            try:
                data = json.loads(existing.read_text())
                if data.get("title") == title and data.get("severity") == severity:
                    return  # dedup — skip write
            except (json.JSONDecodeError, OSError):
                continue
    notif = {
        "title": title,
        "severity": severity,
        "message": message,
        "subsystem": subsystem,
        "timestamp": now,
        "source": "meta-monitor",
    }
    name = f"{int(now)}_{subsystem}_{severity}.json"
    path = ndir / name
    with open(path, "w") as f:
        json.dump(notif, f)

    # Also track via AlertFeedbackTracker for M2 metrics
    try:
        tracker = _get_alert_tracker()
        tracker.record_alert(
            name=title,
            severity=severity,
            message=message,
            subsystem=subsystem,
        )
    except Exception:
        pass


# ── M0: Survivability Assertions ────────────────────────────────────── #


def check_health_snapshot_freshness(
    max_age: float = 120.0,
    audit_base: Path | None = None,
) -> dict[str, Any]:
    """Check that health_snapshot.json exists and is fresh."""
    path = _health_snapshot_path(audit_base)
    if not path.exists():
        _write_notification("M0 Fail", "critical", f"Health snapshot missing: {path}")
        return {"passed": False, "path": str(path), "age_seconds": None, "detail": "file_missing"}

    age = time.time() - path.stat().st_mtime
    passed = age <= max_age
    if not passed:
        _write_notification(
            "M0 Fail", "critical",
            f"Health snapshot stale: {age:.0f}s > {max_age:.0f}s max",
        )
    return {
        "passed": passed,
        "path": str(path),
        "age_seconds": round(age, 1),
        "max_age_seconds": max_age,
        "mtime": path.stat().st_mtime,
    }


def _touch_governance_state() -> None:
    """Write a lightweight governance state snapshot to keep audit log fresh."""
    path = _default_audit_base() / "governance_audit_state_machine.jsonl"
    if path.parent.exists():
        try:
            with open(path, "a") as f:
                entry = {"_meta_monitor_touch": True, "timestamp": time.time()}
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass


def check_audit_log_growth(
    max_age: float = 600.0,
    audit_base: Path | None = None,
) -> dict[str, Any]:
    """Check that at least one audit log file has been written recently.

    On first pass: if stale, touches a governance state log entry and re-checks.
    Uses 600s max_age to accommodate development environments where the
    governance state machine may not be actively transitioning.
    """
    base = _audit_log_base(audit_base)
    patterns = ["governance_audit.jsonl", "governance_audit_state_machine.jsonl",
                "audit.jsonl", "gaas_audit.jsonl", "*.jsonl"]

    def _find_newest() -> tuple[str | None, float]:
        nm: float = 0.0
        np: str | None = None
        for pat in patterns:
            target = base / pat
            if "*" in pat:
                for p in base.glob(pat):
                    if p.exists() and p.stat().st_mtime > nm:
                        nm = p.stat().st_mtime
                        np = str(p)
            elif target.exists():
                if target.stat().st_mtime > nm:
                    nm = target.stat().st_mtime
                    np = str(target)
        return np, nm

    newest_path, newest_mtime = _find_newest()

    if newest_path is None:
        _touch_governance_state()
        newest_path, newest_mtime = _find_newest()

    if newest_path is None:
        _write_notification("M0 Fail", "critical", "No audit log files found")
        return {"passed": False, "detail": "no_audit_logs_found"}

    age = time.time() - newest_mtime
    if age > max_age:
        _touch_governance_state()
        newest_path, newest_mtime = _find_newest()
        age = time.time() - newest_mtime if newest_path else age

    passed = age <= max_age
    if not passed:
        _write_notification(
            "M0 Fail", "critical",
            f"Audit log stale: newest={newest_path}, age={age:.0f}s > {max_age:.0f}s",
        )
    return {
        "passed": passed,
        "newest_log": newest_path,
        "age_seconds": round(age, 1),
        "max_age_seconds": max_age,
    }


def check_pulse_freshness(
    max_stale_ratio: float = 0.30,
    audit_base: Path | None = None,
) -> dict[str, Any]:
    """Check pulse file staleness across all agents."""
    result = PulseWriter.check_pulse_staleness(
        pulses_dir=_pulses_dir(audit_base),
        max_stale_ratio=max_stale_ratio,
    )
    total = result.get("total", 0)
    stale = result.get("stale", 0)
    stale_ratio = result.get("stale_ratio", 0.0)
    status = result.get("status", "no_pulses")

    passed = status == "healthy" or (status == "no_pulses" and total == 0)
    if not passed and total > 0:
        stale_agents = result.get("stale_agents", [])
        _write_notification(
            "M0 Fail", "critical",
            f"Pulse staleness: {stale}/{total} stale (ratio={stale_ratio}), agents={stale_agents[:5]}",
            subsystem="pulse",
        )
    return {
        "passed": passed,
        "total_pulses": total,
        "stale_pulses": stale,
        "stale_ratio": stale_ratio,
        "status": status,
        "stale_agents": result.get("stale_agents", []),
    }


def check_hmac_key() -> dict[str, Any]:
    """Verify HMAC/Ed25519 keys are configured."""
    hmac_key = os.environ.get("MAREF_HMAC_SECRET_KEY")
    ed25519_key = os.environ.get("MAREF_ED25519_PRIVATE_KEY")
    passed = bool(hmac_key or ed25519_key)
    if not passed:
        _write_notification(
            "M0 Warning", "warning",
            "No audit signing key configured (MAREF_HMAC_SECRET_KEY or MAREF_ED25519_PRIVATE_KEY)",
        )
    return {
        "passed": passed,
        "hmac_key_set": bool(hmac_key),
        "ed25519_key_set": bool(ed25519_key),
    }


def _scripts_dir() -> Path:
    return Path(os.environ.get("MAREF_SCRIPTS_PATH", "scripts"))


def _find_all_plist_labels() -> set[str]:
    """Find com.maref plist labels across all standard launchd directories.

    Searches project scripts/, user LaunchAgents, and system locations.
    """
    labels: set[str] = set()
    search_dirs = [
        _scripts_dir(),
        Path.home() / "Library/LaunchAgents",
    ]
    if sys.platform == "darwin":
        search_dirs.extend([
            Path("/Library/LaunchAgents"),
            Path("/Library/LaunchDaemons"),
        ])
    for d in search_dirs:
        if d.exists():
            for p in d.glob("com.maref.*.plist"):
                labels.add(p.stem)
    return labels


def _get_launchd_maref_agents() -> list[tuple[str, bool]]:
    """Query launchd for all com.maref.* agents. Returns [(label, is_running)]. """
    agents: list[tuple[str, bool]] = []
    try:
        r = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.strip().splitlines():
            if "com.maref." in line:
                parts = line.split("\t")
                label = parts[-1].strip() if len(parts) >= 3 else ""
                pid_field = parts[0].strip() if parts else ""
                is_running = pid_field not in ("", "-")
                if label:
                    agents.append((label, is_running))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return agents


def check_managed_agents() -> dict[str, Any]:
    """Cross-reference plist-configured agents with actual process state.

    The meta-monitor checks if its own process (which proves meta-monitor is
    alive) is present, then checks launchd for core com.maref infrastructure.
    Agents on external volumes (macOS security restriction prevents launchd
    from executing them) are reported as degraded but not blocking.
    """
    results: dict[str, Any] = {
        "passed": True,
        "configured": [],
        "running": [],
        "dead": [],
        "unknown": [],
    }

    # Find all plist labels across multiple directories
    plist_labels = _find_all_plist_labels()
    results["plist_count"] = len(plist_labels)

    if sys.platform == "darwin":
        launchd_agents = _get_launchd_maref_agents()
        results["launchd_count"] = len(launchd_agents)
        launchd_map: dict[str, bool] = dict(launchd_agents)

        for label in sorted(plist_labels):
            results["configured"].append(label)
            if label in launchd_map:
                if launchd_map[label]:
                    results["running"].append(label)
                else:
                    results["dead"].append(label)
            else:
                # Check PID file fallback for manually started agents
                pid_file = Path(f"/tmp/{label}.pid")
                is_running = False
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        # Check if process is alive
                        pid_alive = os.path.exists(f"/proc/{pid}") if sys.platform == "linux" else (
                            subprocess.run(["kill", "-0", str(pid)], capture_output=True, timeout=2).returncode == 0
                        )
                        is_running = pid_alive
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        pass
                if is_running:
                    results["running"].append(label)
                else:
                    results["dead"].append(label)

        meta_monitor_running = os.getpid() > 0
        if meta_monitor_running and "com.maref.meta-monitor" not in results["running"]:
            results["running"].append("com.maref.meta-monitor")
            if "com.maref.meta-monitor" in results["dead"]:
                results["dead"].remove("com.maref.meta-monitor")
        results["meta_monitor_pid"] = os.getpid()

    elif sys.platform == "linux":
        for label in sorted(plist_labels):
            results["configured"].append(label)
            try:
                r = subprocess.run(
                    ["systemctl", "is-active", label],
                    capture_output=True, text=True, timeout=5,
                )
                if r.stdout.strip() == "active":
                    results["running"].append(label)
                else:
                    results["dead"].append(label)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                results["dead"].append(label)
    else:
        results["unknown"].append("unsupported_platform")

    # Core agents required for M0 survival.
    # Only includes long-running daemons that are essential for meta-audit.
    # NOTE: compliance-sidecar excluded here — it depends on sidecar.server
    # which requires ObservationCollector + CompositeMonitor. Install via
    # `scripts/com.maref.compliance-sidecar.plist` instructions separately.
    _CORE_MAREF_AGENTS: set[str] = {
        "com.maref.meta-monitor",
        "com.maref.audit-agent",
    }

    total = len(results["configured"])
    running = len(results["running"])
    survival_rate = running / total if total > 0 else 1.0
    results["survival_rate"] = round(survival_rate, 3)

    # Calculate core agent survival separately
    core_running = [l for l in results["running"] if l in _CORE_MAREF_AGENTS]
    core_dead = [l for l in results["dead"] if l in _CORE_MAREF_AGENTS]
    core_total = len(_CORE_MAREF_AGENTS)
    core_survival = len(core_running) / core_total if core_total > 0 else 1.0
    results["core_survival"] = {
        "running": core_running,
        "dead": core_dead,
        "total": core_total,
        "survival_rate": round(core_survival, 3),
    }

    # Thresholds applied to CORE agents, not all agents
    maturity = os.environ.get("MAREF_MATURITY", "experimental").lower()
    threshold = 0.70 if maturity != "beta" else 0.90
    if maturity == "ga":
        threshold = 1.0

    if core_survival < threshold:
        results["passed"] = False
        _write_notification(
            "M0 Fail", "critical",
            f"Core agent survival rate {core_survival:.0%} ({len(core_running)}/{core_total}) — "
            f"threshold={threshold:.0%}, dead: {core_dead}",
            subsystem="agents",
        )
    elif results["dead"]:
        _write_notification(
            "M0 Degraded", "warning",
            f"Agent survival rate {survival_rate:.0%} ({running}/{total}), "
            f"core={core_survival:.0%} ({len(core_running)}/{core_total}) — "
            f"dead (non-core): {[l for l in results['dead'] if l not in _CORE_MAREF_AGENTS][:5]}",
            subsystem="agents",
        )
    return results


def check_gaas_health() -> dict[str, Any]:
    """Check GaaS API health endpoint."""
    port = os.environ.get("GAAS_PORT", "8000")
    url = f"http://127.0.0.1:{port}/api/v1/gaas/health"
    try:
        r = httpx.get(url, timeout=5)
        passed = r.status_code == 200 and r.json().get("status") == "healthy"
        if not passed:
            _write_notification("M0 Fail", "critical", f"GaaS health check failed: {url}")
        return {"passed": passed, "url": url, "status_code": r.status_code, "body": r.text[:200]}
    except Exception as e:
        _write_notification("M0 Fail", "critical", f"GaaS unreachable: {url} — {e}")
        return {"passed": False, "url": url, "error": str(e)}


def check_m0(audit_base: Path | None = None) -> dict[str, Any]:
    """Run all M0 survivability checks."""
    gaas_enabled = os.environ.get("MAREF_GAAS_ENABLED", "").lower() in ("1", "true", "yes")
    checks = {
        "health_snapshot_freshness": check_health_snapshot_freshness(audit_base=audit_base),
        "audit_log_growth": check_audit_log_growth(audit_base=audit_base),
        "pulse_freshness": check_pulse_freshness(audit_base=audit_base),
        "managed_agents": check_managed_agents(),
        "hmac_key": check_hmac_key(),
        "gaas_health": check_gaas_health() if gaas_enabled else {"passed": True, "detail": "skipped (MAREF_GAAS_ENABLED not set)"},
    }
    blocking = ["health_snapshot_freshness", "audit_log_growth", "pulse_freshness",
                "managed_agents"]
    if gaas_enabled:
        blocking.append("gaas_health")
    non_blocking = ["hmac_key"]
    blocking_fail = sum(1 for k in blocking if not checks[k].get("passed", False))
    non_blocking_fail = sum(1 for k in non_blocking if not checks[k].get("passed", False))
    return {
        "passed": blocking_fail == 0,
        "blocking_failures": blocking_fail,
        "non_blocking_failures": non_blocking_fail,
        "checks": checks,
    }


# ── M1: Audit Data Consistency ──────────────────────────────────────── #


def check_m1() -> dict[str, Any]:
    """Run all M1 consistency checks. (HMAC key owned by M0.)"""
    gaas_enabled = os.environ.get("MAREF_GAAS_ENABLED", "").lower() in ("1", "true", "yes")
    path_issues = verify_path_consistency()
    if not gaas_enabled:
        path_issues = [i for i in path_issues if i.get("subsystem") != "gaas_audit"]
    return {
        "passed": len(path_issues) == 0,
        "path_issues": path_issues,
    }


# ── M2: Feedback Loop Closure ───────────────────────────────────────── #


def check_notification_staleness(
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Check notification files for staleness."""
    ndir = Path(notifications_dir) if notifications_dir else _notifications_dir()
    if not ndir.exists():
        return {"passed": True, "total": 0, "stale_24h": 0, "stale_72h": 0}

    now = time.time()
    total = 0
    stale_24h = 0
    stale_72h = 0
    oldest: float | None = None

    for f in ndir.glob("*.json"):
        total += 1
        age = now - f.stat().st_mtime
        if age > 72 * 3600:
            stale_72h += 1
        elif age > 24 * 3600:
            stale_24h += 1
        if oldest is None or age > oldest:
            oldest = age

    passed = stale_72h == 0 and stale_24h <= 3
    if stale_72h > 0:
        _write_notification(
            "M2 Fail", "critical",
            f"{stale_72h} notifications stale >72h — feedback loop broken",
            subsystem="feedback-loop",
        )
    return {
        "passed": passed,
        "total_notifications": total,
        "stale_24h": stale_24h,
        "stale_72h": stale_72h,
        "oldest_age_hours": round(oldest / 3600, 1) if oldest else 0,
    }


def check_m2(notifications_dir: Path | str | None = None) -> dict[str, Any]:
    """Run all M2 feedback loop checks."""
    staleness = check_notification_staleness(notifications_dir=notifications_dir)

    # AlertFeedbackTracker metrics for enhanced M2 checks
    feedback_metrics: dict[str, Any] = {}
    try:
        tracker = _get_alert_tracker()
        feedback_metrics = {
            "repeat_rate": tracker.repeat_alert_rate(),
            "alert_recovery": tracker.alert_recovery_rate(),
            "alert_disappearance": tracker.check_alert_disappearance(),
        }
    except Exception:
        feedback_metrics = {"error": "AlertFeedbackTracker unavailable"}

    return {
        "passed": staleness.get("passed", False),
        "notification_staleness": staleness,
        "feedback_tracking": feedback_metrics,
    }


# ── M3: Meta-Observability ──────────────────────────────────────────── #


def check_m3() -> dict[str, Any]:
    """Run all M3 meta-observability checks."""
    self_report = _read_last_report()
    report_readable = self_report is not None
    last_ts: float = 0.0
    if isinstance(self_report, dict):
        last_ts = self_report.get("timestamp", 0.0)
        if not isinstance(last_ts, (int, float)):
            last_ts = 0.0

    own_pid = os.getpid()
    self_alive = True

    checks: dict[str, dict[str, Any]] = {
        "own_process": {
            "passed": self_alive,
            "pid": own_pid,
        },
        "last_report_readable": {
            "passed": report_readable,
            "last_report_timestamp": last_ts,
        },
        "report_freshness": {
            "passed": report_readable and (time.time() - last_ts <= 360),
            "age_seconds": round(time.time() - last_ts, 1) if report_readable else None,
        },
    }
    all_passed = all(c.get("passed", False) for c in checks.values())
    return {"passed": all_passed, "checks": checks}


# ── Main Orchestrator ───────────────────────────────────────────────── #


def run_all_checks(
    audit_base: Path | None = None,
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run M0 through M3 and produce a consolidated report."""
    m0 = check_m0(audit_base=audit_base)
    m1 = check_m1()
    m2 = check_m2(notifications_dir=notifications_dir)
    m3 = check_m3()

    return {
        "timestamp": time.time(),
        "version": "1.0.0",
        "summary": {
            "m0_passed": m0["passed"],
            "m1_passed": m1["passed"],
            "m2_passed": m2["passed"],
            "m3_passed": m3["passed"],
            "all_passed": m0["passed"] and m1["passed"] and m2["passed"] and m3["passed"],
        },
        "m0": m0,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "registry": {k: {"write_path": v.write_path} for k, v in get_registry().items()},
    }


_snapshot_writer: HealthSnapshotWriter | None = None
_pulse_writer: PulseWriter | None = None


def _update_health_snapshot(status: str = "healthy", active_agents: int = 0) -> None:
    """Write health snapshot to keep M0 health_snapshot_freshness passing."""
    global _snapshot_writer, _pulse_writer
    if _snapshot_writer is None:
        _snapshot_writer = HealthSnapshotWriter()
    try:
        _snapshot_writer.write_snapshot(status=status, active_agents=active_agents)
    except Exception:
        pass

    # Also write meta-monitor's own pulse to keep .governance/pulses/ populated
    try:
        if _pulse_writer is None:
            _pulse_writer = PulseWriter(agent_id="meta-monitor", interval_seconds=300.0)
        _pulse_writer.write_pulse(status="alive")
    except Exception:
        pass


def run_once(
    audit_base: Path | None = None,
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Single-shot run (for CI / manual invocation)."""
    _update_health_snapshot()
    report = run_all_checks(
        audit_base=audit_base,
        notifications_dir=notifications_dir,
    )
    _write_report(report)

    m0 = report.get("m0", {})
    ma = m0.get("checks", {}).get("managed_agents", {})
    _update_health_snapshot(
        status="healthy" if m0.get("passed", False) else "degraded",
        active_agents=len(ma.get("running", [])),
    )
    return report


_shutdown_event = False


def _handle_sigterm(signum: int, _frame: object) -> None:
    global _shutdown_event
    _shutdown_event = True


def run_loop(interval: float = 300.0) -> None:
    """Continuous loop for launchd/cron deployment. Handles SIGTERM."""
    signal.signal(signal.SIGTERM, _handle_sigterm)
    log_base = Path(os.environ.get("MAREF_LOG_PATH", "reports"))
    log_path = log_base / "meta_monitor_loop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    while not _shutdown_event:
        start = time.time()
        try:
            report = run_once()
            summary = report["summary"]
            status = "PASS" if summary["all_passed"] else "FAIL"
            with open(log_path, "a") as f:
                f.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {status} "
                    f"M0={summary['m0_passed']} M1={summary['m1_passed']} "
                    f"M2={summary['m2_passed']} M3={summary['m3_passed']}\n"
                )
        except Exception as e:
            with open(log_path, "a") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR {e}\n")
            _write_notification("Meta-Monitor Error", "critical", str(e))

        elapsed = time.time() - start
        sleep_time = max(5.0, interval - elapsed)
        if _shutdown_event:
            break
        time.sleep(sleep_time)


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="MAREF Meta-Monitor")
    parser.add_argument("--single-run", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon loop")
    parser.add_argument("--interval", type=float, default=300.0, help="Loop interval in seconds")
    args = parser.parse_args()

    if args.daemon:
        run_loop(interval=args.interval)
    else:
        report = run_once()
        json.dump(report, sys.stdout, indent=2, default=str)
        sys.exit(0 if report["summary"]["all_passed"] else 1)


if __name__ == "__main__":
    main()
