from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.identity.did_registry import AgentDID

DEFAULT_WEIGHTS = {
    "behavior_consistency": 0.30,
    "cb_trigger_frequency": 0.25,
    "halt_avoidance": 0.15,
    "task_completion": 0.15,
    "vc_validity": 0.15,
}


@dataclass
class TrustScore:
    value: float
    confidence: float
    factors: dict[str, float] = field(default_factory=dict)
    last_updated: float = 0.0


class TrustEngine:
    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        audit_logger: AuditLogger,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._cb = circuit_breaker
        self._audit = audit_logger
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._scores: dict[AgentDID, TrustScore] = {}
        self._agent_events: dict[AgentDID, list[dict[str, Any]]] = defaultdict(list)
        total = sum(self._weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Trust weights must sum to 1.0, got {total}")

    def evaluate(self, agent_did: AgentDID) -> TrustScore:
        factors = self._compute_factors(agent_did)
        value = sum(w * factors.get(k, 0.5) for k, w in self._weights.items())
        value = max(0.0, min(1.0, value))
        confidence = self._compute_confidence(agent_did)
        score = TrustScore(
            value=value,
            confidence=confidence,
            factors=factors,
            last_updated=time.time(),
        )
        self._scores[agent_did] = score
        return score

    def _compute_factors(self, agent_did: AgentDID) -> dict[str, float]:
        events = self._agent_events.get(agent_did, [])
        factors: dict[str, float] = {}

        audit_entries = self._audit.read_all()
        agent_entries = [
            e for e in audit_entries
            if e.metadata.get("agent_did") == agent_did.did_string
        ]

        completed = sum(1 for e in agent_entries if e.action == "task_completed")
        total_tasks = max(completed + sum(1 for e in agent_entries if e.action == "task_failed"), 1)
        factors["task_completion"] = completed / total_tasks

        halts = sum(1 for e in agent_entries if "halt" in e.event_type.lower())
        factors["halt_avoidance"] = max(0.0, 1.0 - halts / max(len(agent_entries), 1))

        agent_cb_events = sum(
            1 for e in agent_entries
            if "circuit_breaker" in e.event_type.lower() or "cb_trip" in e.event_type.lower()
        )
        cb_trips = agent_cb_events
        cb_factor = max(0.0, 1.0 - (cb_trips * 0.1)) if cb_trips < 10 else 0.0
        factors["cb_trigger_frequency"] = cb_factor

        behavior_score = 0.7
        behavior_deltas = [e.get("delta", 0) for e in events if "delta" in e]
        if behavior_deltas:
            avg_delta = sum(abs(d) for d in behavior_deltas) / len(behavior_deltas)
            behavior_score = max(0.0, 1.0 - avg_delta)
        factors["behavior_consistency"] = behavior_score

        valid_creds = sum(1 for e in agent_entries if e.metadata.get("credential_valid") is True)
        total_creds = max(valid_creds + sum(1 for e in agent_entries if e.metadata.get("credential_valid") is False), 1)
        factors["vc_validity"] = valid_creds / total_creds if total_creds > 0 else 0.5

        return factors

    def _compute_confidence(self, agent_did: AgentDID) -> float:
        events = self._agent_events.get(agent_did, [])
        n = len(events)
        if n == 0:
            return 0.1
        return min(1.0, n / 100.0)

    def sync_to_circuit_breaker(self, agent_did: AgentDID) -> BreakerState:
        score = self.evaluate(agent_did)
        if score.value < 0.3:
            target_state = BreakerState.OPEN
        elif score.value < 0.5:
            target_state = BreakerState.HALF_OPEN
        else:
            target_state = BreakerState.CLOSED
        self._cb._state = target_state
        self._audit.log(
            event_type="trust_cb_sync",
            actor="TrustEngine",
            action="sync_to_circuit_breaker",
            details=f"Trust={score.value:.3f} → CB={target_state.value}",
            metadata={
                "agent_did": agent_did.did_string,
                "trust_score": score.value,
                "cb_state": target_state.value,
            },
        )
        return target_state

    def record_event(self, agent_did: AgentDID, event_type: str, data: dict[str, Any] | None = None) -> None:
        event = {"type": event_type, "timestamp": time.time(), **(data or {})}
        self._agent_events[agent_did].append(event)

    def get_score(self, agent_did: AgentDID) -> TrustScore | None:
        return self._scores.get(agent_did)
