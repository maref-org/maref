from __future__ import annotations

import time

from maref.federation.health_monitor import (
    DEFAULT_SILENCE_TIMEOUT,
    FederationHealthMonitor,
    HealthCheckResult,
    MemberHealth,
)


class TestMemberHealth:
    def test_is_silent_when_elapsed_exceeds_timeout(self) -> None:
        m = MemberHealth(
            agent_id="agent-1",
            last_seen=time.time() - 400,
            silence_timeout=300,
        )
        assert m.is_silent
        assert m.silence_elapsed > 300

    def test_not_silent_when_within_timeout(self) -> None:
        m = MemberHealth(
            agent_id="agent-1",
            last_seen=time.time() - 10,
            silence_timeout=300,
        )
        assert not m.is_silent

    def test_to_dict_includes_key_fields(self) -> None:
        m = MemberHealth(
            agent_id="agent-1",
            last_seen=1000.0,
            silence_timeout=300,
        )
        d = m.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["suspected"] is False
        assert "silence_elapsed" in d


class TestFederationHealthMonitor:
    def test_probe_registers_new_member(self) -> None:
        monitor = FederationHealthMonitor()
        monitor.probe("agent-1")
        assert "agent-1" in monitor._members
        assert not monitor._members["agent-1"].suspected

    def test_probe_updates_existing_member(self) -> None:
        monitor = FederationHealthMonitor()
        monitor.probe("agent-1")
        old_last_seen = monitor._members["agent-1"].last_seen
        time.sleep(0.001)
        monitor.probe("agent-1")
        assert monitor._members["agent-1"].last_seen > old_last_seen

    def test_unregister_removes_member(self) -> None:
        monitor = FederationHealthMonitor()
        monitor.probe("agent-1")
        monitor.probe("agent-2")
        monitor.unregister("agent-1")
        assert "agent-1" not in monitor._members
        assert "agent-2" in monitor._members

    def test_check_marks_silent_as_suspected(self) -> None:
        monitor = FederationHealthMonitor(
            silence_timeout=0.05, trust_decay_per_cycle=5.0
        )
        monitor.probe("agent-silent")
        time.sleep(0.06)
        result = monitor.check()
        assert result.silent >= 1
        assert result.suspected >= 1
        assert monitor._members["agent-silent"].suspected
        assert monitor._members["agent-silent"].suspicion_started > 0

    def test_check_ignores_active_members(self) -> None:
        monitor = FederationHealthMonitor(silence_timeout=300)
        monitor.probe("agent-active")
        result = monitor.check()
        assert result.silent == 0
        assert result.suspected == 0

    def test_trust_penalty_accrues_over_cycles(self) -> None:
        monitor = FederationHealthMonitor(
            silence_timeout=0.05, trust_decay_per_cycle=10.0
        )
        monitor.probe("agent-decay")
        time.sleep(0.06)
        monitor.check()
        assert monitor._members["agent-decay"].trust_penalty == 10.0
        monitor.check()
        assert monitor._members["agent-decay"].trust_penalty == 20.0

    def test_probe_clears_suspicion(self) -> None:
        monitor = FederationHealthMonitor(
            silence_timeout=0.05, trust_decay_per_cycle=10.0
        )
        monitor.probe("agent-recover")
        time.sleep(0.06)
        monitor.check()
        assert monitor._members["agent-recover"].suspected

        monitor.probe("agent-recover")
        assert not monitor._members["agent-recover"].suspected
        assert monitor._members["agent-recover"].suspicion_started == 0.0

    def test_get_applied_penalties(self) -> None:
        monitor = FederationHealthMonitor(
            silence_timeout=0.05, trust_decay_per_cycle=10.0
        )
        monitor.probe("agent-penalty")
        time.sleep(0.06)
        monitor.check()
        penalties = monitor.get_applied_penalties()
        assert "agent-penalty" in penalties
        assert penalties["agent-penalty"] == 10.0

    def test_summary(self) -> None:
        monitor = FederationHealthMonitor(silence_timeout=30)
        monitor.probe("a1")
        monitor.probe("a2")
        s = monitor.summary()
        assert s["total_members"] == 2
        assert s["active"] == 2
        assert s["suspected"] == 0

    def test_health_check_result_to_dict(self) -> None:
        r = HealthCheckResult(checked=5, silent=2, suspected=1, details=[{"a": 1}])
        d = r.to_dict()
        assert d["checked"] == 5
        assert d["silent"] == 2
        assert d["suspected"] == 1
        assert len(d["details"]) == 1

    def test_default_timeout(self) -> None:
        monitor = FederationHealthMonitor()
        assert monitor._silence_timeout == DEFAULT_SILENCE_TIMEOUT
