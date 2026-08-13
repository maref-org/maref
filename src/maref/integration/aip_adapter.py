"""AIP (Agent Interaction Protocol) Message Adapter.

Bridges MAREF's internal TaskGraph / governance state model with the
ACPs AIP v2.00 protocol: Leader-Partner RPC over JSON-RPC 2.0 with an
8-state task lifecycle.

Provides:
- :class:`AIPTaskState`: AIP's 8-state task state machine enum.
- :class:`AIPMessage`: Core AIP message envelope (type, sender, data items).
- :class:`AIPTaskCommand`: Task lifecycle commands (Start/Continue/Cancel/...).
- :class:`AIPTaskResult`: Task execution result with state and product.
- :class:`AIPAdapter`: Bidirectional mapper between MAREF SubTask /
  GovernanceState and AIP TaskCommand / TaskResult.

Reference: AIP-ACPs-Technical-Analysis.md section 2.6 (AIP v2.00).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.types import GovernanceState
from maref.orchestration.decomposer import SubTask

# AIP protocol version (matches ACPs v2.00).
AIP_PROTOCOL_VERSION = "2.00"


class AIPTaskState(str, Enum):
    """AIP 8-state task lifecycle.

    Transitions (canonical):
        Accepted → Working → AwaitingInput → AwaitingCompletion → Completed
                                                                     ↘ Failed
        Canceled ← (any state)
    """

    ACCEPTED = "accepted"
    WORKING = "working"
    AWAITING_INPUT = "awaiting-input"
    AWAITING_COMPLETION = "awaiting-completion"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"


# Allowed forward transitions per AIP v2.00 state machine.
_AIP_TRANSITIONS: dict[AIPTaskState, set[AIPTaskState]] = {
    AIPTaskState.ACCEPTED: {
        AIPTaskState.WORKING,
        AIPTaskState.REJECTED,
        AIPTaskState.CANCELED,
    },
    AIPTaskState.WORKING: {
        AIPTaskState.AWAITING_INPUT,
        AIPTaskState.AWAITING_COMPLETION,
        AIPTaskState.COMPLETED,
        AIPTaskState.FAILED,
        AIPTaskState.CANCELED,
    },
    AIPTaskState.AWAITING_INPUT: {
        AIPTaskState.WORKING,
        AIPTaskState.FAILED,
        AIPTaskState.CANCELED,
    },
    AIPTaskState.AWAITING_COMPLETION: {
        AIPTaskState.COMPLETED,
        AIPTaskState.FAILED,
        AIPTaskState.CANCELED,
    },
    AIPTaskState.COMPLETED: set(),
    AIPTaskState.FAILED: set(),
    AIPTaskState.CANCELED: set(),
    AIPTaskState.REJECTED: set(),
}


# MAREF GovernanceState ↔ AIP AIPTaskState mapping.
# MAREF has a 10-state governance lifecycle; AIP has 8 task states. The
# mapping is many-to-one in places (MAREF is finer-grained).
MAREF_TO_AIP_MAP: dict[GovernanceState, AIPTaskState] = {
    GovernanceState.INIT: AIPTaskState.ACCEPTED,
    GovernanceState.OBSERVE: AIPTaskState.WORKING,
    GovernanceState.ANALYZE: AIPTaskState.WORKING,
    GovernanceState.EVALUATE: AIPTaskState.AWAITING_INPUT,
    GovernanceState.DECIDE: AIPTaskState.WORKING,
    GovernanceState.ACT: AIPTaskState.WORKING,
    GovernanceState.VERIFY: AIPTaskState.AWAITING_COMPLETION,
    GovernanceState.STABILIZE: AIPTaskState.AWAITING_COMPLETION,
    GovernanceState.REPORT: AIPTaskState.COMPLETED,
    GovernanceState.HALT: AIPTaskState.FAILED,
}

AIP_TO_MAREF_MAP: dict[AIPTaskState, GovernanceState] = {
    AIPTaskState.ACCEPTED: GovernanceState.INIT,
    AIPTaskState.WORKING: GovernanceState.ACT,
    AIPTaskState.AWAITING_INPUT: GovernanceState.EVALUATE,
    AIPTaskState.AWAITING_COMPLETION: GovernanceState.VERIFY,
    AIPTaskState.COMPLETED: GovernanceState.REPORT,
    AIPTaskState.FAILED: GovernanceState.HALT,
    AIPTaskState.CANCELED: GovernanceState.HALT,
    AIPTaskState.REJECTED: GovernanceState.HALT,
}


class AIPTaskCommandType(str, Enum):
    """AIP TaskCommand types (Leader → Partner)."""

    START = "start"
    CONTINUE = "continue"
    CANCEL = "cancel"
    COMPLETE = "complete"
    GET = "get"
    RE_STREAM = "re-stream"


@dataclass
class DataItem:
    """AIP DataItem: a typed payload item carried by a Message."""

    type: str  # "text" | "file" | "structured"
    content: str
    mime_type: str = "text/plain"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "content": self.content,
            "mimeType": self.mime_type,
            "metadata": dict(self.metadata),
        }


@dataclass
class AIPMessage:
    """AIP Message envelope exchanged between Leader and Partner."""

    message_id: str
    message_type: str  # "task-command" | "task-result" | "notification"
    sent_at: float
    sender_role: str  # "leader" | "partner"
    sender_id: str
    data_items: list[DataItem] = field(default_factory=list)
    group_id: str = ""
    session_id: str = ""
    mentions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "messageId": self.message_id,
            "messageType": self.message_type,
            "sentAt": self.sent_at,
            "senderRole": self.sender_role,
            "senderId": self.sender_id,
            "dataItems": [item.to_dict() for item in self.data_items],
            "groupId": self.group_id,
            "sessionId": self.session_id,
            "mentions": list(self.mentions),
        }


@dataclass
class AIPTaskCommand:
    """AIP TaskCommand: Leader instructs Partner on task lifecycle."""

    command_type: AIPTaskCommandType
    task_id: str
    leader_id: str
    partner_id: str
    session_id: str = ""
    data_items: list[DataItem] = field(default_factory=list)
    issued_at: float = field(default_factory=time.time)

    def to_message(self) -> AIPMessage:
        """Wrap this command in an :class:`AIPMessage` envelope."""
        return AIPMessage(
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
            message_type="task-command",
            sent_at=self.issued_at,
            sender_role="leader",
            sender_id=self.leader_id,
            data_items=list(self.data_items),
            session_id=self.session_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "commandType": self.command_type.value,
            "taskId": self.task_id,
            "leaderId": self.leader_id,
            "partnerId": self.partner_id,
            "sessionId": self.session_id,
            "dataItems": [item.to_dict() for item in self.data_items],
            "issuedAt": self.issued_at,
        }


@dataclass
class AIPProduct:
    """AIP Product: a named result artifact produced by a task."""

    name: str
    description: str
    data_items: list[DataItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "dataItems": [item.to_dict() for item in self.data_items],
        }


@dataclass
class AIPTaskResult:
    """AIP TaskResult: Partner reports task state and product back to Leader."""

    task_id: str
    partner_id: str
    state: AIPTaskState
    products: list[AIPProduct] = field(default_factory=list)
    error_message: str = ""
    reported_at: float = field(default_factory=time.time)

    def to_message(self) -> AIPMessage:
        """Wrap this result in an :class:`AIPMessage` envelope."""
        items: list[DataItem] = []
        for product in self.products:
            items.extend(product.data_items)
        return AIPMessage(
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
            message_type="task-result",
            sent_at=self.reported_at,
            sender_role="partner",
            sender_id=self.partner_id,
            data_items=items,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "partnerId": self.partner_id,
            "state": self.state.value,
            "products": [p.to_dict() for p in self.products],
            "errorMessage": self.error_message,
            "reportedAt": self.reported_at,
        }


class AIPStateTransitionError(ValueError):
    """Raised when an invalid AIP task state transition is attempted."""


def is_valid_transition(from_state: AIPTaskState, to_state: AIPTaskState) -> bool:
    """Check whether a transition between two AIP task states is allowed.

    Args:
        from_state: The current AIP task state.
        to_state: The target AIP task state.

    Returns:
        True if the transition is allowed by the AIP state machine.
    """
    if from_state == to_state:
        return True  # self-transitions are allowed (idempotent state reports)
    return to_state in _AIP_TRANSITIONS.get(from_state, set())


def map_maref_to_aip(maref_state: GovernanceState) -> AIPTaskState:
    """Map a MAREF :class:`GovernanceState` to an AIP :class:`AIPTaskState`.

    Args:
        maref_state: The MAREF governance state.

    Returns:
        The corresponding AIP task state.

    Raises:
        ValueError: If the MAREF state has no AIP mapping.
    """
    if maref_state not in MAREF_TO_AIP_MAP:
        raise ValueError(f"Unknown MAREF governance state: {maref_state}")
    return MAREF_TO_AIP_MAP[maref_state]


def map_aip_to_maref(aip_state: AIPTaskState) -> GovernanceState:
    """Map an AIP :class:`AIPTaskState` to a MAREF :class:`GovernanceState`.

    Args:
        aip_state: The AIP task state.

    Returns:
        The corresponding MAREF governance state.

    Raises:
        ValueError: If the AIP state has no MAREF mapping.
    """
    if aip_state not in AIP_TO_MAREF_MAP:
        raise ValueError(f"Unknown AIP task state: {aip_state}")
    return AIP_TO_MAREF_MAP[aip_state]


class AIPAdapter:
    """Adapter that bridges MAREF's internal task model with AIP v2.00.

    Responsibilities:
    - Convert MAREF :class:`SubTask` to AIP :class:`AIPTaskCommand` (Start).
    - Convert AIP :class:`AIPTaskResult` to MAREF governance state updates.
    - Validate AIP state transitions.
    - Maintain a session-scoped task state registry for synchronization.
    """

    def __init__(self, leader_id: str = "maref-leader") -> None:
        self._leader_id = leader_id
        # task_id → current AIP state, for transition validation.
        self._task_states: dict[str, AIPTaskState] = {}
        # task_id → original MAREF SubTask, for context retention.
        self._subtasks: dict[str, SubTask] = {}

    @property
    def leader_id(self) -> str:
        return self._leader_id

    def subtask_to_start_command(
        self,
        subtask: SubTask,
        partner_id: str,
        session_id: str = "",
    ) -> AIPTaskCommand:
        """Convert a MAREF :class:`SubTask` into an AIP ``Start`` command.

        Args:
            subtask: The MAREF subtask to dispatch.
            partner_id: The AIP identifier of the partner agent.
            session_id: Optional AIP session identifier.

        Returns:
            An :class:`AIPTaskCommand` with ``command_type=START``.
        """
        data_items = [
            DataItem(
                type="structured",
                content=subtask.description,
                mime_type="application/json",
                metadata={
                    "task_id": subtask.task_id,
                    "estimated_complexity": subtask.estimated_complexity,
                    "required_capabilities": list(subtask.required_capabilities),
                    "depends_on": list(subtask.depends_on),
                },
            )
        ]
        command = AIPTaskCommand(
            command_type=AIPTaskCommandType.START,
            task_id=subtask.task_id,
            leader_id=self._leader_id,
            partner_id=partner_id,
            session_id=session_id,
            data_items=data_items,
        )
        self._subtasks[subtask.task_id] = subtask
        self._task_states[subtask.task_id] = AIPTaskState.ACCEPTED
        return command

    def apply_task_result(
        self,
        result: AIPTaskResult,
    ) -> GovernanceState:
        """Apply an incoming AIP :class:`AIPTaskResult` to the local state.

        Validates the state transition, updates the local task state
        registry, and returns the corresponding MAREF governance state.

        Args:
            result: The AIP task result received from a partner.

        Returns:
            The MAREF :class:`GovernanceState` corresponding to the new AIP state.

        Raises:
            AIPStateTransitionError: If the reported state transition is invalid.
        """
        current = self._task_states.get(result.task_id)
        if current is not None and not is_valid_transition(current, result.state):
            raise AIPStateTransitionError(
                f"Invalid AIP transition for task {result.task_id}: "
                f"{current.value} → {result.state.value}"
            )
        self._task_states[result.task_id] = result.state
        return map_aip_to_maref(result.state)

    def cancel_task(self, task_id: str, partner_id: str) -> AIPTaskCommand:
        """Build a Cancel command for a task.

        Args:
            task_id: The task to cancel.
            partner_id: The partner agent that should cancel the task.

        Returns:
            An :class:`AIPTaskCommand` with ``command_type=CANCEL``.

        Raises:
            AIPStateTransitionError: If the task is unknown to this adapter
                (never started) or is in a terminal state
                (COMPLETED/FAILED/CANCELED/REJECTED) and cannot be canceled.
        """
        current = self._task_states.get(task_id)
        if current is None:
            raise AIPStateTransitionError(
                f"Cannot cancel unknown task {task_id}: not registered with this adapter"
            )
        if not is_valid_transition(current, AIPTaskState.CANCELED):
            raise AIPStateTransitionError(
                f"Cannot cancel task {task_id} in terminal state {current.value}"
            )
        command = AIPTaskCommand(
            command_type=AIPTaskCommandType.CANCEL,
            task_id=task_id,
            leader_id=self._leader_id,
            partner_id=partner_id,
        )
        self._task_states[task_id] = AIPTaskState.CANCELED
        return command

    def get_task_state(self, task_id: str) -> AIPTaskState | None:
        """Return the current AIP state for a task, or None if unknown."""
        return self._task_states.get(task_id)

    def get_maref_state(self, task_id: str) -> GovernanceState | None:
        """Return the MAREF governance state corresponding to a task's AIP state."""
        aip_state = self._task_states.get(task_id)
        if aip_state is None:
            return None
        return map_aip_to_maref(aip_state)

    def get_subtask(self, task_id: str) -> SubTask | None:
        """Return the original MAREF SubTask for a given AIP task_id."""
        return self._subtasks.get(task_id)

    def list_active_tasks(self) -> list[str]:
        """Return task_ids of all tasks not in a terminal state."""
        terminal = {
            AIPTaskState.COMPLETED,
            AIPTaskState.FAILED,
            AIPTaskState.CANCELED,
            AIPTaskState.REJECTED,
        }
        return [task_id for task_id, state in self._task_states.items() if state not in terminal]

    def clear_finished_tasks(self) -> int:
        """Remove terminal-state tasks from the registry.

        Returns:
            The number of tasks removed.
        """
        terminal = {
            AIPTaskState.COMPLETED,
            AIPTaskState.FAILED,
            AIPTaskState.CANCELED,
            AIPTaskState.REJECTED,
        }
        to_remove = [task_id for task_id, state in self._task_states.items() if state in terminal]
        for task_id in to_remove:
            self._task_states.pop(task_id, None)
            self._subtasks.pop(task_id, None)
        return len(to_remove)


__all__ = [
    "AIP_PROTOCOL_VERSION",
    "AIPAdapter",
    "AIPMessage",
    "AIPProduct",
    "AIPStateTransitionError",
    "AIPTaskCommand",
    "AIPTaskCommandType",
    "AIPTaskResult",
    "AIPTaskState",
    "AIP_TO_MAREF_MAP",
    "DataItem",
    "MAREF_TO_AIP_MAP",
    "is_valid_transition",
    "map_aip_to_maref",
    "map_maref_to_aip",
]
