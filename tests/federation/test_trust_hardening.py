"""Phase 3.3 — cross-domain trust hardening.

Covers:
1. **Byzantine-robust aggregation** — weighted median + MAD outlier
   rejection keeps the federated score reliable even when malicious
   peers report extreme values (a plain mean would be skewed).
2. **Sybil defense** — :class:`SybilTrustGuard` source reputation:
   cold start → eligibility threshold → penalty/reward loop.  Fresh
   attacker identities never vote; established sources that turn
   malicious are penalized out.
3. **Attack scenarios** — bad-mouthing (false reports), Sybil flooding,
   and collusion.  Acceptance: with ≥1/3 malicious reporters the trust
   score remains reliable.
"""

from __future__ import annotations

import pytest

from maref.federation.trust import (
    FederatedTrustEngine,
    PeerTrustReport,
)
from maref.federation.trust_hardening import (
    SybilTrustGuard,
    byzantine_robust_aggregate,
)
from maref.recursive.trust_engine_v2 import TrustEngineV2


class _Report:
    """Minimal report-like object for the aggregator component tests."""

    def __init__(self, trust_score: float, weight: float = 1.0) -> None:
        self.trust_score = trust_score
        self.weight = weight


def _weight(report: _Report) -> float:
    return report.weight


# ── Component: byzantine_robust_aggregate ────────────────────────────────


def test_robust_aggregate_rejects_extreme_outliers() -> None:
    reports = [
        _Report(70.0),
        _Report(75.0),
        _Report(80.0),
        _Report(0.0),  # malicious
        _Report(100.0),  # malicious
    ]
    score, survivors, outliers = byzantine_robust_aggregate(reports, _weight)
    # A plain mean would be 65.0; the robust aggregate stays near honest cluster.
    assert 70.0 <= score <= 80.0
    assert {r.trust_score for r in outliers} == {0.0, 100.0}
    assert {r.trust_score for r in survivors} == {70.0, 75.0, 80.0}


def test_robust_aggregate_single_report_is_unchanged() -> None:
    score, survivors, outliers = byzantine_robust_aggregate([_Report(75.0)], _weight)
    assert score == pytest.approx(75.0)
    assert outliers == []
    assert len(survivors) == 1


def test_robust_aggregate_identical_reports_not_discarded() -> None:
    """MAD == 0 must not trigger the outlier cutoff (floor at min_deviation)."""
    reports = [_Report(75.0), _Report(75.0), _Report(75.0)]
    score, survivors, outliers = byzantine_robust_aggregate(reports, _weight)
    assert score == pytest.approx(75.0)
    assert outliers == []


def test_robust_aggregate_respects_weights() -> None:
    """A well-weighted honest cluster outweighs a single low-weight lie."""
    reports = [
        _Report(75.0, weight=1.0),
        _Report(80.0, weight=1.0),
        _Report(0.0, weight=0.1),  # weak source
    ]
    score, _, outliers = byzantine_robust_aggregate(reports, _weight)
    assert score >= 70.0
    assert len(outliers) == 1


def test_robust_aggregate_empty_raises() -> None:
    with pytest.raises(ValueError):
        byzantine_robust_aggregate([], _weight)


# ── Component: SybilTrustGuard source reputation ─────────────────────────


def test_guard_cold_start_and_reward_loop() -> None:
    guard = SybilTrustGuard()
    assert guard.source_trust("peer-1") == pytest.approx(0.3)
    assert guard.is_eligible("peer-1") is False
    # Two rewards lift a source above the eligibility threshold (0.3→0.6→1.0).
    guard.reward_source("peer-1")
    assert guard.is_eligible("peer-1") is True
    guard.reward_source("peer-1")
    assert guard.source_trust("peer-1") == pytest.approx(1.0)
    # Penalty halves reputation but never below the floor.
    guard.penalize_source("peer-1")
    assert guard.source_trust("peer-1") == pytest.approx(0.5)
    for _ in range(10):
        guard.penalize_source("peer-1")
    assert guard.source_trust("peer-1") == pytest.approx(0.05)


# ── Integration: attack scenarios against FederatedTrustEngine ───────────


def _build_engine() -> tuple[FederatedTrustEngine, SybilTrustGuard]:
    guard = SybilTrustGuard()
    engine = FederatedTrustEngine(
        local_engine=TrustEngineV2(),
        sybil_guard=guard,
    )
    return engine, guard


def _report(agent: str, source: str, score: float) -> PeerTrustReport:
    return PeerTrustReport(
        agent_id=agent,
        source_server=source,
        trust_score=score,
        confidence=1.0,
    )


def _elevate(guard: SybilTrustGuard, *sources: str) -> None:
    """Bump sources above the eligibility threshold (cold start → 0.6)."""
    for source in sources:
        guard.reward_source(source)


def test_bad_mouthing_attack_resisted() -> None:
    """False reports (0/100 from established peers) cannot skew the score."""
    engine, guard = _build_engine()
    agent = "agent-good"
    _elevate(guard, "h1", "h2", "h3", "evil-1", "evil-2")
    engine.submit_peer_reports(
        [
            _report(agent, "h1", 70.0),
            _report(agent, "h2", 75.0),
            _report(agent, "h3", 80.0),
            _report(agent, "evil-1", 0.0),  # bad-mouthing
            _report(agent, "evil-2", 100.0),  # good-mouthing
        ]
    )
    score = engine.assess(agent)
    assert score.federated_score is not None
    assert 70.0 <= score.federated_score <= 80.0
    # Malicious sources were flagged and penalized.
    penalized = set(guard.penalized_sources())
    assert "evil-1" in penalized and "evil-2" in penalized
    assert guard.source_trust("evil-1") < 0.5  # dropped below eligibility
    anomaly_sources = {a.source_server for a in guard.anomalies()}
    assert "evil-1" in anomaly_sources and "evil-2" in anomaly_sources


def test_sybil_flood_attack_resisted() -> None:
    """20 fresh identities reporting 0 cannot outvote 3 established peers."""
    engine, guard = _build_engine()
    agent = "agent-sybil"
    _elevate(guard, "h1", "h2", "h3")
    engine.submit_peer_reports(
        [
            _report(agent, "h1", 70.0),
            _report(agent, "h2", 75.0),
            _report(agent, "h3", 80.0),
        ]
    )
    # Sybil swarm: fresh sources (cold start, ineligible) all report 0.
    engine.submit_peer_reports([_report(agent, f"sybil-{i}", 0.0) for i in range(20)])
    score = engine.assess(agent)
    assert score.federated_score is not None
    assert 70.0 <= score.federated_score <= 80.0
    # Only the three established sources cleared the eligibility gate.
    assert guard.summary()["eligible_sources"] == 3
    # The honest reports survived the 10-report window despite the flood.
    assert len(score.peer_reports) == 10
    assert {r.source_server for r in score.peer_reports if r.trust_score > 0} == {
        "h1",
        "h2",
        "h3",
    }


def test_collusion_attack_resisted() -> None:
    """Colluding fresh sources are excluded; elevated colluders are trimmed."""
    engine, guard = _build_engine()
    agent = "agent-collude"
    _elevate(guard, "h1", "h2", "h3")
    engine.submit_peer_reports(
        [
            _report(agent, "h1", 70.0),
            _report(agent, "h2", 75.0),
            _report(agent, "h3", 80.0),
        ]
    )
    # Phase 1: cold-start colluders — filtered by the eligibility gate.
    engine.submit_peer_reports([_report(agent, f"collude-{i}", 0.0) for i in range(3)])
    score = engine.assess(agent)
    assert 70.0 <= score.federated_score <= 80.0

    # Phase 2: colluders fake a bit of reputation, then lie together.
    # Honest sources carry *deeper* reputation (elevated twice → weight 1.0)
    # than the colluders (elevated once → weight 0.6), so the weighted
    # median lands on the honest cluster and the unanimous 0s are trimmed.
    _elevate(guard, "collude-0", "collude-1", "collude-2")
    _elevate(guard, "h1", "h2", "h3")
    score = engine.assess(agent)
    assert 70.0 <= score.federated_score <= 80.0
    assert "collude-0" in set(guard.penalized_sources())


def test_acceptance_one_third_malicious_still_reliable() -> None:
    """Acceptance: with ≥1/3 malicious reporters the score stays reliable."""
    engine, guard = _build_engine()
    agent = "agent-bft"
    _elevate(guard, "h1", "h2", "h3", "m1", "m2")
    engine.submit_peer_reports(
        [
            _report(agent, "h1", 70.0),
            _report(agent, "h2", 75.0),
            _report(agent, "h3", 80.0),
            _report(agent, "m1", 0.0),
            _report(agent, "m2", 100.0),
        ]
    )
    score = engine.assess(agent)
    assert score.federated_score is not None
    # 2 of 5 reporters (40% ≥ 1/3) are malicious — the score must stay
    # within the honest band, far from the attacker-intended extremes.
    assert 70.0 <= score.federated_score <= 80.0
    assert abs(score.federated_score - 75.0) <= 5.0


def test_default_engine_single_report_unchanged() -> None:
    """Default config (no guard) keeps the classic single-report behavior."""
    engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    engine.submit_peer_report(_report("agent-x", "peer", 75.0))
    score = engine.assess("agent-x")
    assert score.federated_score == pytest.approx(75.0, abs=0.5)
    assert score.confidence == pytest.approx(0.2, abs=0.05)


def test_weighted_fallback_mode_still_available() -> None:
    """robust_aggregation=False restores the plain weighted mean."""
    engine = FederatedTrustEngine(
        local_engine=TrustEngineV2(),
        robust_aggregation=False,
    )
    agent = "agent-fallback"
    engine.submit_peer_reports(
        [
            _report(agent, "s1", 75.0),
            _report(agent, "s2", 75.0),
            _report(agent, "s3", 0.0),  # skews a plain mean
        ]
    )
    score = engine.assess(agent)
    assert score.federated_score is not None
    assert abs(score.federated_score - 50.0) < 0.5  # (75+75+0)/3


def test_summary_exposes_hardening_state() -> None:
    engine, guard = _build_engine()
    engine.submit_peer_report(_report("a", "peer-1", 80.0))
    summary = engine.federated_summary()
    assert summary["robust_aggregation"] is True
    assert summary["sybil_guard_enabled"] is True
    assert summary["sybil_guard"]["sources_tracked"] == 1
    assert summary["sybil_guard"]["eligible_sources"] == 0  # cold start
