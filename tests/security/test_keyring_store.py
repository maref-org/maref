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
