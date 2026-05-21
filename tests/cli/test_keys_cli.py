"""Tests for the `maref-lite keys` Click CLI subcommand."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from maref_lite.keys_cli import keys_cli

runner = CliRunner()


class TestKeysSet:
    def test_set_with_value_option(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = True
            instance.available = True
            result = runner.invoke(keys_cli, ["set", "--key", "DASHSCOPE_API_KEY", "--value", "secret123"])
            assert result.exit_code == 0
            assert "Stored DASHSCOPE_API_KEY in keychain" in result.output
            instance.set.assert_called_once_with("DASHSCOPE_API_KEY", "secret123")

    def test_set_with_short_flags(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = True
            instance.available = True
            result = runner.invoke(keys_cli, ["set", "-k", "OPENAI_API_KEY", "-v", "sk-test"])
            assert result.exit_code == 0
            assert "Stored OPENAI_API_KEY in keychain" in result.output
            instance.set.assert_called_once_with("OPENAI_API_KEY", "sk-test")

    def test_set_without_value_prompts(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = True
            instance.available = True
            result = runner.invoke(
                keys_cli,
                ["set", "--key", "ANTHROPIC_API_KEY"],
                input="my-secret\n",
            )
            assert result.exit_code == 0
            assert "Stored ANTHROPIC_API_KEY in keychain" in result.output
            instance.set.assert_called_once_with("ANTHROPIC_API_KEY", "my-secret")

    def test_set_from_stdin(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = True
            instance.available = True
            result = runner.invoke(
                keys_cli,
                ["set", "--key", "MAREF_ADMIN_TOKEN", "--stdin"],
                input="stdin-secret\n",
            )
            assert result.exit_code == 0
            assert "Stored MAREF_ADMIN_TOKEN in keychain" in result.output
            instance.set.assert_called_once_with("MAREF_ADMIN_TOKEN", "stdin-secret")

    def test_set_failure_shows_error(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = False
            instance.available = True
            result = runner.invoke(keys_cli, ["set", "--key", "DASHSCOPE_API_KEY", "--value", "secret"])
            assert result.exit_code == 0
            assert "Failed to store DASHSCOPE_API_KEY" in result.output

    def test_set_failure_shows_hint_when_keyring_unavailable(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.set.return_value = False
            instance.available = False
            result = runner.invoke(keys_cli, ["set", "--key", "DASHSCOPE_API_KEY", "--value", "secret"])
            assert result.exit_code == 0
            assert "Failed to store DASHSCOPE_API_KEY" in result.output
            assert "pip install keyring" in result.output

    def test_set_missing_key_option(self):
        result = runner.invoke(keys_cli, ["set"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "--key" in result.output


class TestKeysGet:
    def test_get_masked_default(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.get.return_value = "supersecretvalue"
            result = runner.invoke(keys_cli, ["get", "--key", "DASHSCOPE_API_KEY"])
            assert result.exit_code == 0
            assert result.output.strip() == "supe" + "*" * (len("supersecretvalue") - 4)
            instance.get.assert_called_once_with("DASHSCOPE_API_KEY")

    def test_get_show_flag(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.get.return_value = "supersecretvalue"
            result = runner.invoke(keys_cli, ["get", "--key", "DASHSCOPE_API_KEY", "--show"])
            assert result.exit_code == 0
            assert result.output.strip() == "supersecretvalue"

    def test_get_short_flags(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.get.return_value = "abc123"
            result = runner.invoke(keys_cli, ["get", "-k", "OPENAI_API_KEY", "-s"])
            assert result.exit_code == 0
            assert result.output.strip() == "abc123"

    def test_get_short_value_masks(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.get.return_value = "abcd"
            result = runner.invoke(keys_cli, ["get", "--key", "TEST_KEY"])
            assert result.exit_code == 0
            assert result.output.strip() == "****"

    def test_get_not_found(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.get.return_value = None
            result = runner.invoke(keys_cli, ["get", "--key", "UNKNOWN_KEY"])
            assert result.exit_code == 0
            assert "UNKNOWN_KEY not found" in result.output

    def test_get_missing_key_option(self):
        result = runner.invoke(keys_cli, ["get"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "--key" in result.output


class TestKeysDelete:
    def test_delete_with_confirmation_yes(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.delete.return_value = True
            result = runner.invoke(
                keys_cli,
                ["delete", "--key", "DASHSCOPE_API_KEY"],
                input="y\n",
            )
            assert result.exit_code == 0
            assert "Deleted DASHSCOPE_API_KEY from keychain" in result.output
            instance.delete.assert_called_once_with("DASHSCOPE_API_KEY")

    def test_delete_with_confirmation_no(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            result = runner.invoke(
                keys_cli,
                ["delete", "--key", "DASHSCOPE_API_KEY"],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Aborted." in result.output
            instance.delete.assert_not_called()

    def test_delete_with_yes_flag(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.delete.return_value = True
            result = runner.invoke(keys_cli, ["delete", "--key", "DASHSCOPE_API_KEY", "--yes"])
            assert result.exit_code == 0
            assert "Deleted DASHSCOPE_API_KEY from keychain" in result.output
            instance.delete.assert_called_once_with("DASHSCOPE_API_KEY")

    def test_delete_with_short_flags(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.delete.return_value = True
            result = runner.invoke(keys_cli, ["delete", "-k", "OPENAI_API_KEY", "-y"])
            assert result.exit_code == 0
            assert "Deleted OPENAI_API_KEY from keychain" in result.output

    def test_delete_failure(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.delete.return_value = False
            result = runner.invoke(keys_cli, ["delete", "--key", "DASHSCOPE_API_KEY", "--yes"])
            assert result.exit_code == 0
            assert "Failed to delete DASHSCOPE_API_KEY" in result.output

    def test_delete_missing_key_option(self):
        result = runner.invoke(keys_cli, ["delete"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "--key" in result.output


class TestKeysList:
    def test_list_outputs_status(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = [
                "DASHSCOPE_API_KEY",
                "OPENAI_API_KEY",
            ]
            instance.diagnose.return_value = {
                "system": "Darwin",
                "service": "com.maref.agent",
                "keyring_available": True,
                "keyring_backend": "keyring.backends.macOS.Keyring",
                "stored_keys": ["DASHSCOPE_API_KEY"],
                "env_vars": ["OPENAI_API_KEY"],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "MAREF Keychain Status" in result.output
            assert "Darwin" in result.output
            assert "com.maref.agent" in result.output
            assert "Available" in result.output
            assert "keyring.backends.macOS.Keyring" in result.output

    def test_list_shows_known_keys(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = [
                "DASHSCOPE_API_KEY",
                "OPENAI_API_KEY",
            ]
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": False,
                "stored_keys": [],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "Known Keys:" in result.output
            assert "DASHSCOPE_API_KEY" in result.output
            assert "OPENAI_API_KEY" in result.output

    def test_list_shows_env_status(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = ["DASHSCOPE_API_KEY"]
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": True,
                "stored_keys": [],
                "env_vars": ["DASHSCOPE_API_KEY"],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "[env]" in result.output

    def test_list_shows_keychain_status(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = ["DASHSCOPE_API_KEY"]
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": True,
                "stored_keys": ["DASHSCOPE_API_KEY"],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "[keychain]" in result.output

    def test_list_shows_combined_status(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = ["DASHSCOPE_API_KEY"]
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": True,
                "stored_keys": ["DASHSCOPE_API_KEY"],
                "env_vars": ["DASHSCOPE_API_KEY"],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "env, keychain" in result.output

    def test_list_shows_not_set(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = ["DASHSCOPE_API_KEY"]
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": True,
                "stored_keys": [],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "[not set]" in result.output

    def test_list_no_backend_when_unavailable(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.list_keys.return_value = []
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": False,
            }
            result = runner.invoke(keys_cli, ["list"])
            assert result.exit_code == 0
            assert "Not available" in result.output
            assert "Backend" not in result.output


class TestKeysDiagnose:
    def test_diagnose_all_passed(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.diagnose.return_value = {
                "system": "Darwin",
                "service": "com.maref.agent",
                "keyring_available": True,
                "keyring_backend": "keyring.backends.macOS.Keyring",
                "stored_keys": ["DASHSCOPE_API_KEY"],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["diagnose"])
            assert result.exit_code == 0
            assert "MAREF Keychain Diagnostic" in result.output
            assert "All checks passed" in result.output

    def test_diagnose_keyring_not_installed(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.diagnose.return_value = {
                "system": "Linux",
                "service": "com.maref.agent",
                "keyring_available": False,
                "stored_keys": [],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["diagnose"])
            assert result.exit_code == 0
            assert "WARNING: keyring library not installed" in result.output
            assert "pip install keyring" in result.output

    def test_diagnose_no_keys_stored(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.diagnose.return_value = {
                "system": "Darwin",
                "service": "com.maref.agent",
                "keyring_available": True,
                "keyring_backend": "keyring.backends.macOS.Keyring",
                "stored_keys": [],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["diagnose"])
            assert result.exit_code == 0
            assert "WARNING: No keys stored in keychain" in result.output
            assert "maref-lite keys set" in result.output

    def test_diagnose_shows_details(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.diagnose.return_value = {
                "system": "Darwin",
                "service": "com.maref.agent",
                "keyring_available": True,
                "keyring_backend": "keyring.backends.macOS.Keyring",
                "stored_keys": ["DASHSCOPE_API_KEY"],
                "env_vars": ["OPENAI_API_KEY"],
            }
            result = runner.invoke(keys_cli, ["diagnose"])
            assert result.exit_code == 0
            assert "Details:" in result.output
            assert "system: Darwin" in result.output
            assert "service: com.maref.agent" in result.output
            assert "env_vars" not in result.output

    def test_diagnose_multiple_issues(self):
        with patch("maref_lite.keys_cli.KeyringStore") as MockStore:
            instance = MockStore.return_value
            instance.diagnose.return_value = {
                "system": "Windows",
                "service": "com.maref.agent",
                "keyring_available": False,
                "stored_keys": [],
                "env_vars": [],
            }
            result = runner.invoke(keys_cli, ["diagnose"])
            assert result.exit_code == 0
            assert "Issues Found:" in result.output
            assert "keyring library not installed" in result.output
            assert "No keys stored" in result.output


class TestKeysCLIHelp:
    def test_keys_group_help(self):
        result = runner.invoke(keys_cli, ["--help"])
        assert result.exit_code == 0
        assert "Manage MAREF API keys and credentials" in result.output
        assert "set" in result.output
        assert "get" in result.output
        assert "delete" in result.output
        assert "list" in result.output
        assert "diagnose" in result.output

    def test_set_help(self):
        result = runner.invoke(keys_cli, ["set", "--help"])
        assert result.exit_code == 0
        assert "Store a credential" in result.output
        assert "--key" in result.output
        assert "--value" in result.output
        assert "--stdin" in result.output

    def test_get_help(self):
        result = runner.invoke(keys_cli, ["get", "--help"])
        assert result.exit_code == 0
        assert "Retrieve a credential" in result.output
        assert "--show" in result.output

    def test_delete_help(self):
        result = runner.invoke(keys_cli, ["delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a credential" in result.output
        assert "--yes" in result.output

    def test_list_help(self):
        result = runner.invoke(keys_cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all known key names" in result.output

    def test_diagnose_help(self):
        result = runner.invoke(keys_cli, ["diagnose", "--help"])
        assert result.exit_code == 0
        assert "Run diagnostic checks" in result.output
