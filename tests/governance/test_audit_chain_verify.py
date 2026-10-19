from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from maref.governance.audit_chain_verify import verify_audit_chain


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


def _record(prev: str, index: int, key: bytes) -> dict:
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
    record["hmac_signature"] = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    record["chain_hash"] = hashlib.sha256(
        (prev + payload).encode()
    ).hexdigest()
    return record


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_audit_logger_chain_verifies_with_key(tmp_path):
    key = b"test-key"
    p = tmp_path / "audit.jsonl"
    _write(p, [_record("", 1, key), _record("", 2, key)])
    # Fix linkage for record 2.
    records = [json.loads(line) for line in p.read_text().splitlines()]
    records[1] = _record(records[0]["chain_hash"], 2, key)
    _write(p, records)

    report = verify_audit_chain(p, hmac_key=key)
    assert report.integrity_intact
    assert report.total == 2
    assert report.hash_invalid == []
    assert report.signature_invalid == []


def test_chain_hash_verifies_without_key(tmp_path):
    key = b"test-key"
    p = tmp_path / "audit.jsonl"
    _write(p, [_record("", 1, key)])
    report = verify_audit_chain(p, hmac_key=None)
    assert report.hash_invalid == []
    assert report.signature_unverifiable == ["r1"]
    assert report.integrity_intact


def test_tampered_payload_is_detected(tmp_path):
    key = b"test-key"
    p = tmp_path / "audit.jsonl"
    record = _record("", 1, key)
    record["details"] = "tampered"
    _write(p, [record])
    report = verify_audit_chain(p, hmac_key=key)
    assert len(report.hash_invalid) == 1
    assert not report.integrity_intact


def test_link_break_is_detected(tmp_path):
    key = b"test-key"
    p = tmp_path / "audit.jsonl"
    first = _record("", 1, key)
    second = _record("wrong-previous", 2, key)
    _write(p, [first, second])
    report = verify_audit_chain(p, hmac_key=key)
    assert len(report.link_breaks) == 1
    assert not report.integrity_intact


def test_legacy_hmac_digest_is_verified_with_key(tmp_path):
    key = b"test-key"
    record = {
        "id": "legacy1",
        "timestamp": 1.0,
        "event_type": "state_transition",
        "actor": "sm",
        "action": "ACT_to_VERIFY",
        "details": "d",
        "metadata": {"previous_hash": ""},
        "previous_hash": "",
    }
    payload = json.dumps(
        {
            "id": record["id"],
            "timestamp": record["timestamp"],
            "event_type": record["event_type"],
            "actor": record["actor"],
            "action": record["action"],
            "details": record["details"],
            "metadata": record["metadata"],
            "previous_hash": "",
        },
        ensure_ascii=False,
        default=str,
    )
    record["chain_hash"] = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    p = tmp_path / "audit.jsonl"
    _write(p, [record])

    report = verify_audit_chain(p, hmac_key=key)
    assert report.integrity_intact
    assert report.hash_invalid == []
    assert report.formats == {"legacy_state_machine": 1}


def test_legacy_digest_with_wrong_key_is_unverifiable_not_tampered(tmp_path):
    key = b"right-key"
    record = {
        "id": "legacy1",
        "timestamp": 1.0,
        "event_type": "state_transition",
        "actor": "sm",
        "action": "ACT_to_VERIFY",
        "details": "d",
        "metadata": {"previous_hash": ""},
        "previous_hash": "",
    }
    payload = json.dumps(
        {
            "id": record["id"],
            "timestamp": record["timestamp"],
            "event_type": record["event_type"],
            "actor": record["actor"],
            "action": record["action"],
            "details": record["details"],
            "metadata": record["metadata"],
            "previous_hash": "",
        },
        ensure_ascii=False,
        default=str,
    )
    record["chain_hash"] = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    p = tmp_path / "audit.jsonl"
    _write(p, [record])

    report = verify_audit_chain(p, hmac_key=b"wrong-key")
    assert report.integrity_intact
    assert report.hash_invalid == []
    assert report.signature_unverifiable == ["legacy1"]


def test_state_machine_writer_produces_linear_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path))
    monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-key")
    from maref.governance.state_machine import _write_state_transition
    from maref.governance.types import GovernanceState, StateTransition

    for _ in range(5):
        _write_state_transition(
            StateTransition(GovernanceState.ACT, GovernanceState.VERIFY)
        )

    report = verify_audit_chain(tmp_path / "governance_audit.jsonl", hmac_key=b"test-key")
    assert report.total == 5
    assert report.link_breaks == []
    assert report.hash_invalid == []
    assert report.signature_invalid == []
    assert report.formats == {"audit_logger": 5}
