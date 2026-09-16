"""Tests for api_auth.py CredentialManager integration (Task 6)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidecar.api_auth import (
    APIKeyManager,
    AuthMiddleware,
    _load_keys,
    _reset_credential_manager,
    require_auth,
)


@pytest.fixture(autouse=True)
def clear_keys():
    _reset_credential_manager()
    APIKeyManager.reload()
    _reset_credential_manager()
    yield
    _reset_credential_manager()
    APIKeyManager.reload()
    _reset_credential_manager()


class TestCredentialManagerIntegration:
    """测试 CredentialManager 与 api_auth.py 的集成"""

    def test_load_keys_uses_credential_manager_when_available(
        self, tmp_path: Path
    ) -> None:
        """当 CredentialManager 可用时，优先使用它获取 API 密钥"""
        mock_manager = MagicMock()
        mock_manager.get.side_effect = lambda name: {
            "MAREF_API_KEY": "cm-api-key",
            "MAREF_API_KEY_2": "cm-backup-key",
            "MAREF_API_KEY_SCOPES": "read,write",
        }.get(name)

        with patch(
            "maref.identity.credential_manager.CredentialManager",
            return_value=mock_manager,
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            _load_keys()

            assert api_auth._API_KEYS == ["cm-api-key", "cm-backup-key"]
            assert api_auth._ALLOWED_SCOPES == ["read", "write"]

    def test_load_keys_falls_back_to_env_when_import_fails(self) -> None:
        """当 CredentialManager 导入失败时，回退到环境变量"""
        import sys

        with patch.dict(
            os.environ,
            {"MAREF_API_KEY": "env-key", "MAREF_API_KEY_2": "env-backup"},
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            # sys.modules[...]=None → 该模块 import 抛 ImportError（精准，不影响本测试其它 import）
            with patch.dict(sys.modules, {"maref.identity.credential_manager": None}):
                _load_keys()

            assert "env-key" in api_auth._API_KEYS
            assert "env-backup" in api_auth._API_KEYS

    def test_load_keys_credential_manager_takes_priority_over_env(
        self, tmp_path: Path
    ) -> None:
        """CredentialManager 优先于环境变量"""
        mock_manager = MagicMock()
        mock_manager.get.side_effect = lambda name: {
            "MAREF_API_KEY": "cm-priority-key",
        }.get(name)

        with patch.dict(os.environ, {"MAREF_API_KEY": "env-key"}), patch(
            "maref.identity.credential_manager.CredentialManager",
            return_value=mock_manager,
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            _load_keys()

            assert api_auth._API_KEYS == ["cm-priority-key"]

    def test_load_keys_credential_manager_returns_none_falls_back_to_env(
        self, tmp_path: Path
    ) -> None:
        """CredentialManager.get() 返回 None 时回退到环境变量"""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None

        with patch.dict(os.environ, {"MAREF_API_KEY": "env-fallback"}), patch(
            "maref.identity.credential_manager.CredentialManager",
            return_value=mock_manager,
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            _load_keys()

            assert "env-fallback" in api_auth._API_KEYS

    def test_auth_works_with_credential_manager_key(self, tmp_path: Path) -> None:
        """使用 CredentialManager 提供的密钥进行认证"""
        mock_manager = MagicMock()
        mock_manager.get.side_effect = lambda name: {
            "MAREF_API_KEY": "cm-secret-key",
        }.get(name)

        with patch(
            "maref.identity.credential_manager.CredentialManager",
            return_value=mock_manager,
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            APIKeyManager.reload()

            a = FastAPI()
            a.add_middleware(AuthMiddleware)

            @a.get("/api/protected")
            @require_auth()
            def protected():
                return {"status": "ok"}

            client = TestClient(a)
            resp = client.get(
                "/api/protected",
                headers={"Authorization": "Bearer cm-secret-key"},
            )
            assert resp.status_code == 200

    def test_scope_check_with_credential_manager(self, tmp_path: Path) -> None:
        """使用 CredentialManager 提供的 scope 进行权限检查"""
        mock_manager = MagicMock()
        mock_manager.get.side_effect = lambda name: {
            "MAREF_API_KEY": "cm-scoped-key",
            "MAREF_API_KEY_SCOPES": "read",
        }.get(name)

        with patch(
            "maref.identity.credential_manager.CredentialManager",
            return_value=mock_manager,
        ):
            from sidecar import api_auth

            api_auth._API_KEYS = []
            api_auth._ALLOWED_SCOPES = []
            APIKeyManager.reload()

            a = FastAPI()
            a.add_middleware(AuthMiddleware)

            @a.post("/api/v1/hitl/{event_id}/approve")
            @require_auth(scope="hitl:write")
            def hitl_approve(event_id: str):
                return {"approved": True}

            from sidecar.api_auth import _register_route_scope

            _register_route_scope(a)

            client = TestClient(a)
            resp = client.post(
                "/api/v1/hitl/event-1/approve",
                headers={"Authorization": "Bearer cm-scoped-key"},
            )
            assert resp.status_code == 403
            assert "scope" in resp.text.lower()
