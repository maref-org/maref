from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from maref.identity.credential_manager import (
    CredentialManager,
    CredentialRecord,
    CredentialStatus,
    CredentialType,
)


class TestCredentialType:
    def test_enum_values(self) -> None:
        assert CredentialType.API_KEY.value == "api_key"
        assert CredentialType.SIGNING_KEY.value == "signing_key"
        assert CredentialType.HMAC_KEY.value == "hmac_key"
        assert CredentialType.BROWSER_SESSION.value == "browser_session"
        assert CredentialType.OAUTH_TOKEN.value == "oauth_token"
        assert CredentialType.GOVERNANCE_CREDENTIAL.value == "governance_credential"

    def test_string_enum(self) -> None:
        assert CredentialType.API_KEY == "api_key"
        assert CredentialType("signing_key") == CredentialType.SIGNING_KEY


class TestCredentialStatus:
    def test_enum_values(self) -> None:
        assert CredentialStatus.ACTIVE.value == "active"
        assert CredentialStatus.EXPIRED.value == "expired"
        assert CredentialStatus.REVOKED.value == "revoked"
        assert CredentialStatus.PENDING_ROTATION.value == "pending_rotation"

    def test_string_enum(self) -> None:
        assert CredentialStatus.ACTIVE == "active"


class TestCredentialRecord:
    def test_create_basic(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="dashscope",
            domain="api.dashscope.com",
        )
        assert record.credential_id == "cred-001"
        assert record.credential_type == CredentialType.API_KEY
        assert record.name == "dashscope"
        assert record.domain == "api.dashscope.com"
        assert record.status == CredentialStatus.ACTIVE
        assert record.created_at > 0
        assert record.expires_at is None
        assert record.last_rotated is None
        assert record.rotation_interval is None
        assert record.metadata == {}
        assert record.fingerprint == ""

    def test_is_expired_no_expiry(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
        )
        assert record.is_expired() is False

    def test_is_expired_future(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
            expires_at=time.time() + 3600,
        )
        assert record.is_expired() is False

    def test_is_expired_past(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
            expires_at=time.time() - 1,
        )
        assert record.is_expired() is True

    def test_needs_rotation_no_interval(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
        )
        assert record.needs_rotation() is False

    def test_needs_rotation_no_last_rotated(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
            rotation_interval=3600,
        )
        assert record.needs_rotation() is False

    def test_needs_rotation_not_yet(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
            rotation_interval=3600,
            last_rotated=time.time(),
        )
        assert record.needs_rotation() is False

    def test_needs_rotation_overdue(self) -> None:
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
            rotation_interval=3600,
            last_rotated=time.time() - 7200,
        )
        assert record.needs_rotation() is True


class TestCredentialManager:
    def _make_manager(self, tmp_path: Path) -> CredentialManager:
        return CredentialManager(storage_dir=tmp_path)

    def test_init_creates_storage_dir(self, tmp_path: Path) -> None:
        storage = tmp_path / "creds"
        assert not storage.exists()
        CredentialManager(storage_dir=storage)
        assert storage.exists()

    def test_init_default_storage_dir(self) -> None:
        manager = CredentialManager()
        assert manager._storage_dir == Path.home() / ".maref" / "credentials"

    def test_load_records_empty(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert len(manager._records) == 0

    def test_load_records_corrupt_file(self, tmp_path: Path) -> None:
        records_file = tmp_path / "credential_records.json"
        records_file.write_text("not valid json {{{")
        manager = self._make_manager(tmp_path)
        assert len(manager._records) == 0

    def test_save_records_creates_file(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test-key",
            domain="api.example.com",
        )
        manager._records["cred-001"] = record
        manager._save_records()

        assert records_file_exists(tmp_path)
        raw = (tmp_path / "credential_records.json").read_text()
        decrypted = manager._decrypt(raw)
        data = json.loads(decrypted)
        assert len(data) == 1
        assert data[0]["credential_id"] == "cred-001"
        assert data[0]["credential_type"] == "api_key"
        assert data[0]["name"] == "test-key"
        assert data[0]["domain"] == "api.example.com"
        assert data[0]["status"] == "active"

    def test_load_records_roundtrip(self, tmp_path: Path) -> None:
        manager1 = self._make_manager(tmp_path)
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.SIGNING_KEY,
            name="signing",
            domain="auth.example.com",
            expires_at=time.time() + 86400,
            last_rotated=time.time() - 3600,
            rotation_interval=86400,
            status=CredentialStatus.ACTIVE,
            metadata={"algo": "ed25519"},
            fingerprint="abc123",
        )
        manager1._records["cred-001"] = record
        manager1._save_records()

        manager2 = self._make_manager(tmp_path)
        loaded = manager2._records["cred-001"]
        assert loaded.credential_id == "cred-001"
        assert loaded.credential_type == CredentialType.SIGNING_KEY
        assert loaded.name == "signing"
        assert loaded.domain == "auth.example.com"
        assert loaded.expires_at is not None
        assert loaded.last_rotated is not None
        assert loaded.rotation_interval == 86400
        assert loaded.status == CredentialStatus.ACTIVE
        assert loaded.metadata == {"algo": "ed25519"}
        assert loaded.fingerprint == "abc123"

    def test_encryption_key_from_param(self, tmp_path: Path) -> None:
        manager = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"my-secret"
        )
        assert len(manager._encryption_key) == 32

    def test_encryption_key_from_env(self, tmp_path: Path) -> None:
        import os

        os.environ["MAREF_CREDENTIAL_ENCRYPTION_KEY"] = "env-secret-key"
        try:
            manager = CredentialManager(storage_dir=tmp_path)
            assert len(manager._encryption_key) == 32
        finally:
            del os.environ["MAREF_CREDENTIAL_ENCRYPTION_KEY"]

    def test_encryption_key_dev_fallback(self, tmp_path: Path) -> None:
        import os

        os.environ.pop("MAREF_CREDENTIAL_ENCRYPTION_KEY", None)
        manager = CredentialManager(storage_dir=tmp_path)
        expected = hashlib.sha256(b"maref-dev-credential-key").digest()
        assert manager._encryption_key == expected


class TestCredentialManagerEncryption:
    def test_encrypt_decrypt_roundtrip(self, tmp_path: Path) -> None:
        manager = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"secret-key"
        )
        plaintext = "hello world"
        encrypted = manager._encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = manager._decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self, tmp_path: Path) -> None:
        manager = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"secret-key"
        )
        enc1 = manager._encrypt("same text")
        enc2 = manager._encrypt("same text")
        assert enc1 != enc2

    def test_save_load_encrypted_records(self, tmp_path: Path) -> None:
        manager1 = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"secret-key"
        )
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test-key",
            domain="api.example.com",
        )
        manager1._records["cred-001"] = record
        manager1._save_records()

        # File should not contain plaintext
        raw = (tmp_path / "credential_records.json").read_text()
        assert "cred-001" not in raw
        assert "api_key" not in raw

        manager2 = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"secret-key"
        )
        loaded = manager2._records["cred-001"]
        assert loaded.credential_id == "cred-001"
        assert loaded.name == "test-key"

    def test_load_with_wrong_key_raises(self, tmp_path: Path) -> None:
        manager1 = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"key1"
        )
        manager1._records["cred-001"] = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
        )
        manager1._save_records()

        manager2 = CredentialManager(
            storage_dir=tmp_path, encryption_key=b"wrong-key"
        )
        assert len(manager2._records) == 0

    def test_dev_fallback_warning(self, tmp_path: Path, caplog) -> None:
        import os
        import logging

        os.environ.pop("MAREF_CREDENTIAL_ENCRYPTION_KEY", None)
        with caplog.at_level(logging.WARNING):
            CredentialManager(storage_dir=tmp_path)
        assert any("dev fallback" in r.message.lower() for r in caplog.records)

    def test_load_records_warns_on_corrupt(self, tmp_path: Path, caplog) -> None:
        import logging

        records_file = tmp_path / "credential_records.json"
        records_file.write_text("not valid json")
        with caplog.at_level(logging.WARNING):
            CredentialManager(storage_dir=tmp_path)
        assert any("load" in r.message.lower() for r in caplog.records)

    def test_load_records_skips_bad_record(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        raw_data = [
            {"credential_id": "bad-record"},
            {
                "credential_id": "good-record",
                "credential_type": "api_key",
                "name": "test",
                "domain": "example.com",
                "created_at": 1.0,
                "expires_at": None,
                "last_rotated": None,
                "rotation_interval": None,
                "status": "active",
                "metadata": {},
                "fingerprint": "",
            },
        ]
        encrypted = manager._encrypt(json.dumps(raw_data))
        records_file = tmp_path / "credential_records.json"
        records_file.write_text(encrypted)
        manager2 = CredentialManager(storage_dir=tmp_path)
        assert len(manager2._records) == 1
        assert "good-record" in manager2._records

    def test_atomic_write_no_corruption(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        record = CredentialRecord(
            credential_id="cred-001",
            credential_type=CredentialType.API_KEY,
            name="test",
            domain="example.com",
        )
        manager._records["cred-001"] = record
        manager._save_records()

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

        data = json.loads(manager._decrypt(
            manager._records_file.read_text()
        ))
        assert len(data) == 1


def records_file_exists(tmp_path: Path) -> bool:
    return (tmp_path / "credential_records.json").exists()
