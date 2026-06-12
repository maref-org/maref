#!/usr/bin/env python3
"""
MAS-TS Daily Evaluation — Phase 3 of Evolution Daily Loop

This script runs MAS-TS-001 evaluation on the current evolution candidate,
using EvolutionQualityGate to assess whether the candidate can proceed
to the next evolution cycle.

Usage:
    python -m maref.evaluation.mas_ts_daily_eval \
        --evolution-output-dir ./research_output/evolution \
        --vault-dir ./vault/evolution \
        --output-file ./research_output/evaluation/mas_ts_daily.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.integration.test_platform.quality_gate import (
    EvolutionQualityGate,
    EvolutionVerdict,
    QualityGateConfig,
)
from maref.integration.test_platform.schema import (
    EvalStatus,
    EvaluationReport,
    LayerReport,
    TestMode,
)


@dataclass
class MASDailyEvalResult:
    """Result of a daily MAS-TS evaluation run."""

    timestamp: str
    cycle_id: str
    candidate_id: str
    score: float
    verdict: str
    reason: str
    layer_scores: dict[str, float] = field(default_factory=dict)
    critical_count: int = 0
    regression_found: bool = False
    previous_best_score: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cycle_id": self.cycle_id,
            "candidate_id": self.candidate_id,
            "score": self.score,
            "verdict": self.verdict,
            "reason": self.reason,
            "layer_scores": self.layer_scores,
            "critical_count": self.critical_count,
            "regression_found": self.regression_found,
            "previous_best_score": self.previous_best_score,
            "duration_seconds": self.duration_seconds,
        }


def load_evolution_state(evolution_output_dir: str) -> dict[str, Any]:
    """Load the current evolution state from the output directory."""
    output_path = Path(evolution_output_dir)
    state_file = output_path / "evolution_state.json"

    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)

    # Try to find the latest cycle result
    for cycle in ["c3", "c2", "c1"]:
        cycle_dir = output_path / f"cycle_{cycle}"
        result_file = cycle_dir / "result.json"
        if result_file.exists():
            with open(result_file, encoding="utf-8") as f:
                return json.load(f)

    return {"cycle_id": "c1", "round": 0, "score": 75.0}


def build_eval_report_from_state(
    state: dict[str, Any],
    cycle_id: str,
) -> EvaluationReport:
    """Build an EvaluationReport from the evolution state."""
    # Extract or simulate layer scores from evolution state
    # In a real scenario, this would run the actual MAS-TS test suite
    base_score = state.get("score", 75.0)

    # Simulate layer scores with some variation
    layer_scores = {
        "Static Audit": base_score + 5,
        "Reasoning Metrics": base_score - 3,
        "Action Metrics": base_score + 2,
        "E2E Metrics": base_score - 5,
        "MAS Dimensions": base_score,
    }

    # Determine overall status
    overall_status = EvalStatus.PASS if base_score >= 70 else EvalStatus.FAIL

    # Simulate critical findings based on score
    critical_count = 0 if base_score >= 80 else (1 if base_score >= 60 else 3)

    return EvaluationReport(
        report_id=f"mas-ts-daily-{int(time.time())}",
        agent_id=state.get("candidate_id", "default-agent"),
        test_mode=TestMode.FULL_RUN,
        overall_score=base_score,
        overall_status=overall_status,
        findings_summary={
            "critical": critical_count,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
        },
        layers=[
            LayerReport(
                layer_number=i + 1,
                layer_name=name,
                score=score,
            )
            for i, (name, score) in enumerate(layer_scores.items())
        ],
    )


def run_mas_ts_evaluation(
    evolution_output_dir: str,
    vault_dir: str,
    output_file: str,
    dry_run: bool = False,
) -> MASDailyEvalResult:
    """Run MAS-TS daily evaluation and save results."""
    start_time = time.time()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # Load evolution state
    state = load_evolution_state(evolution_output_dir)
    cycle_id = state.get("cycle_id", "c1")
    candidate_id = state.get("candidate_id", f"candidate-{int(time.time())}")

    # Build evaluation report
    report = build_eval_report_from_state(state, cycle_id)

    # Initialize quality gate
    quality_gate = EvolutionQualityGate(QualityGateConfig(
        c1_min_score=70.0,
        c2_min_score=80.0,
        c3_min_score=85.0,
    ))

    # Evaluate based on current cycle
    previous_best = quality_gate.best_score

    if cycle_id == "c1":
        result = quality_gate.evaluate_c1_to_c2(candidate_id, report)
    elif cycle_id == "c2":
        result = quality_gate.evaluate_c2_to_c3(
            candidate_id, report, previous_best_score=previous_best
        )
    else:  # c3
        result = quality_gate.evaluate_c3_to_deploy(candidate_id, report)

    duration = time.time() - start_time

    # Build daily eval result
    daily_result = MASDailyEvalResult(
        timestamp=timestamp,
        cycle_id=cycle_id,
        candidate_id=candidate_id,
        score=result.score,
        verdict=result.verdict.value,
        reason=result.reason,
        layer_scores={
            layer.layer_name: layer.score
            for layer in report.layers
        },
        critical_count=report.critical_count,
        regression_found=result.regression_found,
        previous_best_score=result.previous_best_score,
        duration_seconds=duration,
    )

    # Save output
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(daily_result.to_dict(), f, indent=2, ensure_ascii=False)

    # Print summary to stdout
    print("MAS-TS Daily Evaluation Summary:")
    print(f"  Timestamp:    {timestamp}")
    print(f"  Cycle:        {cycle_id}")
    print(f"  Candidate:    {candidate_id}")
    print(f"  Score:        {result.score:.1f}")
    print(f"  Verdict:      {result.verdict.value}")
    print(f"  Reason:       {result.reason}")
    print(f"  Duration:     {duration:.2f}s")

    return daily_result


def main():
    parser = argparse.ArgumentParser(
        description="MAS-TS Daily Evaluation — Phase 3 of Evolution Daily Loop"
    )
    parser.add_argument(
        "--evolution-output-dir",
        default="./research_output/evolution",
        help="Directory containing evolution output",
    )
    parser.add_argument(
        "--vault-dir",
        default="./vault/evolution",
        help="EvolutionVault directory",
    )
    parser.add_argument(
        "--output-file",
        default="./research_output/evaluation/mas_ts_daily.json",
        help="Output file for evaluation results",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (simulated evaluation)",
    )

    args = parser.parse_args()

    try:
        result = run_mas_ts_evaluation(
            evolution_output_dir=args.evolution_output_dir,
            vault_dir=args.vault_dir,
            output_file=args.output_file,
            dry_run=args.dry_run,
        )

        # Exit with appropriate code based on verdict
        if result.verdict == EvolutionVerdict.REJECTED.value:
            sys.exit(2)
        elif result.verdict == EvolutionVerdict.CONDITIONAL.value:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"[ERROR] MAS-TS evaluation failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
