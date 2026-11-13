"""GB/Z 185.8 授权裁决字段（primary_subject / immediate_actor / actor_chain）。

验证三件事：
1. 默认空值时，记录形态与签名载荷与旧版完全一致（向后兼容）；
2. 非空时进入 to_dict 与签名载荷（防篡改）；
3. 字段变化会改变 chain_hash，读取后可还原。
"""

from __future__ import annotations

import json

from maref.governance.audit import AuditEntry, AuditLogger


def _base_entry(**kw):
    return AuditEntry(
        id="e1",
        timestamp=1.0,
        event_type="governance_decision",
        actor="agent:A",
        action="approve",
        details="ok",
        **kw,
    )


class TestDefaults:
    def test_empty_fields_absent_from_dict(self):
        d = _base_entry().to_dict()
        assert "primary_subject" not in d
        assert "immediate_actor" not in d
        assert "actor_chain" not in d

    def test_empty_fields_absent_from_signing_payload(self):
        payload = json.loads(_base_entry()._payload_for_signing())
        assert "primary_subject" not in payload
        assert "immediate_actor" not in payload
        assert "actor_chain" not in payload

    def test_old_record_dict_roundtrip(self):
        # 旧记录：JSON 中完全没有这三个键
        entry = AuditLogger._entry_from_dict(
            {
                "id": "e1",
                "timestamp": 1.0,
                "event_type": "governance_decision",
                "actor": "agent:A",
                "action": "approve",
                "details": "ok",
            }
        )
        assert entry is not None
        assert entry.primary_subject == ""
        assert entry.immediate_actor == ""
        assert entry.actor_chain == ()


class TestPopulated:
    def test_fields_serialized(self):
        d = _base_entry(
            primary_subject="human:alice",
            immediate_actor="agent:A",
            actor_chain=("human:alice", "agent:A"),
        ).to_dict()
        assert d["primary_subject"] == "human:alice"
        assert d["immediate_actor"] == "agent:A"
        assert d["actor_chain"] == ["human:alice", "agent:A"]

    def test_fields_enter_signing_payload(self):
        payload = json.loads(
            _base_entry(
                primary_subject="human:alice",
                immediate_actor="agent:A",
                actor_chain=("human:alice", "agent:A"),
            )._payload_for_signing()
        )
        assert payload["primary_subject"] == "human:alice"
        assert payload["actor_chain"] == ["human:alice", "agent:A"]

    def test_field_change_changes_payload(self):
        a = _base_entry(primary_subject="human:alice")._payload_for_signing()
        b = _base_entry(primary_subject="human:bob")._payload_for_signing()
        assert a != b

    def test_from_dict_restores_chain_as_tuple(self):
        entry = AuditLogger._entry_from_dict(
            {
                "id": "e1",
                "timestamp": 1.0,
                "event_type": "governance_decision",
                "actor": "agent:A",
                "action": "approve",
                "details": "ok",
                "primary_subject": "human:alice",
                "immediate_actor": "agent:A",
                "actor_chain": ["human:alice", "agent:A"],
            }
        )
        assert entry is not None
        assert isinstance(entry.actor_chain, tuple)
        assert entry.actor_chain == ("human:alice", "agent:A")


class TestLoggerIntegration:
    def test_log_with_fields_verifies_and_reads_back(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(path), hmac_key="k-gbz185")
        logger.log(
            "governance_decision",
            "agent:A",
            "approve",
            details="human approved",
            primary_subject="human:alice",
            immediate_actor="agent:A",
            actor_chain=("human:alice", "agent:A"),
        )
        logger.log("governance_decision", "agent:A", "deny", details="policy deny")

        result = logger.verify_integrity()
        assert result["integrity_intact"] is True
        assert result["valid_signatures"] == 2

        entries = logger.read_all()
        assert entries[0].primary_subject == "human:alice"
        assert entries[0].actor_chain == ("human:alice", "agent:A")
        assert entries[1].primary_subject == ""
        assert entries[1].actor_chain == ()


class TestNullRobustness:
    def test_null_actor_chain_does_not_break_parsing(self):
        entry = AuditLogger._entry_from_dict(
            {
                "id": "e1",
                "timestamp": 1.0,
                "event_type": "governance_decision",
                "actor": "agent:A",
                "action": "approve",
                "details": "ok",
                "actor_chain": None,
            }
        )
        assert entry is not None
        assert entry.actor_chain == ()
