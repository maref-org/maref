"""审计链 CLI 负向测试：篡改必须失败，归档链的失败必须被显式承认。"""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY = REPO_ROOT / "scripts" / "verify_audit_chain.py"
KEY = b"test-key"


def _payload(record: dict) -> str:
    payload = {
        "id": record["id"],
        "timestamp": record["timestamp"],
        "event_type": record["event_type"],
        "actor": record["actor"],
        "action": record["action"],
        "details": record["details"],
        "metadata": record.get("metadata", {}),
        "previous_hash": record.get("previous_hash", ""),
        "layer": "governance",
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _record(prev: str, index: int) -> dict:
    record = {
        "id": f"r{index}",
        "timestamp": float(index),
        "event_type": "governance_decision",
        "actor": "tester",
        "action": "test",
        "details": "d",
        "metadata": {},
        "previous_hash": prev,
        "layer": "governance",
    }
    payload = _payload(record)
    record["hmac_signature"] = hmac.new(KEY, payload.encode(), hashlib.sha256).hexdigest()
    record["chain_hash"] = hashlib.sha256((prev + payload).encode()).hexdigest()
    return record


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _healthy(path: Path) -> Path:
    first = _record("", 1)
    second = _record(first["chain_hash"], 2)
    _write(path, [first, second])
    return path


def _broken(path: Path) -> Path:
    first = _record("", 1)
    second = _record(first["chain_hash"], 2)
    second["details"] = "tampered after signing"
    _write(path, [first, second])
    return path


def _run(path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "--audit-file",
            str(path),
            "--hmac-key",
            KEY.decode(),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_healthy_chain_exits_zero(tmp_path: Path) -> None:
    proc = _run(_healthy(tmp_path / "healthy.jsonl"))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_tampered_record_exits_one(tmp_path: Path) -> None:
    proc = _run(_broken(tmp_path / "broken.jsonl"), "--json")
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["integrity_intact"] is False
    assert report["hash_invalid"]


def test_archived_chain_expect_failed_exits_zero(tmp_path: Path) -> None:
    proc = _run(_broken(tmp_path / "archived.jsonl"), "--expect-failed", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["archived"] is True
    assert report["expected_failed"] is True
    assert report["expectation_met"] is True


def test_healthy_chain_expect_failed_exits_one(tmp_path: Path) -> None:
    proc = _run(_healthy(tmp_path / "healthy.jsonl"), "--expect-failed", "--json")
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["archived"] is True
    assert report["expectation_met"] is False


def test_missing_file_fails(tmp_path: Path) -> None:
    proc = _run(tmp_path / "missing.jsonl")
    assert proc.returncode != 0
