from __future__ import annotations

from maref.desktop.desktop_governance import (
    DesktopGovernance,
    DesktopGovernanceState,
    GovernanceAction,
    GovernanceEvent,
)
from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2


class TestGovernanceEvent:
    def test_to_dict(self) -> None:
        event = GovernanceEvent(
            action=GovernanceAction.CIRCUIT_BREAK,
            reason="Test fail",
            previous_state=DesktopGovernanceState.HEALTHY,
            new_state=DesktopGovernanceState.LOCKED,
        )
        d = event.to_dict()
        assert d["action"] == "circuit_break"
        assert d["previous_state"] == "healthy"
        assert d["new_state"] == "locked"


class TestDesktopGovernance:
    def test_init_healthy(self) -> None:
        gov = DesktopGovernance()
        assert gov.state == DesktopGovernanceState.HEALTHY
        assert gov.is_healthy

    def test_consecutive_failures_triggers_lock(self) -> None:
        gov = DesktopGovernance()
        gov.record_operation_result(success=False, operation_type="click", target="button")
        gov.record_operation_result(success=False, operation_type="click", target="button")
        gov.record_operation_result(success=False, operation_type="click", target="button")
        assert gov.state == DesktopGovernanceState.LOCKED
        assert not gov.is_healthy

    def test_success_after_lock_restores(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.LOCKED
        gov._safety_gate._locked = True
        gov._safety_gate._locked_until = __import__("time").time() + 9999
        gov._safety_gate._consecutive_failures = 3
        gov.record_operation_result(success=True, operation_type="click", target="button")
        assert gov.state == DesktopGovernanceState.RECOVERING

    def test_detect_oscillation_initial(self) -> None:
        gov = DesktopGovernance()
        result = gov.detect_oscillation("hash1")
        assert not result

    def test_detect_oscillation_switching_hashes(self) -> None:
        gov = DesktopGovernance()
        hashes = ["a", "b", "c", "d", "e", "f"]
        for h in hashes:
            gov.detect_oscillation(h)
        assert gov.state == DesktopGovernanceState.OSCILLATING

    def test_detect_drift_no_missing(self) -> None:
        gov = DesktopGovernance()
        result = gov.detect_drift({"button_a", "button_b"}, {"button_a", "button_b"})
        assert not result
        assert gov._ui_change_count == 0

    def test_detect_drift_with_missing(self) -> None:
        gov = DesktopGovernance()
        result = gov.detect_drift({"button_a", "button_b"}, {"button_a"})
        assert not result
        assert gov._ui_change_count == 1

    def test_detect_drift_triggers_after_two(self) -> None:
        gov = DesktopGovernance()
        gov.detect_drift({"button_a", "button_b"}, {"button_a"})
        assert gov._ui_change_count == 1
        result = gov.detect_drift({"button_a", "button_b"}, {"button_a"})
        assert result
        assert gov.state == DesktopGovernanceState.DRIFTING

    def test_escalate_to_human(self) -> None:
        gov = DesktopGovernance()
        gov.escalate_to_human("User requested help")
        assert gov.state == DesktopGovernanceState.LOCKED

    def test_degrade_mode(self) -> None:
        gov = DesktopGovernance()
        gov.degrade_mode("Performance issue")
        assert gov.state == DesktopGovernanceState.DEGRADED

    def test_get_autonomy_level_healthy(self) -> None:
        gov = DesktopGovernance()
        assert gov.get_autonomy_level() == 4

    def test_get_autonomy_level_degraded(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.DEGRADED
        assert gov.get_autonomy_level() == 3

    def test_get_autonomy_level_recovering(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.RECOVERING
        assert gov.get_autonomy_level() == 2

    def test_get_autonomy_level_oscillating(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.OSCILLATING
        assert gov.get_autonomy_level() == 1

    def test_get_autonomy_level_locked(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.LOCKED
        assert gov.get_autonomy_level() == 0

    def test_check_and_intervene_when_locked_but_gate_unlocked(self) -> None:
        gov = DesktopGovernance()
        gov._state = DesktopGovernanceState.LOCKED
        gov._safety_gate._locked = False
        action = gov.check_and_intervene()
        assert action == GovernanceAction.RESTORE_MODE

    def test_check_and_intervene_when_gate_locked(self) -> None:
        gov = DesktopGovernance()
        gov._safety_gate._locked = True
        gov._safety_gate._locked_until = __import__("time").time() + 9999
        action = gov.check_and_intervene()
        assert action == GovernanceAction.CIRCUIT_BREAK

    def test_check_and_intervene_no_action(self) -> None:
        gov = DesktopGovernance()
        action = gov.check_and_intervene()
        assert action is None

    def test_event_log(self) -> None:
        gov = DesktopGovernance()
        gov.record_operation_result(success=False, operation_type="click", target="button")
        gov.record_operation_result(success=False, operation_type="click", target="button")
        gov.record_operation_result(success=False, operation_type="click", target="button")
        assert len(gov.event_log) == 1
        assert gov.event_log[0].action == GovernanceAction.CIRCUIT_BREAK
