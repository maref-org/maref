"""
MAREF Audit Logger

Append-only, structured audit log for all governance decisions.
Every entry is timestamped, immutable after write, and includes
the full decision context for post-mortem analysis.

Compliance: ISO 27001 audit trail requirements (C.5.33).
v0.37.0: HMAC-SHA256 signing for tamper-evident audit chain.
v0.38.0+: Ed25519 signing for offline-verifiable audit chain.
           Old HMAC entries remain readable (backward compatible).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditRecord

_HMAC_KEY_ENV = "MAREF_HMAC_SECRET_KEY"
_ED25519_KEY_ENV = "MAREF_ED25519_PRIVATE_KEY"


@dataclass(frozen=True)
class AuditEntry:
    """An immutable audit log entry with HMAC or Ed25519 signature.

    v0.37.0 entries use ``hmac_signature`` (HMAC-SHA256).
    v0.38.0+ entries use ``ed25519_signature`` + ``signer_fingerprint``.
    Both formats are forward/backward compatible.
    """

    id: str
    timestamp: float
    event_type: str
    actor: str
    action: str
    details: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_action_id: str = ""
    previous_hash: str = ""
    chain_hash: str = ""
    hmac_signature: str = ""
    ed25519_signature: str = ""
    signer_fingerprint: str = ""
    # Unified fields — used by GaaS tenant audit, recursive evolution,
    # and integration layers.  Optional (empty defaults) for full
    # backward compatibility with existing log entries.
    tenant_id: str = ""
    layer: str = "governance"
    round: int = 0

    @property
    def signature_type(self) -> str:
        if self.ed25519_signature:
            return "ed25519"
        if self.hmac_signature:
            return "hmac"
        return "unsigned"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "details": self.details,
            "metadata": self.metadata,
        }
        if self.parent_action_id:
            result["parent_action_id"] = self.parent_action_id
        if self.previous_hash:
            result["previous_hash"] = self.previous_hash
        if self.chain_hash:
            result["chain_hash"] = self.chain_hash
        if self.hmac_signature:
            result["hmac_signature"] = self.hmac_signature
        if self.ed25519_signature:
            result["ed25519_signature"] = self.ed25519_signature
        if self.signer_fingerprint:
            result["signer_fingerprint"] = self.signer_fingerprint
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.round:
            result["round"] = self.round
        return result

    def _payload_for_signing(self) -> str:
        payload: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "details": self.details,
            "metadata": self.metadata,
            "previous_hash": self.previous_hash,
        }
        if self.parent_action_id:
            payload["parent_action_id"] = self.parent_action_id
        if self.tenant_id:
            payload["tenant_id"] = self.tenant_id
        if self.layer:
            payload["layer"] = self.layer
        if self.round:
            payload["round"] = self.round
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

    def to_unified(self, layer: str | None = None, round_num: int | None = None) -> UnifiedAuditRecord:
        from maref.recursive.unified_audit import UnifiedAuditRecord

        outcome: str | None = None
        if "success" in self.details.lower() or "recovery" in self.event_type:
            outcome = "success"
        elif "trip" in self.event_type or "failure" in self.details.lower():
            outcome = "failure"

        return UnifiedAuditRecord(
            record_id=self.id,
            timestamp=self.timestamp,
            layer=layer or self.layer,
            round=round_num if round_num is not None else self.round,
            event_type=self.event_type,
            source_module=self.actor,
            target_module=self.metadata.get("target_module", ""),
            decision=self.action,
            justification=self.details,
            outcome=outcome,
            context_refs=[],
            tenant_id=self.tenant_id,
        )


class AuditLogger:
    """
    Append-only audit logger with Ed25519 (primary) and HMAC (legacy) signing.

    Writes structured JSON lines to a log file. Each entry is
    a single JSON object per line for easy parsing and streaming.

    v0.38.0+ uses Ed25519 signing by default (requires Ed25519KeyPair).
    v0.37.0 HMAC-SHA256 entries remain readable (backward compatible).

    Usage:
        # Ed25519 mode (v0.38.0+)
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        logger = AuditLogger(
            Path("audit.jsonl"),
            ed25519_keypair=Ed25519KeyPair.generate(),
        )
        logger.log_decision(...)

        # Legacy HMAC mode (v0.37.0)
        logger = AuditLogger(
            Path("audit.jsonl"),
            hmac_key="my-hmac-key",
        )
    """

    def __init__(
        self,
        log_path: Path | str | None = None,
        hmac_key: bytes | str | None = None,
        max_file_size_mb: int = 50,
        ed25519_keypair: Any | None = None,
        chain_integrator: Any | None = None,
    ) -> None:
        if log_path is None:
            self._path: Path | None = None
            self._memory_entries: list[AuditEntry] = []
        else:
            self._path = Path(log_path) if not isinstance(log_path, Path) else log_path
            self._memory_entries = []
        self._write_lock: Any = __import__("threading").Lock()
        self._max_file_size = max_file_size_mb * 1024 * 1024
        self._chain_integrator = chain_integrator

        # Resolve Ed25519 keypair (env var takes precedence)
        resolved_keypair = ed25519_keypair
        if resolved_keypair is None:
            env_ed25519 = os.environ.get(_ED25519_KEY_ENV)
            if env_ed25519:
                from maref.crypto.ed25519_keys import Ed25519KeyPair
                resolved_keypair = Ed25519KeyPair.from_private_pem(env_ed25519)
        self._ed25519_keypair = resolved_keypair

        # Resolve HMAC key (fallback for legacy logs)
        self._hmac_key: bytes | None = None
        if hmac_key is not None:
            self._hmac_key = hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        elif not self._ed25519_keypair:
            env_key = os.environ.get(_HMAC_KEY_ENV)
            if env_key is None:
                raise RuntimeError(
                    "Either an Ed25519 keypair or HMAC key is required. "
                    f"Set {_ED25519_KEY_ENV} (Ed25519 PEM), {_HMAC_KEY_ENV} (HMAC, legacy), "
                    "or pass ed25519_keypair/hmac_key to AuditLogger()."
                )
            self._hmac_key = env_key.encode("utf-8")

    def _sign_entry(self, entry: AuditEntry) -> str:
        payload = entry._payload_for_signing().encode("utf-8")
        if self._ed25519_keypair:
            sig = self._ed25519_keypair.sign(payload)
            return sig.hex()
        assert self._hmac_key is not None
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    @property
    def _signer_fingerprint(self) -> str:
        if self._ed25519_keypair:
            return self._ed25519_keypair.fingerprint
        return ""

    def _entry_with_signature(self, entry: AuditEntry) -> AuditEntry:
        sig = self._sign_entry(entry)
        if self._ed25519_keypair:
            return AuditEntry(
                id=entry.id,
                timestamp=entry.timestamp,
                event_type=entry.event_type,
                actor=entry.actor,
                action=entry.action,
                details=entry.details,
                metadata=entry.metadata,
                parent_action_id=entry.parent_action_id,
                previous_hash=entry.previous_hash,
                chain_hash=entry.chain_hash,
                ed25519_signature=sig,
                signer_fingerprint=self._signer_fingerprint,
                tenant_id=entry.tenant_id,
                layer=entry.layer,
                round=entry.round,
            )
        return AuditEntry(
            id=entry.id,
            timestamp=entry.timestamp,
            event_type=entry.event_type,
            actor=entry.actor,
            action=entry.action,
            details=entry.details,
            metadata=entry.metadata,
            parent_action_id=entry.parent_action_id,
            previous_hash=entry.previous_hash,
            chain_hash=entry.chain_hash,
            hmac_signature=sig,
            tenant_id=entry.tenant_id,
            layer=entry.layer,
            round=entry.round,
        )

    def _compute_chain_hash(self, entry: AuditEntry) -> str:
        payload = entry._payload_for_signing().encode("utf-8")
        return hashlib.sha256(entry.previous_hash.encode("utf-8") + payload).hexdigest()

    def verify_integrity(
        self,
        ed25519_public_key_pem: str | None = None,
    ) -> dict[str, Any]:
        """Verify the integrity of all entries in the audit log.

        Handles both HMAC-SHA256 (v0.37.0) and Ed25519 (v0.38.0+) signatures.

        Args:
            ed25519_public_key_pem: Required for verifying Ed25519-signed entries.
                If not provided, Ed25519 entries will be flagged as unverifiable.
                HMAC entries are verified using the configured ``hmac_key``.

        Returns:
            A dict with integrity verification results.
        """
        entries = self.read_all()
        total = len(entries)
        signed = sum(1 for e in entries if e.signature_type != "unsigned")
        valid = 0
        issues: list[str] = []
        previous_chain_hash = ""

        for entry in entries:
            if entry.previous_hash != previous_chain_hash:
                issues.append(entry.id)

            sig_type = entry.signature_type
            if sig_type == "unsigned":
                issues.append(entry.id)
                previous_chain_hash = entry.chain_hash
                continue

            if sig_type == "ed25519":
                if ed25519_public_key_pem is None:
                    issues.append(entry.id)
                else:
                    from maref.crypto.ed25519_keys import Ed25519KeyPair
                    payload = entry._payload_for_signing().encode("utf-8")
                    sig_bytes = bytes.fromhex(entry.ed25519_signature)
                    if Ed25519KeyPair.verify(ed25519_public_key_pem, sig_bytes, payload):
                        valid += 1
                    else:
                        issues.append(entry.id)
            else:
                expected = self._sign_entry(
                    AuditEntry(
                        id=entry.id,
                        timestamp=entry.timestamp,
                        event_type=entry.event_type,
                        actor=entry.actor,
                        action=entry.action,
                        details=entry.details,
                        metadata=entry.metadata,
                        previous_hash=entry.previous_hash,
                    )
                )
                if hmac.compare_digest(expected, entry.hmac_signature):
                    valid += 1
                else:
                    issues.append(entry.id)

            if entry.chain_hash:
                expected_chain = self._compute_chain_hash(entry)
                if not hmac.compare_digest(expected_chain, entry.chain_hash):
                    issues.append(entry.id)
            else:
                issues.append(entry.id)

            previous_chain_hash = entry.chain_hash

        unique_issues = sorted(set(issues))
        return {
            "total_entries": total,
            "signed_entries": signed,
            "valid_signatures": valid,
            "tampered_entries": unique_issues,
            "integrity_intact": len(unique_issues) == 0,
        }

    def log(
        self,
        event_type: str,
        actor: str,
        action: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
        parent_action_id: str = "",
        tenant_id: str = "",
        layer: str = "governance",
        round: int = 0,
    ) -> AuditEntry:
        import uuid

        now = time.time()
        previous_hash = self._memory_entries[-1].chain_hash if self._memory_entries else ""
        if self._path is not None and self._path.exists() and not self._memory_entries:
            existing = self.read_all(max_entries=None)
            if existing:
                previous_hash = existing[-1].chain_hash
        entry = AuditEntry(
            id=uuid.uuid4().hex[:8],
            timestamp=now,
            event_type=event_type,
            actor=actor,
            action=action,
            details=details,
            metadata=metadata or {},
            parent_action_id=parent_action_id,
            previous_hash=previous_hash,
            tenant_id=tenant_id,
            layer=layer,
            round=round,
        )
        signed_entry = self._write(entry)
        return signed_entry

    def log_decision(
        self,
        actor: str,
        action: str,
        reason: str = "",
        from_state: str = "",
        to_state: str = "",
        **extra: Any,
    ) -> AuditEntry:
        return self.log(
            event_type="governance_decision",
            actor=actor,
            action=action,
            details=reason,
            metadata={
                "from_state": from_state,
                "to_state": to_state,
                **extra,
            },
        )

    def log_anomaly(
        self,
        actor: str,
        anomaly_type: str,
        severity: str,
        description: str = "",
    ) -> AuditEntry:
        return self.log(
            event_type="anomaly_detected",
            actor=actor,
            action="handle_anomaly",
            details=description,
            metadata={
                "anomaly_type": anomaly_type,
                "severity": severity,
            },
        )

    def _write(self, entry: AuditEntry) -> AuditEntry:
        signed_entry = self._entry_with_signature(entry)
        chain_hash = self._compute_chain_hash(signed_entry)
        final_entry = AuditEntry(
            id=signed_entry.id,
            timestamp=signed_entry.timestamp,
            event_type=signed_entry.event_type,
            actor=signed_entry.actor,
            action=signed_entry.action,
            details=signed_entry.details,
            metadata=signed_entry.metadata,
            parent_action_id=signed_entry.parent_action_id,
            previous_hash=signed_entry.previous_hash,
            chain_hash=chain_hash,
            hmac_signature=signed_entry.hmac_signature,
            ed25519_signature=signed_entry.ed25519_signature,
            signer_fingerprint=signed_entry.signer_fingerprint,
        )
        if self._chain_integrator is not None:
            self._chain_integrator.record_audit_entry(final_entry)
        if self._path is None:
            self._memory_entries.append(final_entry)
            return final_entry
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and self._path.stat().st_size >= self._max_file_size:
            self._rotate()
        line = json.dumps(final_entry.to_dict(), ensure_ascii=False, default=str)
        with self._write_lock, open(self._path, "a") as f:
            f.write(line + "\n")
        return final_entry

    def _rotate(self) -> None:
        """Rotate audit log: rename current file, start a new one."""
        assert self._path is not None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        rotated = self._path.with_name(f"{self._path.stem}_{timestamp}{self._path.suffix}")
        self._path.rename(rotated)

    def read_all(self, max_entries: int | None = 1000) -> list[AuditEntry]:
        if max_entries is None:
            logger.warning("read_all without limit — may cause OOM on large audit logs")
        if self._path is None:
            return list(
                self._memory_entries[-max_entries:] if max_entries else self._memory_entries
            )
        if not self._path.exists():
            return []
        entries: list[AuditEntry] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entries.append(
                            AuditEntry(
                                id=data["id"],
                                timestamp=data["timestamp"],
                                event_type=data["event_type"],
                                actor=data["actor"],
                                action=data["action"],
                                details=data["details"],
                                metadata=data.get("metadata", {}),
                                parent_action_id=data.get("parent_action_id", ""),
                                previous_hash=data.get("previous_hash", ""),
                                chain_hash=data.get("chain_hash", ""),
                                hmac_signature=data.get("hmac_signature", ""),
                                ed25519_signature=data.get("ed25519_signature", ""),
                                signer_fingerprint=data.get("signer_fingerprint", ""),
                            )
                        )
                    except (json.JSONDecodeError, KeyError):
                        continue
                if max_entries and len(entries) >= max_entries:
                    break
        return entries[-max_entries:] if max_entries else entries

    def read_recent(self, n: int = 100) -> list[AuditEntry]:
        return self.read_all(max_entries=n)

    def read_filtered(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        max_entries: int | None = 1000,
    ) -> list[AuditEntry]:
        if self._path is None:
            filtered = []
            for entry in self._memory_entries:
                if event_type and entry.event_type != event_type:
                    continue
                if actor and entry.actor != actor:
                    continue
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                filtered.append(entry)
        elif not self._path.exists():
            return []
        else:
            filtered = []
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if event_type and data.get("event_type") != event_type:
                        continue
                    if actor and data.get("actor") != actor:
                        continue
                    if start_time and data.get("timestamp", 0) < start_time:
                        continue
                    if end_time and data.get("timestamp", float("inf")) > end_time:
                        continue
                    filtered.append(
                        AuditEntry(
                            id=data["id"],
                            timestamp=data["timestamp"],
                            event_type=data["event_type"],
                            actor=data["actor"],
                            action=data["action"],
                            details=data["details"],
                            metadata=data.get("metadata", {}),
                            previous_hash=data.get("previous_hash", ""),
                            chain_hash=data.get("chain_hash", ""),
                            hmac_signature=data.get("hmac_signature", ""),
                            ed25519_signature=data.get("ed25519_signature", ""),
                            signer_fingerprint=data.get("signer_fingerprint", ""),
                        )
                    )
                    if max_entries and len(filtered) >= max_entries:
                        break
        return filtered[-max_entries:] if max_entries else filtered

    def export_syslog(self, max_entries: int | None = 1000) -> str:
        """Export audit entries in RFC 5424 syslog format."""
        entries = self.read_all(max_entries=max_entries)
        lines: list[str] = []
        for entry in entries:
            priority = 14 * 8 + 6
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(entry.timestamp))
            lines.append(
                f"<{priority}>1 {timestamp} maref MAREF - - "
                f'[audit@32473 event="{entry.event_type}" actor="{entry.actor}" action="{entry.action}"] '
                f"{entry.details}"
            )
        return "\n".join(lines)

    def export_json(
        self,
        event_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        max_entries: int | None = 1000,
    ) -> list[dict[str, Any]]:
        """Export audit entries as JSON list with optional filtering."""
        entries = self.read_filtered(
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            max_entries=max_entries,
        )
        return [entry.to_dict() for entry in entries]

    def get_audit_trail(self, max_entries: int | None = 1000) -> list[AuditEntry]:
        """Return the audit trail with optional limit."""
        return self.read_all(max_entries=max_entries)

    def count(self) -> int:
        return len(self._memory_entries)
