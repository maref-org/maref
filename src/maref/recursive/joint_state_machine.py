from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class JointStateMachine:
    agents: dict[str, str] = field(default_factory=dict)
    conflict_log: list[dict[str, str]] = field(default_factory=list)
    _handoff_timeouts: dict[str, float] = field(default_factory=dict)
    _handoff_pairs: dict[str, str] = field(default_factory=dict)

    VALID_STATES = {
        "IDLE", "RUNNING", "DONE", "ERROR", "PAUSED",
        "HANDOFF_SOURCE", "HANDOFF_TARGET",
    }

    def register_agent(self, agent_id: str) -> None:
        self.agents.setdefault(agent_id, "IDLE")

    def advance(self, agent_id: str, new_state: str) -> None:
        self.agents[agent_id] = new_state

    def all_at_barrier(self, barrier_state: str) -> bool:
        if not self.agents:
            return False
        return all(state == barrier_state for state in self.agents.values())

    def any_at_state(self, state: str) -> bool:
        return any(s == state for s in self.agents.values())

    def advance_all_to(self, new_state: str) -> None:
        for agent_id in self.agents:
            self.agents[agent_id] = new_state

    def arbitrate(self, agent_a: str, agent_b: str, issue: str) -> str:
        resolution = f"arbitration: {issue} resolved between {agent_a} and {agent_b}"
        self.conflict_log.append({
            "agent_a": agent_a,
            "agent_b": agent_b,
            "issue": issue,
            "resolution": "arbitrated",
        })
        return resolution

    def reset(self) -> None:
        self.agents.clear()
        self.conflict_log.clear()
        self._handoff_timeouts.clear()
        self._handoff_pairs.clear()

    def agent_count(self) -> int:
        return len(self.agents)

    def agent_states(self) -> dict[str, str]:
        return dict(self.agents)

    def initiate_handoff(self, source_agent: str, target_agent: str,
                          timeout_seconds: float = 30.0) -> bool:
        if source_agent not in self.agents or target_agent not in self.agents:
            return False
        if self._handoff_pairs.get(source_agent) is not None:
            return False
        self.agents[source_agent] = "HANDOFF_SOURCE"
        self.agents[target_agent] = "HANDOFF_TARGET"
        self._handoff_pairs[source_agent] = target_agent
        deadline = time.time() + timeout_seconds
        self._handoff_timeouts[source_agent] = deadline
        self._handoff_timeouts[target_agent] = deadline
        return True

    def complete_handoff(self, source_agent: str) -> bool:
        target_agent = self._handoff_pairs.get(source_agent)
        if target_agent is None:
            return False
        if self.agents.get(source_agent) != "HANDOFF_SOURCE":
            return False
        if self.agents.get(target_agent) != "HANDOFF_TARGET":
            return False
        self.agents[source_agent] = "DONE"
        self.agents[target_agent] = "RUNNING"
        del self._handoff_pairs[source_agent]
        self._handoff_timeouts.pop(source_agent, None)
        self._handoff_timeouts.pop(target_agent, None)
        return True

    def rollback_handoff(self, source_agent: str) -> bool:
        target_agent = self._handoff_pairs.get(source_agent)
        if target_agent is None:
            return False
        self.agents[source_agent] = "RUNNING"
        self.agents[target_agent] = "IDLE"
        del self._handoff_pairs[source_agent]
        self._handoff_timeouts.pop(source_agent, None)
        self._handoff_timeouts.pop(target_agent, None)
        return True

    def check_handoff_timeout(self) -> list[str]:
        timed_out: list[str] = []
        now = time.time()
        for agent_id, deadline in list(self._handoff_timeouts.items()):
            if now >= deadline:
                timed_out.append(agent_id)
        for agent_id in timed_out:
            if agent_id in self._handoff_pairs:
                self.rollback_handoff(agent_id)
        return timed_out

    def is_in_handoff(self, agent_id: str) -> bool:
        state = self.agents.get(agent_id, "")
        return state in {"HANDOFF_SOURCE", "HANDOFF_TARGET"}

    def handoff_partner(self, agent_id: str) -> str | None:
        partner = self._handoff_pairs.get(agent_id)
        if partner is not None:
            return partner
        for src, tgt in self._handoff_pairs.items():
            if tgt == agent_id:
                return src
        return None

    def active_handoffs(self) -> dict[str, str]:
        return dict(self._handoff_pairs)
