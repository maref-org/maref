"""Shared fixtures for federation unit tests.

Provides factory fixtures that build ``FederatedAgent`` instances via a
real :class:`FederationGateway`, mirroring production usage. Prefixed
names (``fed_*`` / ``make_*``) avoid collisions with module-local
fixtures in existing test files.
"""

from __future__ import annotations

from typing import Callable

import pytest

from maref.federation.gateway import FederatedAgent, FederationGateway, FederationRequest
from maref.identity.aic_adapter import AIC, AICIdentityAdapter
from maref.identity.did_registry import DIDRegistry
from maref.integration.acs_parser import ACSParser
from maref.orchestration.dispatcher import AgentDispatcher


@pytest.fixture
def fed_gateway() -> FederationGateway:
    """A fully-wired FederationGateway for P1 module tests."""
    return FederationGateway(
        identity_adapter=AICIdentityAdapter(),
        acs_parser=ACSParser(),
        dispatcher=AgentDispatcher(),
        did_registry=DIDRegistry(),
    )


@pytest.fixture
def make_acs_doc() -> Callable[[], dict]:
    """Factory returning a fresh ACS document dict.

    Caller is responsible for setting the ``"aic"`` field and any
    per-test overrides (skills, organization, etc.).
    """

    def _make() -> dict:
        return {
            "name": "federated-agent",
            "description": "A federated test agent",
            "protocolVersion": "2.00",
            "version": "1.0",
            "provider": {"organization": "TestOrg"},
            "capabilities": {
                "streaming": False,
                "notification": False,
                "messageQueue": [],
            },
            "endpoints": [
                {
                    "url": "https://agent.example.com/api",
                    "transport": "HTTP_JSON",
                    "security": ["mutualTLS"],
                }
            ],
            "skills": [
                {"id": "research", "name": "Research", "description": "Research capability"},
                {"id": "analysis", "name": "Analysis", "description": "Analysis capability"},
            ],
            "securitySchemes": {"mutualTLS": {"type": "mutualTLS"}},
        }

    return _make


@pytest.fixture
def make_federated_agent(
    fed_gateway: FederationGateway, make_acs_doc: Callable[[], dict]
) -> Callable[..., FederatedAgent]:
    """Factory: registers an agent on ``fed_gateway`` and returns it.

    Accepts optional overrides for skills, organization, protocol, and
    endpoint URL. Each call generates a fresh AIC so agents never
    collide.
    """

    def _make(
        skills: list[str] | None = None,
        organization: str = "TestOrg",
        protocol: str = "aip",
        endpoint_url: str = "https://agent.example.com/api",
    ) -> FederatedAgent:
        aic = AIC.generate()
        doc = make_acs_doc()
        doc["aic"] = aic.aic_string
        if skills is not None:
            doc["skills"] = [
                {"id": s, "name": s.title(), "description": f"{s} capability"} for s in skills
            ]
        doc["provider"]["organization"] = organization
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url=endpoint_url,
            protocol=protocol,
        )
        response = fed_gateway.register_agent(request)
        assert response.success, response.error
        agent = fed_gateway.get_agent_by_aic(aic.aic_string)
        assert agent is not None
        return agent

    return _make
