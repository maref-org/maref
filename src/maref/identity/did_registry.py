from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine

# W3C DID Core 1.0 context
_DID_CONTEXT = "https://www.w3.org/ns/did/v1"
_ED25519_VERIFICATION_METHOD_TYPE = "Ed25519VerificationKey2018"
_ED25519_AUTHENTICATION_TYPE = "Ed25519SignatureAuthentication2018"


@dataclass(frozen=True)
class AgentDID:
    namespace: str
    agent_short_id: str

    @property
    def did_string(self) -> str:
        return f"did:maref:{self.namespace}:{self.agent_short_id}"

    @classmethod
    def parse(cls, did_string: str) -> AgentDID:
        parts = did_string.split(":")
        if len(parts) != 4 or parts[0] != "did" or parts[1] != "maref":
            raise ValueError(f"Invalid MAREF DID: {did_string}")
        return cls(namespace=parts[2], agent_short_id=parts[3])

    @classmethod
    def generate(cls, namespace: str = "default") -> AgentDID:
        short_id = secrets.token_hex(4)
        return cls(namespace=namespace, agent_short_id=short_id)

    def to_did_document(
        self,
        ed25519_public_key_pem: str = "",
        service_endpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a W3C DID Document (DID Core 1.0) for this MAREF DID.

        Args:
            ed25519_public_key_pem: Optional Ed25519 public key PEM to include
                as a verification method.
            service_endpoints: Optional list of service endpoint dicts, each
                with ``id``, ``type``, ``serviceEndpoint`` keys.

        Returns:
            A dict conforming to the W3C DID Document data model.
        """
        doc: dict[str, Any] = {
            "@context": _DID_CONTEXT,
            "id": self.did_string,
        }
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
class AgentIdentityRecord:
    did: AgentDID
    state_machine: GovernanceStateMachine
    roles: list[str] = field(default_factory=list)
    registered_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def ed25519_public_key(self) -> str:
        return self.metadata.get("ed25519_public_key_pem", "")


@dataclass
class DIDResolutionResult:
    """W3C DID Resolution result (DID Resolution v1.0).

    Attributes:
        did_document: The resolved DID Document (or None if not found).
        resolution_metadata: Metadata about the resolution process.
        document_metadata: Metadata about the DID Document itself.
    """

    did_document: dict[str, Any] | None
    resolution_metadata: dict[str, Any]
    document_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resolution_metadata": self.resolution_metadata,
            "document_metadata": self.document_metadata,
        }
        if self.did_document is not None:
            result["did_document"] = self.did_document
        return result

    @property
    def resolved(self) -> bool:
        return self.did_document is not None


class DIDRegistry:
    def __init__(self) -> None:
        self._agents: dict[AgentDID, AgentIdentityRecord] = {}

    def register(
        self,
        did: AgentDID,
        state_machine: GovernanceStateMachine,
        initial_roles: list[str] | None = None,
    ) -> AgentIdentityRecord:
        record = AgentIdentityRecord(
            did=did,
            state_machine=state_machine,
            roles=initial_roles or [],
            metadata={"registered_via": "DIDRegistry"},
        )
        record.registered_at = time.time()
        self._agents[did] = record
        return record

    def resolve(self, did: AgentDID) -> AgentIdentityRecord | None:
        return self._agents.get(did)

    def resolve_did_document(
        self,
        did: AgentDID,
        service_endpoints: list[dict[str, Any]] | None = None,
    ) -> DIDResolutionResult:
        """Resolve a MAREF DID to a W3C DID Document (DID Resolution v1.0).

        Args:
            did: The MAREF DID to resolve.
            service_endpoints: Optional service endpoints for the DID Document.

        Returns:
            A :class:`DIDResolutionResult` with the DID Document and metadata.
        """
        record = self._agents.get(did)
        if record is None:
            return DIDResolutionResult(
                did_document=None,
                resolution_metadata={
                    "error": "notFound",
                    "message": f"DID {did.did_string} not found",
                },
                document_metadata={},
            )

        doc = did.to_did_document(
            ed25519_public_key_pem=record.ed25519_public_key(),
            service_endpoints=service_endpoints,
        )
        return DIDResolutionResult(
            did_document=doc,
            resolution_metadata={
                "method": "maref",
                "resolved": True,
                "retrieved": time.time(),
            },
            document_metadata={
                "created": record.registered_at,
                "updated": record.registered_at,
                "deactivated": False,
                "versionId": "1",
            },
        )

    def unregister(self, did: AgentDID) -> AgentIdentityRecord | None:
        """Remove a DID record from the registry.

        Args:
            did: The MAREF DID to unregister.

        Returns:
            The removed record if found, None otherwise.
        """
        return self._agents.pop(did, None)

    def list_all(self) -> list[AgentIdentityRecord]:
        return list(self._agents.values())

    def agent_count(self) -> int:
        return len(self._agents)
