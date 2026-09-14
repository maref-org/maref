from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CredentialType(str, Enum):
    """凭据类型枚举"""

    API_KEY = "api_key"
    SIGNING_KEY = "signing_key"
    HMAC_KEY = "hmac_key"
    BROWSER_SESSION = "browser_session"
    OAUTH_TOKEN = "oauth_token"
    GOVERNANCE_CREDENTIAL = "governance_credential"


class CredentialStatus(str, Enum):
    """凭据状态"""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING_ROTATION = "pending_rotation"


@dataclass
class CredentialRecord:
    """凭据记录"""

    credential_id: str
    credential_type: CredentialType
    name: str
    domain: str  # 作用域（如 api.dashscope.com）
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    last_rotated: float | None = None
    rotation_interval: float | None = None  # 秒
    status: CredentialStatus = CredentialStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""  # SHA-256 指纹

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def needs_rotation(self) -> bool:
        if self.rotation_interval is None or self.last_rotated is None:
            return False
        return time.time() - self.last_rotated > self.rotation_interval


class CredentialManager:
    """中央凭据管理器

    统一管理所有敏感凭据的生命周期：
    - API 密钥（DashScope、OpenAI、Cloudflare 等）
    - 签名密钥（Ed25519、HMAC）
    - 浏览器登录状态（Cookie、LocalStorage）
    - 治理凭证（VerifiableGovernanceCredential）

    优先级: env > credential_manager > keyring > default
    """

    SERVICE_NAME = "com.maref.credential_manager"

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        encryption_key: bytes | None = None,
    ) -> None:
        self._storage_dir = (
            Path(storage_dir)
            if storage_dir
            else Path.home() / ".maref" / "credentials"
        )
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._records: dict[str, CredentialRecord] = {}
        self._records_file = self._storage_dir / "credential_records.json"
        self._load_records()

        # 加密密钥
        if encryption_key:
            self._encryption_key = hashlib.sha256(encryption_key).digest()
        else:
            env_key = os.environ.get("MAREF_CREDENTIAL_ENCRYPTION_KEY")
            if env_key:
                self._encryption_key = hashlib.sha256(env_key.encode()).digest()
            else:
                # 开发环境回退（生产必须设置）
                self._encryption_key = hashlib.sha256(
                    b"maref-dev-credential-key"
                ).digest()

        # OS Keychain 后端
        self._keyring_store = None
        try:
            from maref.security.keyring_store import KeyringStore

            self._keyring_store = KeyringStore()
        except ImportError:
            pass

    def _load_records(self) -> None:
        """加载凭据记录"""
        if self._records_file.exists():
            try:
                data = json.loads(self._records_file.read_text())
                for item in data:
                    record = CredentialRecord(**item)
                    self._records[record.credential_id] = record
            except Exception:
                pass

    def _save_records(self) -> None:
        """保存凭据记录"""
        data = []
        for record in self._records.values():
            data.append(
                {
                    "credential_id": record.credential_id,
                    "credential_type": record.credential_type.value,
                    "name": record.name,
                    "domain": record.domain,
                    "created_at": record.created_at,
                    "expires_at": record.expires_at,
                    "last_rotated": record.last_rotated,
                    "rotation_interval": record.rotation_interval,
                    "status": record.status.value,
                    "metadata": record.metadata,
                    "fingerprint": record.fingerprint,
                }
            )
        self._records_file.write_text(json.dumps(data, indent=2))
