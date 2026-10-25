#!/usr/bin/env python3
"""Compare coverage claims against a coverage.json artifact.

Supported STATE.yaml shapes:

    coverage:
      value: 76.36
      source_run_id: "123456789"
      verified_at: "2026-10-26T00:00:00Z"

or the legacy scalar:

    coverage_overall: "76.36%"
    coverage_verified: true

A claim that is explicitly marked unverified, lacks a run id, or differs from
the artifact by more than the tolerance fails the check.

Usage:
    python scripts/coverage_claim_check.py \
        --state STATE.yaml --coverage coverage.json \
        [--domains configs/coverage-domains.yaml] [--run-id 123]

Exit codes: 0 = matches, 1 = mismatch/unverified, 2 = tooling error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def find_coverage_node(state: dict) -> dict:
    """STATE.yaml nests the claim under governance/project; search breadth-first."""
    queue = [state]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("coverage"), dict) or "coverage_overall" in node:
            return node
        queue.extend(node.values())
    return {}


def parse_claim(state: dict) -> tuple[float, str | None, str | None]:
    node = find_coverage_node(state)
    coverage = node.get("coverage")
    if isinstance(coverage, dict):
        raw = coverage.get("value")
        if raw is None:
            raise ValueError("coverage.value is missing")
        text = str(raw)
        if "unverified" in text.lower() or "unknown" in text.lower():
            raise ValueError(f"coverage claim is marked unverified: {text}")
        match = PERCENT_RE.search(text)
        if match:
            claimed = float(match.group(1))
        else:
            try:
                claimed = float(text)
            except ValueError as exc:
                raise ValueError(f"coverage.value is not a percentage: {raw!r}") from exc
        return (
            claimed,
            str(coverage.get("source_run_id") or "") or None,
            str(coverage.get("verified_at") or "") or None,
        )

    raw = node.get("coverage_overall")
    if raw is None:
        raise ValueError("STATE.yaml has neither coverage.value nor coverage_overall")
    text = str(raw)
    if "unverified" in text.lower():
        raise ValueError(f"coverage claim is marked unverified: {text}")
    match = PERCENT_RE.search(text)
    if not match:
        raise ValueError(f"coverage_overall is not a percentage: {text!r}")
    if node.get("coverage_verified") is False:
        raise ValueError("coverage_verified is false")
    return float(match.group(1)), None, None


def domain_percent(files: dict, prefixes: list[str]) -> tuple[float, int]:
    covered = 0
    total = 0
    for path, info in files.items():
        if not any(path.startswith(prefix) for prefix in prefixes):
            continue
        summary = info.get("summary") or {}
        covered += int(summary.get("covered_lines") or 0)
        total += int(summary.get("num_statements") or 0)
    if total == 0:
        raise ValueError(f"no statements matched prefixes {prefixes}")
    return covered / total * 100.0, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--domains", type=Path)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()

    if not args.state.is_file():
        print(f"ERROR: STATE file not found: {args.state}")
        return 2
    if not args.coverage.is_file():
        print(f"ERROR: coverage JSON not found: {args.coverage}")
        return 2

    try:
        state = yaml.safe_load(args.state.read_text()) or {}
        coverage = json.loads(args.coverage.read_text())
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot parse inputs: {exc}")
        return 2

    totals = coverage.get("totals") or {}
    actual = totals.get("percent_covered")
    if actual is None:
        print("ERROR: coverage.json has no totals.percent_covered")
        return 2
    actual = float(actual)

    try:
        claimed, source_run_id, verified_at = parse_claim(state)
    except ValueError as exc:
        print(f"CLAIM CHECK FAILED: {exc}")
        return 1

    tolerance = 0.1
    domains_path = args.domains
    if domains_path is not None:
        if not domains_path.is_file():
            print(f"ERROR: domain config not found: {domains_path}")
            return 2
        domains_config = yaml.safe_load(domains_path.read_text()) or {}
        tolerance = float(domains_config.get("tolerance_pp", tolerance))
        domains = domains_config.get("domains") or {}
    else:
        domains = {}

    problems: list[str] = []
    delta = abs(claimed - actual)
    if delta > tolerance + 1e-9:
        problems.append(
            f"global claim {claimed:.2f}% != artifact {actual:.2f}% (delta {delta:.2f}pp > {tolerance}pp)"
        )

    if source_run_id is None:
        problems.append("claim has no source_run_id (cannot be reproduced from an artifact)")
    elif args.run_id and str(args.run_id) != source_run_id:
        problems.append(f"claim source_run_id {source_run_id} != checked run {args.run_id}")

    for name, spec in domains.items():
        prefixes = spec.get("prefixes") or []
        minimum = float(spec.get("min_percent", 0))
        try:
            percent, statements = domain_percent(coverage.get("files") or {}, prefixes)
        except ValueError as exc:
            problems.append(f"domain {name}: {exc}")
            continue
        print(f"domain {name:<14} {percent:6.2f}% (min {minimum:.2f}%, {statements} statements)")
        if percent + 1e-9 < minimum:
            problems.append(f"domain {name} {percent:.2f}% < {minimum:.2f}%")

    print(f"global claim {claimed:.2f}% vs artifact {actual:.2f}% (tolerance {tolerance}pp)")
    if source_run_id:
        print(f"source_run_id {source_run_id}; verified_at {verified_at or 'missing'}")

    if problems:
        print("CLAIM CHECK FAILED:")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("CLAIM CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
