#!/usr/bin/env python3
"""Longevity test runner for RSI unsupervised runs.

Usage:
    python scripts/run_longevity.py --help
    python scripts/run_longevity.py --config configs/longevity/24h-l2-run.yaml
    python scripts/run_longevity.py --quick                  # 5-min smoke test
    python scripts/run_longevity.py --l2 --duration 24 --mock  # 24h L2 mock mode
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_longevity")


def load_config(path: str) -> dict[str, Any]:
    """Load YAML config file."""
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_path(p: str) -> str:
    """Resolve report path with timestamp."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{p}-{ts}"


def main():
    parser = argparse.ArgumentParser(description="RSI Longevity Test Runner")
    parser.add_argument("--config", type=str, help="Path to YAML config file")
    parser.add_argument("--quick", action="store_true", help="5-minute smoke test")
    parser.add_argument("--l2", action="store_true", help="Run in L2 mode")
    parser.add_argument("--duration", type=int, default=24, help="Duration in hours")
    parser.add_argument("--mock", action="store_true", default=True, help="Use mock mode (no LLM)")
    parser.add_argument("--check-interval", type=int, default=30, help="Check interval in minutes")
    args = parser.parse_args()
    
    if args.config:
        config = load_config(args.config)
        logger.info("Loaded config: %s", args.config)
    else:
        if args.quick:
            duration_minutes = 5
            check_interval = 1
        else:
            duration_minutes = args.duration * 60
            check_interval = args.check_interval
        config = {
            "run": {
                "duration_hours": duration_minutes / 60,
                "check_interval_minutes": check_interval,
                "mode": "l2" if args.l2 else "standard",
                "mock": args.mock,
                "l2_dimensions": ["correctness", "testing", "code_quality", "security", "performance"],
            },
            "thresholds": {
                "max_adoption_rate_decline": 0.1,
                "max_score_decline": 5.0,
                "max_safety_alerts": 1,
                "max_human_intervention_pct": 2.0,
            },
            "quality_gates": {
                "c1_min_score": 60.0,
                "c2_min_score": 65.0,
                "c3_min_score": 70.0,
                "c4_min_score": 75.0,
                "l2_dim_count": 5,
                "l2_min_dim_score": 70.0,
            },
        }
        logger.info("Using CLI-generated config for %dh %s mode",
                     args.duration if not args.quick else 0.08,
                     config["run"]["mode"])
    
    duration_h = config["run"]["duration_hours"]
    interval_min = config["run"]["check_interval_minutes"]
    report_base = config.get("reporting", {}).get("report_path", "docs/rsi/longevity-report")
    report_path = resolve_path(report_base)
    
    logger.info("=" * 60)
    logger.info("RSI Longevity Run")
    logger.info("  Duration:     %.1f hours (%.0f minutes)", duration_h, duration_h * 60)
    logger.info("  Interval:     %d minutes", interval_min)
    logger.info("  Mode:         %s", config["run"]["mode"])
    logger.info("  Mock:         %s", config["run"].get("mock", True))
    logger.info("  Report path:  %s", report_path)
    logger.info("=" * 60)
    logger.info("")
    
    # Import the regression test framework
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    
    from tests.longevity.test_24h_rsi_regression import run_longevity_test, RSIRegressionReport
    
    total_checks = int(duration_h * 60 / interval_min)
    logger.info("Starting run with %d checkpoints...", total_checks)
    
    start = time.time()
    config_dict = {
        "duration_hours": duration_h,
        "check_interval_minutes": interval_min,
        "max_adoption_rate_decline": config["thresholds"]["max_adoption_rate_decline"],
        "max_score_decline": config["thresholds"]["max_score_decline"],
    }
    
    report = run_longevity_test(
        duration_minutes=int(duration_h * 60),
        check_interval_minutes=interval_min,
        config=config_dict,
    )
    
    elapsed = time.time() - start
    
    # Save report
    save_path = Path(report_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(f"{save_path}.json", "w") as f:
        import json
        json.dump(report.to_dict(), f, indent=2)
    
    # Print summary
    logger.info("")
    sim_duration = report.duration_hours if hasattr(report, "duration_hours") else duration_h
    logger.info("=" * 60)
    logger.info("RUN COMPLETE")
    logger.info("  Sim duration: %.1f hours (wall-clock: %.1fs)", sim_duration, elapsed)
    logger.info("  Snapshots:    %d", len(report.snapshots))
    logger.info("  Passed:       %s", report.passed)
    logger.info("  Degradations: %s", report.degradations if report.degradations else "None")
    logger.info("  Report saved: %s.json", save_path)
    logger.info("=" * 60)
    
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
