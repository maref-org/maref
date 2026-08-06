"""Federation Gateway with ACS document Ed25519 signature verification.

Unified entry point for external agents (ACPs/A2A/MCP) to attach to the
MAREF governance framework. The gateway performs:

1. **Identity translation**: AIC ↔ DID bidirectional mapping via
   :class:`~maref.identity.aic_adapter.AICIdentityAdapter`.
2. **Capability ingestion**: Parse external ACS documents into MAREF's
   internal capability registry via
   :class:`~maref.integration.acs_parser.ACSParser`.
3. **ACS integrity verification**: Optional Ed25519 signature validation
   of the ACS document at registration time. The raw document hash is
   stored for subsequent integrity checks.
4. **Audit logging**: Every registration and dispatch is recorded in the
   HMAC-signed audit chain.
5. **Agent registry**: Maintains the set of federated agents with their
   AIC, ACS, endpoint URL, and current health.

The gateway is protocol-agnostic: it stores identity and capability
metadata, and delegates protocol-specific transport (A2A/MCP/AIP) to
the existing integration bridges.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from maref.governance.audit import AuditLogger
from maref.identity.aic_adapter import AIC, AICIdentityAdapter
from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.integration.acs_parser import ACSParser, AgentCapabilitySpec
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import AgentDispatcher, DispatchResult


@dataclass
class FederationRequest:
    """A request to register or dispatch through the federation gateway.

    Attributes:
        aic_string: The external agent's AIC identifier.
        acs_document: The external agent's ACS capability document.
        endpoint_url: The external agent's network endpoint.
        protocol: The wire protocol ("a2a", "mcp", "aip").
        did_namespace: Optional MAREF DID namespace to assign.
        acs_signature: Optional Ed25519 hex signature of the ACS document.
            When provided and a verifier is configured, the signature is
            validated during registration.
        acs_public_key_pem: Optional PEM-encoded Ed25519 public key for
            verifying the ACS signature.
    """

    aic_string: str
    acs_document: dict[str, Any]
    endpoint_url: str
    protocol: str = "aip"
    did_namespace: str = "federated"
    acs_signature: str = ""
    acs_public_key_pem: str = ""


@dataclass
class FederationResponse:
    """Response from the federation gateway.

    Attributes:
        success: Whether the operation succeeded.
        did_string: The MAREF DID assigned to the agent (on success).
        aic_string: The AIC bound to the DID.
        error: Error message (on failure).
        metadata: Additional response metadata.
    """

    success: bool
    did_string: str = ""
    aic_string: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FederatedAgent:
    """An agent registered with the federation gateway.

    Attributes:
        did: MAREF DID assigned to the agent.
        aic: ACPs AIC identifier.
        acs: Parsed ACS capability specification.
        endpoint_url: Network endpoint URL.
        protocol: Wire protocol ("a2a", "mcp", "aip").
        registered_at: Registration timestamp.
        last_seen: Last activity timestamp.
        acs_signature: Ed25519 hex signature of the raw ACS document at
            registration time. Empty string if unsigned.
        acs_public_key_pem: PEM-encoded Ed25519 public key that signed the ACS.
        acs_digest: SHA-256 hex digest of the raw ACS document at registration
            time. Used for subsequent integrity verification.
    """

    did: AgentDID
    aic: AIC
    acs: AgentCapabilitySpec
    endpoint_url: str
    protocol: str
    registered_at: float
    last_seen: float = 0.0
    acs_signature: str = ""
    acs_public_key_pem: str = ""
    acs_digest: str = ""

    def touch(self) -> None:
        """Update ``last_seen`` to the current time."""
        self.last_seen = time.time()

    def verify_acs_integrity(self, raw_acs_document: dict[str, Any] | None = None) -> bool:
        """Verify that the ACS document content matches the registration signature.

        If ``raw_acs_document`` is provided, verifies the Ed25519 signature
        against that document. Otherwise, compares the SHA-256 digest of
        ``self.acs.to_dict()`` with the stored ``acs_digest`` (best-effort).

        Returns:
            True if the integrity check passes or no signature was provided.
            False if verification fails.
        """
        if not self.acs_signature or not self.acs_public_key_pem:
            return True  # No signature to verify

        if raw_acs_document is not None:
            from maref.crypto.ed25519_keys import Ed25519KeyPair
            acs_bytes = json.dumps(raw_acs_document, sort_keys=True).encode()
            try:
                return Ed25519KeyPair.verify(
                    self.acs_public_key_pem,
                    bytes.fromhex(self.acs_signature),
                    acs_bytes,
                )
            except (ValueError, Exception):
                return False

        # Without the raw document, compare digest as best-effort
        if self.acs_digest:
            current = hashlib.sha256(
                json.dumps(self.acs.to_dict(), sort_keys=True).encode()
            ).hexdigest()
            return current == self.acs_digest
        return True


class FederationGatewayError(ValueError):
    """Raised when a federation gateway operation fails."""


class FederationGateway:
    """Unified entry point for external agents to join the MAREF federation.

    The gateway coordinates three subsystems:
    - :class:`AICIdentityAdapter` for DID ↔ AIC translation.
    - :class:`ACSParser` for capability document ingestion.
    - :class:`AgentDispatcher` for task routing to federated agents.
    - :class:`AuditLogger` for tamper-evident activity recording.
    """

    def __init__(
        self,
        identity_adapter: AICIdentityAdapter | None = None,
        acs_parser: ACSParser | None = None,
        dispatcher: AgentDispatcher | None = None,
        did_registry: DIDRegistry | None = None,
        audit_logger: AuditLogger | None = None,
        require_acs_signature: bool = False,
    ) -> None:
        self._identity = identity_adapter or AICIdentityAdapter()
        self._acs_parser = acs_parser or ACSParser()
        self._dispatcher = dispatcher
        self._did_registry = did_registry
        self._audit = audit_logger
        self._require_acs_signature = require_acs_signature
        self._agents: dict[AgentDID, FederatedAgent] = {}
        self._aic_to_agent: dict[str, FederatedAgent] = {}

    @property
    def agent_count(self) -> int:
        """Number of federated agents currently registered."""
        return len(self._agents)

    def register_agent(self, request: FederationRequest) -> FederationResponse:
        """Register an external agent with the MAREF federation.

        Performs identity translation (AIC → DID), ACS parsing, dispatcher
        registration, and audit logging.

        Args:
            request: The federation registration request.

        Returns:
            A :class:`FederationResponse` with the assigned DID on success.
        """
        try:
            aic = AIC.parse(request.aic_string)
        except ValueError as exc:
            return FederationResponse(
                success=False,
                aic_string=request.aic_string,
                error=f"Invalid AIC: {exc}",
            )

        try:
            acs = self._acs_parser.parse(request.acs_document)
        except ValueError as exc:
            return FederationResponse(
                success=False,
                aic_string=request.aic_string,
                error=f"Invalid ACS: {exc}",
            )

        if acs.aic != request.aic_string:
            return FederationResponse(
                success=False,
                aic_string=request.aic_string,
                error=(
                    f"AIC mismatch: request AIC '{request.aic_string}' "
                    f"!= ACS AIC '{acs.aic}'"
                ),
            )

        # ACS Ed25519 signature verification
        raw_acs_digest = hashlib.sha256(
            json.dumps(request.acs_document, sort_keys=True).encode()
        ).hexdigest()
        if self._require_acs_signature and (
            not request.acs_signature or not request.acs_public_key_pem
        ):
            return FederationResponse(
                success=False,
                aic_string=request.aic_string,
                error="ACS signature required but missing (fail-closed)",
            )
        if request.acs_signature and request.acs_public_key_pem:
            from maref.crypto.ed25519_keys import Ed25519KeyPair

            acs_bytes = json.dumps(request.acs_document, sort_keys=True).encode()
            sig_valid = Ed25519KeyPair.verify(
                request.acs_public_key_pem,
                bytes.fromhex(request.acs_signature),
                acs_bytes,
            )
            if not sig_valid:
                return FederationResponse(
                    success=False,
                    aic_string=request.aic_string,
                    error="ACS signature verification failed",
                )

        did = AgentDID.generate(namespace=request.did_namespace)

        try:
            self._identity.register(did, aic)
        except ValueError as exc:
            return FederationResponse(
                success=False,
                aic_string=aic.aic_string,
                error=f"Identity registration failed: {exc}",
            )

        try:
            if self._did_registry is not None:
                from maref.governance.state_machine import GovernanceStateMachine

                sm = GovernanceStateMachine()
                self._did_registry.register(did, sm, initial_roles=["federated-agent"])

            if self._dispatcher is not None:
                capabilities = [skill.id for skill in acs.skills]
                self._dispatcher.register_agent(did, capabilities)
        except Exception as exc:
            # Rollback: identity mapping was already committed.
            self._identity.unregister(did)
            if self._did_registry is not None:
                self._did_registry.unregister(did)
            return FederationResponse(
                success=False,
                did_string=did.did_string,
                aic_string=aic.aic_string,
                error=f"Downstream registration failed: {exc}",
            )

        agent = FederatedAgent(
            did=did,
            aic=aic,
            acs=acs,
            endpoint_url=request.endpoint_url,
            protocol=request.protocol,
            registered_at=time.time(),
            acs_signature=request.acs_signature,
            acs_public_key_pem=request.acs_public_key_pem,
            acs_digest=raw_acs_digest,
        )
        agent.touch()
        self._agents[did] = agent
        self._aic_to_agent[aic.aic_string] = agent

        if self._audit is not None:
            self._audit.log(
                event_type="federation_agent_registered",
                actor="FederationGateway",
                action="register_agent",
                details=f"Registered federated agent {did.did_string} (AIC {aic.aic_string})",
                metadata={
                    "did": did.did_string,
                    "aic": aic.aic_string,
                    "protocol": request.protocol,
                    "endpoint": request.endpoint_url,
                    "capabilities": [s.id for s in acs.skills],
                },
            )

        return FederationResponse(
            success=True,
            did_string=did.did_string,
            aic_string=aic.aic_string,
            metadata={
                "protocol": request.protocol,
                "endpoint": request.endpoint_url,
                "capabilities": [s.id for s in acs.skills],
            },
        )

    def unregister_agent(self, did: AgentDID) -> bool:
        """Unregister a federated agent.

        Removes the agent from the gateway and cleans up all downstream
        registrations (identity mapping, DID registry, dispatcher).

        Args:
            did: The MAREF DID of the agent to remove.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        agent = self._agents.pop(did, None)
        if agent is None:
            return False
        self._aic_to_agent.pop(agent.aic.aic_string, None)

        # Clean up downstream subsystems.
        self._identity.unregister(did)
        if self._did_registry is not None:
            self._did_registry.unregister(did)
        if self._dispatcher is not None:
            self._dispatcher.unregister_agent(did)

        if self._audit is not None:
            self._audit.log(
                event_type="federation_agent_unregistered",
                actor="FederationGateway",
                action="unregister_agent",
                details=f"Unregistered federated agent {did.did_string}",
                metadata={"did": did.did_string, "aic": agent.aic.aic_string},
            )
        return True

    def get_agent_by_did(self, did: AgentDID) -> FederatedAgent | None:
        """Look up a federated agent by DID."""
        return self._agents.get(did)

    def get_agent_by_aic(self, aic_string: str) -> FederatedAgent | None:
        """Look up a federated agent by AIC string."""
        return self._aic_to_agent.get(aic_string)

    def list_agents(self, protocol_filter: str | None = None) -> list[FederatedAgent]:
        """List all federated agents, optionally filtered by protocol.

        Args:
            protocol_filter: If provided, only agents using this protocol are returned.

        Returns:
            A list of :class:`FederatedAgent` instances.
        """
        agents = list(self._agents.values())
        if protocol_filter is not None:
            agents = [a for a in agents if a.protocol == protocol_filter]
        return agents

    def discover_by_capability(self, capability: str) -> list[FederatedAgent]:
        """Find federated agents that declare a specific capability.

        Args:
            capability: The capability/skill ID to search for.

        Returns:
            A list of agents whose ACS declares the given capability.
        """
        return [
            agent
            for agent in self._agents.values()
            if any(skill.id == capability for skill in agent.acs.skills)
        ]

    def dispatch_task(self, task: SubTask) -> DispatchResult | None:
        """Dispatch a task to the most suitable federated agent.

        Delegates to the configured :class:`AgentDispatcher`. If no
        dispatcher is configured, returns None.

        Args:
            task: The MAREF :class:`SubTask` to dispatch.

        Returns:
            A :class:`DispatchResult` if a match was found, None otherwise.
        """
        if self._dispatcher is None:
            return None
        result = self._dispatcher.dispatch(task)
        if result is not None:
            agent = self._agents.get(result.agent_did)
            if agent is not None:
                agent.touch()
            if self._audit is not None:
                self._audit.log(
                    event_type="federation_task_dispatched",
                    actor="FederationGateway",
                    action="dispatch_task",
                    details=f"Dispatched task {task.task_id} to {result.agent_did.did_string}",
                    metadata={
                        "task_id": task.task_id,
                        "agent_did": result.agent_did.did_string,
                        "confidence": result.confidence,
                    },
                )
        return result

    def translate_did_to_aic(self, did_string: str) -> str:
        """Translate a MAREF DID string to its bound AIC string.

        Raises:
            FederationGatewayError: If the DID is not registered.
        """
        try:
            return self._identity.translate_did_to_aic_string(did_string)
        except ValueError as exc:
            raise FederationGatewayError(str(exc)) from exc

    def translate_aic_to_did(self, aic_string: str) -> str:
        """Translate an AIC string to its bound MAREF DID string.

        Raises:
            FederationGatewayError: If the AIC is not registered.
        """
        try:
            return self._identity.translate_aic_string_to_did(aic_string)
        except ValueError as exc:
            raise FederationGatewayError(str(exc)) from exc

    def gateway_summary(self) -> dict[str, Any]:
        """Return a summary of the federation gateway state."""
        protocol_counts: dict[str, int] = {}
        for agent in self._agents.values():
            protocol_counts[agent.protocol] = protocol_counts.get(agent.protocol, 0) + 1
        return {
            "agent_count": len(self._agents),
            "identity_mapping_count": self._identity.mapping_count,
            "protocols": protocol_counts,
            "has_dispatcher": self._dispatcher is not None,
            "has_audit": self._audit is not None,
        }


__all__ = [
    "FederatedAgent",
    "FederationGateway",
    "FederationGatewayError",
    "FederationRequest",
    "FederationResponse",
]
