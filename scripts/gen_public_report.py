#!/usr/bin/env python3
"""生成面向公众的签名治理报告。

只发布聚合计数与哈希：审计原文、actor 名称、details/metadata 一律不进入报告。
报告额外绑定外部锚点（RFC 3161）与每日门禁状态，所有字段都在签名覆盖范围内。
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

from maref import __version__  # noqa: E402
from maref.governance.audit import AuditLogger  # noqa: E402
from maref.reporting.generator import ReportGenerator  # noqa: E402
from maref.reporting.models import AuditSummary, SystemStateSnapshot  # noqa: E402
from maref.signing.signing_key import ReportSigningKey  # noqa: E402

# 只用于归类，不发布。未列出的 actor 一律归入 automation。
OPERATOR_ACTORS = {"frankie"}
STATE_ACTORS = {"state_machine"}

SCOPE_HEALTHY_MEANS = ["evidence_integrity", "anchor_complete", "gates_all_pass"]
SCOPE_EXCLUDES = ["individual_agent_content", "decision_quality"]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_actor(name: str) -> str:
    if name in OPERATOR_ACTORS:
        return "operator"
    if name in STATE_ACTORS:
        return "state_machine"
    return "automation"


def load_gates(path: str | Path) -> tuple[list[dict], str]:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    gates = data.get("gates") if isinstance(data, dict) else data
    if not isinstance(gates, list):
        raise SystemExit(f"{path}: gates must be a list")
    digest = hashlib.sha256(raw).hexdigest()
    items = [
        {
            "name": str(g.get("name", "")),
            "status": str(g.get("status", "")),
            "checked_at": str(g.get("checked_at", "")),
            "exit_code": g.get("exit_code"),
            "evidence_sha256": digest,
        }
        for g in gates
    ]
    for item in items:
        if item["name"] and item["status"] not in {"pass", "fail"}:
            raise SystemExit(f"{path}: gate {item['name']} has invalid status {item['status']!r}")
    return items, digest


def derive_status(gates: list[dict], total_events: int) -> str:
    if total_events == 0:
        return "no_data"
    if not gates or any(g["status"] != "pass" for g in gates):
        return "degraded"
    return "healthy"


def build_anchor(manifest_path: str | Path, run_id: str) -> dict:
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    return {
        "run_id": run_id,
        "generated_at": manifest.get("generated_at", ""),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "audit_sha256": manifest.get("audit_sha256", ""),
        "total_events": manifest.get("total_events", 0),
        "anchored_events": manifest.get("anchored_events", 0),
        "uncovered_events": manifest.get("uncovered_events", 0),
        "tsa_url": manifest.get("tsa_url", ""),
        "tsa_ca_sha256": manifest.get("tsa_ca_sha256", ""),
        "batches": [
            {
                "batch_start_id": b.get("batch_start_id", ""),
                "batch_end_id": b.get("batch_end_id", ""),
                "merkle_root": b.get("merkle_root", ""),
                "event_count": b.get("event_count", 0),
            }
            for b in manifest.get("batches", [])
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成脱敏的公开治理报告")
    parser.add_argument("--audit-log", required=True)
    parser.add_argument("--gates", required=True)
    parser.add_argument("--anchor-manifest", required=True)
    parser.add_argument("--signing-key", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--previous-report-id", default="")
    parser.add_argument("--anchor-run-id", default="")
    args = parser.parse_args(argv)

    gates, _ = load_gates(args.gates)
    anchor = build_anchor(args.anchor_manifest, args.anchor_run_id)

    key = ReportSigningKey.from_private_key_file(args.signing_key)
    logger = AuditLogger(log_path=args.audit_log, hmac_key="public-report-reader")
    generator = ReportGenerator(key)

    report = generator.from_audit_log(
        audit_logger=logger,
        previous_report_id=args.previous_report_id,
    )

    class_counts: dict[str, int] = {}
    for name, count in report.audit_summary.actor_counts.items():
        cls = classify_actor(name)
        class_counts[cls] = class_counts.get(cls, 0) + count

    total_events = report.audit_summary.total_events
    status = derive_status(gates, total_events)
    metadata = {
        "scope": {
            "status": status,
            "healthy_means": SCOPE_HEALTHY_MEANS,
            "excludes": SCOPE_EXCLUDES,
            "audit_log_role": "liveness_and_integrity",
            "unreported_fields": ["active_agents_count"],
        },
        "anchor": anchor,
        "gates": gates,
        "privacy": {
            "aggregation": "actor_names_removed; classes_only",
            "redactions": ["actor_counts", "details", "metadata", "local_paths"],
        },
    }

    summary = AuditSummary(
        total_events=total_events,
        time_range_start=report.audit_summary.time_range_start,
        time_range_end=report.audit_summary.time_range_end,
        event_types=report.audit_summary.event_types,
        actor_counts=class_counts,
    )
    state = SystemStateSnapshot(
        governance_state=status.upper(),
        merkle_tree_size=total_events,
        version=__version__,
    )
    report = report.model_copy(
        update={
            "generated_by": f"maref v{__version__}",
            "audit_summary": summary,
            "system_state": state,
            "metadata": metadata,
        }
    )
    report = report.model_copy(update={"signature": key.sign_report(report.payload_bytes())})

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_json() + "\n", encoding="utf-8")
    print(f"report written: {out}")
    print(f"  status={status} events={total_events} anchor_batches={len(anchor['batches'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
