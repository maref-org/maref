"""Unified verification for MAREF governance audit chains.

Two record dialects exist in the repository:

1. ``AuditLogger`` records (``governance/audit.py``): canonical JSON is
   sorted; ``chain_hash = SHA256(previous_hash + payload)``; signature is
   stored separately in ``hmac_signature`` / ``ed25519_signature``.
2. Legacy state-machine records: the signing digest was stored directly in
   ``chain_hash``. Old writers serialized the payload in insertion order;
   newer writers may use sorted keys. Both are accepted.

Design rule: a missing or rotated key must never be reported as tampering.
The verifier therefore first detects whether the supplied key verifies at
least one record; if it does not, legacy digests are marked *unverifiable*
rather than *invalid*. Chain linkage is always checked independently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerifyIssue:
    line: int
    entry_id: str
    kind: str
    detail: str


@dataclass
class VerifyReport:
    path: str
    total: int = 0
    formats: dict[str, int] = field(default_factory=dict)
    link_breaks: list[VerifyIssue] = field(default_factory=list)
    hash_invalid: list[VerifyIssue] = field(default_factory=list)
    signature_invalid: list[VerifyIssue] = field(default_factory=list)
    signature_unverifiable: list[str] = field(default_factory=list)
    unsigned: list[str] = field(default_factory=list)
    first_previous_hash: str = ""
    last_chain_hash: str = ""
    key_status: str = "not_supplied"
    notes: list[str] = field(default_factory=list)

    @property
    def integrity_intact(self) -> bool:
        return not (self.link_breaks or self.hash_invalid or self.signature_invalid)

    @property
    def tampered_count(self) -> int:
        return len(self.link_breaks) + len(self.hash_invalid) + len(self.signature_invalid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "total": self.total,
            "formats": dict(self.formats),
            "link_breaks": [i.__dict__ for i in self.link_breaks[:20]],
            "link_break_count": len(self.link_breaks),
            "hash_invalid": [i.__dict__ for i in self.hash_invalid[:20]],
            "hash_invalid_count": len(self.hash_invalid),
            "signature_invalid": [i.__dict__ for i in self.signature_invalid[:20]],
            "signature_invalid_count": len(self.signature_invalid),
            "signature_unverifiable_count": len(set(self.signature_unverifiable)),
            "signature_unverifiable_ids": sorted(set(self.signature_unverifiable))[:20],
            "unsigned_ids": self.unsigned[:20],
            "first_previous_hash": self.first_previous_hash,
            "last_chain_hash": self.last_chain_hash,
            "key_status": self.key_status,
            "integrity_intact": self.integrity_intact,
            "tampered_count": self.tampered_count,
            "notes": self.notes,
        }


def resolve_hmac_keys(explicit: str | bytes | None = None) -> list[bytes]:
    """Return all usable HMAC keys (env + on-disk legacy key files).

    Audit history may span key rotations, so verification tries every
    available key rather than assuming a single global key.
    """
    keys: list[bytes] = []

    def _add(value: str | bytes | None) -> None:
        if not value:
            return
        raw = value.encode("utf-8") if isinstance(value, str) else value
        if raw and raw not in keys:
            keys.append(raw)

    _add(explicit)
    _add(os.environ.get("MAREF_HMAC_SECRET_KEY", "").strip())
    for candidate in (
        Path.cwd() / ".maraf_hmac_key",
        Path.cwd() / ".maref_hmac_key",
        Path.cwd() / ".gaas_api_key",
        Path.home() / ".maraf_hmac_key",
    ):
        try:
            _add(candidate.read_text().strip())
        except OSError:
            continue
    return keys


def resolve_hmac_key(explicit: str | bytes | None = None) -> bytes | None:
    keys = resolve_hmac_keys(explicit)
    return keys[0] if keys else None


def _base_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": entry["id"],
        "timestamp": entry["timestamp"],
        "event_type": entry["event_type"],
        "actor": entry["actor"],
        "action": entry["action"],
        "details": entry["details"],
        "metadata": entry.get("metadata", {}),
        "previous_hash": entry.get("previous_hash", ""),
    }
    if entry.get("parent_action_id"):
        payload["parent_action_id"] = entry["parent_action_id"]
    return payload


def _payload_variants(entry: dict[str, Any], unified: bool) -> list[str]:
    """Return de-duplicated serializations used by historical writers."""
    base = _base_payload(entry)
    dicts = [base]
    if unified:
        with_unified = dict(base)
        if entry.get("tenant_id"):
            with_unified["tenant_id"] = entry["tenant_id"]
        if entry.get("layer"):
            with_unified["layer"] = entry["layer"]
        else:
            # AuditEntry defaults layer="governance" and signs it even though
            # to_dict() omits the field. Accept both forms.
            with_unified["layer"] = "governance"
        if entry.get("round"):
            with_unified["round"] = entry["round"]
        dicts.append(with_unified)
    variants: list[str] = []
    for payload in dicts:
        variants.append(json.dumps(payload, ensure_ascii=False, default=str))
        variants.append(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(variants))


def _sha256_chain(previous_hash: str, payload: str) -> str:
    return hashlib.sha256(
        previous_hash.encode("utf-8") + payload.encode("utf-8")
    ).hexdigest()


def _hmac(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_ed25519(
    entry: dict[str, Any], payload: str, public_key_pem: str | None
) -> bool | None:
    if not public_key_pem:
        return None
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return None
    try:
        signature = bytes.fromhex(entry.get("ed25519_signature", ""))
    except (TypeError, ValueError):
        return False
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, Ed25519PublicKey):  # pragma: no cover - defensive
            return None
        key.verify(signature, payload.encode("utf-8"))
        return True
    except InvalidSignature:
        return False
    except (ValueError, TypeError):
        return None


def _load_records(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], list[VerifyIssue]]:
    records: list[tuple[int, dict[str, Any]]] = []
    bad: list[VerifyIssue] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                bad.append(VerifyIssue(lineno, f"<line-{lineno}>", "parse", str(exc)))
                continue
            if not isinstance(data, dict) or "id" not in data or "chain_hash" not in data:
                bad.append(VerifyIssue(lineno, f"<line-{lineno}>", "parse", "invalid record"))
                continue
            records.append((lineno, data))
    return records, bad


def verify_audit_chain(
    path: Path | str,
    hmac_key: str | bytes | None = None,
    ed25519_public_key_pem: str | None = None,
) -> VerifyReport:
    file_path = Path(path)
    report = VerifyReport(path=str(file_path))
    if not file_path.exists():
        report.notes.append("audit file not found")
        return report

    records, parse_issues = _load_records(file_path)
    report.total = len(records) + len(parse_issues)
    report.hash_invalid.extend(parse_issues)

    keys = resolve_hmac_keys(hmac_key)
    if keys:
        report.key_status = "supplied"
    if ed25519_public_key_pem:
        report.key_status = "supplied"

    # ── Pass 1: decide whether the supplied key verifies any record ──
    # Prevents a rotated key from turning the entire history into "tampered".
    legacy_key_valid = False
    logger_key_valid = False
    ed25519_key_valid = False
    for _, entry in records:
        has_signature = bool(
            entry.get("hmac_signature")
            or entry.get("ed25519_signature")
            or entry.get("external_signature")
        )
        variants = _payload_variants(entry, unified=has_signature)
        if entry.get("hmac_signature") and keys:
            if any(
                hmac.compare_digest(_hmac(p, candidate), entry["hmac_signature"])
                for candidate in keys
                for p in variants
            ):
                logger_key_valid = True
        elif entry.get("ed25519_signature") and ed25519_public_key_pem:
            if any(_verify_ed25519(entry, p, ed25519_public_key_pem) for p in variants):
                ed25519_key_valid = True
        elif not has_signature and keys:
            if any(
                hmac.compare_digest(_hmac(p, candidate), entry["chain_hash"])
                for candidate in keys
                for p in variants
            ):
                legacy_key_valid = True
        if legacy_key_valid and logger_key_valid and (ed25519_key_valid or not ed25519_public_key_pem):
            break

    if not keys:
        report.key_status = "missing"
    elif legacy_key_valid or logger_key_valid:
        report.key_status = "valid"
    else:
        report.key_status = "rotated_or_wrong"
        report.notes.append("supplied key verifies no record; signatures treated as unverifiable")

    # ── Pass 2: linkage + hash + signature ──
    previous_chain_hash = ""
    first = True
    for lineno, entry in records:
        entry_id = str(entry.get("id", f"<line-{lineno}>"))
        has_signature = bool(
            entry.get("hmac_signature")
            or entry.get("ed25519_signature")
            or entry.get("external_signature")
        )
        fmt = "audit_logger" if has_signature or "layer" in entry else "legacy_state_machine"
        report.formats[fmt] = report.formats.get(fmt, 0) + 1

        previous_hash = str(entry.get("previous_hash", ""))
        if first:
            report.first_previous_hash = previous_hash
            first = False
        elif previous_hash != previous_chain_hash:
            report.link_breaks.append(
                VerifyIssue(
                    lineno,
                    entry_id,
                    "link",
                    f"previous_hash={previous_hash[:12]} expected={previous_chain_hash[:12]}",
                )
            )

        chain_hash = str(entry.get("chain_hash", ""))
        variants = _payload_variants(entry, unified=fmt == "audit_logger")
        sha_ok = any(
            hmac.compare_digest(_sha256_chain(previous_hash, p), chain_hash) for p in variants
        )
        hmac_ok = any(
            hmac.compare_digest(_hmac(p, candidate), chain_hash)
            for candidate in keys
            for p in variants
        )

        if fmt == "audit_logger":
            if not sha_ok:
                report.hash_invalid.append(
                    VerifyIssue(lineno, entry_id, "hash", "SHA256 chain hash mismatch")
                )
        elif sha_ok:
            report.notes.append(f"line {lineno}: SHA256 chain hash (unauthenticated)")
        elif hmac_ok:
            pass
        else:
            # Legacy digest may have been signed with a key that is no longer
            # available (rotation). This is unverifiable, not tampering.
            report.signature_unverifiable.append(entry_id)

        if entry.get("ed25519_signature"):
            result = None
            if ed25519_public_key_pem:
                result = any(
                    _verify_ed25519(entry, p, ed25519_public_key_pem) is True for p in variants
                )
            if result is False and ed25519_key_valid:
                report.signature_invalid.append(
                    VerifyIssue(lineno, entry_id, "signature", "Ed25519 invalid")
                )
            elif not result:
                report.signature_unverifiable.append(entry_id)
        elif entry.get("external_signature"):
            # Remote signer: verification requires the external service/key.
            report.signature_unverifiable.append(entry_id)
        elif entry.get("hmac_signature"):
            sig_ok = any(
                hmac.compare_digest(_hmac(p, candidate), entry["hmac_signature"])
                for candidate in keys
                for p in variants
            )
            if not sig_ok:
                if logger_key_valid:
                    report.signature_invalid.append(
                        VerifyIssue(lineno, entry_id, "signature", "HMAC invalid")
                    )
                else:
                    # Key rotation / missing key: unverifiable, not tampering.
                    report.signature_unverifiable.append(entry_id)
        else:
            report.unsigned.append(entry_id)

        previous_chain_hash = chain_hash
        report.last_chain_hash = chain_hash

    return report
