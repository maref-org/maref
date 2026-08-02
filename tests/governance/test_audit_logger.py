"""
AuditLogger 独立测试

覆盖审计问题 P17：HMAC 签名验证、条目不可变性、文件轮转、to_unified 转换。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditEntry, AuditLogger


class TestAuditEntry:
    def test_entry_is_frozen(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
        )
        with pytest.raises(AttributeError):
            entry.event_type = "modified"

    def test_entry_to_dict(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=1234567890.0,
            event_type="governance_decision",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="test",
            metadata={"key": "value"},
        )
        d = entry.to_dict()
        assert d["id"] == "audit_000001"
        assert d["event_type"] == "governance_decision"
        assert "hmac_signature" not in d

    def test_entry_to_dict_with_signature(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            hmac_signature="abc123",
        )
        d = entry.to_dict()
        assert d["hmac_signature"] == "abc123"

    def test_payload_for_signing_stable(self) -> None:
        entry1 = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            metadata={"b": 2, "a": 1},
        )
        entry2 = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="test",
            actor="test",
            action="test",
            details="",
            metadata={"a": 1, "b": 2},
        )
        assert entry1._payload_for_signing() == entry2._payload_for_signing()


class TestAuditLoggerHMAC:
    def test_sign_entry_with_key(self) -> None:
        logger = AuditLogger(hmac_key="secret_key")
        entry = logger.log("test", "actor", "action")
        assert entry.hmac_signature != ""
        assert len(entry.hmac_signature) == 64  # SHA-256 hex

    def test_sign_entry_requires_key(self) -> None:
        # AuditLogger now requires either an Ed25519 keypair or an HMAC key
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            old_hmac = os.environ.pop("MAREF_HMAC_SECRET_KEY", None)
            old_ed = os.environ.pop("MAREF_ED25519_PRIVATE_KEY", None)
            try:
                with pytest.raises(RuntimeError, match="Ed25519 keypair or HMAC key"):
                    AuditLogger()
            finally:
                os.chdir(old_cwd)
                if old_hmac is not None:
                    os.environ["MAREF_HMAC_SECRET_KEY"] = old_hmac
                if old_ed is not None:
                    os.environ["MAREF_ED25519_PRIVATE_KEY"] = old_ed

    def test_verify_integrity_valid(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="secret")
        logger.log("test", "actor", "action")
        result = logger.verify_integrity()
        assert result["integrity_intact"] is True
        assert result["valid_signatures"] == 1
        assert result["tampered_entries"] == []

    def test_verify_integrity_tampered(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path, hmac_key="secret")
        logger.log("test", "actor", "action")
        # Tamper with the file
        with open(path) as f:
            line = f.read()
        data = json.loads(line)
        data["action"] = "tampered_action"
        with open(path, "w") as f:
            f.write(json.dumps(data) + "\n")
        result = logger.verify_integrity()
        assert result["integrity_intact"] is False
        assert len(result["tampered_entries"]) == 1


class TestAuditLoggerFileOperations:
    def test_log_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        logger = AuditLogger(log_path=path)
        logger.log("test_event", "TestActor", "test_action", "details")
        assert path.exists()
        entries = logger.read_all()
        assert len(entries) == 1
        assert entries[0].event_type == "test_event"

    def test_log_to_memory(self) -> None:
        logger = AuditLogger()
        logger.log("test", "actor", "action")
        entries = logger.read_all()
        assert len(entries) == 1

    def test_read_filtered(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("type_a", "actor1", "action")
        logger.log("type_b", "actor2", "action")
        logger.log("type_a", "actor1", "action")
        filtered = logger.read_filtered(event_type="type_a", actor="actor1")
        assert len(filtered) == 2

    def test_file_rotation(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        logger = AuditLogger(log_path=path, max_file_size_mb=0)
        logger.log("test", "actor", "action")
        # Force rotation by writing a large entry
        logger._max_file_size = 1  # 1 byte
        logger.log("test2", "actor", "action")
        assert any(path.parent.glob(f"{path.stem}_*{path.suffix}"))

    def test_read_all_limit(self) -> None:
        logger = AuditLogger()
        for i in range(10):
            logger.log(f"event_{i}", "actor", "action")
        entries = logger.read_all(max_entries=5)
        assert len(entries) == 5

    def test_count(self) -> None:
        logger = AuditLogger()
        assert logger.count() == 0
        logger.log("test", "actor", "action")
        assert logger.count() == 1


class TestAuditLoggerUnified:
    def test_to_unified(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="governance_decision",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="recovery success",
            metadata={"target_module": "meta_governance"},
        )
        unified = entry.to_unified(layer="governance", round_num=1)
        assert unified.record_id == "audit_000001"
        assert unified.layer == "governance"
        assert unified.round == 1
        assert unified.outcome == "success"

    def test_to_unified_failure(self) -> None:
        entry = AuditEntry(
            id="audit_000001",
            timestamp=0.0,
            event_type="circuit_breaker_trip",
            actor="CircuitBreaker",
            action="trip",
            details="failure detected",
        )
        unified = entry.to_unified()
        assert unified.outcome == "failure"

    def test_export_syslog(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("test", "actor", "action", "details")
        syslog = logger.export_syslog()
        assert "MAREF" in syslog
        assert 'actor="actor"' in syslog

    def test_export_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        logger = AuditLogger(log_path=path)
        logger.log("test", "actor", "action")
        exported = logger.export_json()
        assert len(exported) == 1
        assert exported[0]["event_type"] == "test"


class TestAuditLoggerEd25519:
    """Ed25519 signing compatibility tests (v0.38.0+)."""

    def test_ed25519_sign_and_verify(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        logger = AuditLogger(log_path=path, ed25519_keypair=keypair)
        entry = logger.log("test", "alice", "sign_test")
        assert entry.ed25519_signature, "Expected Ed25519 signature"
        assert entry.signer_fingerprint == keypair.fingerprint
        assert entry.hmac_signature == ""

        entries = logger.read_all()
        assert len(entries) == 1
        result = logger.verify_integrity(ed25519_public_key_pem=keypair.public_key_pem)
        assert result["integrity_intact"] is True

    def test_hmac_and_ed25519_entries_can_coexist(self) -> None:
        """Old HMAC entries remain readable alongside new Ed25519 entries."""
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        logger = AuditLogger(log_path=path, hmac_key=b"test-hmac-key")
        logger.log("test", "alice", "hmac_entry")
        logger = AuditLogger(log_path=path, ed25519_keypair=keypair)
        logger.log("test", "bob", "ed25519_entry")

        entries = logger.read_all()
        assert len(entries) == 2
        types = {e.signature_type for e in entries}
        assert "hmac" in types
        assert "ed25519" in types

    def test_ed25519_verify_detects_tamper(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        logger = AuditLogger(log_path=path, ed25519_keypair=keypair)
        logger.log("test", "alice", "entry1")
        logger.log("test", "bob", "entry2")

        with open(path) as f:
            data = f.read()
        with open(path, "w") as f:
            f.write(data.replace("entry2", "TAMPERED"))

        result = logger.verify_integrity(ed25519_public_key_pem=keypair.public_key_pem)
        assert result["integrity_intact"] is False
        assert len(result["tampered_entries"]) > 0

    def test_ed25519_in_memory_logger(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)

        logger.log("test", "alice", "in_memory")
        entries = logger.read_all()
        assert len(entries) == 1
        assert entries[0].ed25519_signature
        assert entries[0].chain_hash

        result = logger.verify_integrity(ed25519_public_key_pem=keypair.public_key_pem)
        assert result["integrity_intact"] is True


class TestAuditLoggerCausality:
    """P1-1: Delegation chain causality via parent_action_id."""

    def test_log_accepts_parent_action_id(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)

        parent = logger.log("parent", "alice", "parent_action")
        child = logger.log(
            "child",
            "bob",
            "child_action",
            parent_action_id=parent.id,
        )
        assert child.parent_action_id == parent.id

    def test_parent_action_id_in_to_dict(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)

        parent = logger.log("parent", "alice", "parent_action")
        child = logger.log(
            "child",
            "bob",
            "child_action",
            parent_action_id=parent.id,
        )
        d = child.to_dict()
        assert d.get("parent_action_id") == parent.id

    def test_parent_action_id_defaults_empty(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)

        entry = logger.log("test", "alice", "no_parent")
        assert entry.parent_action_id == ""
        d = entry.to_dict()
        assert "parent_action_id" not in d

    def test_parent_action_id_survives_serialization_roundtrip(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        logger = AuditLogger(log_path=path, ed25519_keypair=keypair)
        parent = logger.log("parent", "alice", "parent_action")
        logger.log("child", "bob", "child_action", parent_action_id=parent.id)

        read_logger = AuditLogger(log_path=path, ed25519_keypair=keypair)
        entries = read_logger.read_all()
        assert len(entries) == 2
        child = [e for e in entries if e.action == "child_action"][0]
        assert child.parent_action_id == parent.id
        assert child.signature_type == "ed25519"

    def test_parent_action_id_does_not_break_backward_compat(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)

        entry = logger.log("test", "alice", "old_style")
        d = entry.to_dict()
        assert "parent_action_id" not in d
        assert entry.parent_action_id == ""


class TestAuditLoggerVerifyNewMethods:
    """verify_integrity 修复新增方法专项测试（2026-08-02 review 补测）。

    覆盖 legacy payload 兼容、chain_hash 终裁、HMAC key 文件 fallback、
    bytes.fromhex 损坏签名防御、key 轮换 unverifiable 三态。
    """

    def _make_entry(self, **kw: object) -> AuditEntry:
        base: dict[str, object] = dict(
            id="e1",
            timestamp=1.0,
            event_type="test",
            actor="alice",
            action="act",
            details="",
        )
        base.update(kw)
        return AuditEntry(**base)  # type: ignore[arg-type]

    def test_legacy_payload_omits_unified_fields(self) -> None:
        logger = AuditLogger(hmac_key="secret")
        entry = self._make_entry(tenant_id="t1", layer="x", round=3)
        payload = json.loads(logger._legacy_payload(entry))
        assert "tenant_id" not in payload
        assert "layer" not in payload
        assert "round" not in payload
        assert payload["id"] == "e1"

    def test_verify_hmac_signature_current_and_legacy(self) -> None:
        logger = AuditLogger(hmac_key="secret")
        entry = self._make_entry()
        current = hmac.new(
            b"secret", entry._payload_for_signing().encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert logger._verify_hmac_signature(self._make_entry(hmac_signature=current), b"secret") is True
        legacy = hmac.new(
            b"secret", logger._legacy_payload(entry).encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert logger._verify_hmac_signature(self._make_entry(hmac_signature=legacy), b"secret") is True

    def test_verify_chain_hash_current_and_legacy(self) -> None:
        logger = AuditLogger(hmac_key="secret")
        entry = self._make_entry(previous_hash="")
        current = hashlib.sha256(b"" + entry._payload_for_signing().encode("utf-8")).hexdigest()
        assert logger._verify_chain_hash(self._make_entry(previous_hash="", chain_hash=current)) is True
        legacy = hashlib.sha256(b"" + logger._legacy_payload(entry).encode("utf-8")).hexdigest()
        assert logger._verify_chain_hash(self._make_entry(previous_hash="", chain_hash=legacy)) is True

    def test_resolve_hmac_key_prefers_configured(self) -> None:
        logger = AuditLogger(hmac_key="secret")
        assert logger._resolve_hmac_key_for_verify() == b"secret"

    def test_resolve_hmac_key_from_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        (tmp_path / ".maraf_hmac_key").write_text("file-secret\n")
        monkeypatch.chdir(tmp_path)
        logger = AuditLogger(log_path=None, ed25519_keypair=Ed25519KeyPair.generate())
        assert logger._resolve_hmac_key_for_verify() == b"file-secret"

    def test_resolve_hmac_key_none_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        monkeypatch.chdir(tmp_path)
        logger = AuditLogger(log_path=None, ed25519_keypair=Ed25519KeyPair.generate())
        assert logger._resolve_hmac_key_for_verify() is None

    def test_verify_entry_signature_valid(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)
        entry = logger.log("test", "alice", "act")
        assert logger._verify_entry_signature(entry, keypair.public_key_pem) is True

    def test_verify_entry_signature_malformed_hex(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        logger = AuditLogger(log_path=None, ed25519_keypair=keypair)
        entry = self._make_entry(ed25519_signature="zz-not-hex!!")
        assert logger._verify_entry_signature(entry, keypair.public_key_pem) is False

    def test_key_rotation_marks_unverifiable_not_tampered(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        AuditLogger(log_path=path, hmac_key="old-key").log("test", "alice", "entry1")
        AuditLogger(log_path=path, hmac_key="old-key").log("test", "bob", "entry2")
        verifier = AuditLogger(log_path=path, hmac_key="new-key")
        result = verifier.verify_integrity()
        assert result["valid_signatures"] == 0
        assert len(result["unverifiable_entries"]) == 2
        assert result["tampered_entries"] == []
        assert result["integrity_intact"] is True

    def test_mixed_signatures_verify_all_valid(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        keypair = Ed25519KeyPair.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        AuditLogger(log_path=path, hmac_key="secret").log("test", "alice", "hmac_entry")
        AuditLogger(log_path=path, ed25519_keypair=keypair).log("test", "bob", "ed_entry")
        verifier = AuditLogger(log_path=path, hmac_key="secret")
        result = verifier.verify_integrity(ed25519_public_key_pem=keypair.public_key_pem)
        assert result["valid_signatures"] == 2
        assert result["tampered_entries"] == []
        assert result["integrity_intact"] is True
