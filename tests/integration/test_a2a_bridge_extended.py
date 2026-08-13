from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import A2ASkillDefinition, A2ATaskState


@pytest.fixture
def mock_state_machine():
    return MagicMock()


@pytest.fixture
def mock_audit_logger():
    return MagicMock()


@pytest.fixture
def mock_circuit_breaker():
    cb = MagicMock()
    cb.is_open = False
    return cb


@pytest.fixture
def mock_trajectory():
    return MagicMock()


@pytest.fixture
def bridge(mock_state_machine, mock_audit_logger):
    return A2ABridge(
        state_machine=mock_state_machine,
        audit_logger=mock_audit_logger,
    )


@pytest.fixture
def bridge_with_cb(mock_state_machine, mock_audit_logger, mock_circuit_breaker):
    return A2ABridge(
        state_machine=mock_state_machine,
        audit_logger=mock_audit_logger,
        circuit_breaker=mock_circuit_breaker,
    )


@pytest.fixture
def bridge_with_trajectory(mock_state_machine, mock_audit_logger, mock_trajectory):
    return A2ABridge(
        state_machine=mock_state_machine,
        audit_logger=mock_audit_logger,
        trajectory_collector=mock_trajectory,
    )


class TestInitExtended:
    def test_initializes_async_lock(self, bridge):
        assert bridge._lock is not None

    def test_initializes_state_queues_empty(self, bridge):
        assert bridge._state_queues == {}

    def test_trajectory_default_created(self, bridge):
        assert bridge._trajectory is not None

    def test_trajectory_custom(self, bridge_with_trajectory, mock_trajectory):
        assert bridge_with_trajectory._trajectory is mock_trajectory

    def test_default_capabilities_registered(self, bridge):
        assert len(bridge._capabilities) == 3

    def test_custom_agent_name_and_description(self, mock_state_machine, mock_audit_logger):
        br = A2ABridge(
            state_machine=mock_state_machine,
            audit_logger=mock_audit_logger,
            agent_name="custom-agent",
            agent_description="Custom description",
        )
        assert br._name == "custom-agent"
        assert br._description == "Custom description"


class TestCircuitBreakerExtended:
    def test_cb_closed_allows_operation(self, bridge_with_cb, mock_circuit_breaker):
        mock_circuit_breaker.is_open = False
        bridge_with_cb._check_circuit_breaker()

    def test_cb_open_raises(self, bridge_with_cb, mock_circuit_breaker):
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError, match="Circuit breaker is OPEN"):
            bridge_with_cb._check_circuit_breaker()

    def test_cb_none_skips_check(self, bridge):
        bridge._cb = None
        bridge._check_circuit_breaker()

    def test_cb_closed_after_open(self, bridge_with_cb, mock_circuit_breaker):
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb._check_circuit_breaker()
        mock_circuit_breaker.is_open = False
        bridge_with_cb._check_circuit_breaker()


class TestBuildAgentCardExtended:
    def test_returns_card_with_correct_structure(self, bridge):
        card = bridge.build_agent_card("http://localhost:8080")
        assert isinstance(card, dict)
        assert card["name"] == "maref-agent"
        assert card["protocolVersion"] == "1.0"
        assert card["url"] == "http://localhost:8080"

    def test_capabilities_flags(self, bridge):
        card = bridge.build_agent_card()
        caps = card["capabilities"]
        assert caps["streaming"] is True
        assert caps["pushNotifications"] is True
        assert caps["stateTransitionHistory"] is True

    def test_default_input_output_modes(self, bridge):
        card = bridge.build_agent_card()
        assert card["defaultInputModes"] == ["text/plain"]
        assert card["defaultOutputModes"] == ["application/json"]

    @patch("maref.integration.a2a_bridge.validate_agent_card_json", return_value=False)
    def test_validation_failure_raises(self, mock_validate, bridge):
        with pytest.raises(ValueError, match="AgentCard does not pass schema validation"):
            bridge.build_agent_card()

    def test_skills_serialization_format(self, bridge):
        card = bridge.build_agent_card()
        for skill in card["skills"]:
            assert isinstance(skill["tags"], list)
            assert isinstance(skill["examples"], list)
            assert "inputModes" in skill
            assert "outputModes" in skill

    def test_circuit_breaker_blocks_build(self, bridge_with_cb, mock_circuit_breaker):
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.build_agent_card()


class TestCreateTaskExtended:
    def test_generates_uuid_based_id(self, bridge):
        task_id = bridge.create_task("Test task")
        assert task_id.startswith("maref-task-")
        assert len(task_id) == len("maref-task-") + 12

    def test_stores_task_internal(self, bridge):
        task_id = bridge.create_task("Internal store")
        assert task_id in bridge._tasks

    def test_initial_a2a_state(self, bridge):
        task_id = bridge.create_task("State check")
        task = bridge._tasks[task_id]
        assert task.a2a_state == A2ATaskState.SUBMITTED

    def test_initial_maref_state(self, bridge):
        task_id = bridge.create_task("Maref state")
        task = bridge._tasks[task_id]
        assert task.maref_state == GovernanceState.INIT

    def test_context_stored(self, bridge):
        task_id = bridge.create_task("With ctx", {"key": "val"})
        task = bridge._tasks[task_id]
        assert task.context == {"key": "val"}

    def test_empty_context(self, bridge):
        task_id = bridge.create_task("No ctx")
        task = bridge._tasks[task_id]
        assert task.context == {}

    def test_audit_logged(self, bridge, mock_audit_logger):
        bridge.create_task("Audit test")
        mock_audit_logger.log.assert_called_once()
        call_kwargs = mock_audit_logger.log.call_args[1]
        assert call_kwargs["event_type"] == "a2a_task_created"

    def test_cb_open_raises(self, bridge_with_cb, mock_circuit_breaker):
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.create_task("Fail")

    def test_trajectory_started(self, bridge_with_trajectory, mock_trajectory):
        task_id = bridge_with_trajectory.create_task("Traj test")
        mock_trajectory.start_task.assert_called_once_with(
            task_id, "Traj test", actor="maref-agent"
        )

    def test_multiple_tasks(self, bridge):
        t1 = bridge.create_task("Task 1")
        t2 = bridge.create_task("Task 2")
        t3 = bridge.create_task("Task 3")
        assert len(bridge._tasks) == 3
        assert t1 != t2 != t3

    def test_sm_transition_called(self, bridge, mock_state_machine):
        bridge.create_task("SM check")
        mock_state_machine.transition.assert_called_once()


class TestGetTaskExtended:
    def test_returns_task_by_id(self, bridge):
        task_id = bridge.create_task("Get me")
        task = bridge.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id

    def test_returns_none_for_unknown(self, bridge):
        assert bridge.get_task("nonexistent") is None

    def test_returns_none_for_empty(self, bridge):
        assert bridge.get_task("") is None


class TestDelegateTaskExtended:
    def test_marks_task_working(self, bridge):
        task_id = bridge.create_task("Delegate")
        assert bridge.delegate_task(task_id, "http://target:8000") is True
        assert bridge._tasks[task_id].a2a_state == A2ATaskState.WORKING

    def test_creates_delegated_record(self, bridge):
        task_id = bridge.create_task("Delegate rec")
        bridge.delegate_task(task_id, "http://target:8000")
        assert task_id in bridge._delegated_tasks

    def test_delegated_record_fields(self, bridge):
        task_id = bridge.create_task("Delegate fields")
        bridge.delegate_task(task_id, "http://target:8000")
        dt = bridge._delegated_tasks[task_id]
        assert dt.target_agent_url == "http://target:8000"
        assert dt.status == A2ATaskState.SUBMITTED

    def test_unknown_task_returns_false(self, bridge):
        assert bridge.delegate_task("nonexistent", "http://target:8000") is False

    def test_audit_logged(self, bridge, mock_audit_logger):
        task_id = bridge.create_task("Audit delegate")
        bridge.delegate_task(task_id, "http://target:8000")
        matching = [
            c
            for c in mock_audit_logger.log.call_args_list
            if c.kwargs.get("event_type") == "a2a_task_delegated"
        ]
        assert len(matching) == 1

    def test_cb_open_raises(self, bridge_with_cb, mock_circuit_breaker):
        task_id = bridge_with_cb.create_task("CB delegate")
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.delegate_task(task_id, "http://target:8000")

    def test_trajectory_recorded(self, bridge_with_trajectory, mock_trajectory):
        task_id = bridge_with_trajectory.create_task("Traj delegate")
        bridge_with_trajectory.delegate_task(task_id, "http://target:8000")
        mock_trajectory.record_delegation.assert_called_once_with(task_id, "http://target:8000")

    @patch("maref.integration.a2a_bridge.A2AClient")
    def test_async_send_suppresses_runtime_error(self, mock_client_cls, bridge):
        mock_client_cls.side_effect = RuntimeError("no event loop")
        task_id = bridge.create_task("Suppress err")
        result = bridge.delegate_task(task_id, "http://target:8000")
        assert result is True

    @patch("maref.integration.a2a_bridge.A2AClient")
    def test_async_send_suppresses_general_error(self, mock_client_cls, bridge):
        mock_client_cls.side_effect = Exception("unexpected")
        task_id = bridge.create_task("Suppress gen")
        result = bridge.delegate_task(task_id, "http://target:8000")
        assert result is True


class TestSyncStateFromA2AExtended:
    def test_valid_state_updates_task(self, bridge):
        task_id = bridge.create_task("Sync valid")
        assert bridge.sync_state_from_a2a(task_id, "working") is True
        task = bridge._tasks[task_id]
        assert task.a2a_state == A2ATaskState.WORKING

    def test_unknown_task_returns_false(self, bridge):
        assert bridge.sync_state_from_a2a("unknown", "working") is False

    def test_invalid_state_string_returns_false(self, bridge):
        task_id = bridge.create_task("Invalid state")
        assert bridge.sync_state_from_a2a(task_id, "bogus_state") is False
        assert bridge._tasks[task_id].a2a_state == A2ATaskState.SUBMITTED

    def test_all_valid_states(self, bridge):
        task_id = bridge.create_task("All states")
        for state in A2ATaskState:
            bridge.sync_state_from_a2a(task_id, state.value)
            assert bridge._tasks[task_id].a2a_state == state

    def test_audit_logged(self, bridge, mock_audit_logger):
        task_id = bridge.create_task("Sync audit")
        bridge.sync_state_from_a2a(task_id, "working")
        matching = [
            c
            for c in mock_audit_logger.log.call_args_list
            if c.kwargs.get("event_type") == "a2a_state_sync"
        ]
        assert len(matching) >= 1

    def test_cb_open_raises(self, bridge_with_cb, mock_circuit_breaker):
        task_id = bridge_with_cb.create_task("CB sync")
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.sync_state_from_a2a(task_id, "working")

    def test_trajectory_recorded(self, bridge_with_trajectory, mock_trajectory):
        task_id = bridge_with_trajectory.create_task("Traj sync")
        bridge_with_trajectory.sync_state_from_a2a(task_id, "working")
        mock_trajectory.record_event.assert_called_once()

    def test_notifies_state_change(self, bridge):
        task_id = bridge.create_task("Notify sync")
        bridge.sync_state_from_a2a(task_id, "working")
        assert task_id in bridge._state_queues
        assert not bridge._state_queues[task_id].empty()


class TestHandlePushNotificationExtended:
    def test_state_update_event_syncs(self, bridge):
        task_id = bridge.create_task("Push state")
        bridge.handle_push_notification(task_id, {"type": "state_update", "state": "completed"})
        assert bridge._tasks[task_id].a2a_state == A2ATaskState.COMPLETED

    def test_non_state_event_stores(self, bridge):
        task_id = bridge.create_task("Push non-state")
        bridge.handle_push_notification(task_id, {"type": "heartbeat", "data": "ping"})
        assert bridge._tasks[task_id].context["last_push_event"] == {
            "type": "heartbeat",
            "data": "ping",
        }

    def test_state_update_missing_state_key_noop(self, bridge):
        task_id = bridge.create_task("Push no state")
        bridge.handle_push_notification(task_id, {"type": "state_update"})
        assert bridge._tasks[task_id].a2a_state == A2ATaskState.SUBMITTED

    def test_unknown_task_raises(self, bridge):
        with pytest.raises(ValueError, match="Unknown task"):
            bridge.handle_push_notification(
                "nonexistent", {"type": "state_update", "state": "completed"}
            )

    def test_cb_open_raises(self, bridge_with_cb, mock_circuit_breaker):
        task_id = bridge_with_cb.create_task("CB push")
        mock_circuit_breaker.is_open = True
        with pytest.raises(CommunicationBlockedError):
            bridge_with_cb.handle_push_notification(
                task_id, {"type": "state_update", "state": "completed"}
            )


class TestListGovernedTasksExtended:
    def test_empty_list(self, bridge):
        assert bridge.list_governed_tasks() == []

    def test_filter_none_returns_all(self, bridge):
        bridge.create_task("Task 1")
        bridge.create_task("Task 2")
        assert len(bridge.list_governed_tasks()) == 2

    def test_filter_matching_state(self, bridge):
        t1 = bridge.create_task("Task 1")
        bridge.sync_state_from_a2a(t1, "working")
        bridge.create_task("Task 2")
        tasks = bridge.list_governed_tasks(filter_state=GovernanceState.ACT)
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == t1

    def test_filter_no_match(self, bridge):
        bridge.create_task("Task 1")
        tasks = bridge.list_governed_tasks(filter_state=GovernanceState.HALT)
        assert len(tasks) == 0

    def test_returned_fields(self, bridge):
        bridge.create_task("Fields")
        tasks = bridge.list_governed_tasks()
        entry = tasks[0]
        assert set(entry.keys()) == {
            "task_id",
            "description",
            "a2a_state",
            "maref_state",
            "created_at",
            "updated_at",
        }


class TestForceHaltTaskExtended:
    def test_halt_updates_states(self, bridge):
        task_id = bridge.create_task("Halt")
        assert bridge.force_halt_task(task_id, "reason") is True
        task = bridge._tasks[task_id]
        assert task.a2a_state == A2ATaskState.CANCELED
        assert task.maref_state == GovernanceState.HALT

    def test_halt_unknown_returns_false(self, bridge):
        assert bridge.force_halt_task("nonexistent") is False

    def test_halt_without_reason(self, bridge):
        task_id = bridge.create_task("No reason")
        assert bridge.force_halt_task(task_id) is True
        assert bridge._tasks[task_id].maref_state == GovernanceState.HALT

    def test_halt_audit_logged(self, bridge, mock_audit_logger):
        task_id = bridge.create_task("Audit halt")
        bridge.force_halt_task(task_id, "test halt")
        matching = [
            c
            for c in mock_audit_logger.log.call_args_list
            if c.kwargs.get("event_type") == "a2a_task_halted"
        ]
        assert len(matching) >= 1

    def test_halt_notifies_state_change(self, bridge):
        task_id = bridge.create_task("Notify halt")
        bridge.force_halt_task(task_id)
        assert task_id in bridge._state_queues
        state = bridge._state_queues[task_id].get_nowait()
        assert state == A2ATaskState.CANCELED

    def test_halt_trajectory_completed(self, bridge_with_trajectory, mock_trajectory):
        task_id = bridge_with_trajectory.create_task("Traj halt")
        bridge_with_trajectory.force_halt_task(task_id, "stop")
        mock_trajectory.complete_task.assert_called_once_with(task_id, final_state="canceled")


class TestGetDelegatedTasksExtended:
    def test_empty_returns_empty_list(self, bridge):
        assert bridge.get_delegated_tasks() == []

    def test_after_delegation_returns_list(self, bridge):
        task_id = bridge.create_task("Delegate me")
        bridge.delegate_task(task_id, "http://remote:8000")
        tasks = bridge.get_delegated_tasks()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == task_id
        assert tasks[0]["target_agent_url"] == "http://remote:8000"

    def test_multiple_delegations(self, bridge):
        t1 = bridge.create_task("D1")
        t2 = bridge.create_task("D2")
        bridge.delegate_task(t1, "http://a:8000")
        bridge.delegate_task(t2, "http://b:8000")
        assert len(bridge.get_delegated_tasks()) == 2


class TestNotifyStateChangeExtended:
    def test_notify_existing_task(self, bridge):
        task_id = bridge.create_task("Notify")
        bridge._notify_state_change(task_id)
        assert task_id in bridge._state_queues

    def test_notify_puts_current_state(self, bridge):
        task_id = bridge.create_task("Notify state")
        bridge._notify_state_change(task_id)
        state = bridge._state_queues[task_id].get_nowait()
        assert state == A2ATaskState.SUBMITTED

    def test_notify_creates_queue(self, bridge):
        task_id = bridge.create_task("Create queue")
        bridge._state_queues.clear()
        bridge._notify_state_change(task_id)
        assert task_id in bridge._state_queues

    def test_notify_unknown_task_noop(self, bridge):
        bridge._notify_state_change("unknown")
        assert "unknown" not in bridge._state_queues

    def test_notify_after_state_change(self, bridge):
        task_id = bridge.create_task("After change")
        bridge.sync_state_from_a2a(task_id, "completed")
        queue = bridge._state_queues[task_id]
        states = []
        while not queue.empty():
            states.append(queue.get_nowait())
        assert A2ATaskState.COMPLETED in states


class TestRegisterCapabilityExtended:
    def test_register_custom_capability(self, bridge):
        skill = A2ASkillDefinition(
            id="custom",
            name="Custom Skill",
            description="A custom capability",
        )
        bridge.register_capability(skill)
        assert len(bridge._capabilities) == 4
        assert bridge._capabilities[-1].id == "custom"

    def test_audit_entry_logged(self, bridge, mock_audit_logger):
        skill = A2ASkillDefinition(id="x", name="X", description="X desc")
        bridge.register_capability(skill)
        mock_audit_logger.log.assert_called_once()
        call_kwargs = mock_audit_logger.log.call_args[1]
        assert call_kwargs["event_type"] == "a2a_capability_registered"
        assert call_kwargs["details"] == "Registered capability: x"

    def test_register_with_tags_and_examples(self, bridge):
        skill = A2ASkillDefinition(
            id="complex",
            name="Complex",
            description="Complex skill",
            tags=["tag1", "tag2"],
            examples=["example1"],
        )
        bridge.register_capability(skill)
        assert bridge._capabilities[-1].tags == ["tag1", "tag2"]

    def test_register_empty_skill_definition(self, bridge):
        skill = A2ASkillDefinition(id="", name="", description="")
        bridge.register_capability(skill)
        assert bridge._capabilities[-1].id == ""


class TestWaitForStateChangeExtended:
    @pytest.mark.asyncio
    async def test_wait_returns_state(self, bridge):
        task_id = bridge.create_task("Wait test")
        bridge._notify_state_change(task_id)
        state = await bridge.wait_for_state_change(task_id)
        assert state == A2ATaskState.SUBMITTED

    @pytest.mark.asyncio
    async def test_wait_creates_queue_if_missing(self, bridge):
        """wait_for_state_change creates a queue if none exists and blocks until a state is put."""
        import asyncio

        async def put_after_delay():
            await asyncio.sleep(0.01)
            bridge._state_queues["new-task"].put_nowait(A2ATaskState.SUBMITTED)
            return True

        asyncio.ensure_future(put_after_delay())
        state = await bridge.wait_for_state_change("new-task")
        assert state == A2ATaskState.SUBMITTED


class TestCommunicationBlockedErrorExtended:
    def test_is_exception_subclass(self):
        assert issubclass(CommunicationBlockedError, Exception)

    def test_default_message(self):
        err = CommunicationBlockedError()
        assert str(err) == ""

    def test_custom_message(self):
        err = CommunicationBlockedError("custom message")
        assert str(err) == "custom message"

    def test_can_be_raised_and_caught(self):
        with pytest.raises(CommunicationBlockedError):
            raise CommunicationBlockedError("test")


class TestConnectionManagement:
    def test_multiple_operations_use_same_state(self, bridge):
        t1 = bridge.create_task("Task 1")
        t2 = bridge.create_task("Task 2")
        assert bridge.get_task(t1) is not None
        assert bridge.get_task(t2) is not None
        assert len(bridge.list_governed_tasks()) == 2

    def test_sync_then_halt(self, bridge):
        task_id = bridge.create_task("Sync then halt")
        bridge.sync_state_from_a2a(task_id, "working")
        bridge.force_halt_task(task_id, "stop")
        task = bridge._tasks[task_id]
        assert task.maref_state == GovernanceState.HALT

    def test_delegate_then_sync(self, bridge):
        task_id = bridge.create_task("Delegate then sync")
        bridge.delegate_task(task_id, "http://target:8000")
        bridge.sync_state_from_a2a(task_id, "completed")
        task = bridge._tasks[task_id]
        assert task.a2a_state == A2ATaskState.COMPLETED
