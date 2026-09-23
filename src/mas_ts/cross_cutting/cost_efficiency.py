# SPDX-FileCopyrightText: 2026 maref-org
# SPDX-License-Identifier: Apache-2.0
"""Cost Efficiency: Cross-cutting metric for MAS-TS Gold Standard.

Gold Standard §8 — Tracks token consumption, tool execution cost, retry cost,
and human review cost per task. Normalized against a reference baseline.

Usage:
    result = compute_cost_efficiency(trajectory, model_name="gpt-4o")
    print(result["efficiency"], result["token_waste_rate"])
"""

from typing import Any, cast

COST_BASELINE: dict[str, str | float] = {
    "model": "qwen2.5-72b",
    "hardware": "docker_cpu_baseline",
    "cpt_reference": 0.05,
}


MODEL_COST_MULTIPLIERS: dict[str, float] = {
    "claude-opus-4": 2.0,
    "claude-sonnet-4": 1.5,
    "claude-haiku-3.5": 0.5,
    "gpt-4o": 1.5,
    "deepseek-chat-v3": 0.3,
    "qwen-max": 0.2,
}


def compute_cost_efficiency(
    trajectory: list[dict[str, Any]] | dict[str, Any] | None = None,
    model_name: str = "unknown",
    hardware_coefficient: float = 1.0,
    include_human_review: bool = False,
    compute_overhead: bool = True,
) -> dict[str, Any]:
    """Compute cost-efficiency metrics from execution trajectory.

    Gold Standard §8.1 — measures:
      - CPT: cost per task (total, normalized)
      - Efficiency: ratio vs reference baseline
      - Token waste rate: retry/overhead fraction
      - Retry count: number of retried tool calls
      - Human review cost: optional human intervention cost
      - Cost overhead ratio: (retry + coordination) / direct cost

    Args:
        trajectory: Execution trajectory with cost/token data.
        model_name: Model identifier (for baseline lookup).
        hardware_coefficient: Hardware cost multiplier.
        include_human_review: Whether to track human review costs.
        compute_overhead: Whether to compute cost overhead ratio.

    Returns:
        Dict with cpt, efficiency, token_waste_rate, retry_count, total_tokens,
        human_review_cost, direct_cost, overhead_cost, cost_overhead_ratio.
    """
    # Handle empty trajectory case
    if not trajectory:
        result = {
            "cpt": 0.0,
            "cpt_normalized": 0.0,
            "efficiency": 0.0,
            "token_waste_rate": 0.0,
            "retry_count": 0,
            "total_tokens": 0,
        }

        if include_human_review:
            result["human_review_cost"] = 0.0

        if compute_overhead:
            result.update(
                {
                    "direct_cost": 0.0,
                    "overhead_cost": 0.0,
                    "cost_overhead_ratio": 0.0,
                }
            )

        return result

    # Process non-empty trajectory
    events: list[dict[str, Any]] = (
        trajectory if isinstance(trajectory, list) else trajectory.get("events", [])
    )

    # Extract costs from events
    costs = []
    human_review_costs = []
    coordination_costs = []

    for e in events:
        # Direct tool execution cost
        cost = e.get("cost_usd", 0) or e.get("action", {}).get("cost_usd", 0)
        costs.append(cost)

        # Human review cost (optional)
        if include_human_review:
            human_cost = e.get("human_review_cost", 0) or e.get("action", {}).get(
                "human_review_cost", 0
            )
            human_review_costs.append(human_cost)

        # Coordination cost (for overhead calculation)
        if compute_overhead:
            coord_cost = e.get("coordination_cost", 0) or e.get("action", {}).get(
                "coordination_cost", 0
            )
            coordination_costs.append(coord_cost)

    tokens = [
        e.get("token_usage", {}).get("total", 0) for e in events if e.get("token_usage")
    ]
    retries = sum(1 for e in events if e.get("action", {}).get("is_retry", False))

    total_cost = sum(costs)
    total_tokens = sum(tokens)
    retry_cost = sum(
        e.get("cost_usd", 0)
        for e in events
        if e.get("action", {}).get("is_retry", False)
    )

    # Additional cost components
    human_review_cost = sum(human_review_costs) if include_human_review else 0.0
    coordination_cost = sum(coordination_costs) if compute_overhead else 0.0

    # Cost breakdown
    direct_cost = total_cost - retry_cost  # Non-retry costs are direct
    overhead_cost = retry_cost + coordination_cost

    normalized_cost = (
        total_cost / hardware_coefficient if hardware_coefficient > 0 else total_cost
    )

    model_multiplier = MODEL_COST_MULTIPLIERS.get(model_name, 1.0)
    cpt_ref = cast(float, COST_BASELINE["cpt_reference"])
    effective_baseline = cpt_ref * model_multiplier
    efficiency = min(1.0, effective_baseline / max(normalized_cost, 0.001))

    waste_rate = retry_cost / max(total_cost, 0.001) if total_cost > 0 else 0.0

    # Cost overhead ratio (if compute_overhead is True)
    cost_overhead_ratio = 0.0
    if compute_overhead and direct_cost > 0:
        cost_overhead_ratio = overhead_cost / direct_cost

    result = {
        "cpt": round(total_cost, 6),
        "cpt_normalized": round(normalized_cost, 6),
        "efficiency": round(efficiency, 3),
        "token_waste_rate": round(waste_rate, 3),
        "retry_count": retries,
        "total_tokens": total_tokens,
    }

    # Optional fields
    if include_human_review:
        result["human_review_cost"] = round(human_review_cost, 6)

    if compute_overhead:
        result.update(
            {
                "direct_cost": round(direct_cost, 6),
                "overhead_cost": round(overhead_cost, 6),
                "cost_overhead_ratio": round(cost_overhead_ratio, 3),
            }
        )

    return result


def check_gold_thresholds(
    efficiency: float,
    waste_rate: float,
    overhead_ratio: float,
    level: str = "L2",
) -> dict[str, Any]:
    """Check Cost Efficiency metrics against Gold Standard thresholds.

    Gold Standard §8.2 thresholds:
        L2: Efficiency ≥0.5, Waste Rate ≤25%, Overhead Ratio ≤40%
        L3: Efficiency ≥0.65, Waste Rate ≤20%, Overhead Ratio ≤30%
        L4: Efficiency ≥0.8, Waste Rate ≤15%, Overhead Ratio ≤20%

    Args:
        efficiency: Cost efficiency score (0.0-1.0).
        waste_rate: Token waste rate (0.0-1.0).
        overhead_ratio: Cost overhead ratio (0.0-∞).
        level: Execution level (L2, L3, L4).

    Returns:
        Dict with pass/fail status and details for each metric.
    """
    thresholds: dict[str, dict[str, float]] = {
        "L2": {"efficiency": 0.5, "waste_rate": 0.25, "overhead_ratio": 0.4},
        "L3": {"efficiency": 0.65, "waste_rate": 0.20, "overhead_ratio": 0.3},
        "L4": {"efficiency": 0.8, "waste_rate": 0.15, "overhead_ratio": 0.2},
    }

    if level not in thresholds:
        raise ValueError(f"Unknown level: {level}. Must be L2, L3, or L4.")

    level_thresholds: dict[str, float] = thresholds[level]

    results: dict[str, Any] = {
        "level": level,
        "efficiency": {
            "value": efficiency,
            "threshold": level_thresholds["efficiency"],
            "passed": efficiency >= level_thresholds["efficiency"],
        },
        "waste_rate": {
            "value": waste_rate,
            "threshold": level_thresholds["waste_rate"],
            "passed": waste_rate <= level_thresholds["waste_rate"],
        },
        "overall_pass": True,
    }

    # Only check overhead ratio if it's provided (not 0.0 default)
    if overhead_ratio > 0:
        results["overhead_ratio"] = {
            "value": overhead_ratio,
            "threshold": level_thresholds["overhead_ratio"],
            "passed": overhead_ratio <= level_thresholds["overhead_ratio"],
        }
        results["overall_pass"] = (
            results["efficiency"]["passed"]
            and results["waste_rate"]["passed"]
            and results["overhead_ratio"]["passed"]
        )
    else:
        results["overall_pass"] = (
            results["efficiency"]["passed"] and results["waste_rate"]["passed"]
        )

    return results


def aggregate_cost_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate cost metrics across multiple runs.

    Gold Standard §8.1 — multi-run statistics:
      - CPT_median: median cost per task
      - CPT_p95: 95th percentile cost per task
      - CV: coefficient of variation

    Args:
        runs: List of cost efficiency results from compute_cost_efficiency().

    Returns:
        Dict with aggregated statistics.
    """
    if not runs:
        return {
            "cpt_median": 0.0,
            "cpt_p95": 0.0,
            "cv": 0.0,
            "count": 0,
        }

    # Extract CPT values
    cpt_values = [r.get("cpt", 0.0) for r in runs]

    # Calculate median
    sorted_cpt = sorted(cpt_values)
    n = len(sorted_cpt)
    if n % 2 == 1:
        cpt_median = sorted_cpt[n // 2]
    else:
        cpt_median = (sorted_cpt[n // 2 - 1] + sorted_cpt[n // 2]) / 2

    # Calculate 95th percentile
    p95_index = int(n * 0.95)
    if p95_index >= n:
        cpt_p95 = sorted_cpt[-1]
    else:
        cpt_p95 = sorted_cpt[p95_index]

    # Calculate coefficient of variation
    mean = sum(cpt_values) / n
    if mean == 0:
        cv = 0.0
    else:
        variance = sum((x - mean) ** 2 for x in cpt_values) / n
        std = variance**0.5
        cv = std / mean

    return {
        "cpt_median": round(cpt_median, 6),
        "cpt_p95": round(cpt_p95, 6),
        "cv": round(cv, 3),
        "count": n,
    }
