"""Audit signing backends — 带外签署最小增量 (P0-3).

默认行为与历史完全一致（本地 HMAC-SHA256，密钥经 ``MAREF_HMAC_SECRET_KEY``
或 ``.maraf_hmac_key`` 解析）。当显式配置 ``MAREF_AUDIT_SIGNER_URL`` 时，审计链
签名改由外部签署服务完成，密钥不再驻留在 agent 进程；远程不可用时回退本地并
标记 ``degraded``。

本模块只提供抽象与后端，不改变默认部署行为——把默认切到带外签署是后续的运维
开关，需要 sidecar 提供 ``POST /api/v1/audit/sign`` 端点。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class AuditKeyMissingError(RuntimeError):
    """Raised when no audit signing key is available (fail-closed)."""


def resolve_local_hmac_key() -> bytes:
    """Resolve the local HMAC key from env, then fallback files (b'' if absent)."""
    env_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")
    for candidate in (Path.cwd() / ".maraf_hmac_key", Path.home() / ".maraf_hmac_key"):
        try:
            value = candidate.read_text().strip()
        except OSError:
            continue
        if value:
            return value.encode("utf-8")
    return b""


class AuditSigner(Protocol):
    """Signing backend contract used by the governance audit chain."""

    @property
    def backend_name(self) -> str: ...

    @property
    def degraded(self) -> bool: ...

    def sign(self, payload: bytes) -> str: ...


class LocalHmacSigner:
    """In-process HMAC-SHA256 signer (historical default, byte-identical)."""

    def __init__(self, key: bytes | None = None) -> None:
        self._key: bytes = resolve_local_hmac_key() if key is None else key

    @property
    def backend_name(self) -> str:
        return "local-hmac"

    @property
    def degraded(self) -> bool:
        return False

    @property
    def has_key(self) -> bool:
        """Whether a signing key is available locally."""
        return bool(self._key)

    def sign(self, payload: bytes) -> str:
        """Return the HMAC-SHA256 hex digest of ``payload``."""
        if not self._key:
            raise AuditKeyMissingError("no local HMAC key available")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()


def _http_transport(url: str, payload: bytes, timeout: float) -> str:
    """Default remote transport: POST payload, read ``{"signature": ...}``."""
    import httpx

    response = httpx.post(url, content=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    signature = body.get("signature")
    if not isinstance(signature, str) or not signature:
        raise ValueError("remote signer returned no signature")
    return signature


class RemoteSignerClient:
    """Signs via an external service so the key stays out of the agent process.

    On transport failure the client falls back to ``fallback`` (if provided) and
    permanently marks itself ``degraded`` until a remote call succeeds again.
    """

    def __init__(
        self,
        url: str,
        transport: Callable[[str, bytes, float], str] | None = None,
        fallback: AuditSigner | None = None,
        timeout: float = 5.0,
    ) -> None:
        if not url:
            raise ValueError("remote signer url must be non-empty")
        self._url = url
        self._transport = transport or _http_transport
        self._fallback = fallback
        self._timeout = timeout
        self._degraded = False

    @property
    def backend_name(self) -> str:
        return "remote-signer"

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def url(self) -> str:
        """Configured remote signer endpoint."""
        return self._url

    def sign(self, payload: bytes) -> str:
        """Sign remotely; fall back to local signer and flag degradation on failure."""
        try:
            signature = self._transport(self._url, payload, self._timeout)
            self._degraded = False
            return signature
        except Exception:
            if self._fallback is None:
                raise
            self._degraded = True
            return self._fallback.sign(payload)


def resolve_audit_signer() -> AuditSigner:
    """Pick the signing backend from environment.

    ``MAREF_AUDIT_SIGNER_URL`` set → :class:`RemoteSignerClient` with a local
    fallback; otherwise the historical :class:`LocalHmacSigner`.

    Trust-domain enforce mode (see :mod:`maref.governance.trust_domain`) requires
    the remote signer and forbids any local fallback, so the key never lives in
    the agent process.
    """
    url = os.environ.get("MAREF_AUDIT_SIGNER_URL", "").strip()
    from maref.governance.trust_domain import TrustDomainMode, resolve_mode

    if resolve_mode() == TrustDomainMode.ENFORCE:
        if not url:
            raise AuditKeyMissingError(
                "trust domain enforce: MAREF_AUDIT_SIGNER_URL required "
                "(local audit key not permitted)"
            )
        return RemoteSignerClient(url)
    if not url:
        return LocalHmacSigner()
    return RemoteSignerClient(url, fallback=LocalHmacSigner())
