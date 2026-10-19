from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "triage_archived_alerts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("triage_archived_alerts", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matches_only_same_title_and_close_timestamp() -> None:
    module = _load_module()
    archived = [("M2 Notification Staleness", 1_000.0)]

    assert module._matches_archived_alert("M2 Notification Staleness", 1_000.0, archived)
    assert not module._matches_archived_alert("M4 Telemetry Liveness", 1_000.0, archived)
    assert not module._matches_archived_alert("M2 Notification Staleness", 5_000.0, archived)


def test_missing_timestamp_is_not_treated_as_a_match() -> None:
    module = _load_module()
    archived = [("M1 Audit Chain Integrity", None)]

    assert not module._matches_archived_alert("M1 Audit Chain Integrity", 1_000.0, archived)
    assert not module._matches_archived_alert("M1 Audit Chain Integrity", None, archived)


def test_title_match_is_case_and_whitespace_insensitive() -> None:
    module = _load_module()
    archived = [("  m2 notification staleness ", 1_000.0)]

    assert module._matches_archived_alert("M2 Notification Staleness", 1_000.0, archived)
