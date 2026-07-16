from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine


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


@dataclass
class AgentIdentityRecord:
    did: AgentDID
    state_machine: GovernanceStateMachine
    roles: list[str] = field(default_factory=list)
    registered_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


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
        import time

        record.registered_at = time.time()
        self._agents[did] = record
        return record

    def resolve(self, did: AgentDID) -> AgentIdentityRecord | None:
        return self._agents.get(did)

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
