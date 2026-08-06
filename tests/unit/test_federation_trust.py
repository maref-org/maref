"""Unit tests for FederatedTrustEngine."""

from __future__ import annotations

import time

import pytest

from maref.federation.trust import (
    DEFAULT_LOCAL_WEIGHT,
    DEFAULT_TRUST_FRESHNESS,
    FederatedTrustEngine,
    FederatedTrustScore,
    PeerTrustReport,
)
from maref.recursive.trust_engine_v2 import TrustEngineV2


@pytest.fixture
def local_engine() -> TrustEngineV2:
    return TrustEngineV2()


@pytest.fixture
def fed_engine(local_engine: TrustEngineV2) -> FederatedTrustEngine:
    return FederatedTrustEngine(local_engine=local_engine)


class TestPeerTrustReport:
    def test_freshness_one_for_current_report(self) -> None:
        report = PeerTrustReport(
            agent_id="a1", source_server="s1", trust_score=80.0
        )
        assert abs(report.freshness() - 1.0) < 0.01

    def test_freshness_decays_with_age(self) -> None:
        now = time.time()
        old_report = PeerTrustReport(
            agent_id="a1",
            source_server="s1",
            trust_score=80.0,
            timestamp=now - DEFAULT_TRUST_FRESHNESS,  # 1 hour old
        )
        freshness = old_report.freshness(now)
        # exp(-1) ≈ 0.368
        assert 0.30 < freshness < 0.40

    def test_to_dict(self) -> None:
        r = PeerTrustReport(agent_id="a", source_server="s", trust_score=50.0, tier="BB")
        d = r.to_dict()
        assert d["agent_id"] == "a"
        assert d["trust_score"] == 50.0
        assert d["tier"] == "BB"


class TestFederatedTrustLocalOnly:
    def test_assess_local_only_returns_local_score(
        self, fed_engine: FederatedTrustEngine, local_engine: TrustEngineV2
    ) -> None:
        local_engine.register_agent("agent-1")
        local_score = local_engine.assess("agent-1")
        assert local_score is not None

        fed_score = fed_engine.assess("agent-1")
        assert fed_score.local_score == local_score.overall_trust
        assert fed_score.federated_score is None
        # No peer reports → effective == local, confidence == 1.0.
        assert fed_score.effective_score == local_score.overall_trust
        assert fed_score.confidence == 1.0


class TestFederatedTrustFederatedOnly:
    def test_assess_federated_only_when_no_local(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        report = PeerTrustReport(
            agent_id="agent-2",
            source_server="peer-srv",
            trust_score=75.0,
            confidence=1.0,
        )
        fed_engine.submit_peer_report(report)

        score = fed_engine.assess("agent-2")
        assert score.local_score is None
        assert score.federated_score is not None
        # One fresh report with confidence 1.0 → aggregate == report score.
        assert abs(score.federated_score - 75.0) < 0.5
        # No local → effective == federated.
        assert abs(score.effective_score - 75.0) < 0.5

    def test_assess_no_data_returns_zero(self, fed_engine: FederatedTrustEngine) -> None:
        score = fed_engine.assess("unknown-agent")
        assert score.local_score is None
        assert score.federated_score is None
        assert score.effective_score == 0.0
        assert score.confidence == 0.0


class TestFederatedTrustCombined:
    def test_combined_score_uses_weighted_formula(
        self,
        fed_engine: FederatedTrustEngine,
        local_engine: TrustEngineV2,
    ) -> None:
        # Establish local score.
        local_engine.register_agent("agent-3")
        local_engine.assess("agent-3")
        local_value = local_engine.get_score("agent-3").overall_trust

        # Submit a peer report.
        peer_score = 90.0
        report = PeerTrustReport(
            agent_id="agent-3",
            source_server="peer",
            trust_score=peer_score,
            confidence=1.0,
        )
        fed_engine.submit_peer_report(report)

        score = fed_engine.assess("agent-3")
        alpha = DEFAULT_LOCAL_WEIGHT
        expected = alpha * local_value + (1.0 - alpha) * peer_score
        assert abs(score.effective_score - expected) < 1.0
        assert score.local_score == local_value
        assert score.federated_score is not None

    def test_combined_confidence_blends_local_and_federated(
        self,
        fed_engine: FederatedTrustEngine,
        local_engine: TrustEngineV2,
    ) -> None:
        local_engine.register_agent("agent-c")
        local_engine.assess("agent-c")
        fed_engine.submit_peer_report(
            PeerTrustReport(
                agent_id="agent-c",
                source_server="s",
                trust_score=80.0,
                confidence=1.0,
            )
        )
        score = fed_engine.assess("agent-c")
        # alpha * 1.0 + (1 - alpha) * federated_confidence
        # federated_confidence for 1 report = avg_confidence(1.0) * coverage(0.2) = 0.2
        alpha = DEFAULT_LOCAL_WEIGHT
        expected_conf = alpha * 1.0 + (1.0 - alpha) * 0.2
        assert abs(score.confidence - expected_conf) < 0.05


class TestPeerReportManagement:
    def test_submit_replaces_same_source(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        agent = "agent-r"
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id=agent, source_server="s1", trust_score=50.0)
        )
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id=agent, source_server="s1", trust_score=80.0)
        )
        reports = fed_engine.get_peer_reports(agent)
        assert len(reports) == 1
        assert reports[0].trust_score == 80.0

    def test_submit_multiple_sources(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        agent = "agent-m"
        for src, score in [("s1", 60.0), ("s2", 70.0), ("s3", 80.0)]:
            fed_engine.submit_peer_report(
                PeerTrustReport(agent_id=agent, source_server=src, trust_score=score)
            )
        reports = fed_engine.get_peer_reports(agent)
        assert len(reports) == 3
        sources = {r.source_server for r in reports}
        assert sources == {"s1", "s2", "s3"}

    def test_submit_caps_at_ten_reports(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        agent = "agent-cap"
        for i in range(15):
            fed_engine.submit_peer_report(
                PeerTrustReport(
                    agent_id=agent,
                    source_server=f"s{i}",
                    trust_score=float(i),
                    timestamp=time.time() + i,  # increasing timestamps
                )
            )
        reports = fed_engine.get_peer_reports(agent)
        assert len(reports) == 10

    def test_clear_peer_reports_single_agent(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="a1", source_server="s", trust_score=50.0)
        )
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="a2", source_server="s", trust_score=60.0)
        )
        cleared = fed_engine.clear_peer_reports("a1")
        assert cleared == 1
        assert fed_engine.get_peer_reports("a1") == []
        assert len(fed_engine.get_peer_reports("a2")) == 1

    def test_clear_peer_reports_all(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        for agent in ("a1", "a2"):
            fed_engine.submit_peer_report(
                PeerTrustReport(agent_id=agent, source_server="s", trust_score=50.0)
            )
        cleared = fed_engine.clear_peer_reports()
        assert cleared == 2
        assert fed_engine.list_agents_with_peer_reports() == []


class TestFederatedTrustConfig:
    def test_local_weight_clamped_to_range(self, local_engine: TrustEngineV2) -> None:
        high = FederatedTrustEngine(local_engine=local_engine, local_weight=2.0)
        low = FederatedTrustEngine(local_engine=local_engine, local_weight=-1.0)
        assert high.local_weight == 1.0
        assert low.local_weight == 0.0

    def test_min_peer_reports_threshold(self, local_engine: TrustEngineV2) -> None:
        engine = FederatedTrustEngine(
            local_engine=local_engine, min_peer_reports=3
        )
        # Submit only 1 report — below threshold.
        engine.submit_peer_report(
            PeerTrustReport(agent_id="a", source_server="s", trust_score=80.0)
        )
        score = engine.assess("a")
        # Below threshold → federated_score is None, no local → effective 0.
        assert score.federated_score is None
        assert score.effective_score == 0.0

    def test_get_score_returns_last_computed(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        assert fed_engine.get_score("a") is None
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="a", source_server="s", trust_score=80.0)
        )
        fed_engine.assess("a")
        cached = fed_engine.get_score("a")
        assert cached is not None
        assert cached.agent_id == "a"

    def test_list_agents_with_peer_reports(
        self, fed_engine: FederatedTrustEngine
    ) -> None:
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="x", source_server="s", trust_score=50.0)
        )
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="y", source_server="s", trust_score=60.0)
        )
        agents = set(fed_engine.list_agents_with_peer_reports())
        assert agents == {"x", "y"}


class TestFederatedTrustSummary:
    def test_federated_summary(
        self, fed_engine: FederatedTrustEngine, local_engine: TrustEngineV2
    ) -> None:
        local_engine.register_agent("local-1")
        fed_engine.submit_peer_report(
            PeerTrustReport(agent_id="peer-1", source_server="s", trust_score=70.0)
        )
        summary = fed_engine.federated_summary()
        assert summary["local_agent_count"] == 1
        assert summary["agents_with_peer_reports"] == 1
        assert summary["total_peer_reports"] == 1
        assert summary["local_weight"] == DEFAULT_LOCAL_WEIGHT
        assert summary["min_peer_reports"] == 1
        assert summary["trust_freshness"] == DEFAULT_TRUST_FRESHNESS
