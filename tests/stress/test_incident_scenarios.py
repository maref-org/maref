"""ScenarioLibrary 单元测试 — 事故复现场景库 (chaos/)."""

from __future__ import annotations

import pytest

from maref.stress.chaos_engine import FaultType
from maref.stress.incident_scenarios import (
    Control,
    IncidentScenario,
    ScenarioLibrary,
    to_chaos_faults,
)


@pytest.fixture
def library() -> ScenarioLibrary:
    return ScenarioLibrary()


class TestCatalog:
    def test_catalog_populated(self, library: ScenarioLibrary) -> None:
        assert library.count >= 8

    def test_get_known_scenario(self, library: ScenarioLibrary) -> None:
        scenario = library.get("egress-jfrog-zero-day")
        assert scenario is not None
        assert scenario.severity == "critical"

    def test_get_unknown_returns_none(self, library: ScenarioLibrary) -> None:
        assert library.get("does-not-exist") is None

    def test_by_control(self, library: ScenarioLibrary) -> None:
        ids = {s.scenario_id for s in library.by_control(Control.CREDENTIAL_BROKER)}
        assert "egress-jfrog-zero-day" in ids
        assert "dns-tunnel-escape" in ids

    def test_by_owasp(self, library: ScenarioLibrary) -> None:
        ids = {s.scenario_id for s in library.by_owasp("ASI07")}
        assert "swarm-message-board" in ids
        assert "unicode-stego-exfil" in ids

    def test_serialization(self, library: ScenarioLibrary) -> None:
        scenario = library.get("swarm-message-board")
        assert scenario is not None
        payload = scenario.to_dict()
        assert "p2_11_a2a_semantic_guard" in payload["target_controls"]
        assert payload["fault_types"] == ["byzantine"]


class TestEvaluation:
    def test_fully_covered_is_mitigated(self, library: ScenarioLibrary) -> None:
        scenario = library.get("egress-jfrog-zero-day")
        assert scenario is not None
        active = set(scenario.target_controls)
        result = library.evaluate(scenario, active)
        assert result.mitigated is True
        assert result.gaps == []
        assert result.coverage_ratio == 1.0

    def test_partial_coverage_leaves_gaps(self, library: ScenarioLibrary) -> None:
        result = library.evaluate(
            "credential-harvest-lateral-move",
            {Control.CREDENTIAL_BROKER},
        )
        assert result.mitigated is False
        assert Control.PRINCIPAL_IDENTITY in result.gaps
        assert 0.0 < result.coverage_ratio < 1.0

    def test_unknown_scenario_raises(self, library: ScenarioLibrary) -> None:
        with pytest.raises(KeyError):
            library.evaluate("nope", set())

    def test_coverage_report(self, library: ScenarioLibrary) -> None:
        report = library.coverage_report(set(Control))
        assert report["total"] == library.count
        assert report["mitigated"] == library.count
        assert report["exposed"] == 0


class TestChaosMapping:
    def test_network_scenario_maps_to_network_fault(self, library: ScenarioLibrary) -> None:
        scenario = library.get("dns-tunnel-escape")
        assert scenario is not None
        assert to_chaos_faults(scenario) == [FaultType.NETWORK]

    def test_scenario_without_faults(self, library: ScenarioLibrary) -> None:
        scenario = library.get("identity-hallucination-integrity-leak")
        assert scenario is not None
        assert to_chaos_faults(scenario) == []

    def test_custom_library(self) -> None:
        scenario = IncidentScenario(
            scenario_id="custom",
            name="custom",
            source="test",
            description="d",
            attack_steps=["a"],
            target_controls=[Control.SSR_METRICS],
        )
        library = ScenarioLibrary([scenario])
        assert library.count == 1
        assert library.evaluate("custom", {Control.SSR_METRICS}).mitigated is True
