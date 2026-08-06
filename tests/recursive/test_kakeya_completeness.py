"""Tests for Kakeya completeness checker (task ③).

Inspired by Wang Hong's 3D Kakeya conjecture:
verifies that the 9-factor trust space covers all
canonical attack directions.
"""

from __future__ import annotations

from maref.recursive.kakeya_completeness import (
    AttackDirection,
    BlindSpot,
    CompletenessReport,
    KakeyaCompletenessChecker,
)
from maref.recursive.trust_engine_v2 import TrustFactor, TrustScoreV2


FULL_FACTORS = [
    TrustFactor("task_completion", 0.9, 0.15),
    TrustFactor("response_quality", 0.85, 0.15),
    TrustFactor("latency_performance", 0.7, 0.10),
    TrustFactor("error_rate", 0.8, 0.10),
    TrustFactor("compliance_adherence", 0.9, 0.15),
    TrustFactor("behavioral_consistency", 0.75, 0.10),
    TrustFactor("peer_reputation", 0.7, 0.10),
    TrustFactor("temporal_stability", 0.8, 0.10),
    TrustFactor("cooperation_score", 0.6, 0.05),
]

ZERO_FACTORS = [
    TrustFactor(n, 0.0, w) for n, w in [
        ("task_completion", 0.15),
        ("response_quality", 0.15),
        ("latency_performance", 0.10),
        ("error_rate", 0.10),
        ("compliance_adherence", 0.15),
        ("behavioral_consistency", 0.10),
        ("peer_reputation", 0.10),
        ("temporal_stability", 0.10),
        ("cooperation_score", 0.05),
    ]
]


class TestAttackDirection:
    def test_normalization(self) -> None:
        d = AttackDirection("test", "desc", [0.7, 0.7, 0, 0, 0, 0, 0, 0, 0], ["a", "b"])
        norm = sum(v * v for v in d.vector) ** 0.5
        assert abs(norm - 1.0) < 0.001, f"not unit: {norm}"

    def test_zero_vector_not_normalized(self) -> None:
        d = AttackDirection("zero", "all zero", [0.0] * 9, [])
        assert d.vector == [0.0] * 9

    def test_wrong_dimension_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="9D"):
            AttackDirection("bad", "", [1.0, 0.0], [])

    def test_duplicate_name_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="already exists"):
            checker = KakeyaCompletenessChecker()
            checker.add_direction(checker.CANONICAL_ATTACK_VECTORS[0])


class TestKakeyaCompletenessChecker:
    def test_full_coverage(self) -> None:
        score = TrustScoreV2("full", 78.0, factors=FULL_FACTORS)
        score.finalize()
        report = KakeyaCompletenessChecker().check(score)
        assert report.is_complete
        assert report.effective_dimension >= report.target_dimension * 0.8
        assert len(report.blind_spots) == 0

    def test_zero_factors_all_blind(self) -> None:
        score = TrustScoreV2("blind", 5.0, factors=ZERO_FACTORS)
        score.finalize()
        checker = KakeyaCompletenessChecker()
        report = checker.check(score)
        assert not report.is_complete
        assert len(report.blind_spots) >= len(checker.directions) - 2

    def test_single_factor_dominance_reveals_blind_spots(self) -> None:
        dom_factors = [
            TrustFactor("task_completion", 1.0, 0.15),
            TrustFactor("response_quality", 0.01, 0.15),
            TrustFactor("latency_performance", 0.01, 0.10),
            TrustFactor("error_rate", 0.01, 0.10),
            TrustFactor("compliance_adherence", 0.01, 0.15),
            TrustFactor("behavioral_consistency", 0.01, 0.10),
            TrustFactor("peer_reputation", 0.01, 0.10),
            TrustFactor("temporal_stability", 0.01, 0.10),
            TrustFactor("cooperation_score", 0.01, 0.05),
        ]
        score = TrustScoreV2("dom", 50.0, factors=dom_factors)
        score.finalize()
        report = KakeyaCompletenessChecker().check(score)
        assert not report.is_complete
        assert len(report.blind_spots) >= 2

    def test_completeness_report_to_dict(self) -> None:
        spot = BlindSpot("test_dir", 0.005, "warning", "add monitoring")
        report = CompletenessReport(
            effective_dimension=5.0,
            target_dimension=7,
            is_complete=False,
            blind_spots=[spot],
            factor_coverage={"test": 0.5},
        )
        d = report.to_dict()
        assert d["effective_dimension"] == 5.0
        assert d["is_complete"] is False
        assert len(d["blind_spots"]) == 1
        assert d["blind_spots"][0]["direction"] == "test_dir"

    def test_custom_direction(self) -> None:
        checker = KakeyaCompletenessChecker()
        custom = AttackDirection(
            "custom_attack", "testing custom direction",
            [0.5, 0, 0, 0, 0, 0.5, 0, 0, 0],
            ["task_completion", "behavioral_consistency"],
        )
        checker.add_direction(custom)
        dirs = checker.directions
        names = [d.name for d in dirs]
        assert "custom_attack" in names

    def test_assess_and_check_standalone(self) -> None:
        from maref.recursive.kakeya_completeness import assess_and_check
        from maref.recursive.trust_engine_v2 import TrustEngineV2
        from maref.recursive.unified_audit import UnifiedAuditStore

        engine = TrustEngineV2(audit_store=UnifiedAuditStore())
        engine.register_agent("test-agent")
        checker = KakeyaCompletenessChecker()

        score, report = assess_and_check(engine, "test-agent", checker)
        assert score is not None
        assert report is not None
        assert isinstance(report.effective_dimension, float)

    def test_assess_and_check_no_checker(self) -> None:
        from maref.recursive.kakeya_completeness import assess_and_check
        from maref.recursive.trust_engine_v2 import TrustEngineV2
        from maref.recursive.unified_audit import UnifiedAuditStore

        engine = TrustEngineV2(audit_store=UnifiedAuditStore())
        engine.register_agent("test-agent")

        score, report = assess_and_check(engine, "test-agent", None)
        assert score is not None
        assert report is None
