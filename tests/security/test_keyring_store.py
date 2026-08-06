from __future__ import annotations

from unittest.mock import MagicMock, patch

from maref.security.keyring_store import KeyringStore


class TestKeyringStore:
    def test_get_returns_default_when_no_env_or_keyring(self) -> None:
        store = KeyringStore()
        store._keyring_available = False
        result = store.get("MAREF_NONEXISTENT_KEY", default="fallback")
        assert result == "fallback"

    def test_env_var_takes_priority(self) -> None:
        store = KeyringStore()
        store._keyring_available = False
        with patch.dict("os.environ", {"TEST_KEYRING_VAR": "env_value"}, clear=False):
            result = store.get("TEST_KEYRING_VAR", default="fallback")
        assert result == "env_value"

    def test_env_var_takes_priority_over_keyring(self) -> None:
        store = KeyringStore()
        store._keyring_available = True
        with (
            patch("maref.security.keyring_store.keyring", create=True) as mock_keyring,
            patch.dict("os.environ", {"TEST_PRIORITY_KEY": "env_value"}, clear=False),
        ):
            mock_keyring.get_password.return_value = "keyring_value"
            result = store.get("TEST_PRIORITY_KEY", default="fallback")
        assert result == "env_value"

    def test_get_falls_back_to_default_on_keyring_error(self) -> None:
        store = KeyringStore()
        store._keyring_available = True
        with patch("maref.security.keyring_store.keyring", create=True) as mock_keyring:
            mock_keyring.get_password.side_effect = RuntimeError("keyring unavailable")
            result = store.get("NONEXISTENT", default="fallback")
        assert result == "fallback"

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_set_and_get_roundtrip(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.return_value = "stored_value"

        store = KeyringStore()
        store._keyring_available = True

        result = store.set("MAREF_TEST_KEY", "stored_value")
        assert result is True

        value = store.get("MAREF_TEST_KEY")
        assert value == "stored_value"

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_delete_removes_value(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.return_value = None

        store = KeyringStore()
        store._keyring_available = True

        store.delete("MAREF_TEST_KEY")
        value = store.get("MAREF_TEST_KEY")
        assert value is None

    def test_set_rejects_empty_value(self) -> None:
        store = KeyringStore()
        store._keyring_available = True
        with patch("maref.security.keyring_store.keyring", create=True):
            result = store.set("MAREF_TEST_KEY", "")
        assert result is False

    def test_set_returns_false_when_keyring_unavailable(self) -> None:
        store = KeyringStore()
        store._keyring_available = False
        result = store.set("MAREF_TEST_KEY", "secret")
        assert result is False

    def test_delete_returns_false_when_keyring_unavailable(self) -> None:
        store = KeyringStore()
        store._keyring_available = False
        result = store.delete("MAREF_TEST_KEY")
        assert result is False

    def test_list_keys_returns_known_keys(self) -> None:
        store = KeyringStore()
        keys = store.list_keys()
        assert isinstance(keys, list)
        assert "DASHSCOPE_API_KEY" in keys
        assert "OPENAI_API_KEY" in keys
        assert "ANTHROPIC_API_KEY" in keys
        assert "MAREF_ADMIN_TOKEN" in keys

    def test_available_property(self) -> None:
        store = KeyringStore()
        store._keyring_available = True
        assert store.available is True

        store._keyring_available = False
        assert store.available is False

    def test_diagnose_returns_structure(self) -> None:
        store = KeyringStore()
        store._keyring_available = False
        diag = store.diagnose()
        assert isinstance(diag, dict)
        assert "system" in diag
        assert "service" in diag
        assert diag["service"] == "com.maref.agent"
        assert diag["keyring_available"] is False

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_diagnose_with_keyring(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_keyring.return_value.name = "memory"
        mock_keyring.get_password.return_value = None

        store = KeyringStore()
        store._keyring_available = True
        diag = store.diagnose()
        assert diag["keyring_available"] is True

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_set_calls_keyring_set_password(self, mock_keyring: MagicMock) -> None:
        store = KeyringStore()
        store._keyring_available = True
        store.set("MAREF_TEST_KEY", "my_secret")
        mock_keyring.set_password.assert_called_once_with(
            "com.maref.agent", "MAREF_TEST_KEY", "my_secret"
        )

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_delete_calls_keyring_delete_password(self, mock_keyring: MagicMock) -> None:
        store = KeyringStore()
        store._keyring_available = True
        store.delete("MAREF_TEST_KEY")
        mock_keyring.delete_password.assert_called_once_with(
            "com.maref.agent", "MAREF_TEST_KEY"
        )

    def test_default_service_name(self) -> None:
        store = KeyringStore()
        assert store._service == "com.maref.agent"

    def test_custom_service_name(self) -> None:
        store = KeyringStore(service_name="custom.service")
        assert store._service == "custom.service"

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_set_returns_false_on_keyring_error(self, mock_keyring: MagicMock) -> None:
        mock_keyring.set_password.side_effect = RuntimeError("keyring failure")
        store = KeyringStore()
        store._keyring_available = True
        result = store.set("MAREF_TEST_KEY", "secret")
        assert result is False

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_delete_returns_false_on_keyring_error(self, mock_keyring: MagicMock) -> None:
        mock_keyring.delete_password.side_effect = RuntimeError("keyring failure")
        store = KeyringStore()
        store._keyring_available = True
        result = store.delete("MAREF_TEST_KEY")
        assert result is False

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_diagnose_unknown_backend_on_keyring_error(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_keyring.side_effect = RuntimeError("no backend")
        store = KeyringStore()
        store._keyring_available = True
        diag = store.diagnose()
        assert diag["keyring_backend"] == "unknown"

    @patch("maref.security.keyring_store.keyring", create=True)
    def test_diagnose_skips_stored_keys_on_keyring_error(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_keyring.return_value.name = "memory"
        mock_keyring.get_password.side_effect = RuntimeError("keyring failure")
        store = KeyringStore()
        store._keyring_available = True
        diag = store.diagnose()
        assert diag["stored_keys"] == []
