from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

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


class TestCredentialManagerCRUD:
    def _make_manager(self, tmp_path: Path) -> CredentialManager:
        return CredentialManager(storage_dir=tmp_path)

    def test_register_creates_record(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="dashscope",
            credential_type=CredentialType.API_KEY,
            value="sk-test123",
            domain="api.dashscope.com",
        )
        assert record.name == "dashscope"
        assert record.credential_type == CredentialType.API_KEY
        assert record.domain == "api.dashscope.com"
        assert record.fingerprint == hashlib.sha256(b"sk-test123").hexdigest()[:16]
        assert record.status == CredentialStatus.ACTIVE
        assert record.credential_id.startswith("api_key:dashscope:")

    def test_register_with_expiry(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="temp-key",
            credential_type=CredentialType.API_KEY,
            value="sk-temp",
            expires_in=3600,
        )
        assert record.expires_at is not None
        assert record.expires_at > time.time()

    def test_register_with_rotation(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="rot-key",
            credential_type=CredentialType.HMAC_KEY,
            value="hmac-secret",
            rotation_interval=86400,
        )
        assert record.rotation_interval == 86400

    def test_register_with_metadata(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="meta-key",
            credential_type=CredentialType.API_KEY,
            value="val",
            metadata={"env": "prod"},
        )
        assert record.metadata == {"env": "prod"}

    def test_register_stored_in_keyring(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        mock_keyring = type("MockKeyring", (), {
            "set": lambda self, k, v: True,
            "get": lambda self, k, d=None: None,
            "delete": lambda self, k: True,
        })()
        manager._keyring_store = mock_keyring

        manager.register(
            name="kr-key",
            credential_type=CredentialType.API_KEY,
            value="kr-val",
        )
        assert mock_keyring.set("kr-key", "kr-val")

    def test_get_from_env(self, tmp_path: Path) -> None:
        import os
        os.environ["TEST_CRED_GET_ENV"] = "env-value"
        try:
            manager = self._make_manager(tmp_path)
            result = manager.get("TEST_CRED_GET_ENV")
            assert result == "env-value"
        finally:
            del os.environ["TEST_CRED_GET_ENV"]

    def test_get_expired_returns_none(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="expired-key",
            credential_type=CredentialType.API_KEY,
            value="val",
            expires_in=-1,
        )
        # Force expired status
        record.status = CredentialStatus.EXPIRED
        manager._records[record.credential_id] = record
        assert manager.get("expired-key") is None

    def test_get_from_keyring(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        mock_keyring = type("MockKeyring", (), {
            "set": lambda self, k, v: True,
            "get": lambda self, k, d=None: "kr-stored-value",
            "delete": lambda self, k: True,
        })()
        manager._keyring_store = mock_keyring
        assert manager.get("some-key") == "kr-stored-value"

    def test_rotate_updates_record(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="rot-key",
            credential_type=CredentialType.API_KEY,
            value="old-val",
        )
        old_fp = record.fingerprint
        rotated = manager.rotate(record.credential_id, "new-val")
        assert rotated.fingerprint != old_fp
        assert rotated.fingerprint == hashlib.sha256(b"new-val").hexdigest()[:16]
        assert rotated.status == CredentialStatus.ACTIVE

    def test_rotate_not_found_raises(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            manager.rotate("nonexistent:id", "val")

    def test_revoke_sets_status(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="rev-key",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        assert manager.revoke(record.credential_id, reason="compromised") is True
        assert manager._records[record.credential_id].status == CredentialStatus.REVOKED
        assert manager._records[record.credential_id].metadata["revoke_reason"] == "compromised"

    def test_revoke_not_found_returns_false(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager.revoke("nonexistent:id") is False

    def test_list_credentials_all(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(name="k1", credential_type=CredentialType.API_KEY, value="v1")
        manager.register(name="k2", credential_type=CredentialType.HMAC_KEY, value="v2")
        all_creds = manager.list_credentials()
        assert len(all_creds) == 2

    def test_list_credentials_filter_type(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(name="k1", credential_type=CredentialType.API_KEY, value="v1")
        manager.register(name="k2", credential_type=CredentialType.HMAC_KEY, value="v2")
        api_only = manager.list_credentials(credential_type=CredentialType.API_KEY)
        assert len(api_only) == 1
        assert api_only[0].name == "k1"

    def test_list_credentials_filter_status(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        r1 = manager.register(name="k1", credential_type=CredentialType.API_KEY, value="v1")
        manager.register(name="k2", credential_type=CredentialType.API_KEY, value="v2")
        manager.revoke(r1.credential_id)
        active = manager.list_credentials(status=CredentialStatus.ACTIVE)
        assert len(active) == 1

    def test_check_expiration(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(name="k1", credential_type=CredentialType.API_KEY, value="v1", expires_in=-1)
        expired = manager.check_expiration()
        assert len(expired) == 1

    def test_check_rotation_needed(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        r = manager.register(
            name="k1",
            credential_type=CredentialType.API_KEY,
            value="v1",
            rotation_interval=1,
        )
        r.last_rotated = time.time() - 10
        manager._records[r.credential_id] = r
        needs = manager.check_rotation_needed()
        assert len(needs) == 1

    def test_find_by_name(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(name="find-me", credential_type=CredentialType.API_KEY, value="v")
        found = manager._find_by_name("find-me")
        assert found is not None
        assert found.name == "find-me"

    def test_find_by_name_not_found(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        assert manager._find_by_name("nonexistent") is None


class TestAuditLogGracefulDegradation:
    def test_audit_log_does_not_raise_on_import_error(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        # _audit_log should not raise even if AuditLogger import fails
        manager._audit_log("test", "cred-001", "test-name")

    def test_audit_log_on_register(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        record = manager.register(
            name="audit-test",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        assert record.name == "audit-test"


def records_file_exists(tmp_path: Path) -> bool:
    return (tmp_path / "credential_records.json").exists()
