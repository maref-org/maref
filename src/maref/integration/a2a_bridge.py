from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_types import (
    A2A_PROTOCOL_VERSION,
    A2ASkillDefinition,
    A2ATaskContext,
    A2ATaskState,
    DelegatedTask,
    map_a2a_to_maref,
    validate_agent_card_json,
)
from maref.integration.trajectory import TrajectoryCollector, TrajectoryEventType
from maref.security.decorators import security_critical

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
    """Bridge between MAREF governance and the A2A protocol.

    Wraps a GovernanceStateMachine, AuditLogger, and optional CircuitBreaker
    into an A2A-compatible agent that can create, delegate, and sync tasks
    across a multi-agent federation.

    Attributes:
        _sm: The governance state machine tracking this agent's lifecycle.
        _audit: HMAC-signed audit logger for tamper-evident records.
        _cb: Optional circuit breaker for fault isolation.
        _name: Human-readable agent name.
        _description: Agent description used in Agent Card.
        _tasks: In-memory map of task_id -> A2ATaskContext.
        _delegated_tasks: Map of task_id -> DelegatedTask for cross-agent delegation.
        _capabilities: List of registered A2ASkillDefinition capabilities.
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine,
        audit_logger: AuditLogger,
        circuit_breaker: CircuitBreaker | None = None,
        agent_name: str = "maref-agent",
        agent_description: str = "MAREF-governed agent",
        trajectory_collector: TrajectoryCollector | None = None,
        protocol_bridge: Any | None = None,
        agent_dns: Any | None = None,
        agent_did: str | None = None,
        signing_key: Any | None = None,
    ) -> None:
        """Initialize the A2A bridge with governance components.

        Args:
            state_machine: The governance state machine instance.
            audit_logger: Audit logger for recording decisions.
            circuit_breaker: Optional circuit breaker for fault tolerance.
            agent_name: Name exposed in the Agent Card.
            agent_description: Description exposed in the Agent Card.
            trajectory_collector: Optional trajectory collector for D2/D3 data.
            protocol_bridge: Optional MCP-A2A adapter bridge (方案 A D4).
            agent_dns: Optional :class:`~maref.identity.agent_dns.AgentDNS`;
                when set together with ``agent_did``, the served Agent Card
                is generated from AgentDNS resolution (方案 E M2 / I2).
            agent_did: The agent's MAREF DID string; the Agent Card is only
                published while the DID lifecycle is active.
            signing_key: Optional Ed25519 :class:`ReportSigningKey` used to
                sign outgoing delegated tasks (v0.50 W3-S1 / I7).
        """
        self._sm = state_machine
        self._audit = audit_logger
        self._cb = circuit_breaker
        self._name = agent_name
        self._description = agent_description
        self._signing_key = signing_key
        self._tasks: dict[str, A2ATaskContext] = {}
        self._delegated_tasks: dict[str, DelegatedTask] = {}
        self._capabilities: list[A2ASkillDefinition] = []
        # 可选协议桥：启用 A2A 能力在 MCP 生态的可见性（方案 A D4）
        self._protocol_bridge = protocol_bridge
        # 可选 AgentDNS：Agent Card 由 DID → AgentCard 解析生成（方案 E M2）
        self._agent_dns = agent_dns
        self._agent_did = agent_did
        self._lock = asyncio.Lock()
        self._state_queues: dict[str, asyncio.Queue[A2ATaskState]] = {}
        self._trajectory = trajectory_collector or TrajectoryCollector()
        self._last_action_ids: dict[str, str] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        self._capabilities.extend(DEFAULT_GOVERNANCE_SKILLS)

    def register_capability(self, capability: A2ASkillDefinition) -> None:
        """Register a custom skill capability for this agent.

        The capability is appended to the Agent Card's skills list and
        an audit log entry is created recording the registration.

        Args:
            capability: The skill definition to register.
        """
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

    def _notify_state_change(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task_id not in self._state_queues:
            self._state_queues[task_id] = asyncio.Queue()
        self._state_queues[task_id].put_nowait(task.a2a_state)

    async def wait_for_state_change(self, task_id: str) -> A2ATaskState:
        if task_id not in self._state_queues:
            self._state_queues[task_id] = asyncio.Queue()
        state = await self._state_queues[task_id].get()
        return state

    @security_critical
    def build_agent_card(self, base_url: str = "http://localhost:8000") -> dict[str, Any]:
        """Build an A2A Agent Card for service discovery.

        When an ``agent_dns`` + ``agent_did`` are configured, the card is
        generated from :meth:`AgentDNS.resolve` (方案 E M2 / I2) — the card
        is only served while the DID lifecycle is ``active``; a revoked or
        deactivated DID raises :class:`CommunicationBlockedError`.

        Otherwise falls back to the legacy in-bridge card construction.

        Args:
            base_url: The base URL where this agent is reachable.

        Returns:
            A dictionary representing the Agent Card.

        Raises:
            CommunicationBlockedError: If the circuit breaker is open, or
                the configured agent DID is revoked/deactivated.
            ValueError: If the generated card fails schema validation.
        """
        self._check_circuit_breaker()
        if self._agent_dns is not None and self._agent_did:
            return self._build_agent_card_from_dns(base_url)

        skills = [
            {
                "id": cap.id,
                "name": cap.name,
                "description": cap.description,
                "tags": cap.tags,
                "examples": cap.examples,
                "inputModes": cap.input_modes,
                "outputModes": cap.output_modes,
                "inputSchema": cap.input_schema,
                "outputSchema": cap.output_schema,
            }
            for cap in self._capabilities
        ]
        card = {
            "name": self._name,
            "description": self._description,
            "version": "0.2.0",
            "url": base_url,
            "protocolVersion": A2A_PROTOCOL_VERSION,
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

    def _build_agent_card_from_dns(self, base_url: str) -> dict[str, Any]:
        """从 AgentDNS 解析生成 Agent Card（方案 E M2 / I2）。

        DID 生命周期非 active（未注册/撤销/停用）时解析失败，
        抛 :class:`CommunicationBlockedError`，agent-card 端点据此
        不再对外发布该能力目录。
        """
        from maref.identity.agent_dns import AgentDID

        agent_dns = self._agent_dns
        agent_did = self._agent_did
        assert agent_dns is not None
        if agent_did is None:
            raise CommunicationBlockedError(
                "agent_did 未配置，无法经 AgentDNS 生成 Agent Card"
            )
        try:
            did = AgentDID.parse(agent_did)
        except ValueError as exc:
            raise CommunicationBlockedError(
                f"agent_did 配置非法: {self._agent_did!r}"
            ) from exc
        card = agent_dns.resolve(did)
        if card is None:
            raise CommunicationBlockedError(
                f"Agent DID {self._agent_did} revoked/deactivated/unregistered"
                " — Agent Card unavailable"
            )
        a2a_card = card.to_a2a_card(base_url=base_url)
        a2a_card["protocolVersion"] = A2A_PROTOCOL_VERSION
        # 合并默认能力声明（与 legacy 路径一致），保证 A2A 客户端可发现
        # streaming/pushNotifications 等能力。
        merged_caps = {
            "streaming": True,
            "pushNotifications": True,
            "stateTransitionHistory": True,
            **a2a_card.get("capabilities", {}),
        }
        a2a_card["capabilities"] = merged_caps
        # 合并本地 register_capability 注册的技能（按 id 去重，DNS card 优先）。
        dns_skill_ids = {s.get("id") for s in a2a_card.get("skills", [])}
        local_skills = [
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
            if cap.id not in dns_skill_ids
        ]
        a2a_card["skills"] = list(a2a_card.get("skills", [])) + local_skills
        if not validate_agent_card_json(a2a_card):
            raise ValueError("AgentDNS AgentCard does not pass schema validation")
        self._audit.log(
            event_type="a2a_agent_card_dns",
            actor=self._name,
            action="build_agent_card",
            details=f"Agent Card resolved via AgentDNS for {agent_did}",
            metadata={"did": agent_did, "status": card.status},
        )
        return a2a_card

    def build_mcp_tools(self) -> list[dict[str, Any]]:
        """将本 agent 的 A2A 能力映射为 MCP tool 定义。

        接线点（方案 A D4）：注入 protocol_bridge 时启用——A2A 能力在
        MCP 生态可发现/可调用。未注入时返回空列表，行为不变。

        每个 tool 的 A2A action 取 capability 的 ``a2a_action``（未指定
        时默认 ``execute_task``），由 MCPToA2AAdapter 语义映射保证一致性。
        """
        if self._protocol_bridge is None:
            return []
        return [
            {
                "name": cap.id,
                "description": cap.description,
                "inputSchema": cap.input_schema
                or {"type": "object", "properties": {}},
                "sourceProtocol": "a2a",
                "targetA2AAction": cap.a2a_action or "execute_task",
            }
            for cap in self._capabilities
        ]

    def create_task(self, task_description: str, context: dict[str, Any] | None = None) -> str:
        """Create a new governed task.

        Generates a unique task ID, wraps it in an A2ATaskContext with
        SUBMITTED A2A state and INIT MAREF state, and records an audit entry.

        Args:
            task_description: Human-readable description of the task.
            context: Optional metadata dictionary for the task.

        Returns:
            The generated task ID (format: maref-task-{uuid}).

        Raises:
            CommunicationBlockedError: If the circuit breaker is open.
        """
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
        entry = self._audit.log(
            event_type="a2a_task_created",
            actor=self._name,
            action="create_task",
            details=f"Created task: {task_description}",
            metadata={"task_id": task_id, "a2a_state": A2ATaskState.SUBMITTED.value},
        )
        self._last_action_ids[task_id] = entry.id
        self._trajectory.start_task(task_id, task_description, actor=self._name)
        return task_id

    def get_task(self, task_id: str) -> A2ATaskContext | None:
        """Retrieve a task by its ID.

        Args:
            task_id: The task ID to look up.

        Returns:
            The A2ATaskContext if found, or None.
        """
        return self._tasks.get(task_id)

    def delegate_task(self, task_id: str, target_agent_url: str) -> bool:
        """Delegate a task to another A2A agent.

        Marks the local task as WORKING, creates a DelegatedTask record,
        and attempts to send the task asynchronously via A2AClient.

        Args:
            task_id: The ID of the task to delegate.
            target_agent_url: The URL of the target agent.

        Returns:
            True if the task exists and delegation was initiated, False otherwise.

        Raises:
            CommunicationBlockedError: If the circuit breaker is open.
        """
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
        parent_id = self._last_action_ids.get(task_id, "")
        entry = self._audit.log(
            event_type="a2a_task_delegated",
            actor=self._name,
            action="delegate_task",
            details=f"Delegated task {task_id} to {target_agent_url}",
            metadata={
                "task_id": task_id,
                "target_agent_url": target_agent_url,
                "delegated_at": now,
            },
            parent_action_id=parent_id,
        )
        self._last_action_ids[task_id] = entry.id
        self._trajectory.record_delegation(task_id, target_agent_url)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                client = A2AClient(signing_key=self._signing_key)
                task = self._tasks.get(task_id)
                if task is not None:
                    loop.create_task(
                        client.send_task(
                            agent_url=target_agent_url,
                            skill_id="maref-delegate",
                            input_data=task.description,
                            metadata=task.context,
                        )
                    )
        except RuntimeError:
            pass
        except Exception:
            pass
        return True

    def sync_state_from_a2a(self, task_id: str, a2a_state: str) -> bool:
        """Synchronize task state from an A2A state update.

        Maps the A2A state string to the corresponding MAREF governance state
        and updates the task context accordingly. Creates audit log entry.

        Args:
            task_id: The ID of the task to update.
            a2a_state: The A2A state string (e.g. 'working', 'completed').

        Returns:
            True if the task was found and state was updated, False otherwise.

        Raises:
            CommunicationBlockedError: If the circuit breaker is open.
        """
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
        parent_id = self._last_action_ids.get(task_id, "")
        entry = self._audit.log(
            event_type="a2a_state_sync",
            actor=self._name,
            action="sync_state_from_a2a",
            details=f"Synced task {task_id} to A2A state {a2a_state}",
            metadata={
                "task_id": task_id,
                "a2a_state": a2a_state,
                "maref_state": maref_state.name,
            },
            parent_action_id=parent_id,
        )
        self._last_action_ids[task_id] = entry.id
        self._trajectory.record_event(
            task_id,
            TrajectoryEventType.TASK_STATE_CHANGED,
            self._name,
            {"a2a_state": a2a_state, "maref_state": maref_state.name},
        )
        self._notify_state_change(task_id)
        return True

    def handle_push_notification(self, task_id: str, event: dict[str, Any]) -> None:
        """Handle an incoming SSE push notification for a task.

        Processes state_update events by calling sync_state_from_a2a and
        stores the raw event in the task context.

        Args:
            task_id: The ID of the task the notification applies to.
            event: The push notification event dictionary (must contain 'type' key).

        Raises:
            CommunicationBlockedError: If the circuit breaker is open.
            ValueError: If the task_id is unknown.
        """
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
        """List all governed tasks, optionally filtered by MAREF state.

        Args:
            filter_state: If provided, only tasks in this governance state are returned.

        Returns:
            A list of task summary dictionaries with task_id, description,
            a2a_state, maref_state, created_at, and updated_at.
        """
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

    @security_critical
    def force_halt_task(self, task_id: str, reason: str = "") -> bool:
        """Forcefully halt a task and transition to HALT state.

        Sets the task's A2A state to CANCELED and MAREF state to HALT,
        records the event in the audit log.

        Args:
            task_id: The ID of the task to halt.
            reason: Optional human-readable reason for halting.

        Returns:
            True if the task was found and halted, False otherwise.
        """
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        task.a2a_state = A2ATaskState.CANCELED
        task.maref_state = GovernanceState.HALT
        task.updated_at = time.time()
        self._sm.transition(GovernanceState.HALT, f"Task halted: {reason}")
        parent_id = self._last_action_ids.get(task_id, "")
        self._audit.log(
            event_type="a2a_task_halted",
            actor=self._name,
            action="force_halt_task",
            details=f"Halted task {task_id}: {reason}",
            metadata={"task_id": task_id, "reason": reason},
            parent_action_id=parent_id,
        )
        self._trajectory.complete_task(task_id, final_state="canceled")
        self._notify_state_change(task_id)
        return True

    def get_delegated_tasks(self) -> list[dict[str, Any]]:
        """Return all tasks that have been delegated to other agents.

        Returns:
            A list of delegated task dictionaries with task_id, target_agent_url,
            delegated_at, and status.
        """
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
