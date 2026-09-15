from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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

        # 加密密钥（必须在 _load_records 之前设置）
        if encryption_key:
            self._encryption_key = hashlib.sha256(encryption_key).digest()
        else:
            env_key = os.environ.get("MAREF_CREDENTIAL_ENCRYPTION_KEY")
            if env_key:
                self._encryption_key = hashlib.sha256(env_key.encode()).digest()
            else:
                logger.warning(
                    "MAREF_CREDENTIAL_ENCRYPTION_KEY not set; using dev fallback key. "
                    "Set the env var for production use."
                )
                self._encryption_key = hashlib.sha256(
                    b"maref-dev-credential-key"
                ).digest()

        self._records: dict[str, CredentialRecord] = {}
        self._records_file = self._storage_dir / "credential_records.json"
        self._load_records()

        # OS Keychain 后端
        self._keyring_store = None
        try:
            from maref.security.keyring_store import KeyringStore

            self._keyring_store = KeyringStore()
        except ImportError:
            pass

    def register(
        self,
        name: str,
        credential_type: CredentialType,
        value: str,
        domain: str = "",
        expires_in: float | None = None,
        rotation_interval: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CredentialRecord:
        """注册新凭据"""
        credential_id = f"{credential_type.value}:{name}:{int(time.time())}"
        fingerprint = hashlib.sha256(value.encode()).hexdigest()[:16]

        record = CredentialRecord(
            credential_id=credential_id,
            credential_type=credential_type,
            name=name,
            domain=domain,
            expires_at=time.time() + expires_in if expires_in else None,
            rotation_interval=rotation_interval,
            metadata=metadata or {},
            fingerprint=fingerprint,
        )

        self._records[credential_id] = record
        self._save_records()

        if self._keyring_store:
            self._keyring_store.set(name, value)

        self._audit_log("register", credential_id, name)

        return record

    def get(self, name: str) -> str | None:
        """获取凭据值（优先级: env > manager > keyring）"""
        env_val = os.environ.get(name)
        if env_val:
            return env_val

        record = self._find_by_name(name)
        if record and record.status == CredentialStatus.EXPIRED:
            return None

        if self._keyring_store:
            return self._keyring_store.get(name)

        return None

    def rotate(self, credential_id: str, new_value: str) -> CredentialRecord:
        """轮转凭据"""
        record = self._records.get(credential_id)
        if not record:
            raise ValueError(f"Credential {credential_id} not found")

        record.last_rotated = time.time()
        record.fingerprint = hashlib.sha256(new_value.encode()).hexdigest()[:16]
        record.status = CredentialStatus.ACTIVE

        if self._keyring_store:
            self._keyring_store.set(record.name, new_value)

        self._save_records()
        self._audit_log("rotate", credential_id, record.name)

        return record

    def revoke(self, credential_id: str, reason: str = "") -> bool:
        """吊销凭据"""
        record = self._records.get(credential_id)
        if not record:
            return False

        record.status = CredentialStatus.REVOKED
        record.metadata["revoke_reason"] = reason
        record.metadata["revoked_at"] = time.time()

        self._save_records()

        if self._keyring_store:
            self._keyring_store.delete(record.name)

        self._audit_log("revoke", credential_id, record.name, reason=reason)

        return True

    def list_credentials(
        self,
        credential_type: CredentialType | None = None,
        status: CredentialStatus | None = None,
    ) -> list[CredentialRecord]:
        """列出凭据"""
        results = list(self._records.values())

        if credential_type:
            results = [r for r in results if r.credential_type == credential_type]
        if status:
            results = [r for r in results if r.status == status]

        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def check_expiration(self) -> list[CredentialRecord]:
        """检查过期凭据"""
        return [r for r in self._records.values() if r.is_expired()]

    def check_rotation_needed(self) -> list[CredentialRecord]:
        """检查需要轮转的凭据"""
        return [r for r in self._records.values() if r.needs_rotation()]

    def _find_by_name(self, name: str) -> CredentialRecord | None:
        """按名称查找凭据"""
        for record in self._records.values():
            if record.name == name:
                return record
        return None

    def _audit_log(
        self,
        action: str,
        credential_id: str,
        name: str,
        reason: str = "",
    ) -> None:
        """记录审计日志（优雅降级：AuditLogger 不可用时仅写 warning）"""
        try:
            from maref.governance.audit import AuditLogger

            audit = AuditLogger()
            audit.log(
                event_type=f"credential_{action}",
                actor="credential_manager",
                action=action,
                details=f"credential_id={credential_id}, name={name}",
                metadata={
                    "credential_id": credential_id,
                    "name": name,
                    "reason": reason,
                },
            )
        except Exception as e:
            logger.warning("Audit logging failed for credential %s: %s", action, e)

    def _encrypt(self, plaintext: str) -> str:
        """AES-256-GCM 加密，返回 nonce+ciphertext 的 hex 字符串"""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = os.urandom(12)
            aesgcm = AESGCM(self._encryption_key)
            ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
            return (nonce + ct).hex()
        except ImportError:
            logger.warning(
                "cryptography library not available; falling back to XOR obfuscation"
            )
            key = self._encryption_key
            data = plaintext.encode()
            nonce = os.urandom(len(data))
            xored = bytes(
                a ^ b
                for a, b in zip(
                    data, key * (len(data) // len(key) + 1), strict=False
                )
            )
            return (nonce + xored).hex()

    def _decrypt(self, encrypted_hex: str) -> str:
        """AES-256-GCM 解密，输入 nonce+ciphertext 的 hex 字符串"""
        try:
            raw = bytes.fromhex(encrypted_hex)
            nonce, ct = raw[:12], raw[12:]
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(self._encryption_key)
            return aesgcm.decrypt(nonce, ct, None).decode()
        except Exception:
            try:
                raw = bytes.fromhex(encrypted_hex)
                nonce, xored = raw[: len(raw) // 2], raw[len(raw) // 2 :]
                key = self._encryption_key
                return bytes(
                    a ^ b
                    for a, b in zip(
                        xored, key * (len(xored) // len(key) + 1), strict=False
                    )
                ).decode()
            except Exception as e:
                raise ValueError(f"Decryption failed: {e}") from e

    def _load_records(self) -> None:
        """加载凭据记录（逐条容错）"""
        if self._records_file.exists():
            try:
                raw_text = self._records_file.read_text()
                try:
                    decrypted = self._decrypt(raw_text)
                    data = json.loads(decrypted)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "Corrupt credential file at %s; skipping",
                        self._records_file,
                    )
                    return
                for item in data:
                    try:
                        record = CredentialRecord(**item)
                        self._records[record.credential_id] = record
                    except (TypeError, KeyError) as e:
                        logger.warning("Skipping corrupt credential record: %s", e)
            except OSError as e:
                logger.warning("Failed to read credential file: %s", e)

    def _save_records(self) -> None:
        """保存凭据记录（原子写入）"""
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
        encrypted = self._encrypt(json.dumps(data, indent=2))
        fd, tmp_path = tempfile.mkstemp(
            dir=self._storage_dir, suffix=".tmp", prefix="credential_records."
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(encrypted)
            os.rename(tmp_path, str(self._records_file))
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
