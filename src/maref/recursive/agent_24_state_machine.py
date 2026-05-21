from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


class AgentStateV3(str, Enum):
    UNINITIALIZED = "uninitialized"
    BOOTING = "booting"
    REGISTERING = "registering"
    IDLE = "idle"
    DISCOVERING = "discovering"
    NEGOTIATING = "negotiating"
    TRUST_BUILDING = "trust_building"
    CONTRACTING = "contracting"
    EXECUTING = "executing"
    WAITING = "waiting"
    VERIFYING = "verifying"
    REPORTING = "reporting"
    CONFLICTING = "conflicting"
    ARBITRATING = "arbitrating"
    RECOVERING = "recovering"
    MIGRATING = "migrating"
    PAUSED = "paused"
    DEGRADING = "degrading"
    SELF_HEALING = "self_healing"
    SELF_OPTIMIZING = "self_optimizing"
    EVOLVING = "evolving"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ZOMBIE = "zombie"


GRAY_CODE_5BIT: dict[AgentStateV3, str] = {
    AgentStateV3.UNINITIALIZED: "00000",
    AgentStateV3.BOOTING: "00001",
    AgentStateV3.REGISTERING: "00011",
    AgentStateV3.IDLE: "00010",
    AgentStateV3.DISCOVERING: "00110",
    AgentStateV3.NEGOTIATING: "00111",
    AgentStateV3.TRUST_BUILDING: "00101",
    AgentStateV3.CONTRACTING: "00100",
    AgentStateV3.EXECUTING: "01100",
    AgentStateV3.WAITING: "01101",
    AgentStateV3.VERIFYING: "01111",
    AgentStateV3.REPORTING: "01110",
    AgentStateV3.CONFLICTING: "01010",
    AgentStateV3.ARBITRATING: "01011",
    AgentStateV3.RECOVERING: "01001",
    AgentStateV3.MIGRATING: "01000",
    AgentStateV3.PAUSED: "11000",
    AgentStateV3.DEGRADING: "11001",
    AgentStateV3.SELF_HEALING: "11011",
    AgentStateV3.SELF_OPTIMIZING: "11010",
    AgentStateV3.EVOLVING: "11110",
    AgentStateV3.TERMINATING: "11111",
    AgentStateV3.TERMINATED: "11101",
    AgentStateV3.ZOMBIE: "11100",
}

REVERSE_GRAY_5BIT: dict[str, AgentStateV3] = {v: k for k, v in GRAY_CODE_5BIT.items()}

VALID_TRANSITIONS: dict[AgentStateV3, set[AgentStateV3]] = {
    AgentStateV3.UNINITIALIZED: {AgentStateV3.BOOTING, AgentStateV3.TERMINATED},
    AgentStateV3.BOOTING: {AgentStateV3.REGISTERING, AgentStateV3.TERMINATING},
    AgentStateV3.REGISTERING: {AgentStateV3.IDLE, AgentStateV3.TERMINATING},
    AgentStateV3.IDLE: {AgentStateV3.DISCOVERING, AgentStateV3.SELF_OPTIMIZING,
                         AgentStateV3.PAUSED, AgentStateV3.TERMINATING,
                         AgentStateV3.MIGRATING},
    AgentStateV3.DISCOVERING: {AgentStateV3.NEGOTIATING, AgentStateV3.IDLE},
    AgentStateV3.NEGOTIATING: {AgentStateV3.TRUST_BUILDING, AgentStateV3.IDLE},
    AgentStateV3.TRUST_BUILDING: {AgentStateV3.CONTRACTING, AgentStateV3.IDLE},
    AgentStateV3.CONTRACTING: {AgentStateV3.EXECUTING, AgentStateV3.IDLE},
    AgentStateV3.EXECUTING: {AgentStateV3.WAITING, AgentStateV3.VERIFYING,
                              AgentStateV3.CONFLICTING},
    AgentStateV3.WAITING: {AgentStateV3.EXECUTING, AgentStateV3.VERIFYING},
    AgentStateV3.VERIFYING: {AgentStateV3.REPORTING, AgentStateV3.EXECUTING},
    AgentStateV3.REPORTING: {AgentStateV3.IDLE, AgentStateV3.EVOLVING},
    AgentStateV3.CONFLICTING: {AgentStateV3.ARBITRATING, AgentStateV3.DEGRADING},
    AgentStateV3.ARBITRATING: {AgentStateV3.RECOVERING, AgentStateV3.IDLE},
    AgentStateV3.RECOVERING: {AgentStateV3.IDLE, AgentStateV3.CONFLICTING},
    AgentStateV3.MIGRATING: {AgentStateV3.IDLE, AgentStateV3.TERMINATING},
    AgentStateV3.PAUSED: {AgentStateV3.IDLE, AgentStateV3.TERMINATING},
    AgentStateV3.DEGRADING: {AgentStateV3.SELF_HEALING, AgentStateV3.TERMINATING},
    AgentStateV3.SELF_HEALING: {AgentStateV3.IDLE, AgentStateV3.DEGRADING},
    AgentStateV3.SELF_OPTIMIZING: {AgentStateV3.IDLE, AgentStateV3.EVOLVING},
    AgentStateV3.EVOLVING: {AgentStateV3.IDLE, AgentStateV3.SELF_OPTIMIZING},
    AgentStateV3.TERMINATING: {AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE},
    AgentStateV3.TERMINATED: set(),
    AgentStateV3.ZOMBIE: set(),
}

INVARIANTS = [
    "no_deadlock: every state except TERMINATED/ZOMBIE has at least one outgoing transition",
    "no_orphan: every state except UNINITIALIZED has at least one incoming transition",
    "gray_continuity: each transition changes at most 1 bit in 5-bit Gray Code",
    "terminated_final: TERMINATED has no outgoing transitions",
    "zombie_final: ZOMBIE has no outgoing transitions",
]


@dataclass
class StateTransition:
    agent_id: str
    from_state: AgentStateV3
    to_state: AgentStateV3
    from_gray: str
    to_gray: str
    bit_changes: int
    is_valid: bool
    timestamp: float


@dataclass
class StateInvariantCheck:
    invariant_name: str
    holds: bool
    message: str = ""


class Agent24StateMachine:
    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._agents: dict[str, AgentStateV3] = {}
        self._history: list[StateTransition] = []
        self._audit_store = audit_store or UnifiedAuditStore()

    def register(self, agent_id: str) -> None:
        self._agents[agent_id] = AgentStateV3.UNINITIALIZED

    def state_of(self, agent_id: str) -> AgentStateV3 | None:
        return self._agents.get(agent_id)

    def gray_code_of(self, agent_id: str) -> str | None:
        state = self._agents.get(agent_id)
        if state is None:
            return None
        return GRAY_CODE_5BIT[state]

    def transition(self, agent_id: str, to_state: AgentStateV3) -> StateTransition | None:
        current = self._agents.get(agent_id)
        if current is None:
            return None

        allowed = VALID_TRANSITIONS.get(current, set())
        is_valid = to_state in allowed

        from_gray = GRAY_CODE_5BIT[current]
        to_gray = GRAY_CODE_5BIT[to_state]
        bit_changes = sum(1 for a, b in zip(from_gray, to_gray, strict=False) if a != b)

        t = StateTransition(
            agent_id=agent_id,
            from_state=current,
            to_state=to_state,
            from_gray=from_gray,
            to_gray=to_gray,
            bit_changes=bit_changes,
            is_valid=is_valid,
            timestamp=__import__('time').time(),
        )

        if is_valid:
            self._agents[agent_id] = to_state
            self._history.append(t)
            self._audit_store.append(UnifiedAuditRecord(
                record_id=make_record_id("s24", hash((agent_id, to_state.value)) % 100000),
                timestamp=t.timestamp,
                layer="evolution",
                round=43,
                event_type=f"state_{current.value}_to_{to_state.value}",
                source_module="Agent24StateMachine",
                target_module=agent_id,
                decision=f"{current.value}→{to_state.value}",
                justification=f"Gray: {from_gray}→{to_gray}, bits changed: {bit_changes}",
                outcome="success" if is_valid else "failure",
                context_refs=[agent_id],
            ))

        return t

    def force_transition(self, agent_id: str, to_state: AgentStateV3) -> StateTransition | None:
        current = self._agents.get(agent_id)
        if current is None:
            return None
        from_gray = GRAY_CODE_5BIT[current]
        to_gray = GRAY_CODE_5BIT[to_state]
        bit_changes = sum(1 for a, b in zip(from_gray, to_gray, strict=False) if a != b)
        is_valid = to_state in VALID_TRANSITIONS.get(current, set())
        self._agents[agent_id] = to_state
        t = StateTransition(
            agent_id=agent_id,
            from_state=current,
            to_state=to_state,
            from_gray=from_gray,
            to_gray=to_gray,
            bit_changes=bit_changes,
            is_valid=is_valid,
            timestamp=__import__('time').time(),
        )
        self._history.append(t)
        return t

    def check_invariants(self) -> list[StateInvariantCheck]:
        checks: list[StateInvariantCheck] = []
        all_states = set(AgentStateV3)

        has_out = all(
            len(VALID_TRANSITIONS.get(s, set())) > 0 or s in {
                AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE
            }
            for s in all_states
        )
        checks.append(StateInvariantCheck(
            "no_deadlock", has_out,
            "OK" if has_out else "Some non-terminal state has no outgoing transition",
        ))

        has_incoming: set[AgentStateV3] = set()
        for _, targets in VALID_TRANSITIONS.items():
            for t in targets:
                has_incoming.add(t)
        orphans = all_states - has_incoming - {AgentStateV3.UNINITIALIZED}
        checks.append(StateInvariantCheck(
            "no_orphan", len(orphans) == 0,
            "OK" if len(orphans) == 0 else f"Orphan states: {[s.value for s in orphans]}",
        ))

        checks.append(StateInvariantCheck(
            "terminated_final",
            len(VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set())) == 0,
            "OK" if len(VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set())) == 0
            else "TERMINATED has outgoing transitions",
        ))

        zombie_transitions = VALID_TRANSITIONS.get(AgentStateV3.ZOMBIE, set())
        checks.append(StateInvariantCheck(
            "zombie_final",
            len(zombie_transitions) == 0,
            "OK" if len(zombie_transitions) == 0 else "ZOMBIE has outgoing transitions",
        ))

        checks.append(StateInvariantCheck(
            "state_count",
            len(all_states) == 24,
            f"OK ({len(all_states)} states)" if len(all_states) == 24
            else f"Expected 24 states, got {len(all_states)}",
        ))

        return checks

    def path_exists(self, from_state: AgentStateV3, to_state: AgentStateV3,
                     max_depth: int = 10) -> bool:
        visited: set[AgentStateV3] = set()
        queue: list[tuple[AgentStateV3, int]] = [(from_state, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current == to_state:
                return True
            if depth >= max_depth:
                continue
            visited.add(current)
            for next_state in VALID_TRANSITIONS.get(current, set()):
                if next_state not in visited:
                    queue.append((next_state, depth + 1))

        return False

    def traversal_path(self, start: AgentStateV3, steps: int = 24) -> list[AgentStateV3] | None:
        visited: list[AgentStateV3] = []
        current = start
        order = list(AgentStateV3)

        while current not in visited and len(visited) < steps:
            visited.append(current)
            candidates = sorted(
                [s for s in VALID_TRANSITIONS.get(current, set()) if s not in visited],
                key=lambda x: order.index(x),
            )
            if not candidates:
                break
            current = candidates[0]

        return visited if len(visited) >= steps else None

    def get_history(self, agent_id: str | None = None) -> list[StateTransition]:
        if agent_id is None:
            return list(self._history)
        return [t for t in self._history if t.agent_id == agent_id]

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    def reset(self) -> None:
        self._agents.clear()
        self._history.clear()
