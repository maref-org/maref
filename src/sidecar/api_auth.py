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
import re
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_SCOPE_MAP: dict[str, str] = {}
_API_KEYS: list[str] = []
_ALLOWED_SCOPES: list[str] = []


def _load_keys() -> None:
    global _API_KEYS, _ALLOWED_SCOPES
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
    scopes_raw = os.environ.get("MAREF_API_KEY_SCOPES", "")
    _ALLOWED_SCOPES = [s.strip() for s in scopes_raw.split(",") if s.strip()]


_AUTH_BYPASS_PATHS = {
    "/api/health",
    "/api/version",
    "/api/status",
    "/api/mcp/gateway/health",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces Bearer Token auth on all routes.

    Bypass paths are checked first; any path starting with or matching a bypass
    prefix is allowed through without authentication.

    Fail-closed (v0.47 S6): when no API key is configured the middleware
    rejects requests unless ``allow_unauthenticated=True`` is passed (an
    explicit development flag).
    """

    def __init__(
        self,
        app: FastAPI,
        bypass_paths: set[str] | None = None,
        allow_unauthenticated: bool = False,
    ) -> None:
        super().__init__(app)
        self._bypass = (bypass_paths or set()) | _AUTH_BYPASS_PATHS
        self._allow_unauthenticated = allow_unauthenticated

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        path = request.url.path
        for bp in self._bypass:
            if path.startswith(bp) or path == bp:
                return await call_next(request)

        token = _extract_token(request)
        if not token:
            if self._allow_unauthenticated:
                _audit_auth(request, path, "unauthenticated_dev", True)
                return await call_next(request)
            logger.warning("API auth failed: missing token for %s", path)
            _audit_auth(request, path, "missing_token", False)
            return JSONResponse(status_code=401, content={"detail": "Missing Authorization header (Bearer token required)"})

        if not _verify_token(token):
            if self._allow_unauthenticated:
                _audit_auth(request, path, "unauthenticated_dev", True)
                return await call_next(request)
            logger.warning("API auth failed: invalid token for %s", path)
            _audit_auth(request, path, "invalid_token", False)
            return JSONResponse(status_code=403, content={"detail": "Invalid API key"})

        # Scope enforcement
        required_scope = _resolve_required_scope(path)
        if required_scope and not _has_scope(token, required_scope):
            logger.warning("API auth failed: insufficient scope for %s (required: %s)", path, required_scope)
            _audit_auth(request, path, f"insufficient_scope:{required_scope}", False)
            return JSONResponse(status_code=403, content={"detail": f"Insufficient scope: {required_scope} required"})

        _audit_auth(request, path, "allowed", True)
        return await call_next(request)


def _resolve_required_scope(path: str) -> str | None:
    """Resolve the required scope for a request path.

    Registered scope templates use FastAPI path params (e.g.
    ``/api/v1/hitl/{event_id}/approve``); the incoming request path is a
    concrete URL.  Match the template against the path so scope checks work
    for parameterised routes.
    """
    direct = _SCOPE_MAP.get(path)
    if direct is not None:
        return direct
    for template, scope in _SCOPE_MAP.items():
        if "{" in template:
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", template) + "$"
            if re.match(pattern, path):
                return scope
    return None


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.query_params.get("token")


def _verify_token(token: str) -> bool:
    _load_keys()
    if not _API_KEYS:
        # Fail-closed: no keys configured → no token is accepted unless the
        # development flag allows unauthenticated access.
        return False
    return any(hmac.compare_digest(token, k) for k in _API_KEYS)


def _has_scope(token: str, required_scope: str) -> bool:
    """Check if token has the required scope.

    ``MAREF_API_KEY_SCOPES`` (comma separated) limits the master key to a
    specific scope set.  When unset the master key has every scope (the
    historical master-key model); when set, only the configured scopes pass.
    """
    _load_keys()
    if not _ALLOWED_SCOPES:
        return True
    return required_scope in _ALLOWED_SCOPES


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
        wrapper._maref_required_scope = scope  # type: ignore[union-attr]
        return wrapper  # type: ignore[return-value]
    return decorator


def _register_route_scope(app: FastAPI) -> None:
    """Register scope requirements from route decorators.

    Call this after all routes are added to the app.

    FastAPI 0.141+ lazily wraps included routers in ``_IncludedRouter``
    objects instead of flattening their routes into ``app.routes``, so we
    recurse into them to pick up scopes declared on included routers.
    """
    _collect_route_scopes(app.routes)


def _collect_route_scopes(routes: Sequence[Any]) -> None:
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            _collect_route_scopes(getattr(original_router, "routes", []))
            continue
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
        global _API_KEYS, _ALLOWED_SCOPES
        _API_KEYS = []
        _ALLOWED_SCOPES = []
        _load_keys()

    @staticmethod
    def health() -> dict[str, Any]:
        _load_keys()
        return {
            "auth_enabled": len(_API_KEYS) > 0,
            "key_count": len(_API_KEYS),
        }

