"""Security Audit Chain - tamper-evident chain for security-critical events.

DEPRECATED: Use ``maref.governance.audit.AuditLogger`` + ``maref.governance.audit_bus.AuditBus`` instead.
This module is frozen (no new features, bug fixes only). It remains for
backward compatibility with existing chain files.

The main AuditLogger (v0.38.0+) supports Ed25519 signing and interfaces
with the Merkle audit tree via ``AuditChainIntegrator``. Prefer that
over this module for all new code.

AuditBus (v0.42.0+) provides a unified interface combining governance,
GaaS tenant, and recursive-evolution audit. See ``governance/audit_bus.py``.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HMAC_KEY_ENV = "MAREF_HMAC_SECRET_KEY"


@dataclass
class SecurityAuditEntry:
    """A single entry in the security audit chain."""

    entry_id: str
    timestamp: float
    event_type: str  # auth, access, privilege_escalation, safety_gate, circuit_breaker, etc.
    actor: str
    action: str
    severity: str  # INFO, WARN, CRITICAL
    details: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    chain_hash: str = ""
    hmac_signature: str = ""

    def _payload_for_signing(self) -> str:
        return json.dumps(
            {
                "entry_id": self.entry_id,
                "timestamp": self.timestamp,
                "event_type": self.event_type,
                "actor": self.actor,
                "action": self.action,
                "severity": self.severity,
                "details": self.details,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "severity": self.severity,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "chain_hash": self.chain_hash,
            "hmac_signature": self.hmac_signature,
        }


class SecurityAuditChain:
    """Tamper-evident security audit chain with HMAC signing.

    Each entry is linked to the previous via chain_hash, and signed with
    HMAC-SHA256 for tamper detection. The chain file is append-only.
    """

    def __init__(
        self,
        chain_path: Path | str | None = None,
        hmac_key: bytes | str | None = None,
    ) -> None:
        if chain_path is None:
            base = Path(os.environ.get("MAREF_AUDIT_PATH", ".governance"))
            self._path = base / "security_audit.chain"
        else:
            self._path = Path(chain_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve HMAC key (same logic as AuditLogger)
        resolved_key = hmac_key
        if resolved_key is None:
            env_key = os.environ.get(_HMAC_KEY_ENV)
            if env_key:
                resolved_key = env_key
        if resolved_key is None:
            for key_path in (".maref_hmac_key", ".maraf_hmac_key", ".gaas_api_key"):
                try:
                    with open(key_path) as f:
                        resolved_key = f.read().strip()
                        break
                except (FileNotFoundError, OSError):
                    continue
        if resolved_key:
            self._hmac_key: bytes | None = (
                resolved_key.encode("utf-8") if isinstance(resolved_key, str) else resolved_key
            )
        else:
            self._hmac_key = None
            logger.warning("No HMAC key for SecurityAuditChain - tamper protection disabled")

        self._last_chain_hash = self._get_last_chain_hash()

    def _get_last_chain_hash(self) -> str:
        """Read the last chain_hash from the file, or empty string if new."""
        if not self._path.exists():
            return ""
        try:
            with open(self._path) as f:
                lines = [line.strip() for line in f if line.strip()]
            if not lines:
                return ""
            last = json.loads(lines[-1])
            return last.get("chain_hash", "")
        except (json.JSONDecodeError, OSError):
            return ""

    def _sign(self, entry: SecurityAuditEntry) -> str:
        if self._hmac_key is None:
            return ""
        payload = entry._payload_for_signing().encode("utf-8")
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    def _compute_chain_hash(self, entry: SecurityAuditEntry) -> str:
        payload = entry._payload_for_signing().encode("utf-8")
        return hashlib.sha256(entry.previous_hash.encode("utf-8") + payload).hexdigest()

    def append(
        self,
        event_type: str,
        actor: str,
        action: str,
        severity: str = "INFO",
        details: dict[str, Any] | None = None,
    ) -> SecurityAuditEntry:
        """Append a new security audit entry to the chain."""
        entry = SecurityAuditEntry(
            entry_id=f"sac_{int(time.time() * 1000)}_{os.getpid()}",
            timestamp=time.time(),
            event_type=event_type,
            actor=actor,
            action=action,
            severity=severity,
            details=details or {},
            previous_hash=self._last_chain_hash,
        )
        entry.chain_hash = self._compute_chain_hash(entry)
        entry.hmac_signature = self._sign(entry)

        with open(self._path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        self._last_chain_hash = entry.chain_hash
        return entry

    def verify_integrity(self) -> dict[str, Any]:
        """Verify the integrity of the entire chain.

        Checks:
        1. Each entry's previous_hash matches the prior entry's chain_hash
        2. Each entry's chain_hash is correctly computed
        3. Each entry's HMAC signature is valid (if key configured)
        """
        if not self._path.exists():
            return {"status": "no_file", "total": 0, "valid": 0, "tampered": 0, "issues": []}

        issues: list[str] = []
        total = 0
        valid = 0
        previous_chain_hash = ""

        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    data = json.loads(line)
                    entry = SecurityAuditEntry(**data)
                except (json.JSONDecodeError, TypeError) as e:
                    issues.append(f"Entry {total}: parse error: {e}")
                    continue

                # Check chain linkage
                if entry.previous_hash != previous_chain_hash:
                    issues.append(f"Entry {entry.entry_id}: chain broken (previous_hash mismatch)")

                # Recompute chain_hash
                expected_hash = self._compute_chain_hash(entry)
                if entry.chain_hash != expected_hash:
                    issues.append(f"Entry {entry.entry_id}: chain_hash mismatch (tampered)")

                # Verify HMAC signature
                if self._hmac_key is not None:
                    expected_sig = self._sign(entry)
                    if entry.hmac_signature != expected_sig:
                        issues.append(f"Entry {entry.entry_id}: HMAC signature invalid")
                    else:
                        valid += 1
                else:
                    valid += 1

                previous_chain_hash = entry.chain_hash

        tampered = total - valid
        return {
            "status": "verified" if tampered == 0 else "tampered",
            "total": total,
            "valid": valid,
            "tampered": tampered,
            "issues": issues[:20],  # Limit issues list
        }

    def read_all(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Read all entries from the chain."""
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                if len(entries) >= limit:
                    break
        return entries

    @property
    def path(self) -> Path:
        return self._path
