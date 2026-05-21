from __future__ import annotations

from maref.recursive.federation import (
    FederationCoordinator,
    FederationReport,
    FrameworkType,
)


class TestFederationCoordinator:
    def test_register_single_agent(self) -> None:
        fc = FederationCoordinator()
        agent = fc.register("a1", FrameworkType.AUTOGEN,
                             role="analyzer")
        assert agent.agent_id == "a1"
        assert agent.framework == FrameworkType.AUTOGEN
        assert fc.agent_count() == 1

    def test_register_across_frameworks(self) -> None:
        fc = FederationCoordinator()
        agents = fc.register_across_frameworks({
            "autogen": ["a1", "a2"],
            "dify": ["d1"],
            "coze": ["c1", "c2", "c3"],
        })
        assert len(agents) == 6
        assert fc.agent_count() == 6

    def test_agents_by_framework_filters(self) -> None:
        fc = FederationCoordinator()
        fc.register_across_frameworks({
            "autogen": ["a1"],
            "dify": ["d1", "d2"],
        })
        autogen_agents = fc.agents_by_framework(FrameworkType.AUTOGEN)
        assert len(autogen_agents) == 1

    def test_framework_breakdown(self) -> None:
        fc = FederationCoordinator()
        fc.register_across_frameworks({
            "autogen": ["a1", "a2"],
            "dify": ["d1"],
        })
        breakdown = fc.framework_breakdown()
        assert breakdown["autogen"] == 2
        assert breakdown["dify"] == 1

    def test_cross_framework_trust_comparison(self) -> None:
        fc = FederationCoordinator()
        fc.register_across_frameworks({
            "autogen": ["a1"],
            "dify": ["d1"],
        })
        comparison = fc.cross_framework_trust_comparison()
        assert "autogen" in comparison
        assert "dify" in comparison
        for fw_data in comparison.values():
            assert 0 <= fw_data["avg_trust"] <= 100

    def test_fault_isolation_check(self) -> None:
        fc = FederationCoordinator()
        fc.register_across_frameworks({
            "autogen": ["a1"],
            "dify": ["d1"],
        })
        assert fc.fault_isolation_check(FrameworkType.AUTOGEN) is True

    def test_fault_isolation_no_other_framework(self) -> None:
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        assert fc.fault_isolation_check(FrameworkType.AUTOGEN) is False

    def test_set_agent_status(self) -> None:
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        assert fc.set_agent_status("a1", "CRASHED") is True
        agents = fc.agents_by_framework(FrameworkType.AUTOGEN)
        assert agents[0].status == "CRASHED"

    def test_generate_report(self) -> None:
        fc = FederationCoordinator()
        fc.register_across_frameworks({
            "autogen": ["a1"],
            "dify": ["d1"],
        })
        report = fc.generate_report()
        assert isinstance(report, FederationReport)
        assert report.total_agents == 2
