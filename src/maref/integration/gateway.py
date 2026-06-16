"""
MAREF ↔ LLM Gateway Routing Bridge

M6.6: Injects MAREF state machine `current_entropy` as a routing
decision factor in Athena's LLM Gateway.

Routing strategies:
- entropy-based: high entropy → route to more capable (expensive) models
- state-based: VERIFY/ACT → route to deterministic models (temp=0)
- budget-aware: low entropy OBSERVE → route to cheapest model
- circuit-aware: if circuit breaker open → route to fallback

Gateway decision weights:
  entropy(40%) + state(20%) + budget(20%) + latency(10%) + fallback(10%)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.types import GovernanceState


class GatewayRoute(Enum):
    CHEAP = "cheap"
    STANDARD = "standard"
    CAPABLE = "capable"
    DETERMINISTIC = "deterministic"
    FALLBACK = "fallback"


@dataclass
class RoutingDecision:
    route: GatewayRoute
    entropy: int
    state: str
    confidence: float
    factors: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "entropy": self.entropy,
            "state": self.state,
            "confidence": self.confidence,
            "factors": self.factors,
            "explanation": self.explanation,
        }


STATE_ROUTE_PREFERENCES: dict[GovernanceState, GatewayRoute] = {
    GovernanceState.INIT: GatewayRoute.STANDARD,
    GovernanceState.OBSERVE: GatewayRoute.CHEAP,
    GovernanceState.ANALYZE: GatewayRoute.STANDARD,
    GovernanceState.EVALUATE: GatewayRoute.CAPABLE,
    GovernanceState.DECIDE: GatewayRoute.CAPABLE,
    GovernanceState.ACT: GatewayRoute.DETERMINISTIC,
    GovernanceState.VERIFY: GatewayRoute.DETERMINISTIC,
    GovernanceState.STABILIZE: GatewayRoute.STANDARD,
    GovernanceState.REPORT: GatewayRoute.STANDARD,
    GovernanceState.HALT: GatewayRoute.FALLBACK,
}


ENTROPY_ROUTE_MAP: dict[int, GatewayRoute] = {
    0: GatewayRoute.CHEAP,
    1: GatewayRoute.CHEAP,
    2: GatewayRoute.STANDARD,
    3: GatewayRoute.CAPABLE,
    4: GatewayRoute.DETERMINISTIC,
}


class GatewayRouter:
    """
    Routes LLM requests based on MAREF governance state and entropy.

    Decision formula:
      score = entropy_factor*0.4 + state_factor*0.2 + budget_factor*0.2
            + latency_factor*0.1 + fallback_factor*0.1

    High entropy (3-4) → route to capable/deterministic models
    Low entropy (0-1) → route to cheap models
    HALT state → fallback route (always)
    """

    def __init__(
        self,
        budget_tier: str = "standard",
        latency_budget_ms: float = 500.0,
        percv_adapter: Any = None,
    ) -> None:
        self._budget_tier = budget_tier
        self._latency_budget_ms = latency_budget_ms
        self._percv_adapter = percv_adapter
        self._decision_history: list[RoutingDecision] = []
        self._circuit_open = False

    def set_circuit_open(self, open: bool) -> None:
        self._circuit_open = open

    def compute_route(
        self,
        state: GovernanceState,
        entropy: int,
        budget_override: str | None = None,
    ) -> RoutingDecision:
        # Try to use PERCV adapter if available
        if self._percv_adapter:
            try:
                if hasattr(self._percv_adapter, "get_recommended_route"):
                    route_info = self._percv_adapter.get_recommended_route(
                        state=state.name,
                        entropy=entropy,
                    )
                    if route_info:
                        # Map PERCV route to MAREF GatewayRoute
                        route_map = {
                            "cheap": GatewayRoute.CHEAP,
                            "standard": GatewayRoute.STANDARD,
                            "capable": GatewayRoute.CAPABLE,
                            "deterministic": GatewayRoute.DETERMINISTIC,
                            "fallback": GatewayRoute.FALLBACK,
                        }
                        route = route_map.get(route_info.get("route"), GatewayRoute.STANDARD)

                        decision = RoutingDecision(
                            route=route,
                            entropy=entropy,
                            state=state.name,
                            confidence=route_info.get("confidence", 0.8),
                            factors={"percv_adapter": 1.0},
                            explanation=f"PERCV adapter: {route_info.get('explanation', '')}",
                        )
                        self._decision_history.append(decision)
                        return decision
            except Exception:
                # Fall back to standard routing if PERCV fails
                pass

        if self._circuit_open:
            decision = RoutingDecision(
                route=GatewayRoute.FALLBACK,
                entropy=entropy,
                state=state.name,
                confidence=1.0,
                factors={"circuit_breaker": 1.0},
                explanation="Circuit breaker open — forcing fallback route",
            )
            self._decision_history.append(decision)
            return decision

        if state == GovernanceState.HALT:
            decision = RoutingDecision(
                route=GatewayRoute.FALLBACK,
                entropy=entropy,
                state=state.name,
                confidence=1.0,
                factors={"halt_state": 1.0},
                explanation="HALT state — routing to fallback",
            )
            self._decision_history.append(decision)
            return decision

        entropy_route = ENTROPY_ROUTE_MAP.get(entropy, GatewayRoute.STANDARD)
        state_route = STATE_ROUTE_PREFERENCES.get(state, GatewayRoute.STANDARD)

        route_scores: dict[GatewayRoute, float] = {
            GatewayRoute.CHEAP: 0.0,
            GatewayRoute.STANDARD: 0.0,
            GatewayRoute.CAPABLE: 0.0,
            GatewayRoute.DETERMINISTIC: 0.0,
            GatewayRoute.FALLBACK: 0.0,
        }

        route_scores[entropy_route] += 0.4

        route_scores[state_route] += 0.2

        budget = budget_override or self._budget_tier
        if budget == "cheap":
            route_scores[GatewayRoute.CHEAP] += 0.2
        elif budget == "premium":
            route_scores[GatewayRoute.CAPABLE] += 0.2
        else:
            route_scores[GatewayRoute.STANDARD] += 0.2

        latency_preference = (
            GatewayRoute.CHEAP if self._latency_budget_ms < 200 else GatewayRoute.STANDARD
        )
        route_scores[latency_preference] += 0.1

        route_scores[GatewayRoute.FALLBACK] += 0.1

        best_route = max(route_scores, key=lambda k: route_scores[k])
        confidence = max(route_scores.values()) / sum(route_scores.values())

        explanation_parts: list[str] = []
        if entropy >= 3:
            explanation_parts.append(f"high_entropy({entropy})→{entropy_route.value}")
        if state in (GovernanceState.ACT, GovernanceState.VERIFY):
            explanation_parts.append(f"critical_state({state.name})→{state_route.value}")

        decision = RoutingDecision(
            route=best_route,
            entropy=entropy,
            state=state.name,
            confidence=round(confidence, 2),
            factors={
                "entropy_route": entropy_route.value,
                "state_route": state_route.value,
                "scores": {k.value: round(v, 2) for k, v in route_scores.items()},
            },
            explanation="; ".join(explanation_parts) if explanation_parts else "balanced_routing",
        )
        self._decision_history.append(decision)
        return decision

    def get_recent_decisions(self, n: int = 10) -> list[RoutingDecision]:
        return self._decision_history[-n:]

    def get_stats(self) -> dict[str, Any]:
        route_counts: dict[str, int] = {}
        for d in self._decision_history:
            r = d.route.value
            route_counts[r] = route_counts.get(r, 0) + 1

        avg_confidence = (
            sum(d.confidence for d in self._decision_history) / len(self._decision_history)
            if self._decision_history
            else 0.0
        )

        return {
            "total_decisions": len(self._decision_history),
            "route_distribution": route_counts,
            "avg_confidence": round(avg_confidence, 3),
            "circuit_open": self._circuit_open,
            "budget_tier": self._budget_tier,
            "latency_budget_ms": self._latency_budget_ms,
        }
