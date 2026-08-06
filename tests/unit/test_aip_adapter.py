"""Unit tests for the AIP (Agent Interaction Protocol) adapter."""

from __future__ import annotations

import pytest

from maref.governance.types import GovernanceState
from maref.integration.aip_adapter import (
    AIP_PROTOCOL_VERSION,
    AIPAdapter,
    AIPMessage,
    AIPProduct,
    AIPStateTransitionError,
    AIPTaskCommand,
    AIPTaskCommandType,
    AIPTaskResult,
    AIPTaskState,
    AIP_TO_MAREF_MAP,
    DataItem,
    MAREF_TO_AIP_MAP,
    is_valid_transition,
    map_aip_to_maref,
    map_maref_to_aip,
)
from maref.orchestration.decomposer import SubTask


class TestAIPTaskState:
    def test_enum_values(self) -> None:
        assert AIPTaskState.ACCEPTED.value == "accepted"
        assert AIPTaskState.WORKING.value == "working"
        assert AIPTaskState.AWAITING_INPUT.value == "awaiting-input"
        assert AIPTaskState.AWAITING_COMPLETION.value == "awaiting-completion"
        assert AIPTaskState.COMPLETED.value == "completed"
        assert AIPTaskState.FAILED.value == "failed"
        assert AIPTaskState.CANCELED.value == "canceled"
        assert AIPTaskState.REJECTED.value == "rejected"

    def test_enum_member_count(self) -> None:
        assert len(AIPTaskState) == 8


class TestStateMaps:
    def test_maref_to_aip_all_keys_covered(self) -> None:
        for state in GovernanceState:
            assert state in MAREF_TO_AIP_MAP, f"Missing: {state}"

    def test_aip_to_maref_all_keys_covered(self) -> None:
        for state in AIPTaskState:
            assert state in AIP_TO_MAREF_MAP, f"Missing: {state}"

    def test_map_maref_to_aip_known(self) -> None:
        assert map_maref_to_aip(GovernanceState.INIT) == AIPTaskState.ACCEPTED
        assert map_maref_to_aip(GovernanceState.ACT) == AIPTaskState.WORKING
        assert map_maref_to_aip(GovernanceState.REPORT) == AIPTaskState.COMPLETED

    def test_map_aip_to_maref_known(self) -> None:
        assert map_aip_to_maref(AIPTaskState.ACCEPTED) == GovernanceState.INIT
        assert map_aip_to_maref(AIPTaskState.WORKING) == GovernanceState.ACT
        assert map_aip_to_maref(AIPTaskState.COMPLETED) == GovernanceState.REPORT


class TestTransitions:
    def test_self_transition_allowed(self) -> None:
        assert is_valid_transition(AIPTaskState.WORKING, AIPTaskState.WORKING) is True

    def test_accepted_to_working_allowed(self) -> None:
        assert is_valid_transition(AIPTaskState.ACCEPTED, AIPTaskState.WORKING) is True

    def test_working_to_completed_allowed(self) -> None:
        assert is_valid_transition(AIPTaskState.WORKING, AIPTaskState.COMPLETED) is True

    def test_completed_to_working_forbidden(self) -> None:
        assert is_valid_transition(AIPTaskState.COMPLETED, AIPTaskState.WORKING) is False

    def test_failed_to_anything_forbidden(self) -> None:
        for target in AIPTaskState:
            if target == AIPTaskState.FAILED:
                continue
            assert is_valid_transition(AIPTaskState.FAILED, target) is False

    def test_canceled_to_anything_forbidden(self) -> None:
        for target in AIPTaskState:
            if target == AIPTaskState.CANCELED:
                continue
            assert is_valid_transition(AIPTaskState.CANCELED, target) is False

    def test_working_to_awaiting_input_allowed(self) -> None:
        assert (
            is_valid_transition(AIPTaskState.WORKING, AIPTaskState.AWAITING_INPUT)
            is True
        )

    def test_awaiting_completion_to_completed_allowed(self) -> None:
        assert (
            is_valid_transition(
                AIPTaskState.AWAITING_COMPLETION, AIPTaskState.COMPLETED
            )
            is True
        )


class TestDataItem:
    def test_to_dict(self) -> None:
        item = DataItem(
            type="text",
            content="hello",
            mime_type="text/plain",
            metadata={"key": "value"},
        )
        d = item.to_dict()
        assert d["type"] == "text"
        assert d["content"] == "hello"
        assert d["mimeType"] == "text/plain"
        assert d["metadata"] == {"key": "value"}


class TestAIPMessage:
    def test_to_dict(self) -> None:
        msg = AIPMessage(
            message_id="msg-1",
            message_type="task-command",
            sent_at=1234567890.0,
            sender_role="leader",
            sender_id="leader-1",
            data_items=[DataItem(type="text", content="hi")],
            session_id="sess-1",
        )
        d = msg.to_dict()
        assert d["messageId"] == "msg-1"
        assert d["messageType"] == "task-command"
        assert d["senderRole"] == "leader"
        assert len(d["dataItems"]) == 1


class TestAIPTaskCommand:
    def test_to_dict(self) -> None:
        cmd = AIPTaskCommand(
            command_type=AIPTaskCommandType.START,
            task_id="task-1",
            leader_id="leader-1",
            partner_id="partner-1",
        )
        d = cmd.to_dict()
        assert d["commandType"] == "start"
        assert d["taskId"] == "task-1"
        assert d["leaderId"] == "leader-1"
        assert d["partnerId"] == "partner-1"

    def test_to_message_wraps_in_envelope(self) -> None:
        cmd = AIPTaskCommand(
            command_type=AIPTaskCommandType.START,
            task_id="task-1",
            leader_id="leader-1",
            partner_id="partner-1",
        )
        msg = cmd.to_message()
        assert msg.message_type == "task-command"
        assert msg.sender_role == "leader"
        assert msg.sender_id == "leader-1"


class TestAIPProduct:
    def test_to_dict(self) -> None:
        product = AIPProduct(
            name="report",
            description="final report",
            data_items=[DataItem(type="text", content="content")],
        )
        d = product.to_dict()
        assert d["name"] == "report"
        assert d["description"] == "final report"
        assert len(d["dataItems"]) == 1


class TestAIPTaskResult:
    def test_to_dict(self) -> None:
        result = AIPTaskResult(
            task_id="task-1",
            partner_id="partner-1",
            state=AIPTaskState.COMPLETED,
            products=[AIPProduct(name="p", description="d")],
        )
        d = result.to_dict()
        assert d["taskId"] == "task-1"
        assert d["state"] == "completed"
        assert len(d["products"]) == 1

    def test_to_message_aggregates_product_data_items(self) -> None:
        result = AIPTaskResult(
            task_id="task-1",
            partner_id="partner-1",
            state=AIPTaskState.COMPLETED,
            products=[
                AIPProduct(
                    name="p1",
                    description="d1",
                    data_items=[DataItem(type="text", content="a")],
                ),
                AIPProduct(
                    name="p2",
                    description="d2",
                    data_items=[DataItem(type="text", content="b")],
                ),
            ],
        )
        msg = result.to_message()
        assert msg.message_type == "task-result"
        assert msg.sender_role == "partner"
        assert len(msg.data_items) == 2


class TestAIPAdapter:
    @pytest.fixture
    def adapter(self) -> AIPAdapter:
        return AIPAdapter(leader_id="test-leader")

    @pytest.fixture
    def subtask(self) -> SubTask:
        return SubTask(
            task_id="subtask-0",
            description="analyze data",
            estimated_complexity=0.5,
            required_capabilities=["research"],
        )

    def test_protocol_version(self) -> None:
        assert AIP_PROTOCOL_VERSION == "2.00"

    def test_leader_id_property(self, adapter: AIPAdapter) -> None:
        assert adapter.leader_id == "test-leader"

    def test_subtask_to_start_command(self, adapter: AIPAdapter, subtask: SubTask) -> None:
        cmd = adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        assert cmd.command_type == AIPTaskCommandType.START
        assert cmd.task_id == "subtask-0"
        assert cmd.leader_id == "test-leader"
        assert cmd.partner_id == "partner-1"
        assert len(cmd.data_items) == 1
        assert cmd.data_items[0].metadata["task_id"] == "subtask-0"

    def test_start_command_sets_initial_state_to_accepted(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        assert adapter.get_task_state("subtask-0") == AIPTaskState.ACCEPTED

    def test_apply_task_result_valid_transition(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        result = AIPTaskResult(
            task_id="subtask-0",
            partner_id="partner-1",
            state=AIPTaskState.WORKING,
        )
        maref_state = adapter.apply_task_result(result)
        assert maref_state == GovernanceState.ACT
        assert adapter.get_task_state("subtask-0") == AIPTaskState.WORKING

    def test_apply_task_result_invalid_transition_raises(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        # ACCEPTED → COMPLETED is not a valid direct transition.
        result = AIPTaskResult(
            task_id="subtask-0",
            partner_id="partner-1",
            state=AIPTaskState.COMPLETED,
        )
        with pytest.raises(AIPStateTransitionError, match="Invalid AIP transition"):
            adapter.apply_task_result(result)

    def test_apply_task_result_full_lifecycle(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        for aip_state, expected_maref in [
            (AIPTaskState.WORKING, GovernanceState.ACT),
            (AIPTaskState.AWAITING_COMPLETION, GovernanceState.VERIFY),
            (AIPTaskState.COMPLETED, GovernanceState.REPORT),
        ]:
            result = AIPTaskResult(
                task_id="subtask-0",
                partner_id="partner-1",
                state=aip_state,
            )
            maref_state = adapter.apply_task_result(result)
            assert maref_state == expected_maref

    def test_cancel_task(self, adapter: AIPAdapter, subtask: SubTask) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        cmd = adapter.cancel_task("subtask-0", partner_id="partner-1")
        assert cmd.command_type == AIPTaskCommandType.CANCEL
        assert adapter.get_task_state("subtask-0") == AIPTaskState.CANCELED

    def test_cancel_task_from_terminal_state_raises(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        # Move through the lifecycle to COMPLETED terminal state.
        # ACCEPTED → WORKING → COMPLETED
        adapter.apply_task_result(
            AIPTaskResult(task_id="subtask-0", partner_id="partner-1", state=AIPTaskState.WORKING)
        )
        adapter.apply_task_result(
            AIPTaskResult(task_id="subtask-0", partner_id="partner-1", state=AIPTaskState.COMPLETED)
        )
        # Canceling a completed task should raise.
        with pytest.raises(AIPStateTransitionError):
            adapter.cancel_task("subtask-0", partner_id="partner-1")

    def test_cancel_unknown_task_raises(self, adapter: AIPAdapter) -> None:
        # Unknown task is not registered with the adapter — cancel must raise
        # rather than create a phantom CANCELED state entry.
        with pytest.raises(AIPStateTransitionError, match="unknown task"):
            adapter.cancel_task("unknown-task", partner_id="partner-1")

    def test_get_maref_state_returns_mapped_state(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        assert adapter.get_maref_state("subtask-0") == GovernanceState.INIT

    def test_get_maref_state_unknown_task_returns_none(self, adapter: AIPAdapter) -> None:
        assert adapter.get_maref_state("unknown") is None

    def test_get_subtask_returns_original(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        result = adapter.get_subtask("subtask-0")
        assert result is not None
        assert result.task_id == "subtask-0"

    def test_list_active_tasks_excludes_terminal(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        assert "subtask-0" in adapter.list_active_tasks()
        # Move to terminal state.
        adapter.apply_task_result(
            AIPTaskResult(
                task_id="subtask-0",
                partner_id="partner-1",
                state=AIPTaskState.WORKING,
            )
        )
        adapter.apply_task_result(
            AIPTaskResult(
                task_id="subtask-0",
                partner_id="partner-1",
                state=AIPTaskState.COMPLETED,
            )
        )
        assert "subtask-0" not in adapter.list_active_tasks()

    def test_clear_finished_tasks(self, adapter: AIPAdapter, subtask: SubTask) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        adapter.apply_task_result(
            AIPTaskResult(
                task_id="subtask-0",
                partner_id="partner-1",
                state=AIPTaskState.WORKING,
            )
        )
        adapter.apply_task_result(
            AIPTaskResult(
                task_id="subtask-0",
                partner_id="partner-1",
                state=AIPTaskState.COMPLETED,
            )
        )
        removed = adapter.clear_finished_tasks()
        assert removed == 1
        assert adapter.get_task_state("subtask-0") is None
        assert adapter.get_subtask("subtask-0") is None

    def test_clear_finished_tasks_keeps_active(
        self, adapter: AIPAdapter, subtask: SubTask
    ) -> None:
        adapter.subtask_to_start_command(subtask, partner_id="partner-1")
        removed = adapter.clear_finished_tasks()
        assert removed == 0
        assert adapter.get_task_state("subtask-0") is not None
