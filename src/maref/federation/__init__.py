"""MAREF Federation Aggregation Layer.

Provides the federation gateway that allows external ACPs/A2A/MCP agents
to attach to the MAREF governance framework, plus identity translation,
capability discovery, and protocol adaptation.

Modules:
- :mod:`gateway`: FederationGateway — unified entry point for external agents.
"""

from maref.federation.gateway import (
    FederationGateway,
    FederationGatewayError,
    FederationRequest,
    FederationResponse,
)

__all__ = [
    "FederationGateway",
    "FederationGatewayError",
    "FederationRequest",
    "FederationResponse",
]
