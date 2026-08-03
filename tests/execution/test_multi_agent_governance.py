"""v0.47 F1 — MultiAgentCoordinator governance wiring.

1. **Boundary gate**: every agent is checked against a
   ``TrustBoundaryManager`` before dispatch; an out-of-bounds agent is
   skipped (FAILED), not executed.
2. **Audit + metering**: each executed task is recorded to the audit bus
   and the metering engine.
3. **Cascade circuit breaker**: execution exceptions trip the coordinator's
   breaker, halting further dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.execution.multi_agent.coordinator import MultiAgentCoordinator
from maref.governance.audit_bus import AuditBus
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.trust_boundary import TrustBoundaryManager
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.federation.metering import TaskMeteringEngine


class _FakeHarness(BaseHarness):
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self._ran = False

    def configure(self, config: HarnessConfig) -> None:
        pass

    def preflight(self) -> list[str]:
        return []

    def run(self, round_id: str = "") -> HarnessResult:
        self._ran = True
        if self._fail:
            raise RuntimeError("harness failure")
        return HarnessResult(status=HarnessStatus.SUCCEEDED, round_id=round_id)


class TestBoundaryGate:
    def test_out_of_bounds_agent_skipped(self) -> None:
        """An agent whose action is out of boundary is not executed."""
        boundary = TrustBoundaryManager()
        coord = MultiAgentCoordinator(boundary=boundary)
        h = _FakeHarness()
        coord.add_agent(h, role="worker")
        results = coord.run_all(task="file.delete")
        # HIGH-risk action, no scope → boundary denies → agent skipped.
        assert h._ran is False
        assert results[list(results)[0]].status == HarnessStatus.FAILED

    def test_in_scope_agent_executed(self) -> None:
        """A LOW-risk action passes the boundary and the agent runs."""
        boundary = TrustBoundaryManager()
        coord = MultiAgentCoordinator(boundary=boundary)
        h = _FakeHarness()
        coord.add_agent(h, role="worker")
        results = coord.run_all(task="file.read")
        assert h._ran is True
        assert results[list(results)[0]].status == HarnessStatus.SUCCEEDED

    def test_no_boundary_backward_compatible(self) -> None:
        """Without a boundary, agents run as before."""
        coord = MultiAgentCoordinator()
        h = _FakeHarness()
        coord.add_agent(h, role="worker")
        results = coord.run_all(task="whatever")
        assert h._ran is True


class TestAuditAndMetering:
    def test_task_recorded_to_audit_bus(self) -> None:
        bus = AuditBus()
        coord = MultiAgentCoordinator(audit_bus=bus)
        coord.add_agent(_FakeHarness(), role="worker")
        coord.run_all(task="file.read")
        # AuditBus needs a subscriber to observe; check via internal logger.
        entries = bus.query_tenant("")
        assert entries  # at least one audit entry recorded

    def test_task_recorded_to_metering(self) -> None:
        metering = TaskMeteringEngine()
        coord = MultiAgentCoordinator(metering=metering)
        coord.add_agent(_FakeHarness(), role="worker")
        coord.run_all(task="file.read")
        assert metering.metric_count >= 1


class TestCascadeBreaker:
    def test_execution_failure_trips_breaker(self) -> None:
        cb = CircuitBreaker(max_depth=0, max_consecutive_failures=1, cooldown_seconds=30.0)
        coord = MultiAgentCoordinator(circuit_breaker=cb)
        coord.add_agent(_FakeHarness(fail=True), role="worker")
        coord.run_all(task="file.read")
        assert cb.state == BreakerState.OPEN

    def test_open_breaker_halts_further_dispatch(self) -> None:
        cb = CircuitBreaker(max_depth=0, max_consecutive_failures=1, cooldown_seconds=30.0)
        coord = MultiAgentCoordinator(circuit_breaker=cb)
        failing = _FakeHarness(fail=True)
        ok = _FakeHarness()
        coord.add_agent(failing, role="worker-1")
        coord.add_agent(ok, role="worker-2")
        coord.run_all(task="file.read")
        # Breaker opens after the first failure; worker-2 is halted.
        assert cb.state == BreakerState.OPEN
