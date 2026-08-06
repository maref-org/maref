#!/usr/bin/env python3
"""Compute Spearman correlation between human and automated RSI scores.

Usage:
  1. Fill reviewer scores in vault/rsi-correlation-data.yaml
  2. Run: python3 scripts/compute_human_correlation.py
"""

import os
import yaml
import math

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO_ROOT, "vault", "rsi-correlation-data.yaml")


def _spearman_rank(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    # Rank
    x_ranked = sorted([(v, i) for i, v in enumerate(xs)])
    y_ranked = sorted([(v, i) for i, v in enumerate(ys)])
    xr = [0] * n
    yr = [0] * n
    for i, (_, idx) in enumerate(x_ranked):
        xr[idx] = i
    for i, (_, idx) in enumerate(y_ranked):
        yr[idx] = i
    d2 = sum((xr[i] - yr[i]) ** 2 for i in range(n))
    num = 1 - (6 * d2) / (n * (n * n - 1))
    return max(-1.0, min(1.0, num))


def main():
    with open(DATA_PATH) as f:
        data = yaml.safe_load(f)

    dimensions = [
        "correctness", "testing", "code_quality",
        "security", "efficiency", "adoption",
    ]

    rounds = sorted(data.keys())
    for reviewer in ["reviewer_1", "reviewer_2"]:
        print(f"\n{'='*60}")
        print(f"  {reviewer}")
        print(f"{'='*60}")

        all_auto = []
        all_human = []
        dim_results = {}

        for dim in dimensions:
            auto_scores = []
            human_scores = []
            for r in rounds:
                entry = data[r]
                rev = entry["reviewer_scores"].get(reviewer, {})
                hs = rev.get(dim)
                if hs is None:
                    continue
                auto = entry["automated_scores"][dim]
                auto_scores.append(auto)
                human_scores.append(hs)
            if len(auto_scores) < 3:
                print(f"  {dim:15s}: INSUFFICIENT DATA ({len(auto_scores)} entries)")
                continue
            rho = _spearman_rank(auto_scores, human_scores)
            dim_results[dim] = rho
            all_auto.extend(auto_scores)
            all_human.extend(human_scores)
            status = "✅" if rho >= 0.7 else "⚠️" if rho >= 0.5 else "❌"
            print(f"  {dim:15s}: Spearman ρ = {rho:.3f}  {status}")

        if all_auto and len(all_auto) >= 3:
            overall = _spearman_rank(all_auto, all_human)
            dims_ok = sum(1 for v in dim_results.values() if v >= 0.7)
            ostatus = "✅ PASS" if (overall >= 0.7 and dims_ok >= 5) else "❌ FAIL"
            print(f"\n  {'OVERALL':15s}: Spearman ρ = {overall:.3f}  {ostatus}")
            print(f"  Dimensions ≥ 0.7: {dims_ok}/6")
            if overall >= 0.7:
                if dims_ok >= 6:
                    print("  Result: PASS (all 6 dimensions + overall)")
                elif dims_ok >= 5:
                    print("  Result: CONDITIONAL PASS (5/6 dimensions + overall)")
                else:
                    print("  Result: FAIL (< 5 dimensions ≥ 0.7)")
            else:
                print("  Result: FAIL (overall < 0.7)")


if __name__ == "__main__":
    main()
