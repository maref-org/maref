from __future__ import annotations

import time
from typing import Any

from maref.execution.harness.types import HarnessConfig
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState

# 允许 Harness 运行的治理状态白名单
_ALLOWED_PREFLIGHT_STATES: frozenset[GovernanceState] = frozenset({
    GovernanceState.OBSERVE,
    GovernanceState.ANALYZE,
    GovernanceState.INIT,
})


class GovernanceBridge:
    """在每个生命周期阶段检查治理状态机。

    - PREFLIGHT: 治理状态需为 OBSERVE/ANALYZE/INIT
    - RUNNING/step: CircuitBreaker 必须 CLOSED
    - 违规时触发 state_machine.transition(HALT)
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._state_machine = state_machine or GovernanceStateMachine()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._check_records: list[dict[str, Any]] = []
        self._halt_triggered = False
        self._max_records = 200

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def state_machine(self) -> GovernanceStateMachine:
        return self._state_machine

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def state_name(self) -> str:
        return self._state_machine.current_state.name

    @property
    def halt_triggered(self) -> bool:
        return self._halt_triggered

    @property
    def check_history(self) -> list[dict[str, Any]]:
        return list(self._check_records)

    # ── Configuration ──────────────────────────────────────────────────

    def configure(self, config: HarnessConfig) -> None:
        if "max_depth" in config.extra:
            self._circuit_breaker = CircuitBreaker(
                max_depth=config.extra["max_depth"],
            )

    # ── Core checks ─────────────────────────────────────────────────────

    def check(self, lifecycle_stage: str) -> bool:
        """检查当前治理状态是否允许此生命周期阶段执行。"""
        if self._state_machine.current_state == GovernanceState.HALT:
            return False

        if lifecycle_stage == "preflight":
            return self._state_machine.current_state in _ALLOWED_PREFLIGHT_STATES

        if lifecycle_stage in ("running", "step"):
            return not self._circuit_breaker.is_open

        if lifecycle_stage in ("validating", "reporting"):
            return self._state_machine.current_state != GovernanceState.HALT

        return True

    def record(self, lifecycle_stage: str, allowed: bool) -> None:
        """记录检查结果，违规时触发 HALT。"""
        record = {
            "stage": lifecycle_stage,
            "allowed": allowed,
            "governance_state": self._state_machine.current_state.name,
            "circuit_breaker": self._circuit_breaker.state.value,
            "timestamp": time.time(),
        }
        self._check_records.append(record)
        if len(self._check_records) > self._max_records:
            self._check_records = self._check_records[-self._max_records:]

        if not allowed and not self._halt_triggered:
            self._halt_triggered = True
            self._state_machine.force_halt(
                reason=f"governance_violation: lifecycle_stage={lifecycle_stage}"
            )

    # ── CircuitBreaker helpers ─────────────────────────────────────────

    def check_depth(self, depth: int) -> bool:
        return self._circuit_breaker.check_depth(depth)

    def record_failure(self) -> None:
        self._circuit_breaker.record_failure()

    def record_success(self) -> None:
        self._circuit_breaker.record_success()

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "governance_state": self._state_machine.current_state.name,
            "governance_entropy": self._state_machine.current_entropy,
            "circuit_breaker": self._circuit_breaker.state.value,
            "circuit_breaker_trips": len(self._circuit_breaker._trips),
            "halt_triggered": self._halt_triggered,
            "check_count": len(self._check_records),
        }
