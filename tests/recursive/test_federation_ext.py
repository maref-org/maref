"""Tests for federation.py — FederationCoordinator, agent registration, reporting."""
from __future__ import annotations

import pytest

from maref.recursive.federation import (
    FederatedAgent,
    FederationCoordinator,
    FrameworkType,
)


class TestFederationCoordinator:
    def test_initial_state(self):
        fc = FederationCoordinator()
        assert fc.agent_count() == 0

    def test_register(self):
        fc = FederationCoordinator()
        agent = fc.register("agent-1", FrameworkType.AUTOGEN, role="worker", trust_score=80.0)
        assert agent.agent_id == "agent-1"
        assert agent.framework == FrameworkType.AUTOGEN
        assert agent.trust_score == 80.0
        assert fc.agent_count() == 1

    def test_register_default_trust(self):
        fc = FederationCoordinator()
        agent = fc.register("agent-1", FrameworkType.DIFY)
        assert agent.trust_score == 50.0

    def test_register_across_frameworks(self):
        fc = FederationCoordinator()
        agents = fc.register_across_frameworks({
            "autogen": ["a1", "a2"],
            "dify": ["b1"],
            "coze": ["c1", "c2"],
        })
        assert len(agents) == 5
        assert fc.agent_count() == 5

    def test_register_across_frameworks_unknown(self):
        fc = FederationCoordinator()
        agents = fc.register_across_frameworks({"unknown_fw": ["x1"]})
        assert agents == []

    def test_agents_by_framework(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        fc.register("a2", FrameworkType.AUTOGEN)
        fc.register("d1", FrameworkType.DIFY)
        assert len(fc.agents_by_framework(FrameworkType.AUTOGEN)) == 2
        assert len(fc.agents_by_framework(FrameworkType.DIFY)) == 1
        assert len(fc.agents_by_framework(FrameworkType.COZE)) == 0

    def test_framework_breakdown(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        fc.register("a2", FrameworkType.AUTOGEN)
        fc.register("d1", FrameworkType.DIFY)
        breakdown = fc.framework_breakdown()
        assert breakdown.get("autogen") == 2
        assert breakdown.get("dify") == 1
        assert breakdown.get("coze", 0) == 0

    def test_cross_framework_trust_comparison(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN, trust_score=60.0)
        fc.register("a2", FrameworkType.AUTOGEN, trust_score=80.0)
        fc.register("d1", FrameworkType.DIFY, trust_score=90.0)
        comparison = fc.cross_framework_trust_comparison()
        assert comparison["autogen"]["avg_trust"] == 70.0
        assert comparison["autogen"]["count"] == 2
        assert comparison["dify"]["avg_trust"] == 90.0

    def test_cross_framework_trust_comparison_empty(self):
        fc = FederationCoordinator()
        assert fc.cross_framework_trust_comparison() == {}

    def test_fault_isolation_check(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        fc.register("d1", FrameworkType.DIFY)
        assert fc.fault_isolation_check(FrameworkType.AUTOGEN) is True
        assert fc.fault_isolation_check(FrameworkType.COZE) is False

    def test_fault_isolation_single_framework(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN)
        assert fc.fault_isolation_check(FrameworkType.AUTOGEN) is False

    def test_set_agent_status(self):
        fc = FederationCoordinator()
        fc.register("agent-1", FrameworkType.AUTOGEN)
        assert fc.set_agent_status("agent-1", "PAUSED") is True
        assert fc._agents["agent-1"].status == "PAUSED"

    def test_set_agent_status_nonexistent(self):
        fc = FederationCoordinator()
        assert fc.set_agent_status("nonexistent", "PAUSED") is False

    def test_generate_report(self):
        fc = FederationCoordinator()
        fc.register("a1", FrameworkType.AUTOGEN, trust_score=70.0)
        fc.register("d1", FrameworkType.DIFY, trust_score=85.0)
        report = fc.generate_report()
        assert report.total_agents == 2
        assert "autogen" in report.framework_stats
        assert "dify" in report.framework_stats
        assert report.trust_comparisons["a1"] == 70.0
