"""
Comprehensive tests for MAREF Gateway Router (gateway.py)
Target: 100% coverage of gateway.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.governance.types import GovernanceState
from maref.integration.gateway import (
    GatewayRoute,
    RoutingDecision,
    GatewayRouter,
    STATE_ROUTE_PREFERENCES,
    ENTROPY_ROUTE_MAP,
)


class TestGatewayRoute:
    """Test GatewayRoute enum."""

    def test_gateway_route_values(self):
        assert GatewayRoute.CHEAP.value == "cheap"
        assert GatewayRoute.STANDARD.value == "standard"
        assert GatewayRoute.CAPABLE.value == "capable"
        assert GatewayRoute.DETERMINISTIC.value == "deterministic"
        assert GatewayRoute.FALLBACK.value == "fallback"

    def test_gateway_route_iteration(self):
        routes = list(GatewayRoute)
        assert len(routes) == 5


class TestRoutingDecision:
    """Test RoutingDecision dataclass."""

    def test_routing_decision_creation(self):
        decision = RoutingDecision(
            route=GatewayRoute.STANDARD,
            entropy=2,
            state="ANALYZE",
            confidence=0.85,
        )
        assert decision.route == GatewayRoute.STANDARD
        assert decision.entropy == 2
        assert decision.state == "ANALYZE"
        assert decision.confidence == 0.85
        assert decision.factors == {}
        assert decision.explanation == ""

    def test_routing_decision_with_factors_and_explanation(self):
        factors = {"entropy_route": "standard", "state_route": "standard"}
        decision = RoutingDecision(
            route=GatewayRoute.STANDARD,
            entropy=2,
            state="ANALYZE",
            confidence=0.85,
            factors=factors,
            explanation="balanced_routing",
        )
        assert decision.factors == factors
        assert decision.explanation == "balanced_routing"

    def test_to_dict(self):
        decision = RoutingDecision(
            route=GatewayRoute.CAPABLE,
            entropy=3,
            state="EVALUATE",
            confidence=0.9,
            factors={"test": "value"},
            explanation="high entropy routing",
        )
        d = decision.to_dict()
        assert d["route"] == "capable"
        assert d["entropy"] == 3
        assert d["state"] == "EVALUATE"
        assert d["confidence"] == 0.9
        assert d["factors"] == {"test": "value"}
        assert d["explanation"] == "high entropy routing"


class TestGatewayRouter:
    """Test GatewayRouter class."""

    def test_init_defaults(self):
        router = GatewayRouter()
        assert router._budget_tier == "standard"
        assert router._latency_budget_ms == 500.0
        assert router._percv_adapter is None
        assert router._decision_history == []
        assert router._circuit_open is False

    def test_init_custom(self):
        adapter = MagicMock()
        router = GatewayRouter(
            budget_tier="premium",
            latency_budget_ms=100.0,
            percv_adapter=adapter,
        )
        assert router._budget_tier == "premium"
        assert router._latency_budget_ms == 100.0
        assert router._percv_adapter == adapter

    def test_set_circuit_open(self):
        router = GatewayRouter()
        assert router._circuit_open is False
        router.set_circuit_open(True)
        assert router._circuit_open is True
        router.set_circuit_open(False)
        assert router._circuit_open is False

    def test_compute_route_circuit_breaker_open(self):
        router = GatewayRouter()
        router.set_circuit_open(True)
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert decision.route == GatewayRoute.FALLBACK
        assert decision.factors["circuit_breaker"] == 1.0
        assert "Circuit breaker open" in decision.explanation

    def test_compute_route_halt_state(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.HALT, 4)
        assert decision.route == GatewayRoute.FALLBACK
        assert decision.factors["halt_state"] == 1.0
        assert "HALT state" in decision.explanation

    def test_compute_route_percv_adapter_success(self):
        adapter = MagicMock()
        adapter.get_recommended_route.return_value = {
            "route": "capable",
            "confidence": 0.95,
            "explanation": "PERCV recommends capable",
        }
        router = GatewayRouter(percv_adapter=adapter)
        decision = router.compute_route(GovernanceState.EVALUATE, 3)
        assert decision.route == GatewayRoute.CAPABLE
        assert decision.confidence == 0.95
        assert "PERCV adapter" in decision.explanation
        adapter.get_recommended_route.assert_called_once_with(
            state="EVALUATE", entropy=3
        )

    def test_compute_route_percv_adapter_failure_fallback(self):
        adapter = MagicMock()
        adapter.get_recommended_route.side_effect = Exception("PERCV down")
        router = GatewayRouter(percv_adapter=adapter)
        decision = router.compute_route(GovernanceState.ANALYZE, 2)
        assert decision.route == GatewayRoute.STANDARD
        assert "entropy_route" in decision.factors

    def test_compute_route_percv_adapter_invalid_route(self):
        adapter = MagicMock()
        adapter.get_recommended_route.return_value = {"route": "invalid_route"}
        router = GatewayRouter(percv_adapter=adapter)
        decision = router.compute_route(GovernanceState.ANALYZE, 2)
        assert decision.route == GatewayRoute.STANDARD

    @pytest.mark.parametrize(
        "entropy,expected_route",
        [
            (0, GatewayRoute.CHEAP),
            (1, GatewayRoute.CHEAP),
            (2, GatewayRoute.STANDARD),
            (3, GatewayRoute.CAPABLE),
            (4, GatewayRoute.DETERMINISTIC),
            (5, GatewayRoute.STANDARD),
        ],
    )
    def test_entropy_route_map(self, entropy, expected_route):
        assert ENTROPY_ROUTE_MAP.get(entropy, GatewayRoute.STANDARD) == expected_route

    @pytest.mark.parametrize(
        "state,expected_route",
        [
            (GovernanceState.INIT, GatewayRoute.STANDARD),
            (GovernanceState.OBSERVE, GatewayRoute.CHEAP),
            (GovernanceState.ANALYZE, GatewayRoute.STANDARD),
            (GovernanceState.EVALUATE, GatewayRoute.CAPABLE),
            (GovernanceState.DECIDE, GatewayRoute.CAPABLE),
            (GovernanceState.ACT, GatewayRoute.DETERMINISTIC),
            (GovernanceState.VERIFY, GatewayRoute.DETERMINISTIC),
            (GovernanceState.STABILIZE, GatewayRoute.STANDARD),
            (GovernanceState.REPORT, GatewayRoute.STANDARD),
            (GovernanceState.HALT, GatewayRoute.FALLBACK),
        ],
    )
    def test_state_route_preferences(self, state, expected_route):
        assert STATE_ROUTE_PREFERENCES[state] == expected_route

    def test_compute_route_budget_cheap(self):
        router = GatewayRouter(budget_tier="cheap")
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert decision.route == GatewayRoute.CHEAP

    def test_compute_route_budget_premium(self):
        router = GatewayRouter(budget_tier="premium")
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert decision.route in (GatewayRoute.CHEAP, GatewayRoute.CAPABLE, GatewayRoute.STANDARD)

    def test_compute_route_latency_budget_low(self):
        router = GatewayRouter(latency_budget_ms=100.0)
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert decision.route == GatewayRoute.CHEAP

    def test_compute_route_latency_budget_high(self):
        router = GatewayRouter(latency_budget_ms=1000.0)
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert decision.route == GatewayRoute.STANDARD

    def test_compute_route_high_entropy_explanation(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ANALYZE, 3)
        assert "high_entropy(3)" in decision.explanation

    def test_compute_route_critical_state_explanation(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ACT, 1)
        assert "critical_state(ACT)" in decision.explanation
        decision2 = router.compute_route(GovernanceState.VERIFY, 1)
        assert "critical_state(VERIFY)" in decision2.explanation

    def test_compute_route_balanced_routing_explanation(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ANALYZE, 1)
        assert decision.explanation == "balanced_routing"

    def test_compute_route_confidence_calculation(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.OBSERVE, 0)
        assert 0.0 <= decision.confidence <= 1.0

    def test_compute_route_history_tracking(self):
        router = GatewayRouter()
        router.compute_route(GovernanceState.OBSERVE, 0)
        router.compute_route(GovernanceState.ANALYZE, 2)
        router.compute_route(GovernanceState.ACT, 1)
        assert len(router._decision_history) == 3

    def test_get_recent_decisions(self):
        router = GatewayRouter()
        for i in range(15):
            router.compute_route(GovernanceState.OBSERVE, i % 5)
        recent = router.get_recent_decisions(5)
        assert len(recent) == 5
        assert recent[-1].entropy == 4
        recent_all = router.get_recent_decisions(100)
        assert len(recent_all) == 15

    def test_get_stats_empty(self):
        router = GatewayRouter()
        stats = router.get_stats()
        assert stats["total_decisions"] == 0
        assert stats["route_distribution"] == {}
        assert stats["avg_confidence"] == 0.0
        assert stats["circuit_open"] is False
        assert stats["budget_tier"] == "standard"
        assert stats["latency_budget_ms"] == 500.0

    def test_get_stats_with_history(self):
        router = GatewayRouter()
        router.compute_route(GovernanceState.OBSERVE, 0)
        router.compute_route(GovernanceState.ANALYZE, 2)
        router.compute_route(GovernanceState.ACT, 1)
        stats = router.get_stats()
        assert stats["total_decisions"] == 3
        assert sum(stats["route_distribution"].values()) == 3
        assert stats["avg_confidence"] > 0.0

    def test_compute_route_with_budget_override(self):
        router = GatewayRouter(budget_tier="standard")
        decision = router.compute_route(GovernanceState.OBSERVE, 0, budget_override="cheap")
        assert decision.route == GatewayRoute.CHEAP
        decision2 = router.compute_route(GovernanceState.OBSERVE, 0, budget_override="premium")
        assert decision2.route in (GatewayRoute.CAPABLE, GatewayRoute.STANDARD)


class TestGatewayRouterEdgeCases:
    """Test edge cases and error conditions."""

    def test_compute_route_entropy_boundary(self):
        router = GatewayRouter()
        decision = router.compute_route(GovernanceState.ANALYZE, 2)
        assert decision.entropy == 2

    def test_compute_route_with_percv_adapter_none_result(self):
        adapter = MagicMock()
        adapter.get_recommended_route.return_value = None
        router = GatewayRouter(percv_adapter=adapter)
        decision = router.compute_route(GovernanceState.ANALYZE, 2)
        assert decision.route == GatewayRoute.STANDARD

    def test_compute_route_with_percv_adapter_missing_keys(self):
        adapter = MagicMock()
        adapter.get_recommended_route.return_value = {}
        router = GatewayRouter(percv_adapter=adapter)
        decision = router.compute_route(GovernanceState.ANALYZE, 2)
        assert decision.route == GatewayRoute.STANDARD
        assert decision.confidence == 0.8


class TestConstants:
    """Test module constants."""

    def test_state_route_preferences_completeness(self):
        for state in GovernanceState:
            assert state in STATE_ROUTE_PREFERENCES

    def test_entropy_route_map_completeness(self):
        for entropy in range(5):
            assert entropy in ENTROPY_ROUTE_MAP