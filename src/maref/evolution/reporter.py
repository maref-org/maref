"""
MAREF Evolution Reporter — generates markdown reports from EvolutionMetrics.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    EvolutionResult,
)


def generate_cycle_report(
    cycle: CycleResult,
    criteria: AcceptanceCriteria,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_csv = output_dir / "metrics.csv"
    with open(metrics_csv, "w") as f:
        f.write("round,fnr,fpr,entropy,transition_count,learning_rate\n")
        for i in range(len(cycle.metrics.fnr_series)):
            fnr = cycle.metrics.fnr_series[i] if i < len(cycle.metrics.fnr_series) else ""
            fpr = cycle.metrics.fpr_series[i] if i < len(cycle.metrics.fpr_series) else ""
            ent = cycle.metrics.entropy_series[i] if i < len(cycle.metrics.entropy_series) else ""
            tc = cycle.metrics.transition_count_series[i] if i < len(cycle.metrics.transition_count_series) else ""
            lr = cycle.metrics.learning_rate_series[i] if i < len(cycle.metrics.learning_rate_series) else ""
            f.write(f"{i + 1},{fnr},{fpr},{ent},{tc},{lr}\n")

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "cycle_id": cycle.cycle_id,
            "name": cycle.name,
            "rounds_completed": cycle.rounds_completed,
            "rounds_total": cycle.rounds_total,
            "passed": cycle.passed,
            "acceptance": cycle.acceptance,
            "metrics_snapshot": cycle.metrics.to_dict(),
        }, f, indent=2, default=str)

    return summary_path


def generate_final_report(
    result: EvolutionResult,
    criteria: AcceptanceCriteria,
    output_dir: Path,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# MAREF Recursive Evolution — Final Report",
        "",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Stop reason**: {result.stop_reason}",
        f"**Total rounds**: {result.total_rounds}",
        f"**Overall result**: {'**PASSED**' if result.all_passed else '**FAILED**'}",
        "",
        "---",
        "",
        "## Cycles Summary",
        "",
    ]

    for cycle in result.cycles:
        status = "✅ PASSED" if cycle.passed else "❌ FAILED"
        lines.append(f"### {cycle.name} — {status}")
        lines.append(f"- Rounds: {cycle.rounds_completed}/{cycle.rounds_total}")
        if cycle.acceptance:
            lines.append("- Acceptance criteria:")
            for k, v in cycle.acceptance.items():
                lines.append(f"  - {k}: {'✅' if v else '❌'}")
        if cycle.metrics.fnr_series:
            lines.append(f"- FNR range: {min(cycle.metrics.fnr_series):.4f} — {max(cycle.metrics.fnr_series):.4f}")
        if cycle.metrics.fpr_series:
            lines.append(f"- FPR range: {min(cycle.metrics.fpr_series):.4f} — {max(cycle.metrics.fpr_series):.4f}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Acceptance Criteria Reference",
        "",
        "| Criterion | Value |",
        "|-----------|-------|",
        f"| C1 FNR max | {criteria.c1_fnr_max} |",
        f"| C1 FPR max | {criteria.c1_fpr_max} |",
        f"| C2 weight std max | {criteria.c2_weight_std_max} |",
        f"| C2 LR convergence target | {criteria.c2_lr_convergence_target} |",
        f"| C3 FNR std max | {criteria.c3_fnr_std_max} |",
        f"| C3 FPR std max | {criteria.c3_fpr_std_max} |",
        f"| C3 oscillation max | {criteria.c3_oscillation_max} |",
    ]

    report_content = "\n".join(lines)

    report_path = output_dir / "final_report.md"
    with open(report_path, "w") as f:
        f.write(report_content)

    return str(report_path)
