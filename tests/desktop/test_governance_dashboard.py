"""Tests for Phase D4: Governance Dashboard - DesktopGovernance integration and API endpoints."""


from maref.desktop.controller import DesktopController
from maref.desktop.desktop_governance import (
    DesktopGovernanceState,
)


class TestDesktopGovernanceIntegration:
    def test_controller_has_governance_instance(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        assert ctrl._governance is not None
        assert ctrl._governance.state == DesktopGovernanceState.HEALTHY

    def test_governance_status_endpoint(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        status = ctrl.get_governance_status()
        assert status["state"] == "healthy"
        assert status["autonomy_level"] == 4
        assert status["is_healthy"] is True
        assert status["consecutive_failures"] == 0
        assert status["is_locked"] is False
        assert status["total_events"] == 0

    def test_governance_records_operation_result(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl._governance.record_operation_result(
            success=True,
            operation_type="click",
            target="test",
        )
        status = ctrl.get_governance_status()
        assert status["total_events"] == 0

    def test_governance_events_empty_initially(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        events = ctrl.get_governance_events()
        assert len(events) == 0

    def test_set_governance_mode_degrade(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("degrade")
        assert ctrl._governance.state == DesktopGovernanceState.DEGRADED
        events = ctrl.get_governance_events()
        assert len(events) == 1
        assert events[0]["action"] == "degrade_mode"
        assert events[0]["new_state"] == "degraded"

    def test_set_governance_mode_escalate(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("escalate")
        assert ctrl._governance.state == DesktopGovernanceState.LOCKED
        events = ctrl.get_governance_events()
        assert len(events) == 1
        assert events[0]["action"] == "human_escalate"

    def test_governance_status_action_distribution(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("degrade")
        ctrl.set_governance_mode("escalate")
        status = ctrl.get_governance_status()
        assert "degrade_mode" in status["action_distribution"]
        assert "human_escalate" in status["action_distribution"]
        assert status["action_distribution"]["degrade_mode"] == 1
        assert status["action_distribution"]["human_escalate"] == 1

    def test_governance_status_state_distribution(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("degrade")
        status = ctrl.get_governance_status()
        assert "degraded" in status["state_distribution"]
        assert status["state_distribution"]["degraded"] == 1

    def test_governance_events_limit(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        for i in range(10):
            ctrl.set_governance_mode("degrade")
        events = ctrl.get_governance_events(limit=5)
        assert len(events) == 5

    def test_governance_state_distribution_accumulates(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("degrade")
        ctrl._governance._state = DesktopGovernanceState.HEALTHY
        ctrl.set_governance_mode("degrade")
        status = ctrl.get_governance_status()
        assert status["state_distribution"]["degraded"] == 2


class TestGovernanceDashboardIntegration:
    def test_execute_plan_updates_governance(self) -> None:
        ctrl = DesktopController(dry_run=True, history_db=None, parser_backend="mock")
        from maref.desktop.controller import DesktopOperation, DesktopOperationType, ExecutionPlan

        plan = ExecutionPlan(plan_id="governance-test", description="Test governance")
        plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 100, "y": 100}, description="Click"))
        result = ctrl.execute_plan(plan)
        assert result.success is True
        status = ctrl.get_governance_status()
        assert status["state"] == "healthy"

    def test_governance_status_has_operation_history_count(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        status = ctrl.get_governance_status()
        assert "operation_history_count" in status
        assert isinstance(status["operation_history_count"], int)

    def test_governance_status_has_last_operation_time(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        status = ctrl.get_governance_status()
        assert "last_operation_time" in status
        assert isinstance(status["last_operation_time"], float)

    def test_autonomy_level_changes_with_state(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        assert ctrl.get_governance_status()["autonomy_level"] == 4
        ctrl.set_governance_mode("degrade")
        assert ctrl.get_governance_status()["autonomy_level"] == 3
        ctrl.set_governance_mode("escalate")
        assert ctrl.get_governance_status()["autonomy_level"] == 0

    def test_governance_events_return_recent_first(self) -> None:
        ctrl = DesktopController(dry_run=True, parser_backend="mock")
        ctrl.set_governance_mode("degrade")
        ctrl.set_governance_mode("escalate")
        events = ctrl.get_governance_events(limit=1)
        assert len(events) == 1
        assert events[0]["action"] == "human_escalate"
