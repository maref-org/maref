"""Tests for KeyringStore — OS-native credential storage."""

from unittest.mock import MagicMock, patch

import pytest

from maref.security.keyring_store import KeyringStore


@pytest.fixture
def mock_keyring():
    mock = MagicMock()
    mock.get_password.return_value = None
    mock.set_password.return_value = None
    with patch("maref.security.keyring_store.HAS_KEYRING", True), \
         patch("maref.security.keyring_store.keyring", mock, create=True):
        yield mock


class TestKeyringStoreWithoutKeyring:
    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_available_false(self):
        store = KeyringStore()
        assert store.available is False

    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_get_returns_env(self):
        store = KeyringStore()
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": "env-key"}, clear=True):
            val = store.get("DASHSCOPE_API_KEY")
        assert val == "env-key"

    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_get_returns_default(self):
        store = KeyringStore()
        with patch.dict("os.environ", {}, clear=True):
            val = store.get("MISSING_KEY", default="fallback")
        assert val == "fallback"

    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_get_returns_none_when_no_default(self):
        store = KeyringStore()
        with patch.dict("os.environ", {}, clear=True):
            val = store.get("MISSING_KEY")
        assert val is None

    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_set_returns_false(self):
        store = KeyringStore()
        result = store.set("MY_KEY", "my-value")
        assert result is False

    @patch("maref.security.keyring_store.HAS_KEYRING", False)
    def test_delete_returns_false(self):
        store = KeyringStore()
        result = store.delete("MY_KEY")
        assert result is False


class TestKeyringStoreWithKeyring:
    def test_available_true(self, mock_keyring):
        store = KeyringStore()
        assert store.available is True

    def test_get_from_keyring(self, mock_keyring):
        mock_keyring.get_password.return_value = "kr-value"
        store = KeyringStore()
        with patch.dict("os.environ", {}, clear=True):
            val = store.get("OPENAI_API_KEY")
        assert val == "kr-value"
        mock_keyring.get_password.assert_called_with("com.maref.agent", "OPENAI_API_KEY")

    def test_get_env_overrides_keyring(self, mock_keyring):
        mock_keyring.get_password.return_value = "kr-value"
        store = KeyringStore()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-value"}, clear=True):
            val = store.get("OPENAI_API_KEY")
        assert val == "env-value"

    def test_get_from_keyring_exception(self, mock_keyring, caplog):
        caplog.set_level("DEBUG", logger="maref.security.keyring_store")
        mock_keyring.get_password.side_effect = RuntimeError("keychain error")
        store = KeyringStore()
        with patch.dict("os.environ", {}, clear=True):
            val = store.get("MISSING", default="fallback")
        assert val == "fallback"
        assert any("Keyring get failed" in msg for msg in caplog.messages)

    def test_set_success(self, mock_keyring):
        store = KeyringStore()
        result = store.set("MY_KEY", "my-value")
        assert result is True
        mock_keyring.set_password.assert_called_with("com.maref.agent", "MY_KEY", "my-value")

    def test_set_empty_value_fails(self, mock_keyring):
        store = KeyringStore()
        result = store.set("MY_KEY", "")
        assert result is False

    def test_set_exception_returns_false(self, mock_keyring):
        mock_keyring.set_password.side_effect = RuntimeError("keychain locked")
        store = KeyringStore()
        result = store.set("MY_KEY", "val")
        assert result is False

    def test_delete_success(self, mock_keyring):
        store = KeyringStore()
        result = store.delete("MY_KEY")
        assert result is True
        mock_keyring.delete_password.assert_called_with("com.maref.agent", "MY_KEY")

    def test_delete_exception_returns_false(self, mock_keyring):
        mock_keyring.delete_password.side_effect = RuntimeError("not found")
        store = KeyringStore()
        result = store.delete("MY_KEY")
        assert result is False

    def test_list_keys(self, mock_keyring):
        store = KeyringStore()
        keys = store.list_keys()
        assert "DASHSCOPE_API_KEY" in keys
        assert "MAREF_ADMIN_TOKEN" in keys
        assert len(keys) == 4

    def test_diagnose(self, mock_keyring):
        mock_keyring.get_keyring.return_value.name = "macOS Keychain"
        mock_keyring.get_password.return_value = "stored-val"
        store = KeyringStore()
        diag = store.diagnose()
        assert diag["keyring_available"] is True
        assert diag["keyring_backend"] == "macOS Keychain"
        assert "ANTHROPIC_API_KEY" in diag["stored_keys"]
        assert diag["service"] == "com.maref.agent"

    def test_diagnose_backend_unknown(self, mock_keyring):
        mock_keyring.get_keyring.side_effect = RuntimeError("no backend")
        mock_keyring.get_password.return_value = None
        store = KeyringStore()
        diag = store.diagnose()
        assert diag["keyring_backend"] == "unknown"
        assert diag["stored_keys"] == []

    def test_diagnose_password_exception_skips_key(self, mock_keyring):
        mock_keyring.get_keyring.return_value.name = "test"
        mock_keyring.get_password.side_effect = RuntimeError("fail")
        store = KeyringStore()
        diag = store.diagnose()
        assert diag["stored_keys"] == []

    def test_custom_service_name(self, mock_keyring):
        store = KeyringStore(service_name="custom.app")
        assert store._service == "custom.app"
