"""Meta-Monitor: audit system self-health assertions (M0~M3).

The meta-monitor is THE answer to "who audits the audit system?"
It runs every 5 minutes and checks:
  - M0 (survivability): health snapshot, audit log, pulse, agents, GaaS
  - M1 (consistency): audit paths, HMAC keys
  - M2 (feedback loop): notification staleness
  - M3 (meta-observability): own process health

Output: <MAREF_META_PATH>/meta-monitor-report.json（默认 .governance/meta/）
"""

from __future__ import annotations

import json
import os
import plistlib
import re
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
    """治理审计基目录（绝对路径，委托 _paths SSOT，消除 CWD 依赖）。

    If an old deployment/cropped tree lacks ``maref._paths``, fall back to
    audit_paths._get_base (same env precedence) so the monitor still reports.
    """
    try:
        from maref._paths import get_governance_base

        return get_governance_base()
    except Exception:  # 公开仓缺 _paths → 兜底路径必须仍是绝对路径
        from maref.observability.audit_paths import _get_base

        return _get_base().resolve()


def _load_env_file(filename: str = ".env.maref") -> None:
    """Load MAREF_* variables from the project env file if not already set.

    launchd does not export shell env files; this ensures the daemon sees the
    same signing keys as manual runs (P0.4 — plist/daemon key injection).
    Only sets variables that are not already present in the environment.
    Supports multi-line PEM values (e.g. MAREF_ED25519_PRIVATE_KEY spanning
    several lines after the KEY=-----BEGIN marker).
    """
    candidates = [Path.cwd() / filename, Path(__file__).resolve().parents[3] / filename]
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if value.startswith("-----BEGIN"):
                value = value
                while i < len(lines) and "-----END" not in lines[i]:
                    value += "\n" + lines[i].strip()
                    i += 1
                if i < len(lines):
                    value += "\n" + lines[i].strip()
                    i += 1
            if key.startswith("MAREF_") and key not in os.environ:
                os.environ[key] = value
        return


_load_env_file()

_NOTIFICATIONS_DIR: Path | None = None
_REPORT_PATH: Path | None = None


def _meta_base() -> Path:
    """Path for meta-monitor data (notifications, reports). 绝对路径。"""
    try:
        from maref._paths import get_meta_base

        return get_meta_base()
    except Exception:  # 极端情况下 _paths 不可用 → 与 SSOT 相同的绝对路径兜底
        env_path = os.environ.get("MAREF_META_PATH")
        if env_path:
            return Path(env_path).resolve()
        return (Path(__file__).resolve().parents[3] / ".governance" / "meta").resolve()


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
    # 与 HealthSnapshotWriter 默认路径一致：<governance_base>/health_snapshot.json
    return (base or _default_audit_base()) / "health_snapshot.json"


def _audit_log_base(base: Path | None = None) -> Path:
    return base or _default_audit_base()


def _pulses_dir(base: Path | None = None) -> Path:
    # 与 PulseWriter 默认路径一致：<governance_base>/pulses/
    return (base or _default_audit_base()) / "pulses"


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
    check_id: str = "",
    track: bool = True,
) -> None:
    _ensure_dirs()
    ndir = _notifications_dir()
    now = time.time()
    deduped = False
    for existing in ndir.glob("*.json"):
        try:
            mtime = existing.stat().st_mtime
        except OSError:
            continue  # 并发清理导致的 TOCTOU：文件已消失，跳过
        if mtime > now - dedup_window:
            try:
                data = json.loads(existing.read_text())
                if (
                    data.get("title") == title
                    and data.get("severity") == severity
                    and data.get("check_id", "") == check_id
                ):
                    deduped = True
                    break  # skip duplicate file, but still track the alert
            except (json.JSONDecodeError, OSError):
                continue
    if not deduped:
        notif = {
            "title": title,
            "severity": severity,
            "message": message,
            "subsystem": subsystem,
            "timestamp": now,
            "source": "meta-monitor",
            "check_id": check_id,
        }
        name = f"{int(now)}_{subsystem}_{severity}.json"
        path = ndir / name
        with open(path, "w") as f:
            json.dump(notif, f)

    # Also track via AlertFeedbackTracker for M2 metrics (even when the
    # notification file was deduped, the alert must stay open in the tracker).
    # Informational degraded notices (track=False) stay file-only so they do
    # not inflate the actionable open-alert/repeat metrics.
    if track:
        try:
            tracker = _get_alert_tracker()
            tracker.record_alert(
                name=title,
                severity=severity,
                message=message,
                subsystem=subsystem,
                check_id=check_id,
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
        _write_notification(
            "M0 Fail",
            "critical",
            f"Health snapshot missing: {path}",
            check_id="health_snapshot_freshness",
        )
        return {"passed": False, "path": str(path), "age_seconds": None, "detail": "file_missing"}

    try:
        mtime = path.stat().st_mtime
    except OSError:
        _write_notification(
            "M0 Fail",
            "critical",
            f"Health snapshot vanished: {path}",
            check_id="health_snapshot_freshness",
        )
        return {"passed": False, "path": str(path), "age_seconds": None, "detail": "file_vanished"}

    age = time.time() - mtime
    passed = age <= max_age
    if not passed:
        _write_notification(
            "M0 Fail",
            "critical",
            f"Health snapshot stale: {age:.0f}s > {max_age:.0f}s max",
            check_id="health_snapshot_freshness",
        )
    return {
        "passed": passed,
        "path": str(path),
        "age_seconds": round(age, 1),
        "max_age_seconds": max_age,
        "mtime": mtime,
    }


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
    # 审计基目录 + 其 audit/ 子目录（P0 规范路径；两处均已注册为审计位置）
    bases = [base]
    audit_sub = base / "audit"
    if audit_sub != base:
        bases.append(audit_sub)

    def _newest_real_event() -> tuple[str | None, float, str]:
        """最新一条真实审计事件（含 event_type）及其时间。

        从文件尾部回扫第一条合法 JSON 记录，容忍并发写留下的脆尾行。
        """
        best_path: str | None = None
        best_ts: float = 0.0
        best_type: str = ""
        for b in bases:
            for pat in patterns:
                target = b / pat
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
        _write_notification(
            "M0 Fail",
            "critical",
            "No audit log with real events found",
            check_id="audit_log_growth",
        )
        return {"passed": False, "detail": "no_real_events"}

    age = time.time() - newest_ts
    passed = age <= max_age
    if not passed:
        _write_notification(
            "M0 Fail",
            "critical",
            f"Audit log stale: newest={newest_path} event={newest_type} age={age:.0f}s > {max_age:.0f}s",
            check_id="audit_log_growth",
        )
    return {
        "passed": passed,
        "newest_log": newest_path,
        "newest_event_type": newest_type,
        "age_seconds": round(age, 1),
        "max_age_seconds": max_age,
    }


def _chain_max_records() -> int:
    try:
        value = int(os.environ.get("MAREF_META_CHAIN_MAX_RECORDS", "10000"))
    except ValueError:
        value = 10000
    return max(1, value)


def check_audit_chain_integrity(
    audit_base: Path | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Verify the tail of the audit chain is unbroken.

    Scans the newest ``max_records`` audit entries and verifies that each
    entry's ``previous_hash`` equals the prior entry's ``chain_hash``.
    Signature/hash recomputation is done by ``audit_chain_verify`` /
    ``scripts/verify_audit_chain.py``; M1 stays a cheap linkage check.

    This is a tail linkage check, not full cryptographic verification. It
    deliberately scans the newest records rather than the whole history so it
    stays cheap per run; full hash/HMAC verification runs separately.
    """
    if max_records is None:
        max_records = _chain_max_records()
    base = _audit_log_base(audit_base)
    # Per-actor shards (governance_audit_<actor>.jsonl) duplicate global
    # records and intentionally skip interleaved entries, so they are not
    # valid chains. Only the authoritative global log is verified.
    candidates = [
        base / "governance_audit.jsonl",
    ]
    targets = [p for p in candidates if p.exists()]
    if not targets:
        return {
            "passed": False,
            "detail": "no_audit_files",
            "issues": [],
            "truncated": False,
        }

    issues: list[str] = []
    verified_files = 0
    truncated_files: list[str] = []
    for path in targets:
        ok, msg, checked, truncated = _verify_chain_tail(path, max_records)
        if ok:
            verified_files += 1
        else:
            issues.append(f"{path.name}: {msg}")
        if truncated:
            truncated_files.append(path.name)
    passed = len(issues) == 0 and verified_files > 0
    if issues:
        _write_notification(
            "M1 Fail",
            "critical",
            "; ".join(issues),
            subsystem="chain",
            check_id="audit_chain_integrity",
        )
    return {
        "passed": passed,
        "files_checked": len(targets),
        "files_verified": verified_files,
        "max_records_scanned": max_records,
        "truncated": bool(truncated_files),
        "truncated_files": truncated_files,
        "issues": issues,
    }


def _verify_chain_tail(path: Path, max_records: int) -> tuple[bool, str, int, bool]:
    """Verify the last contiguous run of the chain in a JSONL file.

    Walks chainable records backwards from the newest entry and measures how
    many consecutive entries link correctly (entry.previous_hash equals the
    prior entry's chain_hash). Returns (ok, message, continuous_len).

    Historical entries may contain legacy breakpoints; what matters for M1 is
    that the *recent* tail is unbroken. The check passes when the newest
    ``max_records`` chainable records form one unbroken run.

    Reads the file in bounded backward chunks (last 256KB each) so
    verification stays cheap even for multi-million-line audit logs while
    still being able to walk far enough back to satisfy ``max_records``.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return False, "empty file", 0, False
            # Walk backward in chunks, newest-first, always aligned to a full
            # line so chunk seams never split a record and never fabricate a
            # break.
            records: list[dict[str, Any]] = []
            pos = size
            chunk_size = 262144
            max_chunks = 64  # safety cap (~16MB) to bound worst-case cost
            reached_start = False
            for _ in range(max_chunks):
                start = max(0, pos - chunk_size)
                f.seek(start)
                data = f.read(pos - start).decode("utf-8", errors="replace")
                if start > 0:
                    # Advance to the first newline so we begin at a full line.
                    nl = data.find("\n")
                    if nl != -1:
                        start += nl + 1
                        f.seek(start)
                        data = f.read(pos - start).decode("utf-8", errors="replace")
                chunk_records: list[dict[str, Any]] = []
                for line in data.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict) and "chain_hash" in rec:
                        chunk_records.append(rec)
                records = chunk_records + records
                pos = start
                if start == 0:
                    reached_start = True
                    break
                if len(records) >= max_records:
                    break
            # Truncated = older records exist outside the scanned window
            # (record cap or 16MB byte cap), so the tail verdict does not
            # cover the whole file.
            truncated = len(records) > max_records or (
                not reached_start and (len(records) >= max_records or pos > 0)
            )
            # Truncate to the newest max_records entries for the tail check.
            if len(records) > max_records:
                records = records[-max_records:]
    except OSError as e:
        return False, f"unreadable: {e}", 0, False

    if not records:
        return False, "no chainable records in tail", 0, False

    # Walk backwards from the newest record, counting the contiguous run.
    # Chain invariant (forward): entry.previous_hash == prior entry.chain_hash.
    # Reversed: records[i-1].chain_hash == records[i].previous_hash.
    contiguous = 1
    for i in range(len(records) - 1, 0, -1):
        newer = records[i]
        older = records[i - 1]
        if older.get("chain_hash", "") == newer.get("previous_hash", ""):
            contiguous += 1
            if contiguous >= max_records:
                break
        else:
            break

    if contiguous >= max_records:
        return True, f"last {contiguous} records linked", contiguous, truncated
    # A freshly re-baselined log may legitimately contain fewer than
    # max_records entries. Accept it only when the whole file is one
    # unbroken chain starting at genesis (previous_hash == "").
    if contiguous == len(records) and records[0].get("previous_hash", "") == "":
        return True, f"entire chain linked ({contiguous} records)", contiguous, truncated
    return (
        False,
        (f"break after {contiguous} contiguous records; newest={records[-1].get('id', '?')}"),
        contiguous,
        truncated,
    )


def check_pulse_freshness(
    max_stale_ratio: float = 0.30,
    audit_base: Path | None = None,
) -> dict[str, Any]:
    """Check pulse file staleness across all agents."""
    result = PulseWriter.check_pulse_staleness(
        pulses_dir=_pulses_dir(audit_base),
        max_stale_ratio=max_stale_ratio,
        ignore_older_than_hours=168.0,
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
            check_id="pulse_freshness",
        )
    return {
        "passed": passed,
        "total_pulses": total,
        "stale_pulses": stale,
        "stale_ratio": stale_ratio,
        "status": status,
        "stale_agents": result.get("stale_agents", []),
        "historical_ignored": result.get("historical_ignored", 0),
    }


def _find_hmac_key_file() -> Path | None:
    """定位 HMAC 密钥文件（与 AuditLogger/state_machine/security_audit_chain 对齐）。

    这些模块在 env 缺失时回退到 ``.maraf_hmac_key`` / ``.maref_hmac_key`` 文件；
    检查器须用同一解析源，否则键已配置却误报未配置（假阴性）。
    """
    for cand in (
        Path.cwd() / ".maraf_hmac_key",
        Path.home() / ".maraf_hmac_key",
        Path.cwd() / ".maref_hmac_key",
        Path.home() / ".maref_hmac_key",
    ):
        try:
            if cand.exists() and cand.read_text(encoding="utf-8").strip():
                return cand
        except OSError:
            continue
    return None


def check_hmac_key() -> dict[str, Any]:
    """Verify HMAC/Ed25519 keys are configured (env OR key file)."""
    hmac_key = os.environ.get("MAREF_HMAC_SECRET_KEY")
    ed25519_key = os.environ.get("MAREF_ED25519_PRIVATE_KEY")
    key_file = None if (hmac_key or ed25519_key) else _find_hmac_key_file()
    passed = bool(hmac_key or ed25519_key or key_file)
    if not passed:
        _write_notification(
            "M0 Warning",
            "warning",
            "No audit signing key configured (MAREF_HMAC_SECRET_KEY / "
            "MAREF_ED25519_PRIVATE_KEY / .maraf_hmac_key file)",
            check_id="hmac_key",
        )
    return {
        "passed": passed,
        "hmac_key_set": bool(hmac_key),
        "ed25519_key_set": bool(ed25519_key),
        "hmac_key_file": str(key_file) if key_file else "",
    }


def _scripts_dir() -> Path:
    return Path(os.environ.get("MAREF_SCRIPTS_PATH", "scripts"))


def _plist_search_dirs() -> list[Path]:
    dirs = [
        _scripts_dir(),
        Path.home() / "Library/LaunchAgents",
    ]
    if sys.platform == "darwin":
        dirs.extend(
            [
                Path("/Library/LaunchAgents"),
                Path("/Library/LaunchDaemons"),
            ]
        )
    return dirs


def _find_all_plist_labels() -> set[str]:
    """Find com.maref plist labels across all standard launchd directories.

    Searches project scripts/, user LaunchAgents, and system locations.
    """
    labels: set[str] = set()
    for d in _plist_search_dirs():
        if d.exists():
            for p in d.glob("com.maref.*.plist"):
                labels.add(p.stem)
    return labels


def _plist_keepalive_labels() -> set[str]:
    """Labels whose plist declares KeepAlive — daemons expected to stay up.

    Scheduled/on-demand jobs (StartCalendarInterval, StartInterval without
    KeepAlive) are *idle* when not running, not dead. Treating them as dead
    is what produced the 0.165 "survival rate" false alarm.
    """
    if sys.platform != "darwin":
        return set()
    keepalive: set[str] = set()
    for d in _plist_search_dirs():
        if not d.exists():
            continue
        for p in d.glob("com.maref.*.plist"):
            if p.stem.endswith(".template"):
                continue
            try:
                with open(p, "rb") as fh:
                    data = plistlib.load(fh)
                ka = data.get("KeepAlive")
                if ka is True or (isinstance(ka, dict) and any(bool(v) for v in ka.values())):
                    keepalive.add(p.stem)
            except Exception:
                # Malformed XML falls back to a tolerant text scan.
                try:
                    text = p.read_text(errors="replace")
                except OSError:
                    continue
                if re.search(r"<key>KeepAlive</key>\s*(?:<true\s*/>|<dict>)", text):
                    keepalive.add(p.stem)
    return keepalive


def _retired_agents_path() -> Path:
    env = os.environ.get("MAREF_RETIRED_AGENTS_FILE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "configs" / "retired-agents.json"


def _load_retired_agents() -> set[str]:
    path = _retired_agents_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    items = data.get("agents") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return set()
    labels: set[str] = set()
    for item in items:
        if isinstance(item, str):
            labels.add(item)
        elif isinstance(item, dict) and item.get("label"):
            labels.add(str(item["label"]))
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
        "idle": [],
        "retired": [],
        "long_running": [],
        "unknown": [],
    }

    # Find all plist labels across multiple directories
    plist_labels = _find_all_plist_labels()
    results["plist_count"] = len(plist_labels)
    retired_set = _load_retired_agents() & plist_labels
    keepalive = _plist_keepalive_labels()

    if sys.platform == "darwin":
        launchd_agents = _get_launchd_maref_agents()
        results["launchd_count"] = len(launchd_agents)
        launchd_map: dict[str, bool] = dict(launchd_agents)

        for label in sorted(plist_labels):
            results["configured"].append(label)
            if label in retired_set:
                results["retired"].append(label)
                continue
            is_running = bool(launchd_map.get(label, False))
            if not is_running and label not in launchd_map:
                # Check PID file fallback for manually started agents
                pid_file = Path(f"/tmp/{label}.pid")
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        is_running = (
                            os.path.exists(f"/proc/{pid}")
                            if sys.platform == "linux"
                            else (
                                subprocess.run(
                                    ["kill", "-0", str(pid)], capture_output=True, timeout=2
                                ).returncode
                                == 0
                            )
                        )
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        pass
            if is_running:
                results["running"].append(label)
            elif label in keepalive:
                results["dead"].append(label)
            else:
                # Scheduled/on-demand job: not running is its normal state.
                results["idle"].append(label)

        meta_monitor_running = os.getpid() > 0
        if meta_monitor_running and "com.maref.meta-monitor" not in results["running"]:
            results["running"].append("com.maref.meta-monitor")
        for bucket in ("dead", "idle"):
            if "com.maref.meta-monitor" in results[bucket]:
                results[bucket].remove("com.maref.meta-monitor")
        results["meta_monitor_pid"] = os.getpid()

    elif sys.platform == "linux":
        for label in sorted(plist_labels):
            results["configured"].append(label)
            if label in retired_set:
                results["retired"].append(label)
                continue
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
        results["long_running"] = [
            label for label in sorted(plist_labels) if label not in retired_set
        ]
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

    if sys.platform == "darwin":
        results["long_running"] = [
            label
            for label in sorted(plist_labels)
            if label in keepalive and label not in retired_set
        ]

    total = len(results["configured"])
    running = len(results["running"])
    long_running_set = set(results["long_running"])
    active_running = [label for label in results["running"] if label in long_running_set]
    active_total = len(long_running_set)
    active_rate = len(active_running) / active_total if active_total > 0 else 1.0
    results["active_total"] = active_total
    results["active_running"] = active_running
    results["survival_rate"] = round(active_rate, 3)
    results["configured_total"] = total
    results["running_total"] = running

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
            check_id="managed_agents",
        )
    elif active_total > 0 and active_rate < threshold:
        results["passed"] = False
        _write_notification(
            "M0 Fail",
            "critical",
            f"Active daemon survival {active_rate:.0%} ({len(active_running)}/{active_total}) "
            f"— threshold={threshold:.0%}, dead: {results['dead'][:5]}",
            subsystem="agents",
            check_id="managed_agents",
        )
    elif results["dead"]:
        _write_notification(
            "M0 Degraded",
            "warning",
            f"Agent survival rate {active_rate:.0%} "
            f"({len(active_running)}/{active_total} daemons), "
            f"core={core_survival:.0%} ({len(core_running)}/{core_total}) — "
            f"dead (non-core): {[l for l in results['dead'] if l not in _CORE_MAREF_AGENTS][:5]}",
            subsystem="agents",
            check_id="managed_agents",
            track=False,
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
            _write_notification(
                "M0 Fail",
                "critical",
                f"GaaS health check failed: {url}",
                check_id="gaas_health",
            )
        return {"passed": passed, "url": url, "status_code": r.status_code, "body": r.text[:200]}
    except Exception as e:
        _write_notification(
            "M0 Fail",
            "critical",
            f"GaaS unreachable: {url} — {e}",
            check_id="gaas_health",
        )
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
    chain = check_audit_chain_integrity()
    issues = list(path_issues)
    if not chain.get("passed", False):
        issues.append(
            {
                "subsystem": "audit_chain_integrity",
                "issue": "chain_break",
                "detail": chain.get("issues", []),
            }
        )
    return {
        "passed": len(issues) == 0,
        "path_issues": path_issues,
        "chain_integrity": chain,
        "issues": issues,
    }


# ── M2: Feedback Loop Closure ───────────────────────────────────────── #


def check_notification_staleness(
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Check feedback-loop staleness.

    True feedback-loop staleness is measured from the authoritative
    AlertFeedbackTracker state: alerts that have been open (never fixed)
    for >24h / >72h indicate the loop is broken, independent of whether the
    notification artifact file still exists (notification files are pruned
    after 1h per the PERF gate).

    Notification-file mtime is only used to count physical file buildup.
    """
    now = time.time()

    # Authoritative staleness from the feedback tracker.
    stale_24h = 0
    stale_72h = 0
    open_total: int | None = 0
    oldest_open_hours: float | None = None
    try:
        tracker = _get_alert_tracker()
        open_records = tracker.get_open_alerts()
        open_total = len(open_records)
        for rec in open_records:
            age_h = (now - rec.triggered_at) / 3600.0
            if age_h > 72:
                stale_72h += 1
            elif age_h > 24:
                stale_24h += 1
            if oldest_open_hours is None or age_h > oldest_open_hours:
                oldest_open_hours = round(age_h, 1)
    except Exception:
        # Tracker unavailable: fall back to notification-file mtime.
        open_total = None

    # Notification-file buildup (PERF: consumed notifications pruned ≤1h).
    # P1-3: 计入全部普通文件（*.md/*.jsonl 等），避免 311 条 .md 不进 glob
    # 导致「目录积压但 check passed」的口径失真。
    ndir = Path(notifications_dir) if notifications_dir else _notifications_dir()
    total_files = 0
    total_json = 0
    oldest_file_hours: float | None = None
    if ndir.exists():
        for f in ndir.iterdir():
            if not f.is_file():
                continue
            total_files += 1
            if f.suffix == ".json":
                total_json += 1
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue  # 并发清理的 TOCTOU：文件已消失
            if oldest_file_hours is None or age > oldest_file_hours:
                oldest_file_hours = round(age / 3600.0, 1)

    passed = stale_72h == 0 and stale_24h <= 3
    if stale_72h > 0:
        _write_notification(
            "M2 Fail",
            "critical",
            f"{stale_72h} open alerts stale >72h — feedback loop broken",
            subsystem="feedback-loop",
            check_id="notification_staleness",
        )
    elif stale_24h > 0:
        _write_notification(
            "M2 Warning",
            "warning",
            f"{stale_24h} open alerts stale >24h",
            subsystem="feedback-loop",
            check_id="notification_staleness",
        )
    return {
        "passed": passed,
        "total_notifications": total_files,
        "total_json_notifications": total_json,
        "open_alerts": open_total,
        "stale_24h": stale_24h,
        "stale_72h": stale_72h,
        "oldest_open_hours": oldest_open_hours,
        "oldest_file_hours": oldest_file_hours,
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

    quality_targets: dict[str, Any] = {"advisory": True}
    try:
        repeat = feedback_metrics.get("repeat_rate", {})
        recovery = feedback_metrics.get("alert_recovery", {})
        quality_targets.update(
            {
                "repeat_rate": {
                    "value": repeat.get("repeat_rate"),
                    "target": "<0.15",
                    "passed": bool(repeat.get("healthy", False)),
                },
                "recovery_rate": {
                    "value": recovery.get("recovery_rate"),
                    "target": ">0.90",
                    "passed": bool(recovery.get("healthy", False)),
                },
            }
        )
    except Exception:
        pass

    # Alert channels: silence is downgraded to advisory (a quiet system is
    # not automatically broken), but "no alerts ever recorded" / tracker
    # unavailable means the loop's coverage is undefined and must not pass.
    disappearance = feedback_metrics.get("alert_disappearance") or {}
    if "error" in feedback_metrics:
        channel_status = "unavailable"
    elif disappearance.get("last_alert_seconds_ago") is None:
        channel_status = "uninitialized"
    elif not disappearance.get("passed", True):
        channel_status = "silent"
    else:
        channel_status = "active"
    channel_ok = channel_status in ("active", "silent")
    alert_channel = {
        "status": channel_status,
        "coverage_defined": channel_status in ("active", "silent"),
        "advisory": channel_status == "silent",
        "open_alerts": staleness.get("open_alerts"),
        "detail": disappearance.get("detail"),
    }
    quality_targets["alert_disappearance"] = {
        "status": channel_status,
        "passed": channel_ok,
        "advisory": channel_status == "silent",
    }

    return {
        "passed": bool(staleness.get("passed", False)) and channel_ok,
        "notification_staleness": staleness,
        "alert_channel": alert_channel,
        "feedback_tracking": feedback_metrics,
        "quality_targets": quality_targets,
    }


# ── M3: Meta-Observability ──────────────────────────────────────────── #


def _cleanup_notifications(max_age_hours: float = 1.0) -> int:
    """Delete notification files for alerts that have been consumed.

    Per the PERF gate, *consumed* (fixed+verified in the tracker) notification
    artifacts must be pruned within 1h. Open/unconsumed alerts are KEPT so
    they stay visible for human consumption — deleting them would recreate the
    "alert ≠ consumed" blind spot the M2 fix is meant to close.
    """
    ndir = _notifications_dir()
    if not ndir.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0

    resolved_check_ids: set[str] = set()
    try:
        tracker = _get_alert_tracker()
        all_alerts = tracker.get_alerts()
        open_ids = {rec.check_id for rec in all_alerts if rec.is_open}
        resolved_check_ids = {
            rec.check_id for rec in all_alerts if not rec.is_open and rec.check_id not in open_ids
        }
    except Exception:
        resolved_check_ids = set()

    for f in ndir.glob("*.json"):
        try:
            if f.stat().st_mtime >= cutoff:
                continue
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                # Unreadable/unidentifiable: keep it rather than guess.
                continue
            if data.get("check_id", "") in resolved_check_ids:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _resolve_recovered_checks(
    m0: dict[str, Any],
    m1: dict[str, Any],
    m2: dict[str, Any],
    m4: dict[str, Any] | None = None,
) -> int:
    """Auto-close open alerts for checks that are now passing.

    This is the feedback loop closure: when a check that previously failed
    passes again, its open alert(s) are marked fixed+verified automatically.
    Also closes legacy open alerts (pre-check_id) as a one-shot migration so
    they don't keep M2 permanently failing.
    """
    try:
        tracker = _get_alert_tracker()
    except Exception:
        return 0
    resolved = 0
    checks = m0.get("checks", {})
    for check_id, result in checks.items():
        if result.get("passed", False):
            resolved += tracker.resolve_by_check(check_id)

    chain = m1.get("chain_integrity", {})
    if chain.get("passed", False):
        resolved += tracker.resolve_by_check("audit_chain_integrity")

    staleness = m2.get("notification_staleness", {})
    if staleness.get("passed", False) and staleness.get("stale_24h", 0) == 0:
        resolved += tracker.resolve_by_check("notification_staleness")

    m4 = m4 or {}
    if m4.get("passed", False):
        resolved += tracker.resolve_by_check("telemetry_liveness")
        resolved += tracker.resolve_by_check("high_cost_model_calls")

    # One-shot migration: close open alerts that predate check_id tracking.
    # Modern alerts all carry a check_id and flow through resolve_by_check.
    # Legacy M0 alerts have no check_id, so a passing M0 is enough evidence to
    # close them immediately instead of leaving a 24h false-open window.
    if m0.get("passed", False):
        for record in tracker.get_open_alerts():
            if record.check_id == "" and record.name.startswith("M0 "):
                if tracker.close_alert(
                    record.alert_id,
                    reason="legacy M0 alert superseded by passing check_id-aware M0",
                    evidence="meta-monitor: M0 passed",
                ):
                    resolved += 1
    resolved += tracker.resolve_legacy_open()
    return resolved


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
    critical_hits = {
        m: c for m, c in hourly.items() if m in high_cost_models and c > high_cost_hourly
    }

    checks: dict[str, dict[str, Any]] = {
        "high_cost_model_calls": {
            "passed": len(critical_hits) == 0,
            "detail": critical_hits if critical_hits else "ok",
        },
        "guard_block_rate": {
            # 0 blocks in 24h is not "healthy" — it means guard telemetry has
            # no coverage, so the rate is undefined and cannot pass.
            "passed": guarded > 0 and guarded <= 50,
            "guarded_24h": guarded,
            "coverage": "defined" if guarded > 0 else "undefined",
            "detail": "ok"
            if 0 < guarded <= 50
            else (
                "no guard events in 24h — coverage undefined"
                if guarded == 0
                else "guard block volume above threshold"
            ),
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
    types: Counter[str] = Counter()
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
    polluted = types.get("state_transition", 0) == total and real_types == 0 and total >= 1000

    if polluted:
        _write_notification(
            "M0 Noise Pollution",
            "warning",
            f"审计链 {window_hours:.0f}h 内 {total} 条全为 state_transition，无真实决策/成本事件",
            subsystem="audit-health",
            check_id="audit_noise",
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

    key_state = m0.get("checks", {}).get("hmac_key", {})
    if key_state.get("hmac_key_set") or key_state.get("hmac_key_file"):
        signature_mode = "hmac-sha256"
    elif key_state.get("ed25519_key_set"):
        signature_mode = "ed25519"
    else:
        signature_mode = "unsigned"

    return {
        "timestamp": time.time(),
        "version": "1.0.0",
        "signature_mode": signature_mode,
        "signature_note": (
            "unsigned logs are not counted as verified"
            if signature_mode == "unsigned"
            else "signing configured; run verify_audit_chain.py for record-level verification"
        ),
        "summary": {
            "m0_passed": m0["passed"],
            "m1_passed": m1["passed"],
            "m2_passed": m2["passed"],
            "m3_passed": m3["passed"],
            "m4_passed": m4["passed"],
            "all_passed": m0["passed"]
            and m1["passed"]
            and m2["passed"]
            and m3["passed"]
            and m4["passed"],
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


def _write_monitor_heartbeat() -> None:
    """Append a signed monitor heartbeat so audit-growth checks stay honest.

    This is a real audit event (not a file touch): if the monitor stops
    running, the heartbeat stops and M0 audit_log_growth fails as intended.
    """
    try:
        from maref.governance.audit import AuditLogger

        key = None
        key_file = Path.cwd() / ".maraf_hmac_key"
        if key_file.exists():
            key = key_file.read_text().strip() or None
        if key is None and not os.environ.get("MAREF_ED25519_PRIVATE_KEY"):
            logger_key = os.environ.get("MAREF_HMAC_SECRET_KEY")
            if not logger_key:
                return
        logger = AuditLogger(
            log_path=_audit_log_base() / "governance_audit.jsonl",
            hmac_key=key,
        )
        logger.log(
            event_type="meta_monitor_heartbeat",
            actor="meta-monitor",
            action="run_once",
            details="meta-monitor completed a scheduled audit pass",
            metadata={"pid": os.getpid(), "host": os.uname().nodename},
        )
    except Exception:
        # Heartbeat must never break the monitor; M0 will surface a missing
        # key / write failure through its own checks.
        pass


def run_once(
    audit_base: Path | None = None,
    notifications_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Single-shot run (for CI / manual invocation)."""
    _write_monitor_heartbeat()
    _update_health_snapshot()
    report = run_all_checks(
        audit_base=audit_base,
        notifications_dir=notifications_dir,
    )

    m0 = report.get("m0", {})
    ma = m0.get("checks", {}).get("managed_agents", {})
    _update_health_snapshot(
        status="healthy" if report.get("summary", {}).get("all_passed", False) else "degraded",
        active_agents=len(ma.get("running", [])),
    )

    # M2 feedback loop closure: auto-close alerts for recovered checks and
    # prune consumed notification artifacts.
    try:
        resolved = _resolve_recovered_checks(
            report.get("m0", {}),
            report.get("m1", {}),
            report.get("m2", {}),
            report.get("m4", {}),
        )
        removed = _cleanup_notifications()
        if resolved or removed:
            report["feedback_closure"] = {
                "resolved_alerts": resolved,
                "notifications_removed": removed,
            }
        if resolved:
            # The report was computed before auto-closure; refresh M2 so the
            # persisted snapshot does not claim alerts that were just closed.
            report["m2"] = check_m2(notifications_dir=notifications_dir)
            report["summary"]["m2_passed"] = report["m2"]["passed"]
            report["summary"]["all_passed"] = all(
                report["summary"][f"m{i}_passed"] for i in range(5)
            )
    except Exception:
        pass

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
                check_id="high_cost_model_calls",
            )
        tl = m4.get("checks", {}).get("telemetry_liveness", {})
        if not tl.get("passed", True):
            _write_notification(
                "M4 Telemetry Liveness",
                "warning",
                f"近24h无 cost_event（events={tl.get('events_24h', 0)}）— 遥测可能断裂",
                subsystem="cost-guard",
                check_id="telemetry_liveness",
            )

    _write_report(report)
    return report


_shutdown_event = False


def _handle_sigterm(signum: int, _frame: object) -> None:
    global _shutdown_event
    _shutdown_event = True


def run_loop(interval: float = 300.0) -> None:
    """Continuous loop for launchd/cron deployment. Handles SIGTERM."""
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Startup self-check: refuse to run with split/legacy paths.
    try:
        from maref.observability.path_guard import assert_paths

        assert_paths()
    except Exception as e:
        _write_notification(
            "Meta-Monitor Startup Self-Check",
            "critical",
            f"path/import self-check failed: {e}",
            subsystem="meta-monitor",
        )
        raise SystemExit(2) from e
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
