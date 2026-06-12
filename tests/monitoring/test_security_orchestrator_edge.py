from __future__ import annotations

from maref.monitoring.security_orchestrator import (
    ExecutionRecord,
    Playbook,
    PlaybookStep,
    SecurityAction,
    SecurityEvent,
    SecurityOrchestrator,
    TriggerCondition,
    create_security_orchestrator,
)


class TestDataclassMethods:
    def test_action_to_dict(self) -> None:
        action = SecurityAction(
            action_id="a-1",
            name="Test Action",
            description="desc",
            action_type="block_ip",
            parameters={"ip": "10.0.0.1"},
            requires_approval=True,
            rollback_action_id="a-rollback",
        )
        d = action.to_dict()
        assert d["action_id"] == "a-1"
        assert d["requires_approval"] is True
        assert d["rollback"] == "a-rollback"

    def test_event_to_dict(self) -> None:
        from datetime import datetime
        event = SecurityEvent(
            event_id="e-1",
            event_type="threat_detected",
            severity="high",
            title="Alert",
            description="desc",
            source="test",
            detected_at=datetime.now(),
            affected_assets=["server-1"],
            is_resolved=True,
        )
        d = event.to_dict()
        assert d["event_id"] == "e-1"
        assert d["severity"] == "high"
        assert d["is_resolved"] is True

    def test_playbook_step_to_dict(self) -> None:
        step = PlaybookStep(
            step_id="s-1",
            action_id="a-1",
            order=1,
            condition=None,
            on_failure="continue",
            timeout_seconds=60,
        )
        d = step.to_dict()
        assert d["step_id"] == "s-1"
        assert d["on_failure"] == "continue"
        assert d["timeout_seconds"] == 60

    def test_execution_record_to_dict(self) -> None:
        from datetime import datetime
        record = ExecutionRecord(
            record_id="r-1",
            playbook_id="p-1",
            triggered_by="e-1",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            status="completed",
            step_results=[{"step": 1}],
            notes=["done"],
        )
        d = record.to_dict()
        assert d["record_id"] == "r-1"
        assert d["status"] == "completed"
        assert d["step_count"] == 1


class TestSecurityOrchestratorEdgeCases:
    def test_trigger_event_not_found(self) -> None:
        so = create_security_orchestrator()
        result = so.trigger_playbook("playbook-threat-response", "nonexistent-event")
        assert result is None

    def test_trigger_action_not_found(self) -> None:
        so = create_security_orchestrator()
        so.register_action(SecurityAction(
            action_id="action-existing",
            name="Exists",
            description="",
            action_type="test",
        ))
        so.register_playbook(Playbook(
            playbook_id="pb-broken",
            name="Broken Playbook",
            description="",
            trigger=TriggerCondition.MANUAL,
            steps=[PlaybookStep("s-1", "action-missing", order=1)],
        ))
        event = so.create_event("test", "low", "test", "desc")
        record = so.trigger_playbook("pb-broken", event.event_id)
        assert record is not None
        assert record.status == "completed"

    def test_trigger_requires_approval(self) -> None:
        so = create_security_orchestrator()
        event = so.create_event("anomaly", "critical", "Suspicious agent", "desc")
        record = so.trigger_playbook("playbook-agent-isolation", event.event_id)
        assert record is not None
        assert any("requires manual approval" in n for n in record.notes)

    def test_trigger_disabled_playbook_returns_none(self) -> None:
        so = create_security_orchestrator()
        so.register_playbook(Playbook(
            playbook_id="pb-disabled",
            name="Disabled",
            description="",
            trigger=TriggerCondition.MANUAL,
            enabled=False,
            steps=[PlaybookStep("s-1", "action-notify-team", order=1)],
        ))
        event = so.create_event("test", "low", "test", "desc")
        result = so.trigger_playbook("pb-disabled", event.event_id)
        assert result is None

    def test_get_event_direct(self) -> None:
        so = create_security_orchestrator()
        event = so.create_event("test", "low", "Test", "desc")
        retrieved = so.get_event(event.event_id)
        assert retrieved is not None
        assert retrieved.event_id == event.event_id

    def test_get_event_not_found(self) -> None:
        so = create_security_orchestrator()
        assert so.get_event("nonexistent") is None

    def test_get_execution_history_empty(self) -> None:
        so = create_security_orchestrator()
        assert so.get_execution_history() == []

    def test_get_execution_history_after_run(self) -> None:
        so = create_security_orchestrator()
        event = so.create_event("test", "low", "test", "desc")
        so.trigger_playbook("playbook-threat-response", event.event_id)
        history = so.get_execution_history()
        assert len(history) >= 1
        assert history[0].playbook_id == "playbook-threat-response"

    def test_get_statistics_with_history(self) -> None:
        so = create_security_orchestrator()
        event = so.create_event("test", "low", "test", "desc")
        so.trigger_playbook("playbook-threat-response", event.event_id)
        stats = so.get_statistics()
        assert stats["total_executions"] >= 1
        assert stats["most_executed_playbook"] != ""
