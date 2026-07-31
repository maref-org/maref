"""DEPRECATED compatibility layer for the legacy MAREF trust engine.

The single source of truth for trust scoring is now
:class:`~maref.recursive.trust_engine_v2.TrustEngineV2` (9-factor scoring with
Goodhart-overoptimization detection, temporal decay, AAA-F tiers). This
module keeps the legacy ``TrustEngine`` API working by delegating to
``TrustEngineV2`` internally:

- ``evaluate()`` / ``get_score()``  -> ``TrustEngineV2.assess()`` mapped to the
  legacy 0..1 ``TrustScore`` scale
- ``record_event()``              -> feeds V2 signals (task success/failure,
  behavioral delta, compliance violations)
- ``sync_to_circuit_breaker()``   -> legacy CB state mapping kept verbatim

New code MUST use :class:`TrustEngineV2` instead. This module exists only so
existing callers keep working during migration; importing it raises a
``DeprecationWarning``.
"""

from __future__ import annotations

import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.identity.did_registry import AgentDID
from maref.recursive.trust_engine_v2 import TrustEngineV2

# Legacy weights kept for API compatibility (validated on construction).
# Actual scoring weights now live in TrustEngineV2.FACTOR_WEIGHTS.
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
    """Legacy trust-engine API delegating to :class:`TrustEngineV2`.

    Deprecated. Prefer ``TrustEngineV2`` for all new code. The legacy
    constructor signature, ``evaluate()`` 0..1 value scale and
    ``sync_to_circuit_breaker()`` behavior are preserved.
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        audit_logger: AuditLogger,
        weights: dict[str, float] | None = None,
    ) -> None:
        warnings.warn(
            "TrustEngine is deprecated; use maref.recursive.trust_engine_v2.TrustEngineV2",
            DeprecationWarning,
            stacklevel=2,
        )
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        total = sum(self._weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Trust weights must sum to 1.0, got {total}")
        self._cb = circuit_breaker
        self._audit = audit_logger
        self._v2 = TrustEngineV2()
        self._scores: dict[AgentDID, TrustScore] = {}
        self._agent_events: dict[AgentDID, list[dict[str, Any]]] = defaultdict(list)

    def _ensure_profile(self, agent_did: AgentDID) -> str:
        """Idempotently register the agent in the V2 engine (registering twice
        would reset its profile)."""
        aid = agent_did.did_string
        if aid not in self._v2._profiles:
            self._v2.register_agent(aid)
        return aid

    def record_event(
        self, agent_did: AgentDID, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        aid = self._ensure_profile(agent_did)
        event = {"type": event_type, "timestamp": time.time(), **(data or {})}
        self._agent_events[agent_did].append(event)

        d = data or {}
        profile = self._v2._profiles[aid]
        # Behavioral drift lowers the V2 behavioral_consistency factor.
        if "delta" in d:
            delta = abs(float(d["delta"]))
            profile.behavioral_consistency = max(
                0.0, min(1.0, profile.behavioral_consistency - delta)
            )
        # Compliance violations lower the compliance_adherence factor.
        if "violations" in d or "compliance" in d:
            self._v2.update_compliance(aid, int(d.get("violations", d.get("compliance", 0))))
        # Task success/failure feeds the V2 task history.
        success = d.get("success")
        is_failure = success is False or (
            success is None
            and ("fail" in event_type.lower() or "halt" in event_type.lower())
        )
        if success is not None or is_failure:
            self._v2.record_task(
                aid,
                task_id=event_type,
                success=not is_failure,
                quality=float(d.get("quality", 0.5)),
            )

    def evaluate(self, agent_did: AgentDID) -> TrustScore:
        aid = self._ensure_profile(agent_did)
        v2_score = self._v2.assess(aid)
        if v2_score is None:
            # Should not happen after ensure_profile; guard for typing.
            raise RuntimeError(f"agent {aid} could not be assessed")
        n_events = len(self._agent_events.get(agent_did, []))
        confidence = min(1.0, n_events / 100.0) if n_events else 0.1
        score = TrustScore(
            value=round(v2_score.overall_trust / 100.0, 4),
            confidence=confidence,
            factors={f.name: round(f.value, 4) for f in v2_score.factors},
            last_updated=time.time(),
        )
        self._scores[agent_did] = score
        return score

    def get_score(self, agent_did: AgentDID) -> TrustScore | None:
        return self._scores.get(agent_did)

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
