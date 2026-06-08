#!/usr/bin/env python3
"""
7-Day Continuous Autonomous Evolution Verification

This script runs the daily evolution loop for 7 consecutive rounds,
collects metrics from EvolutionVault, analyzes trends and stability,
and generates a final verification report.

Usage:
    python -m maref.evolution.verify_7day \
        --vault-dir ./vault/evolution \
        --output-dir ./research_output/verification \
        --dry-run  # For testing without actual 7-day wait
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from maref.evolution.vault import EvolutionVault


@dataclass
class DayVerification:
    """Verification result for a single day."""

    day: int
    date: str
    snapshots_count: int
    avg_fnr: float
    avg_fpr: float
    trend_direction: str
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "date": self.date,
            "snapshots_count": self.snapshots_count,
            "avg_fnr": self.avg_fnr,
            "avg_fpr": self.avg_fpr,
            "trend_direction": self.trend_direction,
            "issues": self.issues,
        }


@dataclass
class SevenDayVerificationResult:
    """Final verification report for 7-day continuous evolution."""

    start_date: str
    end_date: str
    total_snapshots: int
    days_verified: int
    daily_results: list[DayVerification] = field(default_factory=list)
    overall_trend: str = "unknown"
    stability_score: float = 0.0
    passed: bool = False
    recommendations: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_snapshots": self.total_snapshots,
            "days_verified": self.days_verified,
            "daily_results": [d.to_dict() for d in self.daily_results],
            "overall_trend": self.overall_trend,
            "stability_score": self.stability_score,
            "passed": self.passed,
            "recommendations": self.recommendations,
            "duration_seconds": self.duration_seconds,
        }


def verify_single_day(
    vault: EvolutionVault,
    day: int,
    target_date: str,
) -> DayVerification:
    """Verify a single day's evolution data."""
    snapshots = vault.load_by_date(target_date)

    if not snapshots:
        return DayVerification(
            day=day,
            date=target_date,
            snapshots_count=0,
            avg_fnr=0.0,
            avg_fpr=0.0,
            trend_direction="no_data",
            issues=[f"No snapshots found for {target_date}"],
        )

    # Calculate average metrics
    fnr_values = [s.fnr for s in snapshots if hasattr(s, "fnr")]
    fpr_values = [s.fpr for s in snapshots if hasattr(s, "fpr")]

    avg_fnr = sum(fnr_values) / len(fnr_values) if fnr_values else 0.0
    avg_fpr = sum(fpr_values) / len(fpr_values) if fpr_values else 0.0

    # Analyze trend
    fnr_trend = vault.get_trend("fnr", window=7)
    fpr_trend = vault.get_trend("fpr", window=7)
    trend_direction = "stable"
    if fnr_trend.direction.value == "rising":
        trend_direction = "degrading"
    elif fnr_trend.direction.value == "falling":
        trend_direction = "improving"
    if fpr_trend.direction.value == "rising":
        trend_direction = "degrading"
    elif fpr_trend.direction.value == "falling" and trend_direction == "stable":
        trend_direction = "improving"

    # Identify issues
    issues = []
    if avg_fnr > 0.15:
        issues.append(f"High FNR: {avg_fnr:.3f} > 0.15")
    if avg_fpr > 0.10:
        issues.append(f"High FPR: {avg_fpr:.3f} > 0.10")
    if len(snapshots) < 3:
        issues.append(f"Low snapshot count: {len(snapshots)} < 3")

    return DayVerification(
        day=day,
        date=target_date,
        snapshots_count=len(snapshots),
        avg_fnr=avg_fnr,
        avg_fpr=avg_fpr,
        trend_direction=trend_direction,
        issues=issues,
    )


def run_7day_verification(
    vault_dir: str,
    output_dir: str,
    dry_run: bool = False,
) -> SevenDayVerificationResult:
    """Run 7-day continuous evolution verification."""
    start_time = time.time()
    start_date = datetime.now().strftime("%Y-%m-%d")

    vault = EvolutionVault(vault_dir=vault_dir)

    result = SevenDayVerificationResult(
        start_date=start_date,
        end_date="",
        total_snapshots=0,
        days_verified=0,
    )

    # Verify 7 days (or 1 day in dry-run mode)
    days_to_verify = 1 if dry_run else 7

    for day in range(days_to_verify):
        target_date = (datetime.now() - timedelta(days=6 - day)).strftime("%Y-%m-%d")
        if dry_run:
            target_date = start_date

        day_result = verify_single_day(vault, day + 1, target_date)
        result.daily_results.append(day_result)
        result.total_snapshots += day_result.snapshots_count
        result.days_verified += 1

    # Calculate overall metrics
    valid_days = [d for d in result.daily_results if d.snapshots_count > 0]

    if valid_days:
        result.end_date = valid_days[-1].date

        # Calculate stability score (0-100)
        # Based on: snapshot consistency, low FNR/FPR, stable trend
        snapshot_score = min(len(valid_days) / days_to_verify, 1.0) * 30
        fnr_score = max(0, 1 - (sum(d.avg_fnr for d in valid_days) / len(valid_days))) * 35
        fpr_score = max(0, 1 - (sum(d.avg_fpr for d in valid_days) / len(valid_days))) * 35

        result.stability_score = round(snapshot_score + fnr_score + fpr_score, 1)

        # Determine overall trend
        trends = [d.trend_direction for d in valid_days]
        if trends.count("improving") > len(trends) / 2:
            result.overall_trend = "improving"
        elif trends.count("degrading") > len(trends) / 3:
            result.overall_trend = "degrading"
        else:
            result.overall_trend = "stable"

        # Determine pass/fail
        all_issues = [issue for d in valid_days for issue in d.issues]
        critical_issues = [i for i in all_issues if "High" in i]

        result.passed = (
            len(valid_days) >= days_to_verify and
            len(critical_issues) < 3 and
            result.stability_score >= 60
        )

        # Generate recommendations
        if not result.passed:
            result.recommendations.append("Review high FNR/FPR days for root causes")
        if result.stability_score < 80:
            result.recommendations.append("Increase evolution rounds for better convergence")
        if len(valid_days) < days_to_verify:
            result.recommendations.append("Ensure daily runner executes successfully every day")
        if not result.recommendations:
            result.recommendations.append("System is stable, continue monitoring")

    result.duration_seconds = time.time() - start_time

    # Save output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    report_file = output_path / f"7day_verification_{start_date}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    # Print summary to stdout
    print("7-Day Continuous Evolution Verification Summary:")
    print(f"  Period:         {result.start_date} to {result.end_date}")
    print(f"  Days Verified:  {result.days_verified}")
    print(f"  Total Snapshots: {result.total_snapshots}")
    print(f"  Overall Trend:  {result.overall_trend}")
    print(f"  Stability Score: {result.stability_score:.1f}/100")
    print(f"  Passed:         {result.passed}")
    if result.recommendations:
        print("  Recommendations:")
        for rec in result.recommendations:
            print(f"    - {rec}")
    print(f"  Duration:       {result.duration_seconds:.2f}s")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="7-Day Continuous Autonomous Evolution Verification"
    )
    parser.add_argument(
        "--vault-dir",
        default="./vault/evolution",
        help="EvolutionVault directory",
    )
    parser.add_argument(
        "--output-dir",
        default="./research_output/verification",
        help="Output directory for verification report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (single day verification)",
    )

    args = parser.parse_args()

    try:
        result = run_7day_verification(
            vault_dir=args.vault_dir,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )

        sys.exit(0 if result.passed else 1)

    except Exception as e:
        print(f"[ERROR] 7-day verification failed: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
