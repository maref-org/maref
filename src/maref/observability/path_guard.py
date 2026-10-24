"""Startup / CI guard against audit-path split-brain.

Checks that every runtime writer and reader resolves to the same absolute
base, and that no path points at the legacy external ``openclaw`` tree.

Usage:
    python -m maref.observability.path_guard
    python -m maref.observability.path_guard --json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from maref import _paths


class PathConsistencyError(RuntimeError):
    """Raised when runtime paths do not agree on a single base."""


def collect_paths() -> dict[str, Any]:
    from maref.observability.audit_paths import _get_base, _get_meta_base
    from maref.observability.health_snapshot import HealthSnapshotWriter
    from maref.observability.meta_monitor import (
        _default_audit_base,
        _health_snapshot_path,
        _meta_base,
        _pulses_dir,
        _report_path,
    )
    from maref.recursive import reflexion_bridge
    from maref.recursive.agent_health import PulseWriter

    meta = _paths.get_meta_base()
    governance = _paths.get_governance_base()
    memory = _paths.get_memory_base()
    writer = HealthSnapshotWriter(interval_seconds=3600)
    pulse = PulseWriter(agent_id="path-guard", interval_seconds=3600)
    return {
        "project_root": str(_paths.get_project_root()),
        "governance_base": str(governance),
        "meta_base": str(meta),
        "memory_base": str(memory),
        "reflexion_obs": str(reflexion_bridge.OBS_FILE),
        "reflexion_lessons": str(reflexion_bridge.LESSONS_FILE),
        "audit_paths_base": str(_get_base()),
        "audit_paths_meta": str(_get_meta_base()),
        "meta_monitor_audit": str(_default_audit_base()),
        "meta_monitor_meta": str(_meta_base()),
        "health_writer": str(writer._path),  # noqa: SLF001 - guard is intentionally invasive
        "health_check": str(_health_snapshot_path()),
        "pulse_writer": str(pulse._dir),  # noqa: SLF001 - guard is intentionally invasive
        "pulse_check": str(_pulses_dir()),
        "report": str(_report_path()),
        "env": {
            "MAREF_AUDIT_PATH": os.environ.get("MAREF_AUDIT_PATH", ""),
            "MAREF_META_PATH": os.environ.get("MAREF_META_PATH", ""),
            "MAREF_RUNTIME_DIR": os.environ.get("MAREF_RUNTIME_DIR", ""),
            "MAREF_MEMORY_PATH": os.environ.get("MAREF_MEMORY_PATH", ""),
        },
    }


def validate_paths(paths: dict[str, Any] | None = None) -> list[str]:
    paths = paths or collect_paths()
    issues: list[str] = []

    for key in (
        "governance_base",
        "meta_base",
        "memory_base",
        "audit_paths_base",
        "meta_monitor_audit",
    ):
        value = Path(paths[key])
        if not value.is_absolute():
            issues.append(f"{key} is not absolute: {value}")

    if paths["governance_base"] != paths["audit_paths_base"]:
        issues.append(
            "governance base split: "
            f"_paths={paths['governance_base']} audit_paths={paths['audit_paths_base']}"
        )
    if paths["meta_base"] != paths["audit_paths_meta"]:
        issues.append(
            f"meta base split: _paths={paths['meta_base']} audit_paths={paths['audit_paths_meta']}"
        )
    if paths["meta_base"] != paths["meta_monitor_meta"]:
        issues.append(
            "meta-monitor split: "
            f"_paths={paths['meta_base']} meta_monitor={paths['meta_monitor_meta']}"
        )
    if paths["health_writer"] != paths["health_check"]:
        issues.append(
            "health snapshot split: "
            f"writer={paths['health_writer']} checker={paths['health_check']}"
        )
    if paths["pulse_writer"] != paths["pulse_check"]:
        issues.append(f"pulse split: writer={paths['pulse_writer']} checker={paths['pulse_check']}")

    legacy_markers = ("/.openclaw/", "/.openclaw", "openclaw/.openclaw")
    for key in (
        "governance_base",
        "meta_base",
        "memory_base",
        "reflexion_obs",
        "reflexion_lessons",
        "audit_paths_base",
        "audit_paths_meta",
        "meta_monitor_audit",
        "meta_monitor_meta",
        "health_writer",
        "health_check",
        "pulse_writer",
        "pulse_check",
        "report",
    ):
        value = paths[key]
        if any(marker in value for marker in legacy_markers):
            issues.append(f"{key} still points at legacy openclaw path: {value}")

    return issues


def assert_paths() -> dict[str, Any]:
    paths = collect_paths()
    issues = validate_paths(paths)
    if issues:
        raise PathConsistencyError("; ".join(issues))
    return paths


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    paths = collect_paths()
    issues = validate_paths(paths)
    if "--json" in argv:
        print(json.dumps({"paths": paths, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        for key, value in paths.items():
            if key != "env":
                print(f"{key}: {value}")
        if issues:
            print("\nISSUES:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\npath consistency: OK")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
