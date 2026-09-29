"""Credential broker — agent 持占位凭证，真密钥由 broker 注入 (P1-7).

agent 进程不再持有真实 API key：环境/配置里只放占位符
(``MAREF_PLACEHOLDER_<service>``)。出站请求经 broker 解析：

1. 真 key 只从**安全来源**取（OS keychain，:class:`KeyringProvider` 只读 keyring、
   不读进程 env），不来自 agent 环境；
2. 只把真 key 注入到**白名单端点**（host 精确/子域匹配）；
3. agent 若 presented 出真 key（非占位符）→ 拒绝（疑似窃取）；
4. 未知服务 / 非白名单端点 / 缺失 key 一律 fail-closed 抛
   :class:`CredentialError`。

默认**关闭**（opt-in）：未配置默认 broker 时，:func:`resolve_credential` 退化为
历史行为（返回传入值或环境变量），不改现有部署。``MAREF_CREDENTIAL_BROKER=1``
时经 :func:`build_broker_from_env` 启用。

配合 ``security.tool_sandbox.clean_env``：agent 子进程环境无真 key 变量。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

PLACEHOLDER_PREFIX = "MAREF_PLACEHOLDER_"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


class CredentialError(RuntimeError):
    """Raised when a credential cannot be safely resolved (fail-closed)."""


def is_placeholder(value: object) -> bool:
    """Whether ``value`` is a broker placeholder rather than a real secret."""
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)


def placeholder_for(service: str) -> str:
    """Build the placeholder an agent should present for ``service``."""
    return f"{PLACEHOLDER_PREFIX}{service}"


class KeyProvider(Protocol):
    """Source of real credentials (keychain in production, dict in tests)."""

    def get(self, key: str) -> str | None: ...


class DictKeyProvider:
    """In-memory key provider for tests and explicit wiring."""

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values: dict[str, str] = dict(values or {})

    def set(self, key: str, value: str) -> None:
        """Set a credential value."""
        self._values[key] = value

    def get(self, key: str) -> str | None:
        """Return the credential for ``key`` if present."""
        return self._values.get(key)


class KeyringProvider:
    """Reads real keys from the OS keychain only (bypasses the process env)."""

    def __init__(self, service_name: str | None = None) -> None:
        self._service = service_name

    def get(self, key: str) -> str | None:
        """Look up ``key`` in the OS keychain; None when unavailable."""
        try:
            import keyring

            from maref.security.keyring_store import KeyringStore

            service = self._service or KeyringStore.SERVICE_NAME
            return keyring.get_password(service, key)
        except Exception:
            return None


def _host_allowed(url: str, allowed: Sequence[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for entry in allowed:
        entry_host = urlparse(entry).hostname if "//" in entry else entry
        entry_host = (entry_host or entry).strip().lower()
        if entry_host and (host == entry_host or host.endswith("." + entry_host)):
            return True
    return False


@dataclass
class CredentialBroker:
    """Injects real credentials into allowlisted egress endpoints only."""

    endpoints: Mapping[str, Sequence[str]]
    key_names: Mapping[str, str]
    key_provider: KeyProvider
    enabled: bool = True

    def endpoint_allowed(self, service: str, target_url: str) -> bool:
        """Whether ``target_url`` is allowlisted for ``service``."""
        allowed = self.endpoints.get(service)
        if not allowed:
            return False
        return _host_allowed(target_url, allowed)

    def resolve(self, service: str, target_url: str, presented: str | None = None) -> str:
        """Resolve a real credential for an outbound call (fail-closed)."""
        if not self.enabled:
            return presented or ""
        if service not in self.key_names:
            raise CredentialError(f"unknown service: {service}")
        if not self.endpoint_allowed(service, target_url):
            raise CredentialError(f"endpoint not allowlisted for {service}: {target_url}")
        if presented and not is_placeholder(presented):
            raise CredentialError("agent must present a placeholder, not a real credential")
        key = self.key_provider.get(self.key_names[service])
        if not key:
            raise CredentialError(f"no credential available for service: {service}")
        return key

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "services": sorted(self.key_names),
            "endpoints": {name: list(hosts) for name, hosts in self.endpoints.items()},
        }


_default_broker: CredentialBroker | None = None


def set_default_broker(broker: CredentialBroker | None) -> None:
    """Set (or clear) the process-wide default broker."""
    global _default_broker
    _default_broker = broker


def get_default_broker() -> CredentialBroker | None:
    """Return the process-wide default broker, if configured."""
    return _default_broker


def resolve_credential(
    service: str,
    env_name: str,
    target_url: str,
    presented: str | None = None,
) -> str:
    """Resolve a credential for an outbound call.

    With no default broker this is the legacy path (return ``presented`` or the
    env var, possibly ``""``). With a broker configured, enforcement is
    fail-closed: the real key is injected and invalid inputs raise
    :class:`CredentialError`.
    """
    broker = _default_broker
    if broker is None:
        value = presented if presented is not None else os.environ.get(env_name, "")
        return value or ""
    if presented is None:
        presented = os.environ.get(env_name)
    return broker.resolve(service, target_url, presented)


def build_broker_from_env(environ: Mapping[str, str] | None = None) -> CredentialBroker | None:
    """Build a broker from environment config, or None when disabled.

    Config keys:
        MAREF_CREDENTIAL_BROKER=1        enable
        MAREF_BROKER_ENDPOINTS           JSON {service: [host, ...]}
        MAREF_BROKER_KEY_NAMES           JSON {service: keychain_key_name}
    """
    env = environ if environ is not None else os.environ
    if env.get("MAREF_CREDENTIAL_BROKER", "").strip().lower() not in _ENABLED_VALUES:
        return None
    endpoints = json.loads(env.get("MAREF_BROKER_ENDPOINTS", "") or "{}")
    key_names = json.loads(env.get("MAREF_BROKER_KEY_NAMES", "") or "{}")
    return CredentialBroker(
        endpoints=endpoints,
        key_names=key_names,
        key_provider=KeyringProvider(),
        enabled=True,
    )
