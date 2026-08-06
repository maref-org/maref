from __future__ import annotations

import tempfile
from pathlib import Path

from maref.desktop.browser_auth import AuthSessionManager, AuthState


class TestAuthState:
    def test_to_dict(self) -> None:
        state = AuthState(
            domain="example.com",
            cookies_json='[{"name": "session"}]',
            created_at=1000.0,
            expires_at=2000.0,
            encrypted=False,
        )
        d = state.to_dict()
        assert d["domain"] == "example.com"
        assert d["encrypted"] is False


class TestAuthSessionManager:
    def test_init_creates_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            assert Path(td).exists()

    def test_save_and_load_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            state_id = manager.save_state(
                domain="example.com",
                cookies=[{"name": "session", "value": "abc123"}],
            )
            assert isinstance(state_id, str)
            assert len(state_id) > 0

            state = manager.load_state(state_id)
            assert state is not None
            assert state.domain == "example.com"

    def test_load_state_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            assert manager.load_state("nonexistent") is None

    def test_delete_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            state_id = manager.save_state(domain="example.com")
            assert manager.delete_state(state_id) is True

    def test_delete_nonexistent_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            assert manager.delete_state("nonexistent") is False

    def test_list_states(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = AuthSessionManager(storage_dir=td)
            manager.save_state(domain="a.com")
            manager.save_state(domain="b.com")
            states = manager.list_states()
            assert len(states) == 2
