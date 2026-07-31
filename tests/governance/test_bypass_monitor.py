"""Tests for BypassMonitor rolling-window alert logic."""

from __future__ import annotations

import time

from maref.governance.bypass_monitor import BypassMonitor


def test_record_returns_count() -> None:
    m = BypassMonitor(threshold=3, window_seconds=3600.0)
    r1 = m.record_bypass("cli", "--live")
    assert r1 == {"alert": False, "count": 1}
    r2 = m.record_bypass("mcp", "fail_mode=allow")
    assert r2 == {"alert": False, "count": 2}


def test_threshold_exceeded_triggers_alert() -> None:
    m = BypassMonitor(threshold=2, window_seconds=3600.0)
    m.record_bypass("cli", "a")
    m.record_bypass("cli", "b")
    r = m.record_bypass("cli", "c")
    assert r == {"alert": True, "count": 3}


def test_old_events_outside_window_not_counted() -> None:
    m = BypassMonitor(threshold=2, window_seconds=0.05)
    m.record_bypass("cli", "a")
    m.record_bypass("cli", "b")
    # second bypass happened inside the window — count = 2, no alert
    assert m.get_stats()["recent"] == 2
    time.sleep(0.06)
    # both events are now outside the window
    assert m.get_stats()["recent"] == 0
    r = m.record_bypass("cli", "c")
    assert r == {"alert": False, "count": 1}


def test_alert_callback_fires() -> None:
    m = BypassMonitor(threshold=1, window_seconds=3600.0)
    fired: list[dict] = []

    def cb(result: dict) -> None:
        fired.append(result)

    m.add_alert_callback(cb)
    m.record_bypass("cli", "first")
    assert len(fired) == 0
    m.record_bypass("cli", "second")
    assert len(fired) == 1
    assert fired[0] == {"alert": True, "count": 2}


def test_get_stats_structure() -> None:
    m = BypassMonitor(threshold=5, window_seconds=60.0)
    m.record_bypass("cli", "--no-dry-run")
    m.record_bypass("matrix", "reliability bypass")
    stats = m.get_stats()
    assert stats["total_recorded"] == 2
    assert stats["recent"] == 2
    assert stats["alert_count"] == 0
    assert stats["threshold"] == 5
    assert stats["window_seconds"] == 60.0
