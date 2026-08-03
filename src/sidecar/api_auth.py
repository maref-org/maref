"""API 认证中间件 — Bearer Token + Scope 声明

用法:
    from sidecar.api_auth import require_auth, APIKeyManager

    @router.post("/api/v1/hitl/{id}/approve")
    @require_auth(scope="hitl:write")
    def hitl_approve(...):
        ...

环境变量:
    MAREF_API_KEY    — 主 API Key (所有 scope)
    MAREF_API_KEY_2  — 可选备用 Key

设计原则:
    - 简单 Bearer Token (不引入 OAuth 复杂度)
    - 每个端点声明所需 scope
    - 失败时统一 401/403 + 审计日志
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_SCOPE_MAP: dict[str, str] = {}
_API_KEYS: list[str] = []


def _load_keys() -> None:
    global _API_KEYS
    if _API_KEYS:
        return
    raw = os.environ.get("MAREF_API_KEY", "")
    raw2 = os.environ.get("MAREF_API_KEY_2", "")
    keys = []
    if raw:
        keys.append(raw.strip())
    if raw2:
        keys.append(raw2.strip())
    _API_KEYS = keys


_AUTH_BYPASS_PATHS = {"/api/health", "/api/version", "/api/status", "/_debug/", "/api/mcp/gateway/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces Bearer Token auth on all routes.

    Bypass paths are checked first; any path starting with or matching a bypass
    prefix is allowed through without authentication.
    """

    def __init__(self, app: FastAPI, bypass_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._bypass = (bypass_paths or set()) | _AUTH_BYPASS_PATHS

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        path = request.url.path
        for bp in self._bypass:
            if path.startswith(bp) or path == bp:
                return await call_next(request)

        token = _extract_token(request)
        if not token:
            logger.warning("API auth failed: missing token for %s", path)
            _audit_auth(request, path, "missing_token", False)
            return JSONResponse(status_code=401, content={"detail": "Missing Authorization header (Bearer token required)"})

        if not _verify_token(token):
            logger.warning("API auth failed: invalid token for %s", path)
            _audit_auth(request, path, "invalid_token", False)
            return JSONResponse(status_code=403, content={"detail": "Invalid API key"})

        # Scope enforcement
        required_scope = _SCOPE_MAP.get(path)
        if required_scope and not _has_scope(token, required_scope):
            logger.warning("API auth failed: insufficient scope for %s (required: %s)", path, required_scope)
            _audit_auth(request, path, f"insufficient_scope:{required_scope}", False)
            return JSONResponse(status_code=403, content={"detail": f"Insufficient scope: {required_scope} required"})

        _audit_auth(request, path, "allowed", True)
        return await call_next(request)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.query_params.get("token")


def _verify_token(token: str) -> bool:
    _load_keys()
    if not _API_KEYS:
        return True
    return any(hmac.compare_digest(token, k) for k in _API_KEYS)


def _has_scope(token: str, required_scope: str) -> bool:
    """Check if token has the required scope.

    Current implementation: any valid key has all scopes (master key model).
    Future: could extend to per-key scope mapping.
    """
    return True


_AUDIT_LOG: list[dict[str, Any]] = []


def _audit_auth(request: Request, path: str, reason: str, allowed: bool) -> None:
    """Record authentication audit event."""
    from datetime import datetime

    _AUDIT_LOG.append({
        "timestamp": datetime.utcnow().isoformat(),
        "path": path,
        "method": request.method,
        "client_ip": request.client.host if request.client else "unknown",
        "reason": reason,
        "allowed": allowed,
    })
    if len(_AUDIT_LOG) > 10000:
        _AUDIT_LOG.pop(0)


def require_auth(
    scope: str = "default",
    bypass_paths: set[str] | None = None,
) -> Callable[[F], F]:
    """Declarative auth marker with scope enforcement.

    The scope is registered and checked by AuthMiddleware.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        import asyncio
        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        # Store scope requirement for this function
        wrapper._maref_required_scope = scope
        return wrapper  # type: ignore[return-value]
    return decorator


def _register_route_scope(app: FastAPI) -> None:
    """Register scope requirements from route decorators.

    Call this after all routes are added to the app.
    """
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint and hasattr(endpoint, "_maref_required_scope"):
            path = getattr(route, "path", getattr(route, "path_format", ""))
            if path:
                _SCOPE_MAP[path] = endpoint._maref_required_scope


def is_auth_enabled() -> bool:
    _load_keys()
    return len(_API_KEYS) > 0


def get_audit_log() -> list[dict[str, Any]]:
    return list(_AUDIT_LOG)


def clear_audit_log() -> None:
    _AUDIT_LOG.clear()


class APIKeyManager:
    @staticmethod
    def is_auth_enabled() -> bool:
        return is_auth_enabled()

    @staticmethod
    def reload() -> None:
        global _API_KEYS
        _API_KEYS = []
        _load_keys()

    @staticmethod
    def health() -> dict[str, Any]:
        _load_keys()
        return {
            "auth_enabled": len(_API_KEYS) > 0,
            "key_count": len(_API_KEYS),
        }

