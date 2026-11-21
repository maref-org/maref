#!/usr/bin/env python3
"""Deterministic probes used by ``claims.yaml``.

Every probe prints exactly one machine-readable line.  The claim ledger
(``scripts/claims.py``) is the only consumer; humans should read
``docs/claims.md`` instead of parsing this output.

Design rules:
- no network access;
- deterministic (fixed keys, fixed fixtures);
- fail loud with a non-zero exit code instead of printing a guessed value.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_VERSION_RE = r"([0-9]+\.[0-9]+\.[0-9]+)"


def _load_source(name: str, relative: str):
    """Load a stdlib-only module by path.

    ``import maref.governance.audit`` would execute the governance package
    ``__init__`` and pull the full dependency tree (structlog, pydantic, ...).
    The audit modules themselves are stdlib-only, so the probe loads them
    directly.  This keeps ``claims.py --check`` runnable in a clean CI job.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise SystemExit(f"probe: cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def readme_badge() -> str:
    """Version advertised by the shields.io badge in README.md."""
    match = re.search(rf"badge/version-v?{_VERSION_RE}-blue", _readme())
    if not match:
        raise SystemExit("probe readme_badge: badge not found")
    return match.group(1)


def readme_citation() -> str:
    """Version advertised by the BibTeX citation block in README.md."""
    match = re.search(rf"version\s*=\s*\{{{_VERSION_RE}\}}", _readme())
    if not match:
        raise SystemExit("probe readme_citation: citation version not found")
    return match.group(1)


def citation_version() -> str:
    """Version declared in CITATION.cff (a public-facing claim surface)."""
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?', text, re.MULTILINE)
    if not match:
        raise SystemExit("probe citation_version: version field not found")
    return match.group(1)


def count_tests() -> str:
    """Number of ``def test_*`` functions under tests/ (a floor, not pytest's count)."""
    total = 0
    for path in (ROOT / "tests").rglob("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(re.findall(r"^\s*def (test_[A-Za-z0-9_]*)\s*\(", text, re.MULTILINE))
    return str(total)


def count_deps() -> str:
    """Number of direct runtime dependencies declared in pyproject.toml."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(len(data["project"]["dependencies"]))


def coverage_gate() -> str:
    """Coverage floor enforced by pytest-cov."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["tool"]["coverage"]["report"]["fail_under"])


def _audit_fixture(directory: str, key: str) -> Path:
    audit = _load_source("_claim_audit", "src/maref/governance/audit.py")
    path = Path(directory) / "audit.jsonl"
    log = audit.AuditLogger(path, hmac_key=key)
    for index in range(3):
        log.log(
            event_type="policy_check",
            actor=f"agent-{index}",
            action="tool_call",
            layer="orchestration",
        )
    return path


def audit_tamper() -> str:
    """A modified payload must be reported as tampering, not silently accepted."""
    verify = _load_source("_claim_audit_verify", "src/maref/governance/audit_chain_verify.py")

    key = "claim-probe-tamper"
    with tempfile.TemporaryDirectory() as directory:
        path = _audit_fixture(directory, key)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        rows[1]["action"] = "exfiltrate"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = verify.verify_audit_chain(path, hmac_key=key)
    ok = not report.integrity_intact and len(report.hash_invalid) >= 1
    return "detected" if ok else "missed"


def audit_rotation() -> str:
    """A wrong/rotated key must not be reported as tampering."""
    verify = _load_source("_claim_audit_verify", "src/maref/governance/audit_chain_verify.py")

    key = "claim-probe-rotation"
    with tempfile.TemporaryDirectory() as directory:
        path = _audit_fixture(directory, key)
        report = verify.verify_audit_chain(path, hmac_key="a-different-key")
    ok = (
        report.integrity_intact
        and report.key_status == "rotated_or_wrong"
        and not report.signature_invalid
    )
    return "unverifiable" if ok else "mislabelled"


PROBES = {
    "readme_badge": readme_badge,
    "readme_citation": readme_citation,
    "citation_version": citation_version,
    "count_tests": count_tests,
    "count_deps": count_deps,
    "coverage_gate": coverage_gate,
    "audit_tamper": audit_tamper,
    "audit_rotation": audit_rotation,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in PROBES:
        print(f"usage: {Path(__file__).name} <{'|'.join(PROBES)}>", file=sys.stderr)
        return 2
    try:
        print(PROBES[argv[0]]())
    except SystemExit as exc:  # pragma: no cover - probe-config errors
        print(f"probe error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
