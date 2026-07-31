"""Phase 2.4 — federated cascade circuit breaker tests.

Verifies multi-agent cascade fault isolation: a single point of failure
isolates the failing agent, degrades its direct dependents, never touches
unrelated agents, and unwinds automatically after recovery.

Reference: task_plan Phase 2.4 — 级联断路器（多 Agent 级联故障隔离）。
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.federation.cascade_breaker import (
    CascadeStatus,
    FederationCascadeBreaker,
)

AgentA = "agent-a"
AgentB = "agent-b"
AgentC = "agent-c"
AgentD = "agent-d"


def _chain_breaker(
    propagate_secondary: bool = False,
    cooldown_seconds: float = 60.0,
    max_failures: int = 2,
    audit_logger: Any | None = None,
) -> FederationCascadeBreaker:
    """A breaker with a dependency chain A → B → C and an unrelated D."""
    breaker = FederationCascadeBreaker(
        cooldown_seconds=cooldown_seconds,
        max_failures=max_failures,
        propagate_secondary=propagate_secondary,
        audit_logger=audit_logger,
    )
    breaker.declare_dependency(dependent=AgentA, upstream=AgentB)
    breaker.declare_dependency(dependent=AgentB, upstream=AgentC)
    breaker.register_agent(AgentD)
    return breaker


def _trip_agent_c(breaker: FederationCascadeBreaker, failures: int = 2) -> tuple[str, ...]:
    affected: tuple[str, ...] = ()
    for _ in range(failures):
        affected = breaker.record_failure(AgentC, reason="timeout")
    return affected


class TestBasics:
    def test_nominal_by_default(self) -> None:
        breaker = _chain_breaker()
        for agent in (AgentA, AgentB, AgentC, AgentD):
            assert breaker.status(agent) == CascadeStatus.NOMINAL
            assert breaker.can_proceed(agent) is True

    def test_failures_below_threshold_do_not_isolate(self) -> None:
        breaker = _chain_breaker(max_failures=3)
        assert breaker.record_failure(AgentC, reason="timeout") == ()
        assert breaker.record_failure(AgentC, reason="timeout") == ()
        assert breaker.status(AgentC) == CascadeStatus.NOMINAL
        assert breaker.record_failure(AgentC, reason="timeout") == (
            AgentC,
            AgentB,
        )
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED

    def test_unknown_agent_can_proceed_by_default(self) -> None:
        breaker = FederationCascadeBreaker()
        assert breaker.status("unknown") == CascadeStatus.NOMINAL
        assert breaker.can_proceed("unknown") is True

    def test_register_and_declare_are_idempotent(self) -> None:
        breaker = FederationCascadeBreaker()
        breaker.declare_dependency(AgentA, AgentB)
        breaker.declare_dependency(AgentA, AgentB)
        assert breaker.summary()["dependency_edges"] == 1


class TestCascadePropagation:
    def test_single_point_failure_does_not_affect_unrelated(self) -> None:
        breaker = _chain_breaker()
        affected = _trip_agent_c(breaker)

        # Only C (isolated) and its direct dependent B (degraded) are touched.
        assert set(affected) == {AgentC, AgentB}
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED
        assert breaker.status(AgentA) == CascadeStatus.NOMINAL
        assert breaker.status(AgentD) == CascadeStatus.NOMINAL

        # Degraded agents may still proceed (fallback path), isolated cannot.
        assert breaker.can_proceed(AgentC) is False
        assert breaker.can_proceed(AgentB) is True
        assert breaker.can_proceed(AgentA) is True

    def test_direct_dependents_only_by_default(self) -> None:
        breaker = _chain_breaker(propagate_secondary=False)
        _trip_agent_c(breaker)
        assert breaker.status(AgentA) == CascadeStatus.NOMINAL

    def test_secondary_propagation_degrades_transitive(self) -> None:
        breaker = _chain_breaker(propagate_secondary=True)
        _trip_agent_c(breaker)
        assert breaker.status(AgentA) == CascadeStatus.DEGRADED
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED

    def test_multiple_upstreams_are_tracked_independently(self) -> None:
        breaker = FederationCascadeBreaker(max_failures=1, cooldown_seconds=60.0)
        breaker.declare_dependency(dependent=AgentB, upstream=AgentA)
        breaker.declare_dependency(dependent=AgentB, upstream=AgentC)
        breaker.record_failure(AgentA, reason="crash")
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED
        breaker.record_failure(AgentC, reason="crash")
        # Still degraded — both upstreams are isolated.
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED
        assert breaker.status(AgentA) == CascadeStatus.ISOLATED
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED

    def test_probe_failure_reisolates_and_extends_cooldown(self) -> None:
        breaker = _chain_breaker(cooldown_seconds=0.05)
        _trip_agent_c(breaker)
        time.sleep(0.1)
        assert breaker.can_proceed(AgentC) is True  # RECOVERING probe
        assert breaker.status(AgentC) == CascadeStatus.RECOVERING
        affected = breaker.record_failure(AgentC, reason="probe_timeout")
        assert affected == (AgentC,)
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED
        # Cooldown restarted: immediately after re-isolation no probe is allowed.
        assert breaker.can_proceed(AgentC) is False


class TestRecovery:
    def test_recovery_auto_regression(self) -> None:
        breaker = _chain_breaker(cooldown_seconds=0.05)
        _trip_agent_c(breaker)
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED

        time.sleep(0.1)
        assert breaker.can_proceed(AgentC) is True  # probe
        breaker.record_success(AgentC)
        assert breaker.status(AgentC) == CascadeStatus.NOMINAL
        assert breaker.status(AgentB) == CascadeStatus.NOMINAL
        assert breaker.status(AgentA) == CascadeStatus.NOMINAL

    def test_exact_recovery_with_multiple_upstreams(self) -> None:
        breaker = FederationCascadeBreaker(max_failures=1, cooldown_seconds=0.05)
        breaker.declare_dependency(dependent=AgentB, upstream=AgentA)
        breaker.declare_dependency(dependent=AgentB, upstream=AgentC)
        breaker.record_failure(AgentA, reason="crash")
        breaker.record_failure(AgentC, reason="crash")
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED

        time.sleep(0.1)
        assert breaker.can_proceed(AgentA) is True  # RECOVERING probe
        breaker.record_success(AgentA)
        # B stays degraded: C is still isolated.
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED
        assert breaker.can_proceed(AgentC) is True  # RECOVERING probe
        breaker.record_success(AgentC)
        assert breaker.status(AgentB) == CascadeStatus.NOMINAL

    def test_success_on_nominal_is_noop(self) -> None:
        breaker = _chain_breaker()
        breaker.record_success(AgentC)
        assert breaker.status(AgentC) == CascadeStatus.NOMINAL
        assert breaker.summary()["trip_count"] == 0


class TestObservability:
    def test_audit_logging_records_isolation(self) -> None:
        class FakeAuditLogger:
            def __init__(self) -> None:
                self.events: list[dict[str, Any]] = []

            def log(self, **kwargs: Any) -> Any:
                self.events.append(kwargs)
                return self

        logger = FakeAuditLogger()
        breaker = _chain_breaker(audit_logger=logger)
        _trip_agent_c(breaker)
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event["event_type"] == "federation_cascade_isolated"
        assert event["actor"] == "FederationCascadeBreaker"
        assert event["metadata"]["agent_id"] == AgentC
        assert set(event["metadata"]["affected"]) == {AgentC, AgentB}

    def test_audit_failure_does_not_break_isolation(self) -> None:
        class BrokenAuditLogger:
            def log(self, **kwargs: Any) -> Any:
                raise RuntimeError("audit backend down")

        breaker = _chain_breaker(audit_logger=BrokenAuditLogger())
        affected = _trip_agent_c(breaker)
        assert set(affected) == {AgentC, AgentB}
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED

    def test_status_map_and_lists(self) -> None:
        breaker = _chain_breaker()
        _trip_agent_c(breaker)
        assert breaker.get_status_map() == {
            AgentA: "nominal",
            AgentB: "degraded",
            AgentC: "isolated",
            AgentD: "nominal",
        }
        assert breaker.degraded_agents() == [AgentB]
        assert breaker.isolated_agents() == [AgentC]

    def test_summary_reflects_state(self) -> None:
        breaker = _chain_breaker()
        _trip_agent_c(breaker)
        summary = breaker.summary()
        assert summary["total_agents"] == 4
        assert summary["status_counts"]["isolated"] == 1
        assert summary["status_counts"]["degraded"] == 1
        assert summary["status_counts"]["nominal"] == 2
        assert summary["dependency_edges"] == 2
        assert summary["trip_count"] == 1
        assert summary["recent_trips"][0]["agent_id"] == AgentC

    def test_reset_restores_nominal(self) -> None:
        breaker = _chain_breaker()
        _trip_agent_c(breaker)
        breaker.reset()
        assert breaker.summary()["trip_count"] == 0
        for agent in (AgentA, AgentB, AgentC, AgentD):
            assert breaker.status(agent) == CascadeStatus.NOMINAL
            assert breaker.can_proceed(agent) is True


class TestE2EFullCycle:
    def test_full_cascade_lifecycle(self) -> None:
        """Failure → isolate → degrade → cooldown → probe → recover → regress."""
        breaker = _chain_breaker(cooldown_seconds=0.05)
        assert _trip_agent_c(breaker) == (AgentC, AgentB)
        assert breaker.can_proceed(AgentC) is False
        assert breaker.status(AgentB) == CascadeStatus.DEGRADED

        time.sleep(0.1)
        # Isolated agent is allowed one probe after the cooldown.
        assert breaker.can_proceed(AgentC) is True
        # Probe succeeds → full auto regression along the chain.
        breaker.record_success(AgentC)
        assert breaker.status(AgentC) == CascadeStatus.NOMINAL
        assert breaker.status(AgentB) == CascadeStatus.NOMINAL
        assert breaker.status(AgentA) == CascadeStatus.NOMINAL
        assert breaker.summary()["trip_count"] == 1
        assert breaker.degraded_agents() == []
        assert breaker.isolated_agents() == []

    @pytest.mark.parametrize(
        "max_failures",
        [1, 3],
    )
    def test_threshold_configuration(self, max_failures: int) -> None:
        breaker = _chain_breaker(max_failures=max_failures)
        for _ in range(max_failures - 1):
            breaker.record_failure(AgentC, reason="timeout")
        assert breaker.status(AgentC) != CascadeStatus.ISOLATED
        breaker.record_failure(AgentC, reason="timeout")
        assert breaker.status(AgentC) == CascadeStatus.ISOLATED
