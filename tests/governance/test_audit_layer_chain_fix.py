"""审计链 layer 落盘与链尾回归（镜像内部仓 914c6ef5f 的修复）。"""

from __future__ import annotations

import json
from pathlib import Path

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.audit_chain_verify import verify_audit_chain
from maref.governance.state_machine import _last_chain_hash, _last_chain_hash_from_fh

_KEY = "test-hmac-key-for-layer-regression"


def test_entry_to_dict_keeps_layer() -> None:
    entry = AuditEntry(
        id="audit_000001",
        timestamp=0.0,
        event_type="test",
        actor="test",
        action="test",
        details="",
        layer="orchestration",
    )

    assert entry.to_dict()["layer"] == "orchestration"


def test_verify_accepts_record_with_layer(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLogger(path, hmac_key=_KEY).log(
        event_type="meta_cognitive_audit",
        actor="openclaw",
        action="baseline_normal",
        layer="execution",
    )

    report = verify_audit_chain(path, hmac_key=_KEY)

    assert report.key_status == "valid"
    assert report.hash_invalid == []
    assert report.signature_invalid == []
    assert report.integrity_intact


def test_verify_accepts_historical_record_without_layer(tmp_path: Path) -> None:
    """历史记录丢失 layer 字段时，验证器按已知 layer 复算（不能报篡改）。"""
    path = tmp_path / "audit.jsonl"
    AuditLogger(path, hmac_key=_KEY).log(
        event_type="governance_cycle",
        actor="tiered-loop",
        action="tick",
        layer="orchestration",
    )

    row = json.loads(path.read_text().strip())
    assert row["layer"] == "orchestration"
    row.pop("layer")
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n")

    report = verify_audit_chain(path, hmac_key=_KEY)

    assert report.key_status == "valid"
    assert report.hash_invalid == []
    assert report.signature_invalid == []
    assert report.integrity_intact


def test_last_chain_hash_ignores_bypass_id(tmp_path: Path) -> None:
    """带 id 但无 chain_hash 的旁路记录不得被当作链尾（历史断链根因）。"""
    path = tmp_path / "governance_audit.jsonl"
    rows = [
        {"id": "audit_a", "chain_hash": "a" * 64},
        {"id": "openclaw_meta_cognitive_audit_1", "event": "meta_cognitive_audit"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    assert _last_chain_hash(path) == "a" * 64


def test_last_chain_hash_from_fh_ignores_bypass_id(tmp_path: Path) -> None:
    path = tmp_path / "governance_audit.jsonl"
    rows = [
        {"id": "audit_a", "chain_hash": "b" * 64},
        {"id": "openclaw_meta_cognitive_audit_1", "event": "meta_cognitive_audit"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    with open(path, "rb") as fh:
        assert _last_chain_hash_from_fh(fh) == "b" * 64
