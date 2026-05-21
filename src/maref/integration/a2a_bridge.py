from __future__ import annotations

import time
import uuid
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_types import (
    A2ASkillDefinition,
    A2ATaskContext,
    A2ATaskState,
    DelegatedTask,
    map_a2a_to_maref,
    validate_agent_card_json,
)

DEFAULT_GOVERNANCE_SKILLS = [
    A2ASkillDefinition(
        id="maref-governance",
        name="MAREF Governance",
        description="Execute tasks under MAREF 10-state governance with entropy-aware state machine",
        tags=["governance", "state-machine", "entropy"],
        examples=["Govern a research task through the MAREF lifecycle"],
    ),
    A2ASkillDefinition(
        id="maref-delegate",
        name="MAREF Task Delegation",
        description="Delegate sub-tasks to other A2A-compatible agents with governance oversight",
        tags=["delegation", "multi-agent"],
        examples=["Decompose and delegate analysis task to specialist agent"],
    ),
    A2ASkillDefinition(
        id="maref-audit",
        name="MAREF Audit Trail",
        description="Provide append-only, immutable audit trail for all governed actions",
        tags=["audit", "compliance", "iso27001"],
        examples=["Retrieve audit log for a specific task execution"],
    ),
]


class A2ABridge:
    def __init__(
        self,
        state_machine: GovernanceStateMachine,
        audit_logger: AuditLogger,
        circuit_breaker: CircuitBreaker | None = None,
        agent_name: str = "maref-agent",
        agent_description: str = "MAREF-governed agent",
    ) -> None:
        self._sm = state_machine
        self._audit = audit_logger
        self._cb = circuit_breaker
        self._name = agent_name
        self._description = agent_description
        self._tasks: dict[str, A2ATaskContext] = {}
        self._delegated_tasks: dict[str, DelegatedTask] = {}
        self._capabilities: list[A2ASkillDefinition] = []
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        self._capabilities.extend(DEFAULT_GOVERNANCE_SKILLS)

    def register_capability(self, capability: A2ASkillDefinition) -> None:
        self._capabilities.append(capability)
        self._audit.log(
            event_type="a2a_capability_registered",
            actor=self._name,
            action="register_capability",
            details=f"Registered capability: {capability.id}",
            metadata={"capability_id": capability.id, "capability_name": capability.name},
        )

    def _check_circuit_breaker(self) -> None:
        if self._cb is not None and self._cb.is_open:
            raise CommunicationBlockedError(
                "Circuit breaker is OPEN — all A2A communication is blocked"
            )

    def build_agent_card(self, base_url: str = "http://localhost:8000") -> dict[str, Any]:
        self._check_circuit_breaker()
        skills = [
            {
                "id": cap.id,
                "name": cap.name,
                "description": cap.description,
                "tags": cap.tags,
                "examples": cap.examples,
                "inputModes": cap.input_modes,
                "outputModes": cap.output_modes,
            }
            for cap in self._capabilities
        ]
        card = {
            "name": self._name,
            "description": self._description,
            "version": "0.2.0",
            "url": base_url,
            "protocolVersion": "0.2.6",
            "capabilities": {
                "streaming": True,
                "pushNotifications": True,
                "stateTransitionHistory": True,
            },
            "skills": skills,
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["application/json"],
        }
        if not validate_agent_card_json(card):
            raise ValueError("Generated AgentCard does not pass schema validation")
        return card

    def create_task(self, task_description: str, context: dict[str, Any] | None = None) -> str:
        self._check_circuit_breaker()
        task_id = f"maref-task-{uuid.uuid4().hex[:12]}"
        now = time.time()
        task_ctx = A2ATaskContext(
            task_id=task_id,
            description=task_description,
            a2a_state=A2ATaskState.SUBMITTED,
            maref_state=GovernanceState.INIT,
            context=context or {},
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = task_ctx
        self._sm.transition(GovernanceState.INIT, f"Task created: {task_description}")
        self._audit.log(
            event_type="a2a_task_created",
            actor=self._name,
            action="create_task",
            details=f"Created task: {task_description}",
            metadata={"task_id": task_id, "a2a_state": A2ATaskState.SUBMITTED.value},
        )
        return task_id

    def get_task(self, task_id: str) -> A2ATaskContext | None:
        return self._tasks.get(task_id)

    def delegate_task(self, task_id: str, target_agent_url: str) -> bool:
        self._check_circuit_breaker()
        if task_id not in self._tasks:
            return False
        now = time.time()
        delegated = DelegatedTask(
            task_id=task_id,
            target_agent_url=target_agent_url,
            delegated_at=now,
            status=A2ATaskState.SUBMITTED,
        )
        self._delegated_tasks[task_id] = delegated
        self._tasks[task_id].a2a_state = A2ATaskState.WORKING
        self._tasks[task_id].updated_at = now
        self._audit.log(
            event_type="a2a_task_delegated",
            actor=self._name,
            action="delegate_task",
            details=f"Delegated task {task_id} to {target_agent_url}",
            metadata={
                "task_id": task_id,
                "target_agent_url": target_agent_url,
                "delegated_at": now,
            },
        )
        return True

    def sync_state_from_a2a(self, task_id: str, a2a_state: str) -> bool:
        self._check_circuit_breaker()
        if task_id not in self._tasks:
            return False
        try:
            a2a_enum = A2ATaskState(a2a_state)
        except ValueError:
            return False
        maref_state = map_a2a_to_maref(a2a_enum)
        self._tasks[task_id].a2a_state = a2a_enum
        self._tasks[task_id].maref_state = maref_state
        self._tasks[task_id].updated_at = time.time()
        self._sm.transition(maref_state, f"A2A state sync: {a2a_state}")
        self._audit.log(
            event_type="a2a_state_sync",
            actor=self._name,
            action="sync_state_from_a2a",
            details=f"Synced task {task_id} to A2A state {a2a_state}",
            metadata={
                "task_id": task_id,
                "a2a_state": a2a_state,
                "maref_state": maref_state.name,
            },
        )
        return True

    def handle_push_notification(self, task_id: str, event: dict[str, Any]) -> None:
        self._check_circuit_breaker()
        if task_id not in self._tasks:
            raise ValueError(f"Unknown task: {task_id}")
        event_type = event.get("type", "unknown")
        if event_type == "state_update":
            new_state = event.get("state", "")
            if new_state:
                self.sync_state_from_a2a(task_id, new_state)
        self._tasks[task_id].context["last_push_event"] = event
        self._tasks[task_id].updated_at = time.time()

    def list_governed_tasks(
        self, filter_state: GovernanceState | None = None
    ) -> list[dict[str, Any]]:
        tasks = []
        for task in self._tasks.values():
            if filter_state is not None and task.maref_state != filter_state:
                continue
            tasks.append(
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "a2a_state": task.a2a_state.value,
                    "maref_state": task.maref_state.name,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                }
            )
        return tasks

    def force_halt_task(self, task_id: str, reason: str = "") -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        task.a2a_state = A2ATaskState.CANCELED
        task.maref_state = GovernanceState.HALT
        task.updated_at = time.time()
        self._sm.transition(GovernanceState.HALT, f"Task halted: {reason}")
        self._audit.log(
            event_type="a2a_task_halted",
            actor=self._name,
            action="force_halt_task",
            details=f"Halted task {task_id}: {reason}",
            metadata={"task_id": task_id, "reason": reason},
        )
        return True

    def get_delegated_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": dt.task_id,
                "target_agent_url": dt.target_agent_url,
                "delegated_at": dt.delegated_at,
                "status": dt.status.value,
            }
            for dt in self._delegated_tasks.values()
        ]


class CommunicationBlockedError(Exception):
    pass
