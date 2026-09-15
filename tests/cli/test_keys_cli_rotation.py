"""Tests for the rotate and audit CLI commands."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from maref.identity.credential_manager import (
    CredentialManager,
    CredentialType,
)
from maref_lite.keys_cli import keys_cli

runner = CliRunner()


class TestKeysRotate:
    def test_rotate_success(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="test-key",
            credential_type=CredentialType.API_KEY,
            value="old-value",
        )

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(
                keys_cli,
                ["rotate", "--key", "test-key"],
                input="new-value\n",
            )
            assert result.exit_code == 0
            assert "Rotated test-key" in result.output

    def test_rotate_not_found(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(
                keys_cli,
                ["rotate", "--key", "nonexistent"],
                input="val\n",
            )
            assert result.exit_code == 0
            assert "not found" in result.output

    def test_rotate_short_flags(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="my-key",
            credential_type=CredentialType.HMAC_KEY,
            value="old",
        )

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(
                keys_cli,
                ["rotate", "-k", "my-key"],
                input="new\n",
            )
            assert result.exit_code == 0
            assert "Rotated my-key" in result.output


class TestKeysAudit:
    def test_audit_empty(self) -> None:
        manager = MagicMock()
        manager.list_credentials.return_value = []

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(keys_cli, ["audit"])
            assert result.exit_code == 0
            assert "Credential Audit Report" in result.output
            assert "Total credentials: 0" in result.output

    def test_audit_with_credentials(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="api-key",
            credential_type=CredentialType.API_KEY,
            value="val",
            rotation_interval=90 * 24 * 3600,
        )
        manager.register(
            name="hmac-key",
            credential_type=CredentialType.HMAC_KEY,
            value="hval",
            rotation_interval=180 * 24 * 3600,
        )

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(keys_cli, ["audit"])
            assert result.exit_code == 0
            assert "Credential Audit Report" in result.output
            assert "Total credentials: 2" in result.output
            assert "Needs rotation: 0" in result.output

    def test_audit_shows_expiring(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        manager.register(
            name="oauth-token",
            credential_type=CredentialType.OAUTH_TOKEN,
            value="val",
            expires_in=200,  # 200s from now, warning_before is 300s
        )

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(keys_cli, ["audit"])
            assert result.exit_code == 0
            assert "Warnings: 1" in result.output

    def test_audit_shows_needs_rotation(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        record = manager.register(
            name="old-hmac",
            credential_type=CredentialType.HMAC_KEY,
            value="val",
            rotation_interval=3600,
        )
        record.last_rotated = time.time() - 7200
        manager._records[record.credential_id] = record

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(keys_cli, ["audit"])
            assert result.exit_code == 0
            assert "Needs rotation: 1" in result.output

    def test_audit_shows_revoked(self, tmp_path: Path) -> None:
        manager = CredentialManager(storage_dir=tmp_path)
        record = manager.register(
            name="revoked",
            credential_type=CredentialType.API_KEY,
            value="val",
        )
        manager.revoke(record.credential_id, reason="test")

        with patch("maref.identity.credential_manager.CredentialManager") as MockManager:
            MockManager.return_value = manager
            result = runner.invoke(keys_cli, ["audit"])
            assert result.exit_code == 0
            assert "revoked" in result.output


class TestKeysCLIHelpUpdated:
    def test_help_includes_rotate(self) -> None:
        result = runner.invoke(keys_cli, ["--help"])
        assert result.exit_code == 0
        assert "rotate" in result.output

    def test_help_includes_audit(self) -> None:
        result = runner.invoke(keys_cli, ["--help"])
        assert result.exit_code == 0
        assert "audit" in result.output

    def test_rotate_help(self) -> None:
        result = runner.invoke(keys_cli, ["rotate", "--help"])
        assert result.exit_code == 0
        assert "Rotate a credential" in result.output
        assert "--key" in result.output

    def test_audit_help(self) -> None:
        result = runner.invoke(keys_cli, ["audit", "--help"])
        assert result.exit_code == 0
        assert "Audit credential status" in result.output
