"""Tests for the meta-monitor engine (M0~M3 checks)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import maref.observability.meta_monitor as meta_monitor
from maref.observability.audit_paths import (
    AuditPathEntry,
    get_registry,
    register,
    verify_path_consistency,
)
from maref.observability.health_snapshot import HealthSnapshotWriter
from maref.observability.meta_monitor import (
    check_audit_log_growth,
    check_gaas_health,
    check_health_snapshot_freshness,
    check_hmac_key,
    check_notification_staleness,
    check_pulse_freshness,
    run_all_checks,
)
from maref.recursive.agent_health import PulseWriter


class TestM0HealthSnapshotFreshness:
    def test_healthy_snapshot_passes(self, tmp_path: Path) -> None:
        writer = HealthSnapshotWriter(snapshot_path=tmp_path / "health_snapshot.json")
        writer.write_snapshot()
        result = check_health_snapshot_freshness(max_age=120.0, audit_base=tmp_path)
        assert result["passed"] is True
        assert result["age_seconds"] < 5

    def test_stale_snapshot_fails(self, tmp_path: Path) -> None:
        writer = HealthSnapshotWriter(snapshot_path=tmp_path / "health_snapshot.json")
        writer.write_snapshot()
        old_mtime = time.time() - 300
        os.utime(tmp_path / "health_snapshot.json", (old_mtime, old_mtime))
        result = check_health_snapshot_freshness(max_age=10.0, audit_base=tmp_path)
        assert result["passed"] is False

    def test_missing_snapshot_fails(self, tmp_path: Path) -> None:
        result = check_health_snapshot_freshness(max_age=10.0, audit_base=tmp_path)
        assert result["passed"] is False
        assert result["detail"] == "file_missing"


class TestM0AuditLogGrowth:
    def test_recent_audit_log_passes(self, tmp_path: Path) -> None:
        log = tmp_path / "audit.jsonl"
        log.write_text("")
        result = check_audit_log_growth(max_age=300.0, audit_base=tmp_path)
        assert result["passed"] is True

    def test_stale_audit_log_fails(self, tmp_path: Path) -> None:
        log = tmp_path / "audit.jsonl"
        log.touch()
        old_mtime = time.time() - 600
        os.utime(log, (old_mtime, old_mtime))
        result = check_audit_log_growth(max_age=60.0, audit_base=tmp_path)
        assert result["passed"] is False


class TestM0PulseFreshness:
    def test_no_pulses_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d_path = Path(d)
            result = check_pulse_freshness(max_stale_ratio=0.30, audit_base=d_path)
            assert result["passed"] is True

    def test_all_fresh_pulses_passes(self, tmp_path: Path) -> None:
        pulses_dir = tmp_path / "pulses"
        pw = PulseWriter(agent_id="test-agent", pulses_dir=pulses_dir, interval_seconds=30.0)
        pw.write_pulse()

        result = check_pulse_freshness(max_stale_ratio=0.30, audit_base=tmp_path)
        assert result["passed"] is True
        assert result["total_pulses"] >= 1
        assert result["stale_pulses"] == 0

    def test_stale_pulse_detected(self, tmp_path: Path) -> None:
        pulses_dir = tmp_path / "pulses"
        pulses_dir.mkdir(parents=True, exist_ok=True)
        (pulses_dir / "stale-agent.json").write_text(
            json.dumps({"agent": "stale-agent", "timestamp": time.time() - 120, "interval": 30.0}),
        )
        result = check_pulse_freshness(max_stale_ratio=0.0, audit_base=tmp_path)
        assert result["stale_pulses"] >= 1
        assert "stale-agent" in result["stale_agents"]


class TestM0HmacKey:
    def test_key_present_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-key-123")
        result = check_hmac_key()
        assert result["passed"] is True
        assert result["hmac_key_set"] is True

    def test_ed25519_key_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_ED25519_PRIVATE_KEY", "test-ed25519-key")
        result = check_hmac_key()
        assert result["passed"] is True
        assert result["ed25519_key_set"] is True

    def test_no_key_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        monkeypatch.delenv("MAREF_ED25519_PRIVATE_KEY", raising=False)
        result = check_hmac_key()
        assert result["passed"] is False


class TestM0ManagedAgents:
    def test_configures_plist_list(self) -> None:
        from maref.observability.meta_monitor import check_managed_agents
        result = check_managed_agents()
        assert "configured" in result
        assert "plist_count" in result
        assert "running" in result
        assert "dead" in result
        assert "unknown" in result


class TestM2NotificationStaleness:
    def _stale_tracker(self, age_hours: float) -> object:
        """Build an AlertFeedbackTracker with one open alert aged age_hours."""
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

        tracker = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        tracker.record_alert(
            name="Test Stale Alert",
            severity="critical",
            message="test",
            check_id="test_stale_check",
        )
        record = tracker.get_open_alerts()[0]
        record.triggered_at = time.time() - age_hours * 3600
        return tracker

    def test_no_notifications_passes(self, tmp_path: Path) -> None:
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

        clean = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        with patch.object(meta_monitor, "_get_alert_tracker", return_value=clean):
            result = check_notification_staleness(notifications_dir=tmp_path / "notifications")
        assert result["passed"] is True
        assert result["total_notifications"] == 0
        assert result["open_alerts"] == 0

    def test_fresh_notifications_pass(self, tmp_path: Path) -> None:
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

        notif_dir = tmp_path / "notifications"
        notif_dir.mkdir(parents=True)
        (notif_dir / "test.json").write_text(json.dumps({"ts": time.time()}))
        clean = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        with patch.object(meta_monitor, "_get_alert_tracker", return_value=clean):
            result = check_notification_staleness(notifications_dir=notif_dir)
        assert result["passed"] is True

    def test_old_notification_fails(self, tmp_path: Path) -> None:
        """Feedback-loop staleness is measured from open alerts, not files."""
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

        notif_dir = tmp_path / "notifications"
        notif_dir.mkdir(parents=True)
        nf = notif_dir / "stale.json"
        nf.write_text(json.dumps({"ts": time.time() - 300000}))
        old_mtime = time.time() - 300000
        os.utime(nf, (old_mtime, old_mtime))
        clean = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        with patch.object(meta_monitor, "_get_alert_tracker", return_value=clean):
            result = check_notification_staleness(notifications_dir=notif_dir)
        assert result["passed"] is True  # stale file alone does not fail

    def test_old_open_alert_fails(self, tmp_path: Path) -> None:
        """An open alert aged >72h must fail the staleness check."""

        with patch.object(meta_monitor, "_get_alert_tracker",
                          return_value=self._stale_tracker(age_hours=73)):
            result = check_notification_staleness(notifications_dir=tmp_path / "notifications")
        assert result["passed"] is False
        assert result["stale_72h"] == 1

    def test_old_open_alert_24h_warns(self, tmp_path: Path) -> None:
        """An open alert aged 25h must not fail but be tracked as stale_24h."""

        with patch.object(meta_monitor, "_get_alert_tracker",
                          return_value=self._stale_tracker(age_hours=25)):
            result = check_notification_staleness(notifications_dir=tmp_path / "notifications")
        assert result["passed"] is True
        assert result["stale_24h"] == 1


class TestM2NotificationCleanup:
    def test_only_consumed_notifications_pruned(self, tmp_path: Path) -> None:
        """Open (unconsumed) notification files must survive cleanup."""
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker
        from maref.observability.meta_monitor import _cleanup_notifications

        tracker = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        tracker.record_alert(
            name="Open Alert", severity="critical", message="open",
            check_id="open_check",
        )
        tracker.record_alert(
            name="Closed Alert", severity="warning", message="closed",
            check_id="closed_check",
        )
        # Resolve only the closed one.
        tracker.resolve_by_check("closed_check", description="fixed")

        ndir = tmp_path / "notifications"
        ndir.mkdir(parents=True)
        for check_id, name in (("open_check", "open"), ("closed_check", "closed")):
            f = ndir / f"{check_id}.json"
            f.write_text(json.dumps({
                "title": name, "severity": "critical", "check_id": check_id,
                "timestamp": time.time(), "source": "meta-monitor",
            }))
            # Age it past the cleanup window.
            old = time.time() - 2 * 3600
            os.utime(f, (old, old))

        with patch.object(meta_monitor, "_get_alert_tracker", return_value=tracker), \
                patch.object(meta_monitor, "_notifications_dir", return_value=ndir):
            removed = _cleanup_notifications(max_age_hours=1.0)

        assert removed == 1
        assert not (ndir / "closed_check.json").exists()
        assert (ndir / "open_check.json").exists()

    def test_fresh_notifications_never_pruned(self, tmp_path: Path) -> None:
        """Notifications within the cleanup window are always kept."""
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker
        from maref.observability.meta_monitor import _cleanup_notifications

        tracker = AlertFeedbackTracker(state_path=tempfile.mktemp(suffix=".json"))
        tracker.record_alert(
            name="Fresh", severity="warning", message="fresh",
            check_id="fresh_check",
        )
        tracker.resolve_by_check("fresh_check")

        ndir = tmp_path / "notifications"
        ndir.mkdir(parents=True)
        f = ndir / "fresh.json"
        f.write_text(json.dumps({
            "title": "Fresh", "severity": "warning", "check_id": "fresh_check",
            "timestamp": time.time(), "source": "meta-monitor",
        }))

        with patch.object(meta_monitor, "_get_alert_tracker", return_value=tracker), \
                patch.object(meta_monitor, "_notifications_dir", return_value=ndir):
            removed = _cleanup_notifications(max_age_hours=1.0)

        assert removed == 0
        assert (ndir / "fresh.json").exists()


class TestGaaSHealth:
    def test_gaas_unreachable_returns_false(self) -> None:
        with patch("httpx.get", side_effect=ConnectionError("mock unreachable")):
            result = check_gaas_health()
            assert result["passed"] is False


class TestAuditPathRegistry:
    def test_registry_has_entries(self) -> None:
        registry = get_registry()
        assert len(registry) > 0
        assert "health_snapshot" in registry
        assert "audit_logger" in registry
        assert "pulse_writer" in registry
        assert "meta_monitor" in registry
        assert "notifications" in registry
        assert "gaas_audit" in registry

    def test_registered_paths_are_valid(self) -> None:
        for _name, entry in get_registry().items():
            assert entry.write_path
            assert entry.description
            assert entry.file_pattern

    def test_verify_path_consistency_detects_missing_paths(self) -> None:
        register(AuditPathEntry(
            subsystem="__test_missing__",
            description="test always-missing path",
            write_path="/tmp/__maref_test_nonexistent__/data.json",
            read_paths=("/tmp/__maref_test_nonexistent__/data.json",),
        ))
        subsystem_issues = verify_path_consistency(subsystem="__test_missing__")
        assert len(subsystem_issues) >= 1
        for issue in subsystem_issues:
            assert issue["subsystem"] == "__test_missing__"
            assert issue["issue"] in ("write_path_missing", "read_path_missing")
            assert "path" in issue


class TestAuditPathEntry:
    def test_register_new_path(self) -> None:
        register(AuditPathEntry(
            subsystem="test_subsystem",
            description="test",
            write_path="/tmp/test.json",
            read_paths=("/tmp/test.json",),
        ))
        registry = get_registry()
        assert "test_subsystem" in registry
        assert registry["test_subsystem"].write_path == "/tmp/test.json"


class TestRunAllChecks:
    def test_run_all_returns_full_report(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-key")
        with tempfile.TemporaryDirectory() as d:
            d_path = Path(d)
            report = run_all_checks(audit_base=d_path, notifications_dir=d_path / "notifications")
            assert "timestamp" in report
            assert "m0" in report
            assert "m1" in report
            assert "m2" in report
            assert "m3" in report
            assert "summary" in report
            assert all(k in report["summary"] for k in ("m0_passed", "m1_passed", "m2_passed", "m3_passed", "all_passed"))
