#!/usr/bin/env python3
"""Runtime meta-audit gate.

Runs meta-monitor once and exits non-zero when required checks fail. This is
the gate used by the deployment daemon / self-hosted CI; the GitHub-hosted
smoke job only checks that the report is generated and parseable.

Usage:
    python scripts/meta_audit_gate.py
    python scripts/meta_audit_gate.py --require m0,m1,m2,m3
    python scripts/meta_audit_gate.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MAREF runtime meta-audit gate")
    parser.add_argument(
        "--require",
        default="m0,m1,m2",
        help="Comma-separated checks required to pass (default: m0,m1,m2)",
    )
    parser.add_argument("--p0", action="store_true", help="Require m0-m3 (P0 gate)")
    parser.add_argument("--all", action="store_true", help="Require m0-m4")
    parser.add_argument("--json", action="store_true", help="Print the full report JSON")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Evaluate an existing meta-monitor report instead of running the monitor",
    )
    args = parser.parse_args()

    if args.report is not None:
        try:
            report = json.loads(args.report.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read report {args.report}: {exc}", file=sys.stderr)
            return 2
        if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
            print(
                f"ERROR: report {args.report} has no summary object",
                file=sys.stderr,
            )
            return 2
    else:
        from maref.observability.meta_monitor import run_once

        report = run_once()
    summary = report.get("summary", {})
    if args.all:
        required = ["m0", "m1", "m2", "m3", "m4"]
    elif args.p0:
        required = ["m0", "m1", "m2", "m3"]
    else:
        required = [
            item.strip().lower() for item in args.require.split(",") if item.strip()
        ]

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        for key in ("m0", "m1", "m2", "m3", "m4"):
            status = "PASS" if summary.get(f"{key}_passed") else "FAIL"
            marker = "required" if key in required else "advisory"
            print(f"{key}: {status} ({marker})")
        print(f"all_passed: {summary.get('all_passed')}")

    failed = [key for key in required if not summary.get(f"{key}_passed")]
    # A report that itself says all_passed=false must never be masked by
    # selecting a narrower --require set.
    if summary.get("all_passed") is False and "all_passed" not in failed:
        failed.append("all_passed")
    if failed:
        print(
            "meta-audit gate FAILED: " + ", ".join(failed),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
