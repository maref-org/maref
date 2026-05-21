from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2


class GovernanceAction(str, Enum):
    CIRCUIT_BREAK = "circuit_break"
    OSCILLATION_REPAIR = "oscillation_repair"
    DRIFT_RECALIBRATE = "drift_recalibrate"
    HUMAN_ESCALATE = "human_escalate"
    DEGRADE_MODE = "degrade_mode"
    RESTORE_MODE = "restore_mode"


class DesktopGovernanceState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OSCILLATING = "oscillating"
    DRIFTING = "drifting"
    LOCKED = "locked"
    RECOVERING = "recovering"


@dataclass
class GovernanceEvent:
    timestamp: float = field(default_factory=time.time)
    action: GovernanceAction = GovernanceAction.CIRCUIT_BREAK
    reason: str = ""
    previous_state: DesktopGovernanceState = DesktopGovernanceState.HEALTHY
    new_state: DesktopGovernanceState = DesktopGovernanceState.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action.value,
            "reason": self.reason,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
        }


class DesktopGovernance:
    """Desktop-side governance layer bridging MAREF governance to desktop operations.

    Integrates with:
    - FourPhaseGovernance for autonomy level mapping
    - CircuitBreaker for operation failure detection
    - OscillationRepair for UI change detection
    - UnifiedAudit for immutable operation logging

    Autonomous interventions:
    - 3 consecutive operation failures → CircuitBreaker trip + LOCKED
    - UI layout change detected → pause + recalibration request
    - Agent oscillation (rapid mode switching) → degradation
    - Recovery: automatic cooldown + verification before restore
    """

    MAX_CONSECUTIVE_FAILURES = 3
    COOLDOWN_SECONDS = 30
    MAX_OSCILLATION_COUNT = 5
    OSCILLATION_WINDOW_SECONDS = 60

    def __init__(self, safety_gate: DesktopSafetyGateV2 | None = None) -> None:
        self._safety_gate = safety_gate or DesktopSafetyGateV2()
        self._state = DesktopGovernanceState.HEALTHY
        self._event_log: list[GovernanceEvent] = []
        self._oscillation_counter: int = 0
        self._last_oscillation_time: float = 0.0
        self._mode_switches: list[float] = []
        self._last_screenshot_hash: str = ""
        self._ui_change_count: int = 0

    @property
    def state(self) -> DesktopGovernanceState:
        return self._state

    @property
    def is_healthy(self) -> bool:
        return self._state == DesktopGovernanceState.HEALTHY

    @property
    def event_log(self) -> list[GovernanceEvent]:
        return list(self._event_log)

    def record_operation_result(self, success: bool, operation_type: str, target: str) -> None:
        self._safety_gate.record_operation(
            operation_type=operation_type,
            target=target,
            success=success,
        )

        if not success and self._safety_gate.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._transition(GovernanceAction.CIRCUIT_BREAK, f"{self.MAX_CONSECUTIVE_FAILURES} consecutive failures on {operation_type}")

        if success and self._state == DesktopGovernanceState.LOCKED:
            self._safety_gate.reset_failure_count()
            self._transition(GovernanceAction.RESTORE_MODE, "Operation succeeded after cooldown, restoring mode")

    def detect_oscillation(self, screenshot_hash: str) -> bool:
        now = time.time()
        if screenshot_hash == self._last_screenshot_hash:
            self._oscillation_counter += 1
        else:
            if self._oscillation_counter > 0:
                self._mode_switches.append(now)
            self._oscillation_counter = 1
            self._last_screenshot_hash = screenshot_hash

        recent_switches = [t for t in self._mode_switches if now - t < self.OSCILLATION_WINDOW_SECONDS]
        self._mode_switches = recent_switches

        if len(recent_switches) >= self.MAX_OSCILLATION_COUNT:
            self._transition(GovernanceAction.OSCILLATION_REPAIR, f"UI oscillation detected: {len(recent_switches)} changes in {self.OSCILLATION_WINDOW_SECONDS}s")
            return True
        return False

    def detect_drift(self, expected_ui_elements: set[str], actual_ui_elements: set[str]) -> bool:
        missing = expected_ui_elements - actual_ui_elements
        if missing:
            self._ui_change_count += 1
            if self._ui_change_count >= 2:
                self._transition(GovernanceAction.DRIFT_RECALIBRATE, f"UI drift detected: missing elements {missing}")
                return True
        else:
            self._ui_change_count = 0
        return False

    def escalate_to_human(self, reason: str) -> None:
        self._transition(GovernanceAction.HUMAN_ESCALATE, reason)

    def degrade_mode(self, reason: str) -> None:
        self._transition(GovernanceAction.DEGRADE_MODE, reason)

    def check_and_intervene(self) -> GovernanceAction | None:
        if self._safety_gate.is_locked and self._state != DesktopGovernanceState.LOCKED:
            self._transition(GovernanceAction.CIRCUIT_BREAK, "Safety gate lock detected")
            return GovernanceAction.CIRCUIT_BREAK

        if self._state == DesktopGovernanceState.LOCKED and not self._safety_gate.is_locked:
            self._transition(GovernanceAction.RESTORE_MODE, "Cooldown expired, auto-restoring")
            return GovernanceAction.RESTORE_MODE

        return None

    def get_autonomy_level(self) -> int:
        if self._state == DesktopGovernanceState.HEALTHY:
            return 4
        elif self._state == DesktopGovernanceState.DEGRADED:
            return 3
        elif self._state == DesktopGovernanceState.RECOVERING:
            return 2
        elif self._state in (DesktopGovernanceState.OSCILLATING, DesktopGovernanceState.DRIFTING):
            return 1
        return 0

    def _transition(self, action: GovernanceAction, reason: str) -> None:
        previous = self._state
        if action == GovernanceAction.CIRCUIT_BREAK:
            self._state = DesktopGovernanceState.LOCKED
        elif action == GovernanceAction.OSCILLATION_REPAIR:
            self._state = DesktopGovernanceState.OSCILLATING
        elif action == GovernanceAction.DRIFT_RECALIBRATE:
            self._state = DesktopGovernanceState.DRIFTING
        elif action == GovernanceAction.DEGRADE_MODE:
            self._state = DesktopGovernanceState.DEGRADED
        elif action == GovernanceAction.RESTORE_MODE:
            self._state = DesktopGovernanceState.RECOVERING
        elif action == GovernanceAction.HUMAN_ESCALATE:
            self._state = DesktopGovernanceState.LOCKED

        event = GovernanceEvent(
            action=action,
            reason=reason,
            previous_state=previous,
            new_state=self._state,
        )
        self._event_log.append(event)
