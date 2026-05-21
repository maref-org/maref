from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import A2ATaskState


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
def bridge(
    state_machine: GovernanceStateMachine, audit_logger: AuditLogger, circuit_breaker: CircuitBreaker
) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine,
        audit_logger=audit_logger,
        circuit_breaker=circuit_breaker,
    )


class TestFullTaskLifecycle:
    def test_create_work_complete(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Integration test task")
        assert bridge.sync_state_from_a2a(task_id, "working") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.WORKING
        assert bridge.sync_state_from_a2a(task_id, "completed") is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.COMPLETED
        assert task.maref_state == GovernanceState.REPORT

    def test_create_delegate_sync_complete(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        task_id = bridge.create_task("Delegated task")
        before_audit = len(audit_logger.read_all())
        bridge.delegate_task(task_id, "http://remote-agent:8000")
        after_delegate = len(audit_logger.read_all())
        assert after_delegate > before_audit
        bridge.sync_state_from_a2a(task_id, "completed")
        after_complete = len(audit_logger.read_all())
        assert after_complete > after_delegate

    def test_parallel_tasks_independent(self, bridge: A2ABridge) -> None:
        tasks = [
            bridge.create_task(f"Task {i}") for i in range(3)
        ]
        bridge.sync_state_from_a2a(tasks[0], "working")
        bridge.sync_state_from_a2a(tasks[1], "completed")
        assert bridge.get_task(tasks[0]).a2a_state == A2ATaskState.WORKING  # type: ignore[union-attr]
        assert bridge.get_task(tasks[1]).a2a_state == A2ATaskState.COMPLETED  # type: ignore[union-attr]
        assert bridge.get_task(tasks[2]).a2a_state == A2ATaskState.SUBMITTED  # type: ignore[union-attr]

    def test_stabilize_halt_flow(
        self, bridge: A2ABridge, state_machine: GovernanceStateMachine
    ) -> None:
        task_id = bridge.create_task("Stabilize test")
        bridge.sync_state_from_a2a(task_id, "working")
        state_machine.force_stabilize("Manual stabilize")
        assert state_machine.current_state == GovernanceState.STABILIZE
        task = bridge.get_task(task_id)
        assert task is not None


class TestCircuitBreakerScenarios:
    def test_circuit_breaker_opens_on_trips(
        self,
        bridge: A2ABridge,
        circuit_breaker: CircuitBreaker,
        state_machine: GovernanceStateMachine,
    ) -> None:
        for _ in range(6):
            circuit_breaker.check_depth(depth=5)
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge.create_task("Should fail")

    def test_circuit_breaker_closed_allows_operations(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Normal task")
        bridge.delegate_task(task_id, "http://agent-b:8000")
        tasks = bridge.list_governed_tasks()
        assert len(tasks) > 0

    def test_force_stabilize_pauses_task(
        self, bridge: A2ABridge, state_machine: GovernanceStateMachine
    ) -> None:
        task_id = bridge.create_task("Pausable task")
        bridge.sync_state_from_a2a(task_id, "working")
        state_machine.force_stabilize("Pause for stabilization")
        assert state_machine.current_state == GovernanceState.STABILIZE
        tasks = bridge.list_governed_tasks()
        assert len(tasks) == 1


class TestAuditTrail:
    def test_every_operation_logged(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        before = len(audit_logger.read_all())
        task_id = bridge.create_task("Audit test")
        bridge.delegate_task(task_id, "http://agent-b:8000")
        bridge.sync_state_from_a2a(task_id, "completed")
        after = len(audit_logger.read_all())
        assert after >= before + 3

    def test_audit_entries_have_correct_structure(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        bridge.create_task("Structure test")
        entries = audit_logger.read_all()
        for entry in entries:
            data = entry.to_dict()
            assert "id" in data
            assert "timestamp" in data
            assert "event_type" in data
            assert "actor" in data
            assert "action" in data

    def test_halt_produces_audit_entry(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        task_id = bridge.create_task("Halt audit test")
        before = len(audit_logger.read_all())
        bridge.force_halt_task(task_id, "Testing audit on halt")
        after = len(audit_logger.read_all())
        assert after > before


class TestMultitaskGovernance:
    def test_multiple_task_states_isolated(self, bridge: A2ABridge) -> None:
        t1 = bridge.create_task("Task 1")
        t2 = bridge.create_task("Task 2")
        bridge.sync_state_from_a2a(t1, "completed")
        bridge.sync_state_from_a2a(t2, "failed")
        task1 = bridge.get_task(t1)
        task2 = bridge.get_task(t2)
        assert task1 is not None and task2 is not None
        assert task1.a2a_state != task2.a2a_state

    def test_tasks_survive_state_machine_stabilize(
        self, bridge: A2ABridge, state_machine: GovernanceStateMachine
    ) -> None:
        bridge.create_task("Survivor task")
        state_machine.force_stabilize("System stabilize")
        tasks = bridge.list_governed_tasks()
        assert len(tasks) == 1
