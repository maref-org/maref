from __future__ import annotations

import logging
import os
import platform
from typing import Any

from maref.security.decorators import security_critical

logger = logging.getLogger(__name__)

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False


class KeyringStore:
    """OS-native credential storage for MAREF.

    Uses system keychain/keyring via the `keyring` library:
      - macOS: Keychain
      - Windows: Credential Locker (via pywin32)
      - Linux: Secret Service (libsecret)

    Priority order:
      1. Environment variable (for development/override)
      2. OS keychain/keyring (for production)
      3. Default value (fallback)
    """

    SERVICE_NAME = "com.maref.agent"

    KNOWN_KEYS = [
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MAREF_ADMIN_TOKEN",
    ]

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self._service = service_name
        self._keyring_available = HAS_KEYRING

    @property
    def available(self) -> bool:
        return self._keyring_available

    @security_critical
    def get(self, key: str, default: str | None = None) -> str | None:
        """Retrieve credential with priority: env > keyring > default."""
        env_val = os.environ.get(key)
        if env_val:
            return env_val
        if self._keyring_available:
            try:
                val = keyring.get_password(self._service, key)
                if val:
                    return val
            except Exception as e:
                logger.debug("Keyring get failed for %s: %s", key, e)
        return default

    @security_critical
    def set(self, key: str, value: str) -> bool:
        """Store credential in OS keychain."""
        if not value:
            logger.warning("Attempted to store empty value for %s", key)
            return False
        if self._keyring_available:
            try:
                keyring.set_password(self._service, key, value)
                logger.info("Stored credential in keychain")
                return True
            except Exception as e:
                logger.error("Keyring set failed for %s: %s", key, e)
        return False

    @security_critical
    def delete(self, key: str) -> bool:
        """Delete credential from OS keychain."""
        if self._keyring_available:
            try:
                keyring.delete_password(self._service, key)
                logger.info("Deleted credential from keychain")
                return True
            except Exception as e:
                logger.debug("Keyring delete failed for %s: %s", key, e)
        return False

    def list_keys(self) -> list[str]:
        """List all known key names."""
        return list(self.KNOWN_KEYS)

    def diagnose(self) -> dict[str, Any]:
        system = platform.system()
        keyring_backend = None
        if self._keyring_available:
            try:
                keyring_backend = keyring.get_keyring().name
            except Exception:
                keyring_backend = "unknown"

        stored_keys = []
        if self._keyring_available:
            for key in self.KNOWN_KEYS:
                try:
                    val = keyring.get_password(self._service, key)
                    if val:
                        stored_keys.append(key)
                except Exception:
                    pass

        return {
            "system": system,
            "service": self._service,
            "keyring_available": self._keyring_available,
            "keyring_backend": keyring_backend,
            "stored_keys": stored_keys,
            "env_vars": [k for k in os.environ if "API_KEY" in k or "TOKEN" in k or "SECRET" in k],
        }
