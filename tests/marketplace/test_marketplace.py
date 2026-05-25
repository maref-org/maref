"""Tests for Skill Marketplace layer."""

import time

import pytest

from maref.marketplace.registry import (
    SkillManifest,
    SkillRegistry,
    SkillStatus,
    SkillValidationResult,
)
from maref.marketplace.reputation import (
    ReputationRecord,
    ReputationTracker,
)
from maref.marketplace.semantic_matcher import (
    MatchScore,
    SemanticMatcher,
)
from maref.marketplace.version_negotiator import (
    Compatibility,
    VersionNegotiator,
)


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        m = SkillManifest(name="csv_parser", version="1.0.0", description="Parse CSV files")
        result = reg.register(m)
        assert result.skill_id == m.skill_id
        assert reg.get(m.skill_id) == m
        assert reg.get_status(m.skill_id) == SkillStatus.PENDING

    def test_static_scan_pass(self):
        reg = SkillRegistry()
        m = SkillManifest(name="safe_skill", version="1.0.0", description="Safe", entrypoint="safe_module.run")
        reg.register(m)
        result = reg.run_static_scan(m.skill_id)
        assert result.static_scan_passed is True
        assert reg.get_status(m.skill_id) == SkillStatus.STATIC_SCAN

    def test_static_scan_fail(self):
        reg = SkillRegistry()
        m = SkillManifest(name="unsafe", version="1.0.0", description="Unsafe", entrypoint="eval(bad_code)")
        reg.register(m)
        result = reg.run_static_scan(m.skill_id)
        assert result.static_scan_passed is False
        assert "eval(" in str(result.errors)

    def test_sandbox_test(self):
        reg = SkillRegistry()
        m = SkillManifest(
            name="tested", version="1.0.0", description="Tested",
            test_cases=[{"input": "a", "expected": "b"}],
        )
        reg.register(m)
        result = reg.run_sandbox_test(m.skill_id)
        assert result.sandbox_test_passed is True

    def test_approve_requires_gates(self):
        reg = SkillRegistry()
        m = SkillManifest(name="approve_me", version="1.0.0", description="Approve")
        reg.register(m)
        with pytest.raises(ValueError, match="failed static scan"):
            reg.approve(m.skill_id)
        reg.run_static_scan(m.skill_id)
        with pytest.raises(ValueError, match="failed sandbox test"):
            reg.approve(m.skill_id)
        reg.run_sandbox_test(m.skill_id)
        reg.approve(m.skill_id)
        assert reg.get_status(m.skill_id) == SkillStatus.APPROVED

    def test_search_approved_only(self):
        reg = SkillRegistry()
        m1 = SkillManifest(name="data_viz", version="1.0.0", description="Visualize data")
        m2 = SkillManifest(name="other", version="1.0.0", description="Other")
        reg.register(m1)
        reg.register(m2)
        # Only approve m1
        reg.run_static_scan(m1.skill_id)
        reg.run_sandbox_test(m1.skill_id)
        reg.approve(m1.skill_id)
        results = reg.search(["visualize"])
        assert len(results) == 1
        assert results[0].name == "data_viz"

    def test_dependency_graph(self):
        reg = SkillRegistry()
        base = SkillManifest(name="base", version="1.0.0", description="Base")
        derived = SkillManifest(
            name="derived", version="1.0.0", description="Derived",
            dependencies=["skill://base@1.0.0"],
        )
        reg.register(base)
        reg.register(derived)
        downstream = reg.get_downstream("base")
        assert derived.skill_id in downstream

    def test_check_dependency_conflicts(self):
        reg = SkillRegistry()
        m = SkillManifest(
            name="needs_base", version="1.0.0", description="Needs base",
            dependencies=["skill://missing@1.0.0"],
        )
        reg.register(m)
        conflicts = reg.check_dependency_conflicts(m.skill_id)
        assert len(conflicts) == 1
        assert "Missing dependency" in conflicts[0]

    def test_deprecate_and_freeze(self):
        reg = SkillRegistry()
        m = SkillManifest(name="old", version="1.0.0", description="Old")
        reg.register(m)
        reg.deprecate(m.skill_id)
        assert reg.get_status(m.skill_id) == SkillStatus.DEPRECATED
        reg.freeze(m.skill_id)
        assert reg.get_status(m.skill_id) == SkillStatus.FROZEN


class TestSemanticMatcher:
    def test_match_relevance(self):
        matcher = SemanticMatcher()
        skills = [
            SkillManifest(name="csv_parser", version="1.0.0", description="Parse CSV files"),
            SkillManifest(name="chart_maker", version="1.0.0", description="Make charts from data"),
        ]
        scores = matcher.match("make a chart from csv", skills)
        assert len(scores) == 2
        # chart_maker should score higher for "chart"
        assert scores[0].skill_id == skills[1].skill_id

    def test_match_with_reputation_and_cost(self):
        matcher = SemanticMatcher()
        skills = [
            SkillManifest(name="a", version="1.0.0", description="Do thing"),
            SkillManifest(name="b", version="1.0.0", description="Do thing"),
        ]
        rep = {skills[0].skill_id: 0.9, skills[1].skill_id: 0.5}
        costs = {skills[0].skill_id: 0.5, skills[1].skill_id: 0.0}
        scores = matcher.match("do thing", skills, reputation_map=rep, cost_map=costs)
        # a has higher reputation but higher cost
        assert scores[0].reputation == 0.9
        assert scores[0].cost == 0.5

    def test_match_multi_skill(self):
        matcher = SemanticMatcher()
        skills = [
            SkillManifest(name="data_clean", version="1.0.0", description="Clean data"),
            SkillManifest(name="visualize", version="1.0.0", description="Visualize data"),
        ]
        results = matcher.match_multi_skill("clean data and visualize", skills)
        assert len(results) == 2


class TestVersionNegotiator:
    def test_exact_match(self):
        vn = VersionNegotiator()
        result = vn.negotiate("s1", "1.0.0", "1.0.0")
        assert result.compatibility == Compatibility.COMPATIBLE

    def test_backward_compatible_minor(self):
        vn = VersionNegotiator()
        result = vn.negotiate("s1", "1.0.0", "1.1.0")
        assert result.compatibility == Compatibility.BACKWARD_COMPATIBLE

    def test_major_bump_incompatible(self):
        vn = VersionNegotiator()
        result = vn.negotiate("s1", "1.0.0", "2.0.0")
        assert result.compatibility == Compatibility.INCOMPATIBLE

    def test_major_bump_grace_period(self):
        vn = VersionNegotiator()
        vn.register_version("s1", "1.0.0", time.time())
        result = vn.negotiate("s1", "1.0.0", "2.0.0")
        assert result.compatibility == Compatibility.BACKWARD_COMPATIBLE
        assert result.adapter_needed is True

    def test_requested_newer_than_available(self):
        vn = VersionNegotiator()
        result = vn.negotiate("s1", "2.0.0", "1.0.0")
        assert result.compatibility == Compatibility.INCOMPATIBLE


class TestReputationTracker:
    def test_record_and_score(self):
        rt = ReputationTracker()
        rt.record(ReputationRecord("s1", "agent-a", success=True, latency_ms=100))
        rt.record(ReputationRecord("s1", "agent-a", success=True, latency_ms=120))
        score = rt.get_score("s1")
        assert score > 0.8

    def test_failure_lowers_score(self):
        rt = ReputationTracker()
        rt.record(ReputationRecord("s1", "agent-a", success=True))
        rt.record(ReputationRecord("s1", "agent-a", success=False))
        score = rt.get_score("s1")
        assert score < 1.0

    def test_security_penalty(self):
        rt = ReputationTracker()
        rt.record(ReputationRecord("s1", "agent-a", success=True, notes="security violation"))
        score = rt.get_score("s1")
        assert score <= 0.9

    def test_frozen_skill_zero_score(self):
        rt = ReputationTracker()
        rt.record(ReputationRecord("s1", "agent-a", success=True))
        rt.freeze_skill("s1")
        assert rt.get_score("s1") == 0.0
        assert rt.is_frozen("s1")

    def test_abnormal_detection(self):
        rt = ReputationTracker()
        now = time.time()
        for _ in range(12):
            rt.record(ReputationRecord("s1", "agent-a", success=True, timestamp=now))
        assert rt.is_abnormal("s1", "agent-a")

    def test_stats(self):
        rt = ReputationTracker()
        rt.record(ReputationRecord("s1", "agent-a", success=True, latency_ms=100))
        rt.record(ReputationRecord("s1", "agent-b", success=False, latency_ms=200))
        stats = rt.get_stats("s1")
        assert stats["total_calls"] == 2
        assert stats["success_rate"] == 0.5
