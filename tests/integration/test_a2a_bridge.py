from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import A2ASkillDefinition, A2ATaskState


@pytest.fixture
def audit_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def audit_logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


@pytest.fixture
def state_machine() -> GovernanceStateMachine:
    return GovernanceStateMachine()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker()


@pytest.fixture
def bridge(state_machine: GovernanceStateMachine, audit_logger: AuditLogger) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
    )


@pytest.fixture
def bridge_with_cb(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
    circuit_breaker: CircuitBreaker,
) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
        circuit_breaker=circuit_breaker,
    )


class TestInit:
    def test_default_agent_name(self, bridge: A2ABridge) -> None:
        assert bridge._name == "maref-agent"
        assert bridge._description == "MAREF-governed agent"

    def test_custom_agent_name(self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger) -> None:
        br = A2ABridge(state_machine, audit_logger, agent_name="custom-agent", agent_description="Custom desc")
        assert br._name == "custom-agent"
        assert br._description == "Custom desc"

    def test_default_capabilities_registered(self, bridge: A2ABridge) -> None:
        assert len(bridge._capabilities) == 3
        ids = {c.id for c in bridge._capabilities}
        assert ids == {"maref-governance", "maref-delegate", "maref-audit"}

    def test_with_circuit_breaker(self, bridge_with_cb: A2ABridge) -> None:
        assert bridge_with_cb._cb is not None

    def test_without_circuit_breaker(self, bridge: A2ABridge) -> None:
        assert bridge._cb is None

    def test_tasks_empty(self, bridge: A2ABridge) -> None:
        assert bridge._tasks == {}
        assert bridge._delegated_tasks == {}


class TestRegisterCapability:
    def test_registers_and_logs(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        before = len(audit_logger.read_all())
        skill = A2ASkillDefinition(
            id="custom-skill", name="Custom", description="Custom capability"
        )
        bridge.register_capability(skill)
        assert len(bridge._capabilities) == 4
        assert bridge._capabilities[-1].id == "custom-skill"
        after = len(audit_logger.read_all())
        assert after > before

    def test_audit_entry_content(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        skill = A2ASkillDefinition(id="skill-x", name="Skill X", description="Desc X")
        bridge.register_capability(skill)
        entries = audit_logger.read_all()
        matching = [e for e in entries if e.event_type == "a2a_capability_registered"]
        assert len(matching) >= 1
        entry = matching[-1]
        assert entry.action == "register_capability"
        assert "skill-x" in entry.details


class TestCheckCircuitBreaker:
    def test_cb_closed_no_error(self, bridge_with_cb: A2ABridge) -> None:
        bridge_with_cb._check_circuit_breaker()

    def test_cb_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError, match="Circuit breaker is OPEN"):
            bridge_with_cb._check_circuit_breaker()

    def test_cb_none_no_error(self, bridge: A2ABridge) -> None:
        bridge._check_circuit_breaker()


class TestBuildAgentCard:
    def test_returns_valid_card(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card("http://localhost:9999")
        assert card["name"] == "maref-agent"
        assert card["protocolVersion"] == "1.0"
        assert card["url"] == "http://localhost:9999"
        assert len(card["skills"]) == 3
        assert card["capabilities"]["streaming"] is True
        assert card["capabilities"]["pushNotifications"] is True

    def test_default_base_url(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        assert card["url"] == "http://localhost:8000"

    def test_skills_include_registered(self, bridge: A2ABridge) -> None:
        bridge.register_capability(A2ASkillDefinition(id="extra", name="Extra", description="Extra skill"))
        card = bridge.build_agent_card()
        skill_ids = {s["id"] for s in card["skills"]}
        assert "extra" in skill_ids

    def test_circuit_breaker_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.build_agent_card()

    def test_skill_serialization(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        for skill in card["skills"]:
            assert "inputModes" in skill
            assert "outputModes" in skill
            assert "tags" in skill
            assert "examples" in skill


class TestCreateTask:
    def test_creates_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        assert task_id.startswith("maref-task-")
        assert len(task_id) > len("maref-task-")

    def test_task_initial_state(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("State check")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.SUBMITTED
        assert task.maref_state == GovernanceState.INIT

    def test_stores_context(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("With context", {"source": "test"})
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.context == {"source": "test"}
        assert task.description == "With context"

    def test_empty_context(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("No context")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.context == {}

    def test_audit_logged(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        before = len(audit_logger.read_all())
        bridge.create_task("Auditable task")
        after = len(audit_logger.read_all())
        assert after > before

    def test_timestamp_set(self, bridge: A2ABridge) -> None:
        import time
        task_id = bridge.create_task("Timing")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.created_at > 0
        assert task.updated_at == task.created_at

    def test_circuit_breaker_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.create_task("Should fail")

    def test_multiple_tasks_unique_ids(self, bridge: A2ABridge) -> None:
        t1 = bridge.create_task("Task 1")
        t2 = bridge.create_task("Task 2")
        assert t1 != t2


class TestGetTask:
    def test_returns_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Get me")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id

    def test_returns_none_for_unknown(self, bridge: A2ABridge) -> None:
        assert bridge.get_task("nonexistent") is None

    def test_returns_none_for_empty_string(self, bridge: A2ABridge) -> None:
        assert bridge.get_task("") is None


class TestDelegateTask:
    def test_delegate_marks_working(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Delegate me")
        assert bridge.delegate_task(task_id, "http://target:8000") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.WORKING

    def test_delegate_creates_delegated_record(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Delegate records")
        bridge.delegate_task(task_id, "http://target:8000")
        delegated = bridge.get_delegated_tasks()
        assert len(delegated) == 1
        assert delegated[0]["task_id"] == task_id
        assert delegated[0]["target_agent_url"] == "http://target:8000"
        assert delegated[0]["status"] == "submitted"

    def test_delegate_unknown_returns_false(self, bridge: A2ABridge) -> None:
        assert bridge.delegate_task("nonexistent", "http://target:8000") is False

    def test_delegate_audit_logged(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        task_id = bridge.create_task("Audit delegate")
        before = len(audit_logger.read_all())
        bridge.delegate_task(task_id, "http://target:8000")
        after = len(audit_logger.read_all())
        assert after > before

    def test_delegate_circuit_breaker_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        task_id = bridge_with_cb.create_task("CB delegate")
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.delegate_task(task_id, "http://target:8000")

    def test_delegate_updated_at_increased(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Timestamp check")
        original = bridge.get_task(task_id)
        assert original is not None
        original_updated = original.updated_at
        bridge.delegate_task(task_id, "http://target:8000")
        updated = bridge.get_task(task_id)
        assert updated is not None
        assert updated.updated_at >= original_updated

    @patch("maref.integration.a2a_bridge.A2AClient")
    def test_delegate_sends_task_async(self, mock_client_cls: MagicMock, bridge: A2ABridge) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        task_id = bridge.create_task("Async delegate")
        with patch.object(bridge._lock.__class__, "acquire"):
            result = bridge.delegate_task(task_id, "http://target:8000")
        assert result is True


class TestSyncStateFromA2A:
    def test_updates_both_states(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Sync test")
        assert bridge.sync_state_from_a2a(task_id, "working") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.WORKING
        assert task.maref_state == GovernanceState.ACT

    def test_unknown_task_returns_false(self, bridge: A2ABridge) -> None:
        assert bridge.sync_state_from_a2a("nonexistent", "working") is False

    def test_invalid_state_returns_false(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Invalid state")
        assert bridge.sync_state_from_a2a(task_id, "bogus_state") is False
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.SUBMITTED

    def test_completed_sync(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Complete sync")
        assert bridge.sync_state_from_a2a(task_id, "completed") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.COMPLETED
        assert task.maref_state == GovernanceState.REPORT

    def test_failed_sync(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Fail sync")
        assert bridge.sync_state_from_a2a(task_id, "failed") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.maref_state == GovernanceState.HALT

    def test_updated_at_incremented(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Time sync")
        task = bridge.get_task(task_id)
        original = task.updated_at if task else 0.0
        import time
        time.sleep(0.001)
        bridge.sync_state_from_a2a(task_id, "working")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.updated_at > original

    def test_audit_logged(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        task_id = bridge.create_task("Audit sync")
        before = len(audit_logger.read_all())
        bridge.sync_state_from_a2a(task_id, "working")
        after = len(audit_logger.read_all())
        assert after > before

    def test_circuit_breaker_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        task_id = bridge_with_cb.create_task("CB sync")
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.sync_state_from_a2a(task_id, "working")

    def test_notifies_state_change(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Notify sync")
        bridge.sync_state_from_a2a(task_id, "working")
        state = bridge._state_queues.get(task_id)
        assert state is not None
        assert not state.empty()


class TestHandlePushNotification:
    def test_state_update_event(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Push state update")
        bridge.handle_push_notification(task_id, {"type": "state_update", "state": "completed"})
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.COMPLETED

    def test_non_state_event_stores_event(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Push non-state")
        bridge.handle_push_notification(task_id, {"type": "heartbeat", "data": "ping"})
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.context.get("last_push_event") == {"type": "heartbeat", "data": "ping"}
        assert task.a2a_state == A2ATaskState.SUBMITTED

    def test_state_update_without_state_key_noop(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Push no state")
        bridge.handle_push_notification(task_id, {"type": "state_update"})
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.SUBMITTED

    def test_unknown_task_raises(self, bridge: A2ABridge) -> None:
        with pytest.raises(ValueError, match="Unknown task"):
            bridge.handle_push_notification("nonexistent", {"type": "state_update", "state": "completed"})

    def test_updated_at_changed(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Push time")
        task = bridge.get_task(task_id)
        original = task.updated_at if task else 0.0
        import time
        time.sleep(0.001)
        bridge.handle_push_notification(task_id, {"type": "any", "data": "x"})
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.updated_at > original

    def test_circuit_breaker_open_raises(self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker) -> None:
        task_id = bridge_with_cb.create_task("CB push")
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.handle_push_notification(task_id, {"type": "state_update", "state": "completed"})


class TestListGovernedTasks:
    def test_list_all(self, bridge: A2ABridge) -> None:
        bridge.create_task("Task 1")
        bridge.create_task("Task 2")
        tasks = bridge.list_governed_tasks()
        assert len(tasks) == 2

    def test_filter_by_state(self, bridge: A2ABridge) -> None:
        t1 = bridge.create_task("Will work")
        bridge.sync_state_from_a2a(t1, "working")
        t2 = bridge.create_task("Will stay")
        tasks = bridge.list_governed_tasks(filter_state=GovernanceState.ACT)
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == t1
        assert tasks[0]["maref_state"] == "ACT"

    def test_filter_no_match(self, bridge: A2ABridge) -> None:
        bridge.create_task("Task")
        tasks = bridge.list_governed_tasks(filter_state=GovernanceState.REPORT)
        assert len(tasks) == 0

    def test_returns_summary_dict(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Summary test")
        tasks = bridge.list_governed_tasks()
        assert len(tasks) == 1
        entry = tasks[0]
        assert "task_id" in entry
        assert "description" in entry
        assert "a2a_state" in entry
        assert "maref_state" in entry
        assert "created_at" in entry
        assert "updated_at" in entry
        assert entry["a2a_state"] == "submitted"
        assert entry["maref_state"] == "INIT"


class TestForceHaltTask:
    def test_halt_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Halt me")
        assert bridge.force_halt_task(task_id, "Bad data") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.CANCELED
        assert task.maref_state == GovernanceState.HALT

    def test_halt_unknown_returns_false(self, bridge: A2ABridge) -> None:
        assert bridge.force_halt_task("nonexistent", "reason") is False

    def test_halt_logs_audit(self, bridge: A2ABridge, audit_logger: AuditLogger) -> None:
        task_id = bridge.create_task("Audit halt")
        before = len(audit_logger.read_all())
        bridge.force_halt_task(task_id, "Testing halt")
        after = len(audit_logger.read_all())
        assert after > before

    def test_halt_notifies_state_change(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Notify halt")
        bridge.force_halt_task(task_id, "done")
        state = bridge._state_queues.get(task_id)
        assert state is not None
        assert not state.empty()
        assert state.get_nowait() == A2ATaskState.CANCELED

    def test_halt_without_reason(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("No reason halt")
        assert bridge.force_halt_task(task_id) is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.maref_state == GovernanceState.HALT

    def test_updated_at_incremented_on_halt(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Halt time")
        task = bridge.get_task(task_id)
        original = task.updated_at if task else 0.0
        import time
        time.sleep(0.001)
        bridge.force_halt_task(task_id, "stop")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.updated_at > original


class TestGetDelegatedTasks:
    def test_empty(self, bridge: A2ABridge) -> None:
        assert bridge.get_delegated_tasks() == []

    def test_after_delegation(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Delegated")
        bridge.delegate_task(task_id, "http://remote:8000")
        tasks = bridge.get_delegated_tasks()
        assert len(tasks) == 1
        dt = tasks[0]
        assert dt["task_id"] == task_id
        assert dt["target_agent_url"] == "http://remote:8000"
        assert dt["status"] == "submitted"
        assert "delegated_at" in dt

    def test_multiple_delegations(self, bridge: A2ABridge) -> None:
        t1 = bridge.create_task("D1")
        t2 = bridge.create_task("D2")
        bridge.delegate_task(t1, "http://a:8000")
        bridge.delegate_task(t2, "http://b:8000")
        assert len(bridge.get_delegated_tasks()) == 2


class TestWaitForStateChange:
    def test_notify_puts_state_in_queue(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Queue test")
        bridge._notify_state_change(task_id)
        result = bridge._state_queues[task_id].get_nowait()
        assert result == A2ATaskState.SUBMITTED

    def test_wait_for_state(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Async wait")
        import asyncio
        async def trigger_and_wait() -> A2ATaskState:
            bridge._notify_state_change(task_id)
            return await bridge.wait_for_state_change(task_id)
        result = asyncio.run(trigger_and_wait())
        assert result == A2ATaskState.SUBMITTED

    def test_notify_creates_queue_if_missing(self, bridge: A2ABridge) -> None:
        # Create a task first
        task_id = bridge.create_task("test task")
        # Clear any queue that might have been created
        bridge._state_queues.clear()
        # Now notify - should create queue for existing task
        bridge._notify_state_change(task_id)
        assert task_id in bridge._state_queues

    def test_notify_noop_for_unknown(self, bridge: A2ABridge) -> None:
        bridge._notify_state_change("nonexistent-task")
        assert "nonexistent-task" not in bridge._state_queues


class TestDEFAULT_GOVERNANCE_SKILLS:
    def test_three_skills(self, bridge: A2ABridge) -> None:
        assert len(bridge._capabilities) == 3

    def test_governance_skill(self, bridge: A2ABridge) -> None:
        skill = bridge._capabilities[0]
        assert skill.id == "maref-governance"
        assert "state-machine" in skill.tags

    def test_delegate_skill(self, bridge: A2ABridge) -> None:
        skill = bridge._capabilities[1]
        assert skill.id == "maref-delegate"
        assert "multi-agent" in skill.tags

    def test_audit_skill(self, bridge: A2ABridge) -> None:
        skill = bridge._capabilities[2]
        assert skill.id == "maref-audit"
        assert "audit" in skill.tags


class TestCommunicationBlockedError:
    def test_is_exception(self) -> None:
        err = CommunicationBlockedError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_can_be_caught_as_exception(self) -> None:
        with pytest.raises(CommunicationBlockedError):
            raise CommunicationBlockedError("blocked")
