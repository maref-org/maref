"""Conformance suite regression: the ruler must fail closed and stay portable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from maref.conformance import (
    CONTROLS,
    TraceError,
    build_trace,
    load_trace,
    run,
    sign_report,
    tamper,
    verify_report,
    verify_report_dict,
)
from maref.conformance.types import Status, event_digest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "conformance_run.py"


def _statuses(report) -> dict[str, str]:
    return {control.id: control.status.value for control in report.controls}


def test_spec_declares_ten_controls() -> None:
    assert [control.id for control in CONTROLS] == [f"AG-{index:02d}" for index in range(1, 11)]


def test_good_trace_is_conformant() -> None:
    report = run(build_trace(compliant=True))
    assert report.conformant
    assert report.verdict == "conformant"
    assert report.score == 1.0
    assert report.passed == len(CONTROLS)
    assert all(control.status is Status.PASS for control in report.controls)


def test_bad_trace_fails_expected_controls() -> None:
    report = run(build_trace(compliant=False))
    statuses = _statuses(report)
    expected_failures = {"AG-01", "AG-02", "AG-03", "AG-04", "AG-07", "AG-08", "AG-09"}
    assert {control_id for control_id, status in statuses.items() if status == "fail"} == (
        expected_failures
    )
    assert statuses["AG-05"] == "pass"
    assert statuses["AG-06"] == "pass"
    assert statuses["AG-10"] == "pass"
    assert not report.conformant


def test_tampering_is_detected_by_hash_controls() -> None:
    report = run(tamper(build_trace(compliant=True)))
    statuses = _statuses(report)
    assert statuses["AG-06"] == "fail"
    assert not report.conformant


def test_broken_chain_link_is_detected() -> None:
    trace = build_trace(compliant=True)
    trace[2]["prev_hash"] = "sha256:" + "0" * 64
    report = run(trace)
    assert _statuses(report)["AG-05"] == "fail"


def test_report_signature_round_trip() -> None:
    report = sign_report(run(build_trace()), "test-key")
    assert report.signature is not None
    assert verify_report(report, "test-key")
    assert not verify_report(report, "wrong-key")

    payload = report.to_dict()
    assert verify_report_dict(payload, "test-key")
    payload["run_id"] = "tampered-run"
    assert not verify_report_dict(payload, "test-key")


def test_load_trace_round_trip(tmp_path: Path) -> None:
    trace = build_trace()
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in trace) + "\n", encoding="utf-8")
    loaded = load_trace(path)
    assert len(loaded) == len(trace)
    assert load_trace(path.read_text(encoding="utf-8").splitlines()) == trace


def test_load_trace_rejects_missing_manifest() -> None:
    with pytest.raises(TraceError):
        load_trace(['{"type": "event", "actor": "a"}'])


def test_missing_manifest_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"not": "a manifest"}\n', encoding="utf-8")
    with pytest.raises(TraceError):
        load_trace(path)


def test_controls_are_na_without_tool_calls() -> None:
    manifest = {
        "type": "manifest",
        "run_id": "no-tools",
        "allowed_tools": [],
        "tool_manifest_hash": "sha256:" + "a" * 64,
        "genesis_hash": "genesis",
    }
    event = {
        "seq": 1,
        "ts": "2026-11-21T10:00:00Z",
        "actor": "agent:x",
        "identity": {"type": "ed25519", "key_id": "k"},
        "action": "state_transition",
        "prev_hash": "genesis",
    }
    event["hash"] = event_digest(event)
    report = run([manifest, event])
    statuses = _statuses(report)
    for control_id in {"AG-02", "AG-03", "AG-04", "AG-07", "AG-08", "AG-09"}:
        assert statuses[control_id] == "not_applicable"
    assert report.conformant


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_cli_good_exits_zero(tmp_path: Path) -> None:
    proc = _run_cli("--demo", "good", "--out", str(tmp_path / "report.json"))
    assert proc.returncode == 0, proc.stderr
    assert "conformant" in proc.stderr


def test_cli_bad_exits_one(tmp_path: Path) -> None:
    proc = _run_cli("--demo", "bad", "--out", str(tmp_path / "report.json"))
    assert proc.returncode == 1, proc.stderr
    assert "non_conformant" in proc.stderr


def test_cli_verify_detects_wrong_key(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    assert _run_cli("--demo", "good", "--key", "k1", "--out", str(report_path)).returncode == 0
    assert _run_cli("--verify", str(report_path), "--key", "k1").returncode == 0
    assert _run_cli("--verify", str(report_path), "--key", "k2").returncode == 1
