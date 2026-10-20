"""证据报告与证据门禁回归测试。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import evidence_gate as gate
import gen_evidence_report as evidence


def _healthy_report() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "healthy",
        "sections": {
            "telemetry": {
                "probe": {"fresh_26h": True, "age_hours": 0.1},
                "sidecar": {"healthy": True, "url": "http://127.0.0.1:8931"},
                "mcp_wellknown_reachable": True,
            },
            "self_proof": {
                "audit_health": {"rc": 0},
                "health": {"healthy": True, "issues": []},
                "chain_verify": {
                    "required_ok": True,
                    "required_total": 1,
                    "required_passed": 1,
                },
                "chain_scope": {
                    "complete": True,
                    "chains": {
                        "audit_primary": {"scope": "in_scope", "records": 1},
                        "hooks_agent": {"scope": "foreign", "records": 1},
                    },
                },
                "verdicts": {
                    "approval_tier_unknown_rate": 0.1,
                    "confidence_critical_rate": 0.1,
                    "backlog_sla_met": True,
                },
            },
            "governance_execution": {"global_kpi": {"tool_calls_total": 5}},
            "coverage": {"reconciled": True, "gap_count": 0, "age_hours": 1},
        },
    }


def test_gate_p0_passes_for_healthy_report():
    checks = gate.evaluate(_healthy_report(), hashes_ok=True)
    assert all(check["ok"] for check in checks)


def test_gate_p0_fails_when_chain_or_health_fails():
    report = _healthy_report()
    report["sections"]["self_proof"]["chain_verify"]["required_ok"] = False
    report["sections"]["self_proof"]["health"]["healthy"] = False

    checks = gate.evaluate(report, hashes_ok=True)
    failed = {check["name"] for check in checks if not check["ok"]}
    assert "required chain verify" in failed
    assert "audit health" in failed


def test_gate_p0_fails_when_chain_scope_is_missing():
    report = _healthy_report()
    del report["sections"]["self_proof"]["chain_scope"]

    checks = gate.evaluate(report, hashes_ok=True)
    failed = {check["name"] for check in checks if not check["ok"]}
    assert "chain scope declared" in failed


def test_gate_all_fails_for_stale_governance_metrics():
    report = _healthy_report()
    report["sections"]["coverage"]["age_hours"] = 200
    report["sections"]["governance_execution"]["global_kpi"]["tool_calls_total"] = 0
    report["sections"]["self_proof"]["verdicts"]["approval_tier_unknown_rate"] = 0.9
    report["sections"]["self_proof"]["verdicts"]["confidence_critical_rate"] = 0.5
    report["sections"]["self_proof"]["verdicts"]["backlog_sla_met"] = False

    checks = gate.evaluate(report, full=True, hashes_ok=True)
    failed = {check["name"] for check in checks if not check["ok"]}
    assert "coverage fresh" in failed
    assert "coding kpi > 0" in failed
    assert "approval unknown <= 30%" in failed
    assert "backlog sla" in failed
    assert "confidence critical 5%-15%" in failed


def _write_report(path: Path, entries: list[dict]) -> None:
    report = {
        "evidence_files": entries,
        "evidence_hash": evidence.merkle_root([entry["sha256"] for entry in entries]),
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def test_verify_report_allows_append_only_growth(tmp_path):
    chain = tmp_path / "audit.jsonl"
    chain.write_text("line-1\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    _write_report(
        report_path,
        [
            {
                "path": str(chain),
                "sha256": evidence.sha256_file(chain),
                "size": chain.stat().st_size,
                "mode": "append",
            }
        ],
    )

    assert evidence.verify_report(report_path) == []

    chain.write_text("line-1\nline-2\n", encoding="utf-8")
    assert evidence.verify_report(report_path) == []


def test_verify_report_detects_truncation_and_tamper(tmp_path):
    chain = tmp_path / "audit.jsonl"
    chain.write_text("line-1\nline-2\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    _write_report(
        report_path,
        [
            {
                "path": str(chain),
                "sha256": evidence.sha256_file(chain),
                "size": chain.stat().st_size,
                "mode": "append",
            }
        ],
    )

    chain.write_text("line-1\n", encoding="utf-8")
    issues = evidence.verify_report(report_path)
    assert any("truncated" in issue for issue in issues)


def test_verify_report_detects_merkle_root_mismatch(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "evidence_files": [
                    {"path": str(payload), "sha256": evidence.sha256_file(payload), "mode": "exact"}
                ],
                "evidence_hash": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    issues = evidence.verify_report(report_path)
    assert "evidence merkle root mismatch" in issues
