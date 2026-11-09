#!/usr/bin/env python3
"""第三方可执行的公开报告复验。

校验六件事：报告签名、锚点清单哈希、门禁摘要哈希、门禁状态一致性、
报告链连续、scope.status 自洽。任何一项不通过即 exit 1。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from maref.reporting.models import GovernanceReport  # noqa: E402

ANCHOR_KEYS = (
    "audit_sha256",
    "total_events",
    "anchored_events",
    "uncovered_events",
    "tsa_url",
    "tsa_ca_sha256",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_gates(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    gates = data.get("gates") if isinstance(data, dict) else data
    if not isinstance(gates, list):
        raise SystemExit(f"{path}: gates must be a list")
    return gates


def _pick(candidates: list[Path], label: str) -> Path | None:
    """多个文件名同字节（如 20261109.json 与 latest.json）视为唯一匹配."""
    if not candidates:
        print(f"❌ {label}: no matching file")
        return None
    digests = {sha256_bytes(p.read_bytes()) for p in candidates}
    if len(digests) != 1:
        print(f"❌ {label}: {len(digests)} distinct candidates, selection ambiguous")
        return None
    return candidates[0]


def select_anchor_manifest(root: str | Path, expected_sha256: str) -> Path | None:
    matches = [
        p
        for p in sorted(Path(root).glob("*/ANCHOR_MANIFEST.json"))
        if sha256_bytes(p.read_bytes()) == expected_sha256
    ]
    return _pick(matches, "anchor.manifest")


def select_gates_file(root: str | Path, expected: set[str]) -> Path | None:
    matches = [
        p for p in sorted(Path(root).glob("*.json")) if sha256_bytes(p.read_bytes()) in expected
    ]
    return _pick(matches, "gates")


def check_scope(report: GovernanceReport, gates: list[dict]) -> list[str]:
    scope = (report.metadata or {}).get("scope") or {}
    status = scope.get("status")
    total = report.audit_summary.total_events
    failures: list[str] = []
    if status not in {"healthy", "degraded", "no_data"}:
        failures.append("scope.status_invalid")
    if total == 0 and status != "no_data":
        failures.append("scope.no_data_required")
    if status == "no_data" and total != 0:
        failures.append("scope.no_data_with_events")
    all_pass = bool(gates) and all(g.get("status") == "pass" for g in gates)
    if status == "healthy" and not all_pass:
        failures.append("scope.healthy_requires_all_gates_pass")
    if status == "degraded" and all_pass:
        failures.append("scope.degraded_with_all_gates_pass")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="复验公开治理报告")
    parser.add_argument("--report", required=True)
    parser.add_argument("--pubkey", required=True)
    parser.add_argument("--anchor-manifest", default="")
    parser.add_argument(
        "--anchor-root",
        default="",
        help="按 manifest_sha256 在 <root>/*/ANCHOR_MANIFEST.json 中选文件",
    )
    parser.add_argument("--gates", default="")
    parser.add_argument(
        "--gates-dir", default="", help="按 evidence_sha256 在 <dir>/*.json 中选文件"
    )
    parser.add_argument("--previous-report", default="")
    args = parser.parse_args(argv)

    report = GovernanceReport.from_json(Path(args.report).read_text(encoding="utf-8"))
    pubkey = Path(args.pubkey).read_text(encoding="utf-8")
    metadata = report.metadata or {}
    failures: list[str] = []

    if not report.verify_signature(pubkey):
        failures.append("signature")

    anchor = metadata.get("anchor") or {}
    anchor_manifest = args.anchor_manifest
    if not anchor_manifest and args.anchor_root:
        picked = select_anchor_manifest(args.anchor_root, str(anchor.get("manifest_sha256", "")))
        if picked is None:
            failures.append("anchor.manifest_selection")
        else:
            anchor_manifest = str(picked)
    if anchor_manifest:
        raw = Path(anchor_manifest).read_bytes()
        manifest = json.loads(raw)
        if anchor.get("manifest_sha256") != sha256_bytes(raw):
            failures.append("anchor.manifest_sha256")
        for key in ANCHOR_KEYS:
            if str(anchor.get(key, "")) != str(manifest.get(key, "")):
                failures.append(f"anchor.{key}")
    elif not anchor:
        failures.append("anchor.missing")

    gates = metadata.get("gates") or []
    gates_path = args.gates
    if not gates_path and args.gates_dir:
        expected_digests = {str(g.get("evidence_sha256", "")) for g in gates}
        picked = select_gates_file(args.gates_dir, expected_digests)
        if picked is None:
            failures.append("gates.selection")
        else:
            gates_path = str(picked)
    if gates_path:
        raw = Path(gates_path).read_bytes()
        digest = sha256_bytes(raw)
        expected = {g.get("name", ""): g for g in load_gates(gates_path)}
        reported = {g.get("name", ""): g for g in gates}
        if set(expected) != set(reported):
            failures.append("gates.set")
        for name, item in reported.items():
            source = expected.get(name, {})
            if item.get("evidence_sha256") != digest:
                failures.append(f"gates.{name}.evidence_sha256")
            if item.get("status") != source.get("status"):
                failures.append(f"gates.{name}.status")
            if str(item.get("exit_code")) != str(source.get("exit_code")):
                failures.append(f"gates.{name}.exit_code")
    elif not gates:
        failures.append("gates.missing")

    if args.previous_report:
        previous = GovernanceReport.from_json(
            Path(args.previous_report).read_text(encoding="utf-8")
        )
        if report.previous_report_id != previous.report_id:
            failures.append("previous_report_id")

    failures.extend(check_scope(report, gates))

    failures = sorted(set(failures))
    for item in failures:
        print(f"❌ {item}")
    if failures:
        return 1
    print(
        f"✅ report {report.report_id[:8]} verified: "
        f"events={report.audit_summary.total_events} "
        f"gates={len(gates)} status={((metadata.get('scope') or {}).get('status'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
