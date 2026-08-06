#!/usr/bin/env python3
"""Generate per-module coverage report from coverage.json."""

import json
import sys
from pathlib import Path


def generate_module_report():
    coverage_json = Path("coverage.json")
    if not coverage_json.exists():
        print("ERROR: coverage.json not found. Run pytest with --cov-report=json first.")
        sys.exit(1)

    with open(coverage_json) as f:
        data = json.load(f)

    modules = {
        "maref_governance": ["src/maref/governance/"],
        "maref_observation": ["src/maref/observation/"],
        "maref_knowledge": ["src/maref/knowledge/"],
        "maref_identity": ["src/maref/identity/"],
        "maref_learning": ["src/maref/learning/"],
        "maref_orchestration": ["src/maref/orchestration/"],
        "maref_integration": ["src/maref/integration/"],
        "maref_evolution": ["src/maref/evolution/"],
        "maref_recursive": ["src/maref/recursive/"],
        "drift_guard": ["src/drift_guard/"],
        "sidecar": ["src/sidecar/"],
        "maref_lite": ["src/maref_lite/"],
    }

    report = {}
    for module_name, paths in modules.items():
        total_statements = 0
        total_missing = 0

        for path in paths:
            for file_path, file_data in data["files"].items():
                if file_path.startswith(path):
                    total_statements += file_data["summary"]["num_statements"]
                    total_missing += file_data["summary"]["missing_lines"]

        if total_statements > 0:
            coverage_pct = round(((total_statements - total_missing) / total_statements) * 100, 2)
        else:
            coverage_pct = 0.0

        report[module_name] = {
            "coverage_pct": coverage_pct,
            "threshold": 60.0,
            "passed": coverage_pct >= 60.0,
        }

    output_path = Path("coverage_per_module_report.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Generated {output_path}")
    print()
    for k, v in report.items():
        status = "✅" if v["passed"] else "❌"
        print(f"  {status} {k}: {v['coverage_pct']}% (threshold: {v['threshold']}%)")

    all_passed = all(v["passed"] for v in report.values())
    if all_passed:
        print("\n🎉 All modules passed coverage threshold!")
    else:
        print("\n⚠️ Some modules failed coverage threshold.")

    return all_passed


if __name__ == "__main__":
    success = generate_module_report()
    sys.exit(0 if success else 1)
