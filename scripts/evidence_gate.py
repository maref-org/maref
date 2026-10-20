#!/usr/bin/env python3
"""治理证据门禁。

默认执行 P0 检查：遥测新鲜、sidecar 健康、审计健康、必需链验证、
证据报告新鲜且可复现。`--all` 追加治理质量指标检查。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audit_health_check import _parse_timestamp  # noqa: E402
from maref_config import REPO_DIR, REPORTS_DIR  # noqa: E402

REPORT_PATH = REPORTS_DIR / "governance_evidence_report.json"
GENERATOR = REPO_DIR / "scripts" / "gen_evidence_report.py"
MAX_REPORT_AGE_HOURS = 26.0


def _get(mapping: object, *keys: str, default: object = None) -> object:
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def evaluate(report: dict | None, *, full: bool = False, hashes_ok: bool = False) -> list[dict]:
    checks: list[dict] = []
    if report is None:
        return [_check("evidence report", False, "missing or invalid JSON")]

    generated_at = report.get("generated_at")
    generated = _parse_timestamp(generated_at)
    age_hours = (
        (datetime.now(timezone.utc) - generated).total_seconds() / 3600
        if generated is not None
        else None
    )

    telemetry = _get(report, "sections", "telemetry", default={})
    proof = _get(report, "sections", "self_proof", default={})
    coverage = _get(report, "sections", "coverage", default={})
    verdicts = _get(proof, "verdicts", default={})
    chain = _get(proof, "chain_verify", default={})
    chain_scope = _get(proof, "chain_scope", default={})
    scoped_chains = chain_scope.get("chains") if isinstance(chain_scope, dict) else None

    checks += [
        _check("report status", report.get("status") == "healthy", str(report.get("status"))),
        _check(
            "report fresh",
            age_hours is not None and age_hours <= MAX_REPORT_AGE_HOURS,
            f"{age_hours:.1f}h" if age_hours is not None else "no generated_at",
        ),
        _check(
            "probe fresh",
            bool(_get(telemetry, "probe", "fresh_26h", default=False)),
            str(_get(telemetry, "probe", "age_hours", default="?")),
        ),
        _check(
            "sidecar healthy",
            bool(_get(telemetry, "sidecar", "healthy", default=False)),
            str(_get(telemetry, "sidecar", "url", default="?")),
        ),
        _check(
            "mcp well-known",
            bool(telemetry.get("mcp_wellknown_reachable")) if isinstance(telemetry, dict) else False,
        ),
        _check(
            "audit health",
            _get(proof, "audit_health", "rc", default=1) == 0
            and _get(proof, "health", "healthy", default=False) is True,
            str(_get(proof, "health", "issues", default="")),
        ),
        _check(
            "required chain verify",
            bool(chain.get("required_ok"))
            and int(chain.get("required_total") or 0) > 0,
            f"{chain.get('required_passed')}/{chain.get('required_total')}",
        ),
        _check(
            "chain scope declared",
            bool(chain_scope.get("complete")) and isinstance(scoped_chains, dict) and bool(scoped_chains),
            f"{len(scoped_chains)} chains" if isinstance(scoped_chains, dict) else "missing",
        ),
        _check("evidence hashes", hashes_ok, "gen_evidence_report.py --check"),
    ]

    if full:
        coverage_age = coverage.get("age_hours") if isinstance(coverage, dict) else None
        kpi = _get(
            report,
            "sections",
            "governance_execution",
            "global_kpi",
            "tool_calls_total",
            default=0,
        )
        unknown_rate = verdicts.get("approval_tier_unknown_rate")
        critical_rate = verdicts.get("confidence_critical_rate")

        checks += [
            _check(
                "coverage reconciled",
                bool(coverage.get("reconciled")) and int(coverage.get("gap_count") or 0) == 0,
                f"gaps={coverage.get('gap_count')}",
            ),
            _check(
                "coverage fresh",
                isinstance(coverage_age, (int, float)) and coverage_age <= 168,
                f"{coverage_age}h" if coverage_age is not None else "stale",
            ),
            _check("coding kpi > 0", int(kpi or 0) > 0, str(kpi)),
            _check(
                "approval unknown <= 30%",
                isinstance(unknown_rate, (int, float)) and unknown_rate <= 0.30,
                f"{unknown_rate:.1%}" if isinstance(unknown_rate, (int, float)) else "missing",
            ),
            _check(
                "backlog sla",
                verdicts.get("backlog_sla_met") is True,
                str(verdicts.get("backlog_sla_met")),
            ),
            _check(
                "confidence critical 5%-15%",
                isinstance(critical_rate, (int, float)) and 0.05 <= critical_rate <= 0.15,
                f"{critical_rate:.1%}" if isinstance(critical_rate, (int, float)) else "missing",
            ),
        ]

    return checks


def _run_generator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        cwd=str(REPO_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="追加治理质量指标检查")
    args = parser.parse_args()

    generated = _run_generator()
    if generated.stdout:
        print(generated.stdout.rstrip())
    if generated.stderr:
        print(generated.stderr.rstrip(), file=sys.stderr)

    report = None
    try:
        with open(REPORT_PATH, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError):
        report = None

    hashes = _run_generator("--check")
    if hashes.stdout:
        print(hashes.stdout.rstrip())
    if hashes.stderr:
        print(hashes.stderr.rstrip(), file=sys.stderr)

    checks = evaluate(report, full=args.all, hashes_ok=hashes.returncode == 0)
    if generated.returncode != 0:
        checks.insert(
            0,
            _check("evidence report generation", False, f"rc={generated.returncode}"),
        )

    failed = 0
    print("\n治理证据门禁:")
    for check in checks:
        status = "OK" if check["ok"] else "FAIL"
        suffix = f" ({check['detail']})" if check.get("detail") else ""
        print(f"- [{status}] {check['name']}{suffix}")
        failed += int(not check["ok"])

    mode = "all" if args.all else "p0"
    print(f"evidence_gate[{mode}]: {'PASS' if failed == 0 else 'FAIL'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
