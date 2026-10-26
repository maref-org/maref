"""M0–M4 语义回归：不能用「没数据」冒充健康。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from maref.observability import meta_monitor as mm


def _chain_record(index: int, previous: str) -> dict:
    record = {
        "id": f"rec-{index}",
        "timestamp": time.time(),
        "event_type": "test",
        "actor": "pytest",
        "action": "append",
        "details": "x",
        "previous_hash": previous,
    }
    canonical = json.dumps(record, sort_keys=True)
    record["chain_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return record


def _write_chain(path: Path, count: int) -> None:
    previous = ""
    lines = []
    for index in range(count):
        record = _chain_record(index, previous)
        previous = record["chain_hash"]
        lines.append(json.dumps(record))
    path.write_text("\n".join(lines) + "\n")


def test_m1_reports_truncated_when_record_cap_hit(tmp_path: Path) -> None:
    _write_chain(tmp_path / "governance_audit.jsonl", 20)
    result = mm.check_audit_chain_integrity(audit_base=tmp_path, max_records=5)
    assert result["passed"] is True
    assert result["truncated"] is True


def test_m1_reports_not_truncated_when_whole_file_scanned(tmp_path: Path) -> None:
    _write_chain(tmp_path / "governance_audit.jsonl", 5)
    result = mm.check_audit_chain_integrity(audit_base=tmp_path, max_records=100)
    assert result["passed"] is True
    assert result["truncated"] is False


def test_m4_zero_guard_events_is_undefined_not_healthy(tmp_path: Path) -> None:
    now = time.time()
    cost = tmp_path / "cost.jsonl"
    cost.write_text(json.dumps({"timestamp": now, "model": "deepseek-v4-flash"}) + "\n")
    result = mm.check_cost(
        cost_events_path=cost,
        guard_events_path=tmp_path / "missing-guards.jsonl",
    )
    guard = result["checks"]["guard_block_rate"]
    assert guard["passed"] is False
    assert guard["coverage"] == "undefined"
    assert result["passed"] is False


def test_m2_uninitialized_alert_channel_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

    tracker = AlertFeedbackTracker(state_path=str(tmp_path / "tracker.json"))
    monkeypatch.setattr(mm, "_get_alert_tracker", lambda: tracker)
    monkeypatch.setattr(mm, "_write_notification", lambda *a, **k: None)
    result = mm.check_m2(notifications_dir=tmp_path / "notifications")
    assert result["alert_channel"]["status"] == "uninitialized"
    assert result["passed"] is False


def test_m2_tracker_unavailable_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    def explode():
        raise RuntimeError("tracker down")

    monkeypatch.setattr(mm, "_get_alert_tracker", explode)
    monkeypatch.setattr(mm, "_write_notification", lambda *a, **k: None)
    result = mm.check_m2(notifications_dir=tmp_path / "notifications")
    assert result["alert_channel"]["status"] == "unavailable"
    assert result["passed"] is False


def test_m2_silent_channel_is_advisory_not_failure(tmp_path: Path, monkeypatch) -> None:
    from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

    tracker = AlertFeedbackTracker(state_path=str(tmp_path / "tracker.json"))
    tracker.record_alert(name="recent", severity="warning", message="m", check_id="c")
    # Push the alert outside the 15-minute silence window.
    tracker._alert_timestamps = [time.time() - 20 * 60]
    monkeypatch.setattr(mm, "_get_alert_tracker", lambda: tracker)
    monkeypatch.setattr(mm, "_write_notification", lambda *a, **k: None)
    result = mm.check_m2(notifications_dir=tmp_path / "notifications")
    assert result["alert_channel"]["status"] == "silent"
    assert result["alert_channel"]["advisory"] is True
    assert result["passed"] is True


def test_m0_retired_and_idle_are_not_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mm.sys, "platform", "darwin")
    monkeypatch.setattr(mm, "_find_all_plist_labels", lambda: {"a", "b", "c", "d"})
    monkeypatch.setattr(mm, "_plist_keepalive_labels", lambda: {"a", "b", "c"})
    monkeypatch.setattr(mm, "_load_retired_agents", lambda: {"c"})
    monkeypatch.setattr(mm, "_get_launchd_maref_agents", lambda: [("a", True), ("b", False)])
    monkeypatch.setattr(mm, "_write_notification", lambda *a, **k: None)

    result = mm.check_managed_agents()
    assert result["retired"] == ["c"]
    assert result["dead"] == ["b"]
    assert result["idle"] == ["d"]
    assert result["active_total"] == 2
    assert result["survival_rate"] == 0.5


def test_m0_core_daemons_running_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = {"com.maref.meta-monitor", "com.maref.audit-agent"}
    monkeypatch.setattr(mm.sys, "platform", "darwin")
    monkeypatch.setattr(mm, "_find_all_plist_labels", lambda: set(labels))
    monkeypatch.setattr(mm, "_plist_keepalive_labels", lambda: set(labels))
    monkeypatch.setattr(mm, "_load_retired_agents", lambda: set())
    monkeypatch.setattr(
        mm,
        "_get_launchd_maref_agents",
        lambda: [(label, True) for label in sorted(labels)],
    )
    monkeypatch.setattr(mm, "_write_notification", lambda *a, **k: None)

    result = mm.check_managed_agents()
    assert result["passed"] is True
    assert result["survival_rate"] == 1.0
    assert result["dead"] == []
