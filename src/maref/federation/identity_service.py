"""Phase 3.4 — global identity service.

Combines the in-memory :class:`DIDRegistry` and :class:`AICIdentityAdapter`
into a unified, HTTP-facing identity service:

1. **DID lifecycle** — ``did:maref:{namespace}:{short_id}`` create /
   resolve (W3C DID Document) / deactivate (soft delete, resolution then
   reports ``deactivated``).
2. **AIC derivation + verification** — every created DID is automatically
   bound to a fresh ACPs AIC (AUTOSAR CRC-16/CCITT-FALSE checksum via
   :func:`~maref.identity.aic_adapter.compute_aic_checksum`), and any AIC
   string can be verified and translated back to its DID.
3. **Optional JSONL persistence** — identity state survives restarts by
   replaying an append-only change log (same pattern as the audit log).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from maref.governance.state_machine import GovernanceStateMachine
from maref.identity.aic_adapter import AIC, AICIdentityAdapter
from maref.identity.did_registry import AgentDID, DIDRegistry


@dataclass(frozen=True)
class IdentityCreationResult:
    """Result of a DID creation: DID, derived AIC, and DID Document."""

    did: str
    aic: str
    did_document: dict[str, Any]
    registered_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "did": self.did,
            "aic": self.aic,
            "did_document": self.did_document,
            "registered_at": self.registered_at,
        }


class IdentityService:
    """Unified DID + AIC identity service with optional JSONL persistence.

    Attributes:
        registry: The underlying :class:`DIDRegistry`.
        adapter: The underlying :class:`AICIdentityAdapter`.
    """

    def __init__(
        self,
        registry: DIDRegistry | None = None,
        adapter: AICIdentityAdapter | None = None,
        persist_path: str | Path | None = None,
    ) -> None:
        self.registry = registry or DIDRegistry()
        self.adapter = adapter or AICIdentityAdapter()
        self._persist_path = Path(persist_path) if persist_path is not None else None
        self._deactivated: set[str] = set()
        self._deactivated_at: dict[str, float] = {}
        self._persist_handle: TextIO | None = None
        if self._persist_path is not None:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    # ── DID lifecycle ───────────────────────────────────────────────────

    def create_did(
        self,
        namespace: str = "default",
        roles: list[str] | None = None,
        ed25519_public_key_pem: str = "",
        service_endpoints: list[dict[str, Any]] | None = None,
        aic: dict[str, Any] | None = None,
    ) -> IdentityCreationResult:
        """Create a new ``did:maref:{namespace}:{id}`` with a derived AIC.

        Args:
            namespace: DID namespace (must not contain ``:``).
            roles: Initial agent roles.
            ed25519_public_key_pem: Ed25519 public key for the DID Document.
            service_endpoints: Optional W3C service endpoints.
            aic: Optional AIC parameters (``arsp`` / ``provider_id`` /
                ``ontology_seq`` / ``version``); defaults to fresh values.

        Returns:
            The creation result (DID string + derived AIC + DID Document).

        Raises:
            ValueError: If the namespace contains ``:``.
        """
        if ":" in namespace or not namespace:
            raise ValueError(f"Invalid DID namespace: {namespace!r}")
        did = AgentDID.generate(namespace=namespace)
        state_machine = GovernanceStateMachine()
        record = self.registry.register(did, state_machine, initial_roles=roles or [])
        if ed25519_public_key_pem:
            record.metadata["ed25519_public_key_pem"] = ed25519_public_key_pem
        if service_endpoints:
            record.metadata["service_endpoints"] = service_endpoints

        params: dict[str, Any] = dict(aic or {})
        aic_obj = self.adapter.register_new(
            did,
            arsp=str(params.get("arsp", "1")),
            provider_id=str(params.get("provider_id", "1")),
            ontology_seq=str(params.get("ontology_seq", "1")),
            version=str(params.get("version", "1")),
        )

        doc = did.to_did_document(
            ed25519_public_key_pem=ed25519_public_key_pem,
            service_endpoints=service_endpoints,
        )
        self._append(
            {
                "op": "create",
                "did": did.did_string,
                "namespace": namespace,
                "agent_short_id": did.agent_short_id,
                "aic": aic_obj.aic_string,
                "roles": roles or [],
                "ed25519_public_key_pem": ed25519_public_key_pem,
                "service_endpoints": service_endpoints or [],
                "registered_at": record.registered_at,
            }
        )
        return IdentityCreationResult(
            did=did.did_string,
            aic=aic_obj.aic_string,
            did_document=doc,
            registered_at=record.registered_at,
        )

    def resolve_did(self, did_string: str) -> dict[str, Any]:
        """Resolve a DID to a W3C DID Document.

        Returns a W3C DID Resolution result dict. Deactivated DIDs resolve
        to ``resolution_metadata.error == "deactivated"``; unknown DIDs to
        ``"notFound"``.
        """
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return {
                "resolution_metadata": {
                    "error": "invalidDid",
                    "message": f"Invalid MAREF DID: {did_string}",
                },
                "document_metadata": {},
            }
        if did_string in self._deactivated:
            return {
                "resolution_metadata": {
                    "error": "deactivated",
                    "message": f"DID {did_string} has been deactivated",
                },
                "document_metadata": {
                    "deactivated": True,
                    "deactivated_at": self._deactivated_at.get(did_string),
                },
            }
        record = self.registry.resolve(did)
        if record is None:
            return self.registry.resolve_did_document(did).to_dict()
        return self.registry.resolve_did_document(
            did,
            service_endpoints=record.metadata.get("service_endpoints"),
        ).to_dict()

    def deactivate_did(self, did_string: str) -> dict[str, Any]:
        """Soft-deactivate a DID (resolution then reports ``deactivated``).

        The registry record and AIC mapping are retained for auditability;
        only the resolution state flips.

        Args:
            did_string: The MAREF DID to deactivate.

        Returns:
            Operation status.

        Raises:
            ValueError: If the DID is invalid or unknown.
        """
        did = AgentDID.parse(did_string)
        if self.registry.resolve(did) is None:
            raise ValueError(f"DID {did_string} not found")
        if did_string in self._deactivated:
            return {"success": True, "did": did_string, "already_deactivated": True}
        now = time.time()
        self._deactivated.add(did_string)
        self._deactivated_at[did_string] = now
        self._append({"op": "deactivate", "did": did_string, "timestamp": now})
        return {"success": True, "did": did_string, "deactivated_at": now}

    def list_identities(self) -> list[dict[str, Any]]:
        """List all registered identities with their status."""
        result: list[dict[str, Any]] = []
        for record in self.registry.list_all():
            aic = self.adapter.did_to_aic(record.did)
            result.append(
                {
                    "did": record.did.did_string,
                    "aic": aic.aic_string if aic is not None else None,
                    "roles": record.roles,
                    "registered_at": record.registered_at,
                    "deactivated": record.did.did_string in self._deactivated,
                }
            )
        return result

    # ── AIC derivation + verification ───────────────────────────────────

    def verify_aic(self, aic_string: str) -> dict[str, Any]:
        """Verify an AIC string (format + CRC-16 checksum) and bindings.

        Returns:
            ``valid`` (format + checksum), ``checksum_valid``,
            ``bound`` (mapped to a DID), ``did`` (if bound), and
            ``deactivated`` (if the bound DID was deactivated).
        """
        try:
            aic = AIC.parse(aic_string)
        except ValueError:
            return {
                "valid": False,
                "checksum_valid": False,
                "bound": False,
                "did": None,
                "deactivated": False,
                "reason": "invalid_format",
            }
        checksum_valid = aic.verify()
        did = self.adapter.aic_to_did(aic)
        bound = did is not None
        deactivated = did is not None and did.did_string in self._deactivated
        return {
            "valid": checksum_valid,
            "checksum_valid": checksum_valid,
            "bound": bound,
            "did": did.did_string if did is not None else None,
            "deactivated": deactivated,
        }

    def did_to_aic(self, did_string: str) -> str:
        """Translate a DID string to its bound AIC string."""
        did = AgentDID.parse(did_string)
        aic = self.adapter.did_to_aic(did)
        if aic is None:
            raise ValueError(f"No AIC mapping for DID: {did_string}")
        return aic.aic_string

    def aic_to_did(self, aic_string: str) -> str:
        """Translate an AIC string to its bound DID string."""
        aic = AIC.parse(aic_string)
        did = self.adapter.aic_to_did(aic)
        if did is None:
            raise ValueError(f"No DID mapping for AIC: {aic_string}")
        return did.did_string

    def summary(self) -> dict[str, Any]:
        """Operational summary for observability."""
        return {
            "identities": self.registry.agent_count(),
            "deactivated": len(self._deactivated),
            "aic_mappings": self.adapter.mapping_count,
            "persistence": self._persist_path.as_posix() if self._persist_path else None,
        }

    # ── JSONL persistence ───────────────────────────────────────────────

    def _load(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return
        for line in self._persist_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._replay(event)

    def _replay(self, event: dict[str, Any]) -> None:
        op = event.get("op")
        if op == "create":
            did = AgentDID(namespace=event["namespace"], agent_short_id=event["agent_short_id"])
            record = self.registry.register(did, GovernanceStateMachine(), initial_roles=event.get("roles"))
            if event.get("ed25519_public_key_pem"):
                record.metadata["ed25519_public_key_pem"] = event["ed25519_public_key_pem"]
            if event.get("service_endpoints"):
                record.metadata["service_endpoints"] = event["service_endpoints"]
            self.adapter.register(did, AIC.parse(event["aic"]))
        elif op == "deactivate":
            self._deactivated.add(event["did"])
            self._deactivated_at[event["did"]] = event.get("timestamp", 0.0)

    def _append(self, event: dict[str, Any]) -> None:
        if self._persist_path is None:
            return
        if self._persist_handle is None:
            self._persist_handle = self._persist_path.open("a", encoding="utf-8")
        self._persist_handle.write(json.dumps(event, sort_keys=True) + "\n")
        self._persist_handle.flush()

    def close(self) -> None:
        """Flush and close the persistence handle (if any)."""
        if self._persist_handle is not None:
            self._persist_handle.close()
            self._persist_handle = None

    def __enter__(self) -> IdentityService:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


__all__ = ["IdentityCreationResult", "IdentityService"]
