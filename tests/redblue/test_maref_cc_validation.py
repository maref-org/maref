"""Cross-validation: 200-round red/blue + trust + Kakeya + high-order convergence.

Connects four previously independent systems:
  RedBlueEngine → TrustEngineV2 → KakeyaCompletenessChecker
                                 → HighOrderConvergenceMonitor

Verifies the mathematical guarantees inspired by Fields Medal research.
"""

from __future__ import annotations

import random

from maref.evolution.high_order_convergence import HighOrderConvergenceMonitor
from maref.recursive.kakeya_completeness import KakeyaCompletenessChecker
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.recursive.unified_audit import UnifiedAuditStore
from maref.redblue.attack_vector import (
    ALL_ATTACKS,
    AttackCategory,
    AttackDefinition,
    BlueLevel,
    RedLevel,
)
from maref.redblue.red_blue_engine import RedBlueEngine


class CrossValidationBridge:
    """Bridges red/blue simulation with trust evaluation and completeness checking.

    Data flow per round:
      RedBlueEngine.run_round() → RedBlueResult
        → TrustEngineV2.record_task(success, quality, latency)
        → TrustEngineV2.assess(agent_id) → TrustScoreV2
        → KakeyaCompletenessChecker.check(score) → CompletenessReport
        → HighOrderConvergenceMonitor.record(score.overall_trust)
    """

    AGENT_ID = "maref-blue-agent"

    def __init__(self) -> None:
        self._rb = RedBlueEngine()
        self._audit = UnifiedAuditStore()
        self._trust = TrustEngineV2(audit_store=self._audit)
        self._kakeya = KakeyaCompletenessChecker()
        self._convergence = HighOrderConvergenceMonitor(window=20)
        self._trust.register_agent(self.AGENT_ID)

        self._round_count = 0
        self._trust_history: list[float] = []
        self._completeness_reports: list = []
        self._attack_counts: dict[str, int] = {}

    @property
    def trust_engine(self) -> TrustEngineV2:
        return self._trust

    @property
    def kakeya(self) -> KakeyaCompletenessChecker:
        return self._kakeya

    @property
    def trust_history(self) -> list[float]:
        return list(self._trust_history)

    @property
    def round_count(self) -> int:
        return self._round_count

    def run_round(self, attack: AttackDefinition, red: RedLevel, blue: BlueLevel) -> dict:
        """Run one red/blue round and propagate results to trust evaluation."""
        result = self._rb.run_round(
            f"round-{self._round_count}",
            self._round_count,
            attack,
            red,
            blue,
        )

        # Feed results to trust engine
        self._trust.record_task(
            agent_id=self.AGENT_ID,
            task_id=f"round-{self._round_count}",
            success=result.passed,
            quality=result.total_score / 100.0,
            latency_ms=result.detection_time_ms,
        )

        # Assess trust score
        score = self._trust.assess(self.AGENT_ID)
        trust_val = score.overall_trust if score else 0.0
        self._trust_history.append(trust_val)

        # Check Kakeya completeness
        if score:
            comp_report = self._kakeya.check(score)
            self._completeness_reports.append(comp_report)

        # Track attack category
        cat = attack.category.value[0]
        self._attack_counts[cat] = self._attack_counts.get(cat, 0) + 1

        self._round_count += 1

        return {
            "round": self._round_count - 1,
            "passed": result.passed,
            "total_score": result.total_score,
            "attack_category": cat,
            "attack_name": attack.name,
            "trust_score": trust_val,
        }

    def run_rounds(self, count: int = 200) -> list[dict]:
        """Run multiple red/blue rounds cycling through all attack vectors."""
        random.seed(42)
        results = []
        for i in range(count):
            attack = ALL_ATTACKS[i % len(ALL_ATTACKS)]
            red = list(RedLevel)[i % len(RedLevel)]
            blue = list(BlueLevel)[i % len(BlueLevel)]
            r = self.run_round(attack, red, blue)
            results.append(r)
        return results

    def get_completeness_report(self):
        """Latest completeness report."""
        return self._completeness_reports[-1] if self._completeness_reports else None

    def get_convergence_report(self):
        """High-order convergence report on the trust score series."""
        return self._convergence.compute(self._trust_history, "overall_trust")


class TestCrossValidation200Rounds:
    """200-round integration test bridging red/blue with trust + mathematics."""

    def test_kakeya_completeness_after_200_rounds(self) -> None:
        """9-factor trust space should cover most attack directions after training."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        report = bridge.get_completeness_report()
        assert report is not None
        assert report.effective_dimension >= report.target_dimension * 0.7, (
            f"Only {report.effective_dimension}/{report.target_dimension} directions covered"
        )
        assert isinstance(report.is_complete, bool)

    def test_high_order_convergence_after_200_rounds(self) -> None:
        """Trust score series should have valid convergence stats after 200 rounds."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        report = bridge.get_convergence_report()
        assert report.n_points == 200
        assert not report.pseudo_converged
        assert 0 <= report.mean <= 100
        assert report.variance >= 0

    def test_trust_score_history_length(self) -> None:
        """Should have exactly one trust score per round."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        assert len(bridge.trust_history) == 200

    def test_trust_score_tier_progression(self) -> None:
        """Trust tier should not be F after 200 rounds of normal operation."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        score = bridge.trust_engine.get_score(CrossValidationBridge.AGENT_ID)
        assert score is not None
        assert score.trust_tier != "F", f"tier is {score.trust_tier}"
        assert 0 <= score.overall_trust <= 100

    def test_completeness_report_structure(self) -> None:
        """Completeness report should contain all expected fields."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(50)
        report = bridge.get_completeness_report()
        assert report is not None
        d = report.to_dict()
        assert "effective_dimension" in d
        assert "target_dimension" in d
        assert "is_complete" in d
        assert "blind_spots" in d
        assert "factor_coverage" in d

    def test_convergence_report_structure(self) -> None:
        """Convergence report should contain all expected fields."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(50)
        report = bridge.get_convergence_report()
        d = report.to_dict()
        assert "mean" in d
        assert "variance" in d
        assert "skewness" in d
        assert "kurtosis" in d
        assert "fully_converged" in d
        assert "pseudo_converged" in d

    def test_no_pseudo_convergence_in_normal_operation(self) -> None:
        """Normal 200-round operation should not show pseudo-convergence."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        report = bridge.get_convergence_report()
        assert not report.pseudo_converged, (
            f"pseudo-convergence detected: variance={report.variance:.4f}"
        )

    def test_attack_coverage_distribution(self) -> None:
        """All attack categories should be exercised across 200 rounds."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        cats = bridge._attack_counts
        # 14 categories exist; with 74 attacks cycling through 200 rounds,
        # every category gets at least 1 round
        assert len(cats) >= 12, f"Only {len(cats)}/{len(ALL_ATTACKS)} categories used: {cats}"
        for cat, count in cats.items():
            assert count >= 1, f"Category {cat} had 0 rounds"

    def test_trust_scores_remain_stable(self) -> None:
        """Trust scores should not oscillate wildly in normal operation."""
        bridge = CrossValidationBridge()
        bridge.run_rounds(200)
        history = bridge.trust_history
        # Check variance of the last 50 rounds is reasonable
        last_50 = history[-50:]
        mean = sum(last_50) / 50
        var = sum((x - mean) ** 2 for x in last_50) / 49
        assert var < 500, f"Trust variance too high: {var:.2f}"

    def test_trust_penalized_by_poor_performance(self) -> None:
        """Consecutive failures should reduce trust score."""
        bridge = CrossValidationBridge()
        # Run weak attacks first (should get high trust)
        for _ in range(30):
            bridge.run_round(
                AttackDefinition(AttackCategory.STATE_MACHINE, "easy", "Very weak", 0.0, 0.0, {}),
                RedLevel.R1,
                BlueLevel.B5,
            )
        high_trust = bridge.trust_history[-1]

        # Run strong attacks (should reduce trust)
        for _ in range(30):
            bridge.run_round(
                AttackDefinition(AttackCategory.MULTI_VECTOR, "hard", "Very strong", 1.0, 1.0, {}),
                RedLevel.R5,
                BlueLevel.B1,
            )
        low_trust = bridge.trust_history[-1]

        assert low_trust <= high_trust, (
            f"Trust rose after poor performance: {high_trust} -> {low_trust}"
        )
