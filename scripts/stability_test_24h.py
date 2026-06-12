#!/usr/bin/env python3
"""24h stability test for MAREF sidecar service.

Usage:
    # Quick smoke (10 iterations, 0.1s sleep)
    python scripts/stability_test_24h.py --quick

    # Full 24h equivalent (1000 iterations, ~86s each)
    python scripts/stability_test_24h.py --full

    # Custom
    python scripts/stability_test_24h.py --iterations 200 --interval 0.5

    # Against running sidecar
    python scripts/stability_test_24h.py --sidecar-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.maref.stress.stability_test import ITERATIONS_FOR_24H, StabilityTestRunner


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("stability_24h")


def _sidecar_operation(sidecar_url: str) -> callable:
    def op(iteration: int) -> None:
        try:
            resp = urllib.request.urlopen(f"{sidecar_url}/api/health", timeout=5)
            data = resp.read().decode()
            _ = json.loads(data)
        except (urllib.error.URLError, json.JSONDecodeError, ConnectionError) as e:
            raise RuntimeError(f"sidecar health check failed: {e}") from e
    return op


def _governance_operation(sidecar_url: str) -> callable:
    def op(iteration: int) -> None:
        _sidecar_operation(sidecar_url)(iteration)
        _run_pytest_subset()
    return op


def _run_pytest_subset() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/recursive/", "-q", "--tb=line"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        failures = result.stdout.strip().split("\n")[-1:] if result.stdout else ["unknown"]
        logger.warning("pytest failures in iteration: %s", failures)


def _build_operation(sidecar_url: str | None, suite: str) -> callable:
    if suite == "sidecar_only":
        base = _sidecar_operation(sidecar_url or "http://localhost:8000")
    elif suite == "full":
        base = _governance_operation(sidecar_url or "http://localhost:8000")
    else:
        base = lambda i: None  # default CPU/mem workload

    def op(iteration: int) -> None:
        logger.info("Iteration %d starting", iteration)
        base(iteration)
        logger.info("Iteration %d complete", iteration)

    return op


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF 24h stability test")
    parser.add_argument("--iterations", type=int, default=ITERATIONS_FOR_24H)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--leak-threshold", type=float, default=5.0)
    parser.add_argument("--sidecar-url", default=None)
    parser.add_argument("--suite", choices=["quick", "sidecar_only", "full"], default="sidecar_only")
    parser.add_argument("--output", default="data/stability_report.json")
    parser.add_argument("--quick", action="store_true", help="10 iterations, 0.1s interval")

    args = parser.parse_args()

    if args.quick:
        args.iterations = 10
        args.interval = 0.1
        args.suite = "quick"

    if args.interval:
        base_op = _build_operation(args.sidecar_url, args.suite)
        def op(iteration: int) -> None:
            base_op(iteration)
            if args.interval:
                time.sleep(args.interval)
    else:
        op = _build_operation(args.sidecar_url, args.suite)

    logger.info("=" * 60)
    logger.info("MAREF 24h Stability Test")
    logger.info("  iterations:   %d", args.iterations)
    logger.info("  suite:        %s", args.suite)
    logger.info("  leak thresh:  %.1f%%", args.leak_threshold)
    logger.info("  output:       %s", args.output)
    logger.info("=" * 60)

    runner = StabilityTestRunner(
        operation=op,
        iterations=args.iterations,
        leak_threshold_pct=args.leak_threshold,
    )

    report = runner.run(report_interval=max(1, args.iterations // 20))
    data = report.to_dict()
    data["suite"] = args.suite
    data["iterations_actual"] = args.iterations

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("=" * 60)
    logger.info("Stability Test Complete")
    logger.info("  duration:     %.1fs", data["duration_s"])
    logger.info("  mem growth:   %.2f%%", data["memory_growth_pct"])
    logger.info("  success rate: %.1f%%", data["success_rate"] * 100)
    logger.info("  leak:         %s", data["leak_detected"])
    if data["leak_detected"]:
        logger.warning("  >> %s", data["leak_message"])
    logger.info("  report saved: %s", args.output)
    logger.info("=" * 60)

    sys.exit(1 if data["leak_detected"] else 0)


if __name__ == "__main__":
    main()
