"""公开治理报告生成与复验的回归测试.

锁定三条不变式：只发布 actor 类别计数；报告绑定发布副本的字节哈希；
scope.status 与门禁/事件数自洽（无数据必须是 no_data）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gen_public_report as gen  # noqa: E402
import verify_public_report as verify  # noqa: E402

from maref.governance.audit import AuditLogger  # noqa: E402
from maref.signing.signing_key import ReportSigningKey  # noqa: E402


@pytest.fixture()
def key_files(tmp_path: Path) -> tuple[Path, Path]:
    key = ReportSigningKey.generate()
    private = tmp_path / "signing.pem"
    public = tmp_path / "signing.pub"
    key.save_private_key(private)
    key.save_public_key(public)
    return private, public


@pytest.fixture()
def audit_log(tmp_path: Path) -> Path:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_path=path, hmac_key="test-key")
    logger.log("meta_monitor_heartbeat", "automation-agent", "beat", "")
    logger.log("state_transition", "state_machine", "transition", "")
    logger.log("chain_rebaseline", "frankie", "rebaseline", "")
    return path


def _write_gates(path: Path, failed: bool) -> Path:
    gates = [
        {
            "name": "threshold-verify",
            "status": "fail" if failed else "pass",
            "checked_at": "2026-11-09T06:00:08Z",
            "exit_code": 1 if failed else 0,
        },
        {
            "name": "evidence-gate",
            "status": "pass",
            "checked_at": "2026-11-09T06:00:10Z",
            "exit_code": 0,
        },
    ]
    path.write_text(
        json.dumps({"generated_at": "2026-11-09T06:00:10Z", "gates": gates}), encoding="utf-8"
    )
    return path


def _write_manifest(path: Path, total_events: int) -> Path:
    manifest = {
        "generated_at": "2026-11-09T08:48:25+00:00",
        "audit_file": "<deployment-local>",
        "audit_sha256": "a1" * 32,
        "total_events": total_events,
        "anchored_events": total_events,
        "uncovered_events": 0,
        "tsa_url": "https://freetsa.org/tsr",
        "tsa_ca_sha256": "b2" * 32,
        "batches": [
            {
                "batch_start_id": "s",
                "batch_end_id": "e",
                "merkle_root": "c3" * 32,
                "event_count": total_events,
            }
        ],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _generate(
    tmp_path: Path,
    audit_log: Path,
    key_files: tuple[Path, Path],
    *,
    gates_failed: bool = True,
    previous_report_id: str = "",
    name: str = "latest.json",
) -> tuple[Path, Path, Path, Path, Path]:
    gates = _write_gates(tmp_path / "gates.json", gates_failed)
    manifest = _write_manifest(tmp_path / "ANCHOR_MANIFEST.json", 3)
    private, public = key_files
    out = tmp_path / name
    rc = gen.main(
        [
            "--audit-log",
            str(audit_log),
            "--gates",
            str(gates),
            "--anchor-manifest",
            str(manifest),
            "--signing-key",
            str(private),
            "--output",
            str(out),
            "--previous-report-id",
            previous_report_id,
        ]
    )
    assert rc == 0
    return out, public, manifest, gates, private


def _verify(
    report: Path, public: Path, manifest: Path, gates: Path, extra: list[str] | None = None
) -> int:
    return verify.main(
        [
            "--report",
            str(report),
            "--pubkey",
            str(public),
            "--anchor-manifest",
            str(manifest),
            "--gates",
            str(gates),
            *(extra or []),
        ]
    )


class TestGenerate:
    def test_actor_names_replaced_by_classes(self, tmp_path, audit_log, key_files):
        report_path, *_ = _generate(tmp_path, audit_log, key_files)
        report = json.loads(report_path.read_text(encoding="utf-8"))

        counts = report["audit_summary"]["actor_counts"]
        assert sum(counts.values()) == 3
        assert set(counts) <= {"operator", "state_machine", "automation"}
        assert "frankie" not in json.dumps(report)

    def test_anchor_bound_to_published_manifest_bytes(self, tmp_path, audit_log, key_files):
        report_path, _, manifest, _, _ = _generate(tmp_path, audit_log, key_files)
        report = json.loads(report_path.read_text(encoding="utf-8"))

        expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
        assert report["metadata"]["anchor"]["manifest_sha256"] == expected

    def test_status_degraded_when_gate_fails(self, tmp_path, audit_log, key_files):
        report_path, *_ = _generate(tmp_path, audit_log, key_files, gates_failed=True)
        report = json.loads(report_path.read_text(encoding="utf-8"))

        assert report["metadata"]["scope"]["status"] == "degraded"
        assert report["system_state"]["governance_state"] == "DEGRADED"

    def test_no_events_means_no_data(self, tmp_path, key_files):
        empty = tmp_path / "empty.jsonl"
        out, public, manifest, gates, _ = _generate(tmp_path, empty, key_files, gates_failed=False)
        report = json.loads(out.read_text(encoding="utf-8"))

        assert report["audit_summary"]["total_events"] == 0
        assert report["metadata"]["scope"]["status"] == "no_data"
        assert _verify(out, public, manifest, gates) == 0


class TestVerify:
    def test_clean_report_passes(self, tmp_path, audit_log, key_files):
        out, public, manifest, gates, _ = _generate(tmp_path, audit_log, key_files)

        assert _verify(out, public, manifest, gates) == 0

    def test_tampered_report_fails_signature(self, tmp_path, audit_log, key_files):
        out, public, manifest, gates, _ = _generate(tmp_path, audit_log, key_files)
        data = json.loads(out.read_text(encoding="utf-8"))
        data["audit_summary"]["total_events"] += 1
        tampered = tmp_path / "n1.json"
        tampered.write_text(json.dumps(data), encoding="utf-8")

        assert _verify(tampered, public, manifest, gates) == 1

    def test_tampered_gates_fail_hash_binding(self, tmp_path, audit_log, key_files):
        out, public, manifest, gates, _ = _generate(tmp_path, audit_log, key_files)
        data = json.loads(gates.read_text(encoding="utf-8"))
        data["gates"][0]["exit_code"] = 99
        tampered = tmp_path / "gates-tampered.json"
        tampered.write_text(json.dumps(data), encoding="utf-8")

        assert _verify(out, public, manifest, tampered) == 1

    def test_report_chain_links_to_previous(self, tmp_path, audit_log, key_files):
        first, public, manifest, gates, _ = _generate(
            tmp_path, audit_log, key_files, name="first.json"
        )
        first_id = json.loads(first.read_text(encoding="utf-8"))["report_id"]
        second, *_ = _generate(
            tmp_path, audit_log, key_files, previous_report_id=first_id, name="second.json"
        )
        assert json.loads(second.read_text(encoding="utf-8"))["previous_report_id"] == first_id
        assert _verify(second, public, manifest, gates, ["--previous-report", str(first)]) == 0

        third, *_ = _generate(tmp_path, audit_log, key_files, name="third.json")
        assert _verify(third, public, manifest, gates, ["--previous-report", str(first)]) == 1
