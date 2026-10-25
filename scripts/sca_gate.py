#!/usr/bin/env python3
"""Fail-closed software composition analysis gate.

Input: pip-audit JSON (`pip-audit --format json`) produced from a `uv export`
of the repo's own `uv.lock`, plus `.github/dependency-exceptions.yaml`.

An exception only applies when package, version and advisory all match, and it
must carry a reason and an ISO expiry date. Expired or malformed entries fail
the gate, so an exception cannot silently become a permanent allowlist.

Exit codes: 0 = no unexcepted findings, 1 = findings/expired exceptions,
2 = tooling or ledger error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import yaml

REQUIRED_EXCEPTION_FIELDS = ("package", "version", "advisories", "reason", "expires")


def load_audit(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "dependencies" not in data:
        raise ValueError("pip-audit JSON must contain a 'dependencies' array")
    return data.get("dependencies") or []


def load_exceptions(path: Path) -> tuple[list[dict], list[str]]:
    data = yaml.safe_load(path.read_text()) or {}
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("exception ledger must declare 'version: 1'")
    entries = data.get("exceptions") or []
    if not isinstance(entries, list):
        raise ValueError("'exceptions' must be a list")
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"exception #{index}: must be a mapping")
            continue
        missing = [field for field in REQUIRED_EXCEPTION_FIELDS if not entry.get(field)]
        if missing:
            errors.append(f"exception #{index}: missing {', '.join(missing)}")
            continue
        try:
            _dt.date.fromisoformat(str(entry["expires"]))
        except ValueError:
            errors.append(f"exception #{index}: expires must be YYYY-MM-DD")
        if not isinstance(entry["advisories"], list) or not entry["advisories"]:
            errors.append(f"exception #{index}: advisories must be a non-empty list")
    return entries, errors


def exception_matches(entry: dict, package: str, version: str, advisory_ids: set[str]) -> bool:
    if str(entry["package"]).lower() != package.lower():
        return False
    if str(entry["version"]) != str(version):
        return False
    listed = {str(item) for item in entry["advisories"]}
    return bool(listed & advisory_ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-json", required=True, type=Path)
    parser.add_argument("--exceptions", required=True, type=Path)
    parser.add_argument(
        "--today",
        default=_dt.date.today().isoformat(),
        help="ISO date used to evaluate expiry (for tests)",
    )
    args = parser.parse_args()

    if not args.audit_json.is_file():
        print(f"ERROR: audit JSON not found: {args.audit_json}")
        return 2
    if not args.exceptions.is_file():
        print(f"ERROR: exception ledger not found: {args.exceptions}")
        return 2

    today = _dt.date.fromisoformat(args.today)

    try:
        dependencies = load_audit(args.audit_json)
        entries, ledger_errors = load_exceptions(args.exceptions)
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if ledger_errors:
        print("ERROR: invalid exception ledger:")
        for item in ledger_errors:
            print(f"  - {item}")
        return 2

    expired = [entry for entry in entries if _dt.date.fromisoformat(str(entry["expires"])) < today]
    active = [entry for entry in entries if entry not in expired]

    findings: list[tuple[str, str, dict]] = []
    for dep in dependencies:
        for vuln in dep.get("vulns") or []:
            findings.append((dep.get("name", "?"), dep.get("version", "?"), vuln))

    uncovered: list[tuple[str, str, dict]] = []
    covered = 0
    for package, version, vuln in findings:
        ids = {str(vuln.get("id"))} | {str(item) for item in vuln.get("aliases") or []}
        if any(exception_matches(entry, package, version, ids) for entry in active):
            covered += 1
        else:
            uncovered.append((package, version, vuln))

    print(f"findings: {len(findings)} in {len({f'{p}=={v}' for p, v, _ in findings})} package(s)")
    print(f"excepted: {covered}; unexcepted: {len(uncovered)}; expired exceptions: {len(expired)}")

    for entry in expired:
        print(f"  EXPIRED {entry['package']}=={entry['version']} → {entry['expires']}")

    for package, version, vuln in uncovered:
        fixes = ",".join(vuln.get("fix_versions") or []) or "none"
        print(f"  FAIL {package}=={version} {vuln.get('id')} (fix: {fixes})")

    if expired or uncovered:
        print("SCA GATE FAILED")
        return 1

    print("SCA GATE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
