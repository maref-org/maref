from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from maref.identity.credential_manager import (
    CredentialManager,
    CredentialType,
)
from maref.identity.key_rotation import KeyRotator, RotationPolicy


class TestRotationPolicy:
    def test_default_api_key_policy(self) -> None:
        policy = KeyRotator.DEFAULT_POLICIES[CredentialType.API_KEY]
        assert policy.rotation_interval == 90 * 24 * 3600
        assert policy.warning_before == 7 * 24 * 3600
        assert policy.auto_rotate is False
        assert policy.max_age is None

    def test_default_oauth_token_policy(self) -> None:
        policy = KeyRotator.DEFAULT_POLICIES[CredentialType.OAUTH_TOKEN]
        assert policy.rotation_interval == 3600
        assert policy.warning_before == 300
        assert policy.auto_rotate is True

    def test_default_browser_session_policy(self) -> None:
        policy = KeyRotator.DEFAULT_POLICIES[CredentialType.BROWSER_SESSION]
        assert policy.rotation_interval == 24 * 3600
        assert policy.max_age == 7 * 24 * 3600

    def test_custom_policy(self) -> None:
        policy = RotationPolicy(
            rotation_interval=60,
            warning_before=10,
            auto_rotate=True,
            max_age=120,
        )
        assert policy.rotation_interval == 60
        assert policy.warning_before == 10
        assert policy.auto_rotate is True
        assert policy.max_age == 120


class TestKeyRotatorCheckAll:
    def _make_manager(self, tmp_path: Path) -> CredentialManager:
        return CredentialManager(storage_dir=tmp_path)

    def test_empty_credentials(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert results == []

    def test_active_credential_no_issues(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="good-key",
            credential_type=CredentialType.API_KEY,
            value="val",
            rotation_interval=90 * 24 * 3600,
        )
        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["needs_rotation"] is False
        assert results[0]["warning"] is False
        assert results[0]["reason"] == ""

    def test_expired_credential(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="old-key",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        record.expires_at = time.time() - 1
        manager._records[record.credential_id] = record

        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["needs_rotation"] is True
        assert results[0]["reason"] == "expired"

    def test_rotation_interval_reached(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="rot-key",
            credential_type=CredentialType.HMAC_KEY,
            value="val",
            rotation_interval=3600,
        )
        record.last_rotated = time.time() - 7200
        manager._records[record.credential_id] = record

        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["needs_rotation"] is True
        assert results[0]["reason"] == "rotation_interval_reached"

    def test_expiring_warning(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="expiring-key",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=200,  # 200s from now, warning_before is 300s
        )
        # warning_before for OAUTH_TOKEN is 300s, so 200 < 300 -> warning
        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["warning"] is True
        assert results[0]["needs_rotation"] is False
        assert "expires_in_" in results[0]["reason"]

    def test_revoked_credential(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="revoked-key",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        manager.revoke(record.credential_id, reason="test")

        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["reason"] == "revoked"

    def test_credential_without_policy_skipped(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="gov-cred",
            credential_type=CredentialType.GOVERNANCE_CREDENTIAL,
            value="val",
        )
        custom_policies: dict[CredentialType, RotationPolicy] = {}
        rotator = KeyRotator(manager, policies=custom_policies)
        results = rotator.check_all()
        assert results == []

    def test_max_age_exceeded(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        record = manager.register(
            name="old-session",
            credential_type=CredentialType.BROWSER_SESSION,
            value="val",
        )
        # created 8 days ago, max_age is 7 days
        record.created_at = time.time() - 8 * 24 * 3600
        # expires in 1 day (not yet expired)
        record.expires_at = time.time() + 24 * 3600
        manager._records[record.credential_id] = record

        rotator = KeyRotator(manager)
        results = rotator.check_all()
        assert len(results) == 1
        assert results[0]["needs_rotation"] is True
        assert results[0]["reason"] == "max_age_exceeded"


class TestKeyRotatorNotifyExpiring:
    def _make_manager(self, tmp_path: Path) -> CredentialManager:
        return CredentialManager(storage_dir=tmp_path)

    def test_no_expiring(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="ok-key",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=7200,  # 2 hours, warning_before is 300s
        )
        rotator = KeyRotator(manager)
        expiring = rotator.notify_expiring()
        assert expiring == []

    def test_expiring_detected(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="soon-expire",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=200,  # 200s from now, warning_before is 300s
        )
        rotator = KeyRotator(manager)
        expiring = rotator.notify_expiring()
        assert len(expiring) == 1
        assert expiring[0].name == "soon-expire"

    def test_callback_invoked(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="cb-key",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=100,
        )
        rotator = KeyRotator(manager)
        callback = MagicMock()
        rotator.register_rotation_callback(callback)

        rotator.notify_expiring()
        callback.assert_called_once()

    def test_callback_exception_does_not_propagate(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="err-key",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=100,
        )
        rotator = KeyRotator(manager)
        bad_callback = MagicMock(side_effect=RuntimeError("boom"))
        rotator.register_rotation_callback(bad_callback)

        # Should not raise
        expiring = rotator.notify_expiring()
        assert len(expiring) == 1
        bad_callback.assert_called_once()

    def test_no_expiry_not_included(self, tmp_path: Path) -> None:
        manager = self._make_manager(tmp_path)
        manager.register(
            name="no-exp",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        rotator = KeyRotator(manager)
        expiring = rotator.notify_expiring()
        assert expiring == []


class TestKeyRotatorCustomPolicies:
    def test_custom_policies_override(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="api-key",
            credential_type=CredentialType.API_KEY,
            value="val",
            rotation_interval=90 * 24 * 3600,
        )
        record = manager._find_by_name("api-key")
        assert record is not None
        # Set last_rotated to just under the default 90-day interval
        record.last_rotated = time.time() - (90 * 24 * 3600 - 1)
        manager._records[record.credential_id] = record

        # Custom policy with much shorter interval
        custom_policies = {
            CredentialType.API_KEY: RotationPolicy(
                rotation_interval=60,
                warning_before=30,
            ),
        }
        rotator = KeyRotator(manager, policies=custom_policies)
        results = rotator.check_all()
        # Credential's own rotation_interval is 90 days, not yet overdue
        assert results[0]["needs_rotation"] is False

    def test_register_multiple_callbacks(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="cb-key",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=100,
        )
        rotator = KeyRotator(manager)
        cb1 = MagicMock()
        cb2 = MagicMock()
        rotator.register_rotation_callback(cb1)
        rotator.register_rotation_callback(cb2)

        rotator.notify_expiring()
        cb1.assert_called_once()
        cb2.assert_called_once()
