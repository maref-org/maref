"""TopologyPolicy 单元测试 — 拓扑即策略 (P2-9)."""

from __future__ import annotations

import pytest

from maref.orchestration.topology_policy import (
    ERROR_AMPLIFICATION,
    FLAT_AMPLIFICATION,
    ORCHESTRATOR_VERIFIER_AMPLIFICATION,
    TopologyKind,
    TopologyPolicy,
    preset_roles,
)


class TestAmplification:
    def test_mast_constants(self) -> None:
        assert ERROR_AMPLIFICATION[TopologyKind.FLAT] == 17.2
        assert ERROR_AMPLIFICATION[TopologyKind.ORCHESTRATOR_VERIFIER] == 4.4

    def test_cost_multiplier_normalized(self) -> None:
        policy = TopologyPolicy()
        assert policy.cost_multiplier(TopologyKind.FLAT) == pytest.approx(1.0)
        assert policy.cost_multiplier(TopologyKind.ORCHESTRATOR_VERIFIER) == pytest.approx(
            ORCHESTRATOR_VERIFIER_AMPLIFICATION / FLAT_AMPLIFICATION
        )

    def test_amplification_lookup(self) -> None:
        assert TopologyPolicy().amplification("flat") == FLAT_AMPLIFICATION


class TestSelection:
    def test_single_agent_flat(self) -> None:
        rec = TopologyPolicy().select(risk_level="high", agent_count=1)
        assert rec.topology == TopologyKind.FLAT

    def test_default_orchestrator_verifier(self) -> None:
        rec = TopologyPolicy().select(risk_level="low", agent_count=3, model_count=2)
        assert rec.topology == TopologyKind.ORCHESTRATOR_VERIFIER
        assert "verifier" in rec.roles

    def test_medium_risk_monoculture_escalates(self) -> None:
        rec = TopologyPolicy().select(risk_level="medium", agent_count=3, model_count=1)
        assert rec.topology == TopologyKind.CHALLENGER_INSPECTOR
        assert "challenger" in rec.roles and "inspector" in rec.roles

    def test_high_risk_escalates(self) -> None:
        rec = TopologyPolicy().select(risk_level="critical", agent_count=2, model_count=3)
        assert rec.topology == TopologyKind.CHALLENGER_INSPECTOR

    def test_default_topology_property(self) -> None:
        assert TopologyPolicy().default_topology == TopologyKind.ORCHESTRATOR_VERIFIER

    def test_recommendation_serializable(self) -> None:
        payload = TopologyPolicy().select(risk_level="high", agent_count=2).to_dict()
        assert payload["topology"] == "challenger_inspector"
        assert "cost_multiplier" in payload


class TestPresetRoles:
    def test_flat_roles(self) -> None:
        assert preset_roles("flat") == ["worker"]

    def test_challenger_inspector_roles(self) -> None:
        roles = preset_roles(TopologyKind.CHALLENGER_INSPECTOR)
        assert roles == ["orchestrator", "worker", "challenger", "inspector"]

    def test_unknown_topology_raises(self) -> None:
        with pytest.raises(ValueError):
            preset_roles("nope")
