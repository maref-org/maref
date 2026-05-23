"""
Evolution Quality Gate — MAS-TS-001 as C1→C2→C3 Quality Gate

Integrates the full MAS-TS-001 evaluation into MAREF's recursive evolution
loop as an objective quality gate. Every candidate agent must pass the
MAS-TS-001 assessment before promotion to the next evolution cycle.

Flow:
  C1 → generate candidate → mas_full_run → score >= 70 + 0 CRITICAL → C2
  C2 → optimize candidate → mas_full_run → score >= 80 + no regression → C3
  C3 → converge candidate → mas_full_run → score >= 85 + stable → DEPLOY

If any gate fails, the candidate is rejected and the previous cycle's
best candidate is used as fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from maref.integration.test_platform.schema import (
    EvalStatus,
    EvaluationReport,
    LayerReport,
    TestMode,
)


class EvolutionVerdict(str, Enum):
    APPROVED = "approved"           # Full promotion to next cycle
    CONDITIONAL = "conditional"     # Partial approval, needs human review
    REJECTED = "rejected"           # Blocked, fallback to previous candidate


@dataclass
class QualityGateResult:
    """Result from a single quality gate evaluation."""

    cycle_id: str
    candidate_id: str
    eval_report: EvaluationReport
    verdict: EvolutionVerdict
    score: float
    reason: str
    regression_found: bool = False
    previous_best_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "candidate_id": self.candidate_id,
            "verdict": self.verdict.value,
            "score": self.score,
            "reason": self.reason,
            "regression_found": self.regression_found,
            "previous_best_score": self.previous_best_score,
            "critical_count": self.eval_report.critical_count,
        }


@dataclass
class QualityGateConfig:
    """Configuration thresholds for each evolution cycle."""

    c1_min_score: float = 70.0
    c1_max_critical: int = 0
    c2_min_score: float = 80.0
    c2_max_critical: int = 0
    c2_no_regression: bool = True
    c2_max_score_drop_pp: float = 5.0
    c3_min_score: float = 85.0
    c3_max_critical: int = 0
    c3_fnr_std_max: float = 0.05
    c3_fpr_std_max: float = 0.03

    def to_dict(self) -> dict[str, Any]:
        return {
            "c1_min_score": self.c1_min_score,
            "c1_max_critical": self.c1_max_critical,
            "c2_min_score": self.c2_min_score,
            "c2_max_critical": self.c2_max_critical,
            "c2_no_regression": self.c2_no_regression,
            "c2_max_score_drop_pp": self.c2_max_score_drop_pp,
            "c3_min_score": self.c3_min_score,
            "c3_max_critical": self.c3_max_critical,
        }


class EvolutionQualityGate:
    """
    Quality gate for evolution cycle transitions.

    Evaluates candidate agents using MAS-TS-001 criteria before
    allowing promotion between C1→C2→C3 cycles.
    """

    def __init__(self, config: QualityGateConfig | None = None) -> None:
        self._config = config or QualityGateConfig()
        self._history: list[QualityGateResult] = []

    # --- Cycle-specific evaluation ---

    def evaluate_c1_to_c2(
        self,
        candidate_id: str,
        report: EvaluationReport,
    ) -> QualityGateResult:
        """Evaluate if candidate can move from C1 to C2."""
        score = report.overall_score
        critical_count = report.critical_count

        if score >= self._config.c1_min_score and critical_count <= self._config.c1_max_critical:
            verdict = EvolutionVerdict.APPROVED
            reason = f"C1→C2 APPROVED: score={score:.0f} >= {self._config.c1_min_score}"
        elif score >= self._config.c1_min_score * 0.85:
            verdict = EvolutionVerdict.CONDITIONAL
            reason = f"C1→C2 CONDITIONAL: score={score:.0f}, needs human review"
        else:
            verdict = EvolutionVerdict.REJECTED
            reason = f"C1→C2 REJECTED: score={score:.0f} < {self._config.c1_min_score}"

        result = QualityGateResult(
            cycle_id="c1",
            candidate_id=candidate_id,
            eval_report=report,
            verdict=verdict,
            score=score,
            reason=reason,
        )
        self._history.append(result)
        return result

    def evaluate_c2_to_c3(
        self,
        candidate_id: str,
        report: EvaluationReport,
        previous_best_score: float = 0.0,
    ) -> QualityGateResult:
        """Evaluate if candidate can move from C2 to C3."""
        score = report.overall_score
        critical_count = report.critical_count

        regression_found = False
        if self._config.c2_no_regression and previous_best_score > 0:
            regression_found = (previous_best_score - score) > self._config.c2_max_score_drop_pp

        if (
            score >= self._config.c2_min_score
            and critical_count <= self._config.c2_max_critical
            and not regression_found
        ):
            verdict = EvolutionVerdict.APPROVED
            reason = f"C2→C3 APPROVED: score={score:.0f}, no regression"
        elif regression_found:
            verdict = EvolutionVerdict.REJECTED
            reason = (
                f"C2→C3 REJECTED: regression detected "
                f"(prev={previous_best_score:.0f}, curr={score:.0f})"
            )
        else:
            verdict = EvolutionVerdict.CONDITIONAL
            reason = f"C2→C3 CONDITIONAL: score={score:.0f}, needs human review"

        result = QualityGateResult(
            cycle_id="c2",
            candidate_id=candidate_id,
            eval_report=report,
            verdict=verdict,
            score=score,
            reason=reason,
            regression_found=regression_found,
            previous_best_score=previous_best_score,
        )
        self._history.append(result)
        return result

    def evaluate_c3_to_deploy(
        self,
        candidate_id: str,
        report: EvaluationReport,
        convergence_metrics: dict[str, float] | None = None,
    ) -> QualityGateResult:
        """Evaluate if candidate can deploy from C3."""
        score = report.overall_score
        critical_count = report.critical_count

        converged = True
        if convergence_metrics:
            fnr_std = convergence_metrics.get("fnr_std", 0.0)
            fpr_std = convergence_metrics.get("fpr_std", 0.0)
            converged = (
                fnr_std <= self._config.c3_fnr_std_max
                and fpr_std <= self._config.c3_fpr_std_max
            )

        if (
            score >= self._config.c3_min_score
            and critical_count <= self._config.c3_max_critical
            and converged
        ):
            verdict = EvolutionVerdict.APPROVED
            reason = f"C3→DEPLOY APPROVED: score={score:.0f}, converged={converged}"
        elif not converged:
            verdict = EvolutionVerdict.REJECTED
            reason = f"C3→DEPLOY REJECTED: not converged {convergence_metrics}"
        else:
            verdict = EvolutionVerdict.CONDITIONAL
            reason = f"C3→DEPLOY CONDITIONAL: score={score:.0f}"

        result = QualityGateResult(
            cycle_id="c3",
            candidate_id=candidate_id,
            eval_report=report,
            verdict=verdict,
            score=score,
            reason=reason,
        )
        self._history.append(result)
        return result

    # --- History ---

    @property
    def history(self) -> list[QualityGateResult]:
        return list(self._history)

    def get_cycle_results(self, cycle_id: str) -> list[QualityGateResult]:
        return [r for r in self._history if r.cycle_id == cycle_id]

    @property
    def best_score(self) -> float:
        if not self._history:
            return 0.0
        return max(r.score for r in self._history)

    # --- Simulated evaluation (for integration with existing engine) ---

    @staticmethod
    def build_mock_report(
        agent_id: str,
        score: float,
        critical: int = 0,
    ) -> EvaluationReport:
        return EvaluationReport(
            report_id=f"qg-{agent_id}",
            agent_id=agent_id,
            test_mode=TestMode.FULL_RUN,
            overall_score=score,
            overall_status=EvalStatus.PASS if score >= 70 else EvalStatus.FAIL,
            findings_summary={"critical": critical, "high": 0, "medium": 0, "low": 0, "info": 0},
            layers=[
                LayerReport(layer_number=1, layer_name="Static Audit", score=score),
                LayerReport(layer_number=5, layer_name="MAS Dimensions", score=score),
            ],
        )


__all__ = [
    "EvolutionVerdict",
    "QualityGateResult",
    "QualityGateConfig",
    "EvolutionQualityGate",
]
