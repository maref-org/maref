#!/usr/bin/env python3
"""Coverage report per module for MAREF.

Outputs JSON with per-module coverage percentages,
identifying modules below the quality threshold (60%).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGET_MODULES = {
    "autogen_adapter": {
        "include": "*autogen*",
        "threshold": 60,
    },
    "cli_entry": {
        "include": "*maref_lite/cli*",
        "threshold": 60,
    },
    "recursive_governance": {
        "include": "*maref_lite/recursive_governance*",
        "threshold": 60,
    },
}

ALL_MODULES = {
    "maref_governance": "*maref/governance/*",
    "maref_observation": "*maref/observation/*",
    "maref_knowledge": "*maref/knowledge/*",
    "maref_identity": "*maref/identity/*",
    "maref_learning": "*maref/learning/*",
    "maref_orchestration": "*maref/orchestration/*",
    "maref_integration": "*maref/integration/*",
    "maref_evolution": "*maref/evolution/*",
    "maref_recursive": "*maref/recursive/*",
    "drift_guard": "*drift_guard/*",
    "sidecar": "*sidecar/*",
    "maref_lite": "*maref_lite/*",
}


def run_coverage_for(include_pattern: str) -> float:
    result = subprocess.run(
        [
            sys.executable, "-m", "coverage", "report",
            f"--include={include_pattern}",
            "--show-missing",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    output = result.stdout
    for line in output.strip().split("\n"):
        if line.startswith("TOTAL"):
            parts = line.split()
            if len(parts) >= 4:
                pct_str = parts[-1].rstrip("%")
                try:
                    return float(pct_str)
                except ValueError:
                    pass
    return 0.0


def main() -> int:
    report: dict[str, dict[str, float | bool]] = {}
    all_passed = True

    print("=" * 60)
    print("MAREF Per-Module Coverage Report")
    print("=" * 60)
    print()

    for name, pattern in ALL_MODULES.items():
        pct = run_coverage_for(pattern)
        threshold = 60.0
        passed = pct >= threshold
        status = "PASS" if passed else "FAIL"
        report[name] = {
            "coverage_pct": pct,
            "threshold": threshold,
            "passed": passed,
        }
        if not passed:
            all_passed = False

    print()
    print(f"{'Module':<30} {'Coverage':>10} {'Threshold':>10} {'Status':>8}")
    print("-" * 60)
    for name, data in sorted(report.items()):
        pct = data["coverage_pct"]
        threshold = data["threshold"]
        passed = data["passed"]
        print(f"{name:<30} {pct:>9.2f}% {threshold:>9.2f}% {'PASS' if passed else 'FAIL':>8}")

    print()
    print("--- Quality Gating ---")
    print(f"  Modules below 60% threshold: {sum(1 for d in report.values() if not d['passed'])}")
    if all_passed:
        print("  ALL MODULES PASSED QUALITY GATE.")
    else:
        print("  WARNING: Some modules below quality threshold!")
        for name, data in sorted(report.items()):
            if not data["passed"]:
                print(f"    - {name}: {data['coverage_pct']:.2f}%")

    output_path = ROOT / "coverage_per_module_report.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {output_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
