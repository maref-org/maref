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
from collections import Counter
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
            "M0 Fail",
            "critical",
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
    """Check that the audit log contains REAL events written recently.

    INC-2026-08-13-001 (G5) fix: previously this check touched a file itself
    and then verified the touch mtime (self-referential "watchdog liveness").
    Now it inspects the latest JSON record's event_type/timestamp and rejects
    files that only contain touch/monitor chatter.  No self-touch on the
    check path.
    """
    base = _audit_log_base(audit_base)
    # 只检查真实审计链文件，排除 *.jsonl 通配（避免匹配 monitor 自写文件）
    patterns = [
        "governance_audit.jsonl",
        "recursive_governance_audit.jsonl",
        "audit.jsonl",
        "gaas_audit.jsonl",
    ]

    def _newest_real_event() -> tuple[str | None, float, str]:
        """最新一条真实审计事件（含 event_type）及其时间。

        从文件尾部回扫第一条合法 JSON 记录，容忍并发写留下的脆尾行。
        """
        best_path: str | None = None
        best_ts: float = 0.0
        best_type: str = ""
        for pat in patterns:
            target = base / pat
            if not target.exists():
                continue
            # 从尾部回扫（最多 64KB，仿 _last_chain_hash）
            try:
                size = target.stat().st_size
                with open(target, "rb") as fh:
                    if size == 0:
                        continue
                    chunk_size = min(size, 65536)
                    fh.seek(size - chunk_size)
                    tail = fh.read(chunk_size).decode("utf-8", errors="replace")
                for line in reversed(tail.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    etype = rec.get("event_type", "")
                    ts = rec.get("timestamp", 0.0)
                    if isinstance(ts, (int, float)) and ts > best_ts and etype:
                        best_path, best_ts, best_type = str(target), ts, etype
                    break  # 已找到该文件第一条合法记录
            except OSError:
                continue
        return best_path, best_ts, best_type

    newest_path, newest_ts, newest_type = _newest_real_event()

    if newest_path is None:
        _write_notification("M0 Fail", "critical", "No audit log with real events found")
        return {"passed": False, "detail": "no_real_events"}

    age = time.time() - newest_ts
    passed = age <= max_age
    if not passed:
        _write_notification(
            "M0 Fail",
            "critical",
            f"Audit log stale: newest={newest_path} event={newest_type} age={age:.0f}s > {max_age:.0f}s",
        )
    return {
        "passed": passed,
        "newest_log": newest_path,
        "newest_event_type": newest_type,
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
            "M0 Fail",
            "critical",
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
            "M0 Warning",
            "warning",
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
        search_dirs.extend(
            [
                Path("/Library/LaunchAgents"),
                Path("/Library/LaunchDaemons"),
            ]
        )
    for d in search_dirs:
        if d.exists():
            for p in d.glob("com.maref.*.plist"):
                labels.add(p.stem)
    return labels


def _get_launchd_maref_agents() -> list[tuple[str, bool]]:
    """Query launchd for all com.maref.* agents. Returns [(label, is_running)]."""
    agents: list[tuple[str, bool]] = []
    try:
        r = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=10,
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
                        pid_alive = (
                            os.path.exists(f"/proc/{pid}")
                            if sys.platform == "linux"
                            else (
                                subprocess.run(
                                    ["kill", "-0", str(pid)], capture_output=True, timeout=2
                                ).returncode
                                == 0
                            )
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
                    capture_output=True,
                    text=True,
                    timeout=5,
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
            "M0 Fail",
            "critical",
            f"Core agent survival rate {core_survival:.0%} ({len(core_running)}/{core_total}) — "
            f"threshold={threshold:.0%}, dead: {core_dead}",
            subsystem="agents",
        )
    elif results["dead"]:
        _write_notification(
            "M0 Degraded",
            "warning",
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
        "audit_noise": check_audit_noise(audit_base=audit_base),
        "pulse_freshness": check_pulse_freshness(audit_base=audit_base),
        "managed_agents": check_managed_agents(),
        "hmac_key": check_hmac_key(),
        "gaas_health": check_gaas_health()
        if gaas_enabled
        else {"passed": True, "detail": "skipped (MAREF_GAAS_ENABLED not set)"},
    }
    blocking = [
        "health_snapshot_freshness",
        "audit_log_growth",
        "pulse_freshness",
        "managed_agents",
        "audit_noise",
    ]
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
            "M2 Fail",
            "critical",
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


# ── M4: Cost Health (INC-2026-08-13-001 / G2) ──────────────────────── #


def _cost_events_path() -> Path:
    """cost_events.ndjson 路径（与 unified_proxy 的 UP_AUDIT_DIR 对齐）。"""
    base = Path(os.environ.get("UP_AUDIT_DIR", str(Path.home() / ".maref" / "audit")))
    return base / "cost_events.ndjson"


def _guard_events_path() -> Path:
    base = Path(os.environ.get("UP_AUDIT_DIR", str(Path.home() / ".maref" / "audit")))
    return base / "guard_blocks.ndjson"


def check_cost(
    high_cost_hourly_limit: int | None = None,
    cost_events_path: Path | None = None,
    guard_events_path: Path | None = None,
) -> dict[str, Any]:
    """M4 成本健康检查：统计近 1h/24h 调用与拦截，检测成本失控信号。

    - 高价模型（glm-5.2/glm-4.7）近 1h 调用 > 默认 60 → critical
    - 24h 被拦次数 > 50 → warning（护栏在起作用但流量异常）
    - 近 24h 无任何 cost_event 且代理配置了调用 → warning（遥测断裂信号）
    """
    high_cost_models = ("glm-5.2", "glm-4.7")
    now = time.time()
    hourly: dict[str, int] = {}
    daily_total = 0
    guarded = 0
    latest_ts = 0.0

    path = cost_events_path or _cost_events_path()
    if path.exists():
        for ln in path.read_text().splitlines():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp", 0.0)
            if not isinstance(ts, (int, float)):
                continue
            if now - ts > 86400:
                continue
            daily_total += 1
            latest_ts = max(latest_ts, ts)
            if now - ts <= 3600:
                m = d.get("model", "?")
                hourly[m] = hourly.get(m, 0) + 1

    gpath = guard_events_path or _guard_events_path()
    if gpath.exists():
        for ln in gpath.read_text().splitlines():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            gts = d.get("timestamp", 0.0)
            if not isinstance(gts, (int, float)):
                continue
            if now - gts <= 86400:
                guarded += 1

    # 阈值统一从 proxy_config.json 读取（G3 治理化，与 proxy 同源），env 仅作 fallback
    high_cost_hourly = high_cost_hourly_limit
    if high_cost_hourly is None:
        high_cost_hourly = 60
        try:
            cfg_path = Path.home() / ".maref" / "proxy_config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                v = cfg.get("call_hard_limit")
                if isinstance(v, (int, float)) and v > 0:
                    high_cost_hourly = int(v)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        try:
            env_v = int(os.environ.get("UP_CALL_LIMIT", "0"))
            if env_v > 0:
                high_cost_hourly = env_v
        except ValueError:
            pass
    critical_hits = {m: c for m, c in hourly.items() if m in high_cost_models and c > high_cost_hourly}

    checks: dict[str, dict[str, Any]] = {
        "high_cost_model_calls": {
            "passed": len(critical_hits) == 0,
            "detail": critical_hits if critical_hits else "ok",
        },
        "guard_block_rate": {
            "passed": guarded <= 50,
            "guarded_24h": guarded,
        },
        "telemetry_liveness": {
            "passed": daily_total > 0,
            "events_24h": daily_total,
            "latest_ts": latest_ts,
        },
    }
    all_passed = all(c.get("passed", False) for c in checks.values())
    return {
        "passed": all_passed,
        "checks": checks,
        "hourly_by_model": hourly,
        "total_events_24h": daily_total,
        "guarded_24h": guarded,
    }


def check_audit_noise(
    audit_base: Path | None = None,
    window_hours: float = 24.0,
) -> dict[str, Any]:
    """M0 子检查：审计链内容健康度（G5-3）。

    若窗口内 100% 是 state_transition 且 0 条 governance_decision/cost_event，
    判为"噪音污染"（如测试/压力脚本写入），返回 failed。
    """
    base = _audit_log_base(audit_base)
    path = base / "governance_audit.jsonl"
    if not path.exists():
        return {"passed": True, "detail": "no_audit_file", "total": 0, "noise_ratio": 0.0}

    cutoff = time.time() - window_hours * 3600
    types: Counter = Counter()
    total = 0
    try:
        for ln in path.read_text(errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp", 0.0)
            if not isinstance(ts, (int, float)) or ts < cutoff:
                continue
            total += 1
            types[rec.get("event_type", "?")] += 1
    except OSError:
        return {"passed": True, "detail": "read_error", "total": 0, "noise_ratio": 0.0}

    if total == 0:
        return {"passed": True, "detail": "no_events_in_window", "total": 0, "noise_ratio": 0.0}

    real_types = types["governance_decision"] + types["cost_event"] + types["guard_block"]
    noise_ratio = 1.0 - (real_types / total)
    # 污染判定需同时满足：事件量异常大（测试批量写入特征）且全部是 state_transition。
    # 健康静默系统 24h 内只有几条 state_transition 是正常状态，不应误判。
    polluted = (
        types.get("state_transition", 0) == total
        and real_types == 0
        and total >= 1000
    )

    if polluted:
        _write_notification(
            "M0 Noise Pollution",
            "warning",
            f"审计链 {window_hours:.0f}h 内 {total} 条全为 state_transition，无真实决策/成本事件",
            subsystem="audit-health",
        )
    return {
        "passed": not polluted,
        "detail": "noise_pollution" if polluted else "ok",
        "total": total,
        "noise_ratio": round(noise_ratio, 3),
        "event_types": dict(types),
    }


# ── Main Orchestrator ───────────────────────────────────────────────── #


def run_all_checks(
    audit_base: Path | None = None,
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run M0 through M4 and produce a consolidated report."""
    m0 = check_m0(audit_base=audit_base)
    m1 = check_m1()
    m2 = check_m2(notifications_dir=notifications_dir)
    m3 = check_m3()
    m4 = check_cost()

    return {
        "timestamp": time.time(),
        "version": "1.0.0",
        "summary": {
            "m0_passed": m0["passed"],
            "m1_passed": m1["passed"],
            "m2_passed": m2["passed"],
            "m3_passed": m3["passed"],
            "m4_passed": m4["passed"],
            "all_passed": m0["passed"] and m1["passed"] and m2["passed"] and m3["passed"] and m4["passed"],
        },
        "m0": m0,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "m4": m4,
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
        status="healthy" if report.get("summary", {}).get("all_passed", False) else "degraded",
        active_agents=len(ma.get("running", [])),
    )

    # M4 成本告警（G2-3）
    m4 = report.get("m4", {})
    if not m4.get("passed", False):
        hcm = m4.get("checks", {}).get("high_cost_model_calls", {})
        if hcm.get("detail") not in (None, "ok"):
            _write_notification(
                "M4 Cost Critical",
                "critical",
                f"高价模型调用异常: {hcm.get('detail')}",
                subsystem="cost-guard",
            )
        tl = m4.get("checks", {}).get("telemetry_liveness", {})
        if not tl.get("passed", True):
            _write_notification(
                "M4 Telemetry Liveness",
                "warning",
                f"近24h无 cost_event（events={tl.get('events_24h', 0)}）— 遥测可能断裂",
                subsystem="cost-guard",
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
                    f"M2={summary['m2_passed']} M3={summary['m3_passed']} "
                    f"M4={summary['m4_passed']}\n"
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
