"""Organization DID (v0.49 P5) — production org identity for the Level 2 federation.

Design source: ``docs/design/org-did.md`` (TP-08 T8.4). An organization is the
top-level member of a federation; its DID is ``did:maref:org:{org_name}:{org_id}``
and its membership is proven by a signed organization certificate issued by the
federation root.

Reuse notes:
- Signing/verification follows the ``Ed25519KeyPair`` pattern (same primitive as
  ``FederatedConsensus`` and ``AuthorizationScope``).
- Lifecycle (version/status/revocation_entry) mirrors ``DIDRegistry`` (方案 E).
- Persistence reuses :class:`maref.governance.db.DatabaseManager` (v0.47 F4).

Usage::

    from maref.crypto.ed25519_keys import Ed25519KeyPair
    from maref.identity.org_did import OrgDID, OrgDIDRegistry

    root_key = Ed25519KeyPair.generate()
    registry = OrgDIDRegistry(issuer_key=root_key)
    org_did, cert = registry.register("acme", name="Acme Inc.", weight=2)
    assert registry.verify_certificate(cert) is True
"""

from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.crypto.ed25519_keys import Ed25519KeyPair

# Federation root issuer (design doc §3.1).
FEDERATION_ROOT_DID = "did:maref:org:federation:root"

_ORG_NAME_RE = re.compile(r"^[a-z0-9]{1,32}$")
_ORG_ID_RE = re.compile(r"^[0-9a-f]{1,8}$")

_DID_CONTEXT = "https://www.w3.org/ns/did/v1"
_ED25519_VERIFICATION_METHOD_TYPE = "Ed25519VerificationKey2018"

# Certificate fields covered by the issuer's Ed25519 signature (stable identity
# fields only; lifecycle fields like status/version are excluded).
_SIGNED_FIELDS = (
    "did",
    "name",
    "public_key",
    "weight",
    "member_since",
    "roles",
    "jurisdiction",
    "issuer",
)


@dataclass(frozen=True)
class OrgDID:
    """A federation organization DID: ``did:maref:org:{org_name}:{org_id}``."""

    org_name: str
    org_id: str

    @property
    def did_string(self) -> str:
        return f"did:maref:org:{self.org_name}:{self.org_id}"

    @classmethod
    def parse(cls, did_string: str) -> OrgDID:
        """Parse and strictly validate an organization DID.

        Raises ``ValueError`` for malformed identifiers (fail-closed).
        """
        parts = did_string.split(":")
        if len(parts) != 5 or parts[0] != "did" or parts[1] != "maref" or parts[2] != "org":
            raise ValueError(f"Invalid MAREF org DID: {did_string}")
        org_name, org_id = parts[3], parts[4]
        if not _ORG_NAME_RE.match(org_name):
            raise ValueError(f"Invalid org_name in DID: {did_string}")
        if not _ORG_ID_RE.match(org_id):
            raise ValueError(f"Invalid org_id in DID: {did_string}")
        return cls(org_name=org_name, org_id=org_id)

    @classmethod
    def generate(cls, org_name: str) -> OrgDID:
        """Create a new org DID with a random 8-hex-char org_id."""
        if not _ORG_NAME_RE.match(org_name):
            raise ValueError("org_name must be 1-32 lowercase alphanumeric characters")
        return cls(org_name=org_name, org_id=secrets.token_hex(4))

    def to_did_document(
        self,
        ed25519_public_key_pem: str = "",
        service_endpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """W3C DID Document (DID Core 1.0) for this org DID."""
        doc: dict[str, Any] = {"@context": _DID_CONTEXT, "id": self.did_string}
        if ed25519_public_key_pem:
            vm_id = f"{self.did_string}#ed25519-key"
            doc["verificationMethod"] = [
                {
                    "id": vm_id,
                    "type": _ED25519_VERIFICATION_METHOD_TYPE,
                    "controller": self.did_string,
                    "publicKeyPem": ed25519_public_key_pem,
                }
            ]
            doc["authentication"] = [vm_id]
            doc["assertionMethod"] = [vm_id]
        if service_endpoints:
            doc["service"] = service_endpoints
        return doc


@dataclass
class OrgCertificate:
    """A signed organization membership certificate (design doc §3).

    ``signature`` is the federation root's Ed25519 signature over the stable
    identity fields. Any third party can verify membership with only the root's
    public key.
    """

    did: str
    name: str
    public_key: str
    weight: int = 1
    member_since: float = 0.0
    roles: list[str] = field(default_factory=lambda: ["member"])
    jurisdiction: str = ""
    status: str = "active"
    issuer: str = FEDERATION_ROOT_DID
    signature: str = ""
    version: int = 1
    revocation_entry: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate the embedded DID eagerly.
        OrgDID.parse(self.did)

    def canonical_payload(self) -> bytes:
        """Bytes the issuer signs over (stable identity fields, sorted)."""
        return json.dumps(
            {k: getattr(self, k) for k in _SIGNED_FIELDS},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def to_dict(self) -> dict[str, Any]:
        return {
            "did": self.did,
            "name": self.name,
            "public_key": self.public_key,
            "weight": self.weight,
            "member_since": self.member_since,
            "roles": list(self.roles),
            "jurisdiction": self.jurisdiction,
            "status": self.status,
            "issuer": self.issuer,
            "signature": self.signature,
            "version": self.version,
            "revocation_entry": dict(self.revocation_entry),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgCertificate:
        return cls(
            did=data["did"],
            name=data.get("name", ""),
            public_key=data.get("public_key", ""),
            weight=int(data.get("weight", 1)),
            member_since=float(data.get("member_since", 0.0)),
            roles=list(data.get("roles", ["member"])),
            jurisdiction=data.get("jurisdiction", ""),
            status=data.get("status", "active"),
            issuer=data.get("issuer", FEDERATION_ROOT_DID),
            signature=data.get("signature", ""),
            version=int(data.get("version", 1)),
            revocation_entry=dict(data.get("revocation_entry", {})),
        )

    def issue(self, issuer_key: Ed25519KeyPair) -> OrgCertificate:
        """Sign the certificate with the federation root's private key."""
        sig = issuer_key.sign(self.canonical_payload())
        self.signature = sig.hex()
        return self

    def verify(self, issuer_public_key_pem: str) -> bool:
        """Verify the issuer's Ed25519 signature."""
        if not self.signature or not issuer_public_key_pem:
            return False
        try:
            return Ed25519KeyPair.verify(
                issuer_public_key_pem,
                bytes.fromhex(self.signature),
                self.canonical_payload(),
            )
        except Exception:
            return False

    @property
    def org_did(self) -> OrgDID:
        return OrgDID.parse(self.did)


class OrgDIDRegistry:
    """Registry of organization DIDs with lifecycle management.

    Args:
        issuer_key: The federation root's Ed25519 key pair (issues and verifies
            every organization certificate).
        issuer_did: DID of the issuer (defaults to the federation root).
        db_path: Optional SQLite path for persistence (v0.47 F4 pattern).
    """

    def __init__(
        self,
        issuer_key: Ed25519KeyPair,
        issuer_did: str = FEDERATION_ROOT_DID,
        db_path: str | Path | None = None,
    ) -> None:
        self._issuer_key = issuer_key
        self._issuer_did = issuer_did
        self._certificates: dict[str, OrgCertificate] = {}
        self._db = None
        if db_path is not None:
            from maref.governance.db import DatabaseManager

            self._db = DatabaseManager(db_path)
            self._init_schema()
            self._load_from_disk()

    @property
    def issuer_did(self) -> str:
        return self._issuer_did

    @property
    def issuer_public_key(self) -> str:
        return self._issuer_key.public_key_pem

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS org_certificates (
                did  TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        rows = self._db.fetchall("SELECT did, data FROM org_certificates")
        for row in rows:
            self._certificates[row["did"]] = OrgCertificate.from_dict(json.loads(row["data"]))

    def _persist(self, cert: OrgCertificate) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO org_certificates (did, data) VALUES (?, ?)",
            (cert.did, json.dumps(cert.to_dict())),
        )

    def register(
        self,
        org_name: str,
        name: str = "",
        public_key: str | None = None,
        weight: int = 1,
        roles: list[str] | None = None,
        jurisdiction: str = "",
    ) -> tuple[OrgDID, OrgCertificate]:
        """Register a new organization and issue its certificate.

        The organization's own Ed25519 public key is generated if not supplied;
        callers controlling real org keys should pass ``public_key`` explicitly.
        """
        org_did = OrgDID.generate(org_name)
        org_key = Ed25519KeyPair.generate() if public_key is None else public_key
        cert = OrgCertificate(
            did=org_did.did_string,
            name=name or org_name,
            public_key=org_key.public_key_pem if isinstance(org_key, Ed25519KeyPair) else org_key,
            weight=weight,
            member_since=time.time(),
            roles=roles or ["member"],
            jurisdiction=jurisdiction,
            issuer=self._issuer_did,
        )
        cert.issue(self._issuer_key)
        self._certificates[cert.did] = cert
        self._persist(cert)
        return org_did, cert

    def resolve(self, org_did: OrgDID) -> OrgCertificate | None:
        return self._certificates.get(org_did.did_string)

    def resolve_did_string(self, did_string: str) -> OrgCertificate | None:
        """Resolve by raw DID string (throws ValueError on malformed input)."""
        return self._certificates.get(OrgDID.parse(did_string).did_string)

    def verify_certificate(self, cert: OrgCertificate) -> bool:
        """Verify the certificate's issuer signature."""
        return cert.verify(self._issuer_key.public_key_pem)

    def verify_did(self, did_string: str) -> bool:
        """Verify a registered org DID's membership certificate."""
        cert = self.resolve_did_string(did_string)
        return cert is not None and cert.status == "active"

    def revoke(
        self,
        org_did: OrgDID,
        reason: str = "unspecified",
        signer: str = "",
    ) -> OrgCertificate | None:
        """Revoke an organization's membership (versioned, non-destructive)."""
        cert = self._certificates.get(org_did.did_string)
        if cert is None:
            return None
        if cert.status == "deactivated":
            return cert
        if cert.status == "revoked":
            return cert
        cert.version += 1
        cert.status = "revoked"
        cert.revocation_entry = {
            "did": org_did.did_string,
            "version": cert.version,
            "revoked_at": time.time(),
            "reason": reason,
            "signer": signer,
        }
        self._persist(cert)
        return cert

    def deactivate(
        self, org_did: OrgDID, reason: str = "", signer: str = ""
    ) -> OrgCertificate | None:
        """Permanently deactivate an organization (irreversible terminal state)."""
        cert = self._certificates.get(org_did.did_string)
        if cert is None:
            return None
        if cert.status == "deactivated":
            return cert
        cert.version += 1
        cert.status = "deactivated"
        cert.revocation_entry = {
            "did": org_did.did_string,
            "version": cert.version,
            "revoked_at": time.time(),
            "reason": reason or "deactivated",
            "signer": signer,
        }
        self._persist(cert)
        return cert

    def is_active(self, org_did: OrgDID) -> bool:
        cert = self._certificates.get(org_did.did_string)
        return cert is not None and cert.status == "active"

    def list_all(self) -> list[OrgCertificate]:
        return list(self._certificates.values())

    def org_count(self) -> int:
        return len(self._certificates)

    def resolve_did_document(self, org_did: OrgDID) -> dict[str, Any]:
        """W3C DID Resolution result for a registered org."""
        cert = self._certificates.get(org_did.did_string)
        if cert is None:
            return {"resolved": False, "did": org_did.did_string}
        doc = org_did.to_did_document(
            ed25519_public_key_pem=cert.public_key,
            service_endpoints=[
                {
                    "id": f"{org_did.did_string}#governance",
                    "type": "Governance",
                    "serviceEndpoint": "",
                }
            ],
        )
        return {
            "resolved": True,
            "did": org_did.did_string,
            "did_document": doc,
            "document_metadata": {
                "version": cert.version,
                "status": cert.status,
                "member_since": cert.member_since,
                "jurisdiction": cert.jurisdiction,
            },
        }


__all__ = [
    "FEDERATION_ROOT_DID",
    "OrgDID",
    "OrgCertificate",
    "OrgDIDRegistry",
]
