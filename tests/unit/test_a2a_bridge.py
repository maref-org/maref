from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import (
    A2ASkillDefinition,
    A2ATaskState,
    map_a2a_to_maref,
    map_maref_to_a2a,
    validate_agent_card_json,
)


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
    return A2ABridge(state_machine=state_machine, audit_logger=audit_logger)


@pytest.fixture
def bridge_with_cb(
    state_machine: GovernanceStateMachine,
    audit_logger: AuditLogger,
    circuit_breaker: CircuitBreaker,
) -> A2ABridge:
    return A2ABridge(
        state_machine=state_machine, audit_logger=audit_logger, circuit_breaker=circuit_breaker
    )


class TestAgentCardGeneration:
    def test_build_agent_card_contains_required_fields(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        assert card["name"] == "maref-agent"
        assert card["description"] == "MAREF-governed agent"
        assert card["version"] == "0.2.0"
        assert "url" in card
        assert "skills" in card

    def test_build_agent_card_skills_non_empty(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        assert len(card["skills"]) >= 3

    def test_build_agent_card_passes_schema_validation(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        assert validate_agent_card_json(card) is True

    def test_build_agent_card_json_serializable(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        serialized = json.dumps(card)
        deserialized = json.loads(serialized)
        assert deserialized["name"] == card["name"]

    def test_build_agent_card_custom_agent_name(
        self, state_machine: GovernanceStateMachine, audit_logger: AuditLogger
    ) -> None:
        bridge = A2ABridge(
            state_machine=state_machine, audit_logger=audit_logger, agent_name="custom-agent"
        )
        card = bridge.build_agent_card()
        assert card["name"] == "custom-agent"

    def test_build_agent_card_capability_structure(self, bridge: A2ABridge) -> None:
        card = bridge.build_agent_card()
        caps = card["capabilities"]
        assert caps["streaming"] is True
        assert caps["pushNotifications"] is True
        assert caps["stateTransitionHistory"] is True


class TestA2AStateMapping:
    @pytest.mark.parametrize(
        "a2a_state,expected_maref",
        [
            (A2ATaskState.SUBMITTED, GovernanceState.INIT),
            (A2ATaskState.WORKING, GovernanceState.ACT),
            (A2ATaskState.INPUT_REQUIRED, GovernanceState.ANALYZE),
            (A2ATaskState.COMPLETED, GovernanceState.REPORT),
            (A2ATaskState.CANCELED, GovernanceState.HALT),
            (A2ATaskState.FAILED, GovernanceState.HALT),
            (A2ATaskState.REJECTED, GovernanceState.HALT),
            (A2ATaskState.AUTH_REQUIRED, GovernanceState.EVALUATE),
        ],
    )
    def test_a2a_to_maref(self, a2a_state: A2ATaskState, expected_maref: GovernanceState) -> None:
        assert map_a2a_to_maref(a2a_state) == expected_maref

    @pytest.mark.parametrize(
        "maref_state,expected_a2a",
        [
            (GovernanceState.INIT, A2ATaskState.SUBMITTED),
            (GovernanceState.OBSERVE, A2ATaskState.WORKING),
            (GovernanceState.ANALYZE, A2ATaskState.WORKING),
            (GovernanceState.EVALUATE, A2ATaskState.INPUT_REQUIRED),
            (GovernanceState.DECIDE, A2ATaskState.WORKING),
            (GovernanceState.ACT, A2ATaskState.WORKING),
            (GovernanceState.VERIFY, A2ATaskState.WORKING),
            (GovernanceState.STABILIZE, A2ATaskState.WORKING),
            (GovernanceState.REPORT, A2ATaskState.COMPLETED),
            (GovernanceState.HALT, A2ATaskState.FAILED),
        ],
    )
    def test_maref_to_a2a(self, maref_state: GovernanceState, expected_a2a: A2ATaskState) -> None:
        assert map_maref_to_a2a(maref_state) == expected_a2a

    def test_invalid_a2a_state_raises(self) -> None:
        with pytest.raises(ValueError):
            map_a2a_to_maref("unknown_state")  # type: ignore[arg-type]


class TestTaskLifecycle:
    def test_create_task_returns_id(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        assert task_id.startswith("maref-task-")
        assert len(task_id) > 12

    def test_create_task_adds_to_registry(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.description == "Test task"
        assert task.a2a_state == A2ATaskState.SUBMITTED
        assert task.maref_state == GovernanceState.INIT

    def test_get_task_unknown_returns_none(self, bridge: A2ABridge) -> None:
        assert bridge.get_task("nonexistent") is None

    def test_create_task_produces_audit_entry(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        before_count = len(audit_logger.read_all())
        bridge.create_task("Test task")
        after_count = len(audit_logger.read_all())
        assert after_count > before_count

    def test_sync_state_updates_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        result = bridge.sync_state_from_a2a(task_id, "working")
        assert result is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.WORKING

    def test_sync_state_unknown_task(self, bridge: A2ABridge) -> None:
        result = bridge.sync_state_from_a2a("nonexistent", "working")
        assert result is False

    def test_sync_state_invalid_state(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        result = bridge.sync_state_from_a2a(task_id, "invalid-state")
        assert result is False

    def test_sync_state_produces_audit_entry(
        self, bridge: A2ABridge, audit_logger: AuditLogger
    ) -> None:
        task_id = bridge.create_task("Test task")
        before_count = len(audit_logger.read_all())
        bridge.sync_state_from_a2a(task_id, "completed")
        after_count = len(audit_logger.read_all())
        assert after_count > before_count


class TestTaskDelegation:
    def test_delegate_task_succeeds(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        result = bridge.delegate_task(task_id, "http://agent-b:8000")
        assert result is True

    def test_delegate_task_unknown(self, bridge: A2ABridge) -> None:
        result = bridge.delegate_task("nonexistent", "http://agent-b:8000")
        assert result is False

    def test_delegate_task_sets_working_state(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        bridge.delegate_task(task_id, "http://agent-b:8000")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.WORKING

    def test_get_delegated_tasks(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        bridge.delegate_task(task_id, "http://agent-b:8000")
        delegated = bridge.get_delegated_tasks()
        assert len(delegated) == 1
        assert delegated[0]["task_id"] == task_id


class TestCircuitBreakerIntegration:
    def test_open_circuit_breaker_blocks_agent_card(
        self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.build_agent_card()

    def test_open_circuit_breaker_blocks_create_task(
        self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.create_task("Test task")

    def test_open_circuit_breaker_blocks_delegate(
        self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.delegate_task("some-task", "http://agent-b:8000")

    def test_open_circuit_breaker_blocks_sync(
        self, bridge_with_cb: A2ABridge, circuit_breaker: CircuitBreaker
    ) -> None:
        circuit_breaker._state = BreakerState.OPEN
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.sync_state_from_a2a("some-task", "working")

    def test_closed_circuit_breaker_allows_operations(self, bridge_with_cb: A2ABridge) -> None:
        card = bridge_with_cb.build_agent_card()
        assert card is not None


class TestPushNotification:
    def test_push_notification_updates_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        event = {"type": "state_update", "state": "completed"}
        bridge.handle_push_notification(task_id, event)
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.COMPLETED

    def test_push_notification_unknown_task(self, bridge: A2ABridge) -> None:
        event = {"type": "state_update", "state": "completed"}
        with pytest.raises(ValueError):
            bridge.handle_push_notification("nonexistent", event)


class TestHaltTask:
    def test_force_halt_task(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Test task")
        result = bridge.force_halt_task(task_id, "Testing halt")
        assert result is True
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.CANCELED
        assert task.maref_state == GovernanceState.HALT

    def test_force_halt_unknown_task(self, bridge: A2ABridge) -> None:
        result = bridge.force_halt_task("nonexistent")
        assert result is False


class TestListGovernedTasks:
    def test_list_all_tasks(self, bridge: A2ABridge) -> None:
        bridge.create_task("Task A")
        bridge.create_task("Task B")
        tasks = bridge.list_governed_tasks()
        assert len(tasks) == 2

    def test_list_filtered_by_state(self, bridge: A2ABridge) -> None:
        task_id = bridge.create_task("Task A")
        bridge.sync_state_from_a2a(task_id, "completed")
        tasks = bridge.list_governed_tasks(filter_state=GovernanceState.REPORT)
        assert len(tasks) == 1
        assert tasks[0]["maref_state"] == "REPORT"

    def test_list_empty(self, bridge: A2ABridge) -> None:
        tasks = bridge.list_governed_tasks()
        assert tasks == []


class TestCustomCapability:
    def test_register_capability(self, bridge: A2ABridge) -> None:
        cap = A2ASkillDefinition(
            id="custom-cap",
            name="Custom Capability",
            description="A custom capability",
            tags=["custom"],
            examples=["Do something custom"],
        )
        bridge.register_capability(cap)
        card = bridge.build_agent_card()
        skill_ids = [s["id"] for s in card["skills"]]
        assert "custom-cap" in skill_ids


class TestSchemaValidation:
    def test_validate_valid_card(self) -> None:
        card = {
            "name": "test-agent",
            "description": "A test agent",
            "version": "1.0.0",
            "url": "http://localhost:8000",
            "skills": [{"id": "s1", "name": "Skill 1", "description": "A skill"}],
        }
        assert validate_agent_card_json(card) is True

    def test_validate_missing_name(self) -> None:
        card = {
            "description": "A test agent",
            "version": "1.0.0",
            "url": "http://localhost:8000",
            "skills": [],
        }
        assert validate_agent_card_json(card) is False

    def test_validate_skills_not_list(self) -> None:
        card = {
            "name": "test-agent",
            "description": "A test agent",
            "version": "1.0.0",
            "url": "http://localhost:8000",
            "skills": "not-a-list",
        }
        assert validate_agent_card_json(card) is False

    def test_validate_skill_missing_id(self) -> None:
        card = {
            "name": "test-agent",
            "description": "A test agent",
            "version": "1.0.0",
            "url": "http://localhost:8000",
            "skills": [{"name": "Skill 1", "description": "A skill"}],
        }
        assert validate_agent_card_json(card) is False

    def test_validate_non_dict(self) -> None:
        assert validate_agent_card_json("not-a-dict") is False  # type: ignore[arg-type]
