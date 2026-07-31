"""Audit path registry — single source of truth for all audit data paths.

Every MAREF audit/monitoring/health subsystem registers its write and read paths
here so that meta-monitor can verify path consistency (M1 check).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditPathEntry:
    subsystem: str
    description: str
    write_path: str
    read_paths: tuple[str, ...] = ()
    file_pattern: str = "*"
    expected_format: str = "jsonl"


_REGISTRY: dict[str, AuditPathEntry] = {}


def _get_base() -> Path:
    return Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))


def register(entry: AuditPathEntry) -> None:
    _REGISTRY[entry.subsystem] = entry


def get_registry() -> dict[str, AuditPathEntry]:
    return dict(_REGISTRY)


def get_write_path(subsystem: str) -> str | None:
    entry = _REGISTRY.get(subsystem)
    if entry is None:
        return None
    return _resolve(entry.write_path)


def get_read_paths(subsystem: str) -> list[str]:
    entry = _REGISTRY.get(subsystem)
    if entry is None:
        return []
    return [_resolve(p) for p in entry.read_paths]


def _resolve(path_template: str) -> str:
    base = _get_base()
    resolved = path_template.replace("{MAREF_AUDIT_PATH}", str(base))
    resolved = resolved.replace("{BASE}", str(base))
    return str(Path(resolved))


def verify_path_consistency(subsystem: str | None = None) -> list[dict[str, Any]]:
    """Verify write paths exist and match read paths. Returns issues list."""
    issues: list[dict[str, Any]] = []
    targets = {subsystem} if subsystem else set(_REGISTRY.keys())
    for name in targets:
        entry = _REGISTRY.get(name)
        if entry is None:
            issues.append({"subsystem": name, "issue": "not_registered"})
            continue
        write_path = get_write_path(name)
        if write_path is None:
            continue
        write_path_obj = Path(write_path)
        if not write_path_obj.exists():
            issues.append({
                "subsystem": name,
                "issue": "write_path_missing",
                "path": write_path,
            })
        for read_path in entry.read_paths:
            resolved_read = _resolve(read_path)
            read_path_obj = Path(resolved_read)
            if not read_path_obj.exists():
                issues.append({
                    "subsystem": name,
                    "issue": "read_path_missing",
                    "path": resolved_read,
                })
    return issues


register(AuditPathEntry(
    subsystem="health_snapshot",
    description="Health snapshot for M0 survivability assertion",
    write_path="{MAREF_AUDIT_PATH}/health_snapshot.json",
    read_paths=("{MAREF_AUDIT_PATH}/health_snapshot.json",),
    file_pattern="*.json",
    expected_format="json",
))

register(AuditPathEntry(
    subsystem="audit_logger",
    description="GovernanceStateMachine audit trail",
    write_path="{MAREF_AUDIT_PATH}/governance_audit.jsonl",
    read_paths=("{MAREF_AUDIT_PATH}/governance_audit.jsonl",),
    file_pattern="*.jsonl",
    expected_format="jsonl",
))

register(AuditPathEntry(
    subsystem="pulse_writer",
    description="Agent heartbeat pulse files",
    write_path="{MAREF_AUDIT_PATH}/pulses/",
    read_paths=("{MAREF_AUDIT_PATH}/pulses/",),
    file_pattern="*.json",
    expected_format="json",
))

register(AuditPathEntry(
    subsystem="meta_monitor",
    description="Meta-monitor self report",
    write_path=".openclaw/meta-monitor-report.json",
    read_paths=(".openclaw/meta-monitor-report.json",),
    file_pattern="*.json",
    expected_format="json",
))

register(AuditPathEntry(
    subsystem="notifications",
    description="Alert notification files",
    write_path=".openclaw/notifications/",
    read_paths=(".openclaw/notifications/",),
    file_pattern="*.json",
    expected_format="json",
))

register(AuditPathEntry(
    subsystem="gaas_audit",
    description="GaaS multi-tenant audit log",
    write_path="{MAREF_AUDIT_PATH}/gaas_audit.jsonl",
    read_paths=("{MAREF_AUDIT_PATH}/gaas_audit.jsonl",),
    file_pattern="*.jsonl",
    expected_format="jsonl",
))
