from __future__ import annotations

from maref.recursive.trust_engine_v2 import (
    AgentProfileV2,
    GoodhartDetection,
    TrustEngineV2,
    TrustFactor,
    TrustScoreV2,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestTrustFactor:
    def test_create(self) -> None:
        f = TrustFactor("test_factor", 0.7, 0.15)
        assert f.name == "test_factor"
        assert f.value == 0.7
        assert f.weight == 0.15

    def test_normalized(self) -> None:
        f = TrustFactor("f", 0.8, 0.15)
        f.normalized = f.value * f.weight * 100.0
        assert f.normalized == 12.0


class TestGoodhartDetection:
    def test_no_detection(self) -> None:
        g = GoodhartDetection(is_detected=False)
        assert g.is_detected is False
        assert g.severity == "none"

    def test_with_detection(self) -> None:
        g = GoodhartDetection(
            is_detected=True,
            suspicious_factors=["compliance"],
            severity="warning",
        )
        assert g.is_detected is True
        assert g.severity == "warning"
        assert "compliance" in g.suspicious_factors


class TestTrustScoreV2:
    def test_compute_tier_AAA(self) -> None:
        score = TrustScoreV2(agent_id="a1", overall_trust=92.0)
        score.finalize()
        assert score.trust_tier == "AAA"

    def test_compute_tier_A(self) -> None:
        score = TrustScoreV2(agent_id="a2", overall_trust=82.0)
        score.finalize()
        assert score.trust_tier == "A"

    def test_compute_tier_B(self) -> None:
        score = TrustScoreV2(agent_id="a3", overall_trust=55.0)
        score.finalize()
        assert score.trust_tier == "B"

    def test_compute_tier_D(self) -> None:
        score = TrustScoreV2(agent_id="a4", overall_trust=35.0)
        score.finalize()
        assert score.trust_tier == "D"

    def test_confidence_interval(self) -> None:
        score = TrustScoreV2(agent_id="a5", overall_trust=80.0)
        score.finalize()
        ci_low, ci_high = score.confidence_interval
        assert ci_low < 80.0 < ci_high


class TestAgentProfileV2:
    def test_create(self) -> None:
        p = AgentProfileV2(agent_id="a1", framework="autogen")
        assert p.agent_id == "a1"
        assert p.compliance_violations == 0


class TestTrustEngineV2:
    def setup_method(self) -> None:
        self.engine = TrustEngineV2()

    def test_register_agent(self) -> None:
        profile = self.engine.register_agent("agent_1", "autogen")
        assert profile.agent_id == "agent_1"
        assert self.engine.agent_count == 1

    def test_assess_no_tasks(self) -> None:
        self.engine.register_agent("no_tasks", "dify")
        score = self.engine.assess("no_tasks")
        assert score is not None
        assert 0.0 <= score.overall_trust <= 100.0

    def test_assess_with_tasks(self) -> None:
        self.engine.register_agent("busy_agent", "autogen")
        for i in range(20):
            self.engine.record_task(
                "busy_agent",
                f"task_{i}",
                success=i < 18,
                quality=0.9 if i < 18 else 0.3,
                latency_ms=200.0,
            )
        score = self.engine.assess("busy_agent")
        assert score is not None
        assert score.overall_trust >= 70.0

    def test_assess_nonexistent(self) -> None:
        assert self.engine.assess("ghost") is None

    def test_get_score(self) -> None:
        self.engine.register_agent("scored")
        self.engine.assess("scored")
        assert self.engine.get_score("scored") is not None

    def test_compare_agents(self) -> None:
        self.engine.register_agent("a")
        self.engine.register_agent("b")
        self.engine.assess("a")
        self.engine.assess("b")
        result = self.engine.compare("a", "b")
        assert "agent_a" in result
        assert "agent_b" in result

    def test_list_by_tier(self) -> None:
        self.engine.register_agent("top")
        self.engine.record_task("top", "t1", success=True, quality=1.0)
        self.engine.assess("top")
        result = self.engine.list_by_tier("ALL")
        assert len(result) >= 1

    def test_get_statistics(self) -> None:
        self.engine.register_agent("s1")
        self.engine.assess("s1")
        stats = self.engine.get_statistics()
        assert stats["total_agents"] == 1

    def test_update_compliance(self) -> None:
        self.engine.register_agent("bad_agent", compliance_violations=0)
        self.engine.update_compliance("bad_agent", 3)
        score = self.engine.assess("bad_agent")
        assert score is not None
        assert score.overall_trust < 80.0

    def test_add_peer_rating(self) -> None:
        self.engine.register_agent("peer")
        self.engine.add_peer_rating("peer", "rater1", 0.9)
        self.engine.add_peer_rating("peer", "rater2", 0.8)
        score = self.engine.assess("peer")
        assert score is not None

    def test_goodhart_detection(self) -> None:
        self.engine.register_agent("too_perfect")
        for i in range(20):
            self.engine.record_task(
                "too_perfect",
                f"t_{i}",
                success=True,
                quality=1.0,
                latency_ms=50.0,
            )
        score = self.engine.assess("too_perfect")
        assert score is not None
        assert score.goodhart is not None

    def test_temporal_decay(self) -> None:
        self.engine.register_agent("inactive")
        import time

        profile = self.engine._profiles["inactive"]
        profile.last_active_at = time.time() - 86400 * 30
        score = self.engine.assess("inactive")
        assert score is not None
        assert score.temporal_decay_factor < 1.0

    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        engine = TrustEngineV2(audit_store=audit)
        engine.register_agent("audited")
        engine.assess("audited")
        assert audit.count() >= 1

    def test_clear(self) -> None:
        self.engine.register_agent("temp")
        self.engine.clear()
        assert self.engine.agent_count == 0
