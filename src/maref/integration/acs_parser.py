"""ACS (Agent Capability Specification) Parser.

Implements the ACPs ACS v2.00 specification: a JSON Schema-based capability
description that standardizes how agents declare their skills, endpoints,
security schemes, message queue protocols, and streaming support.

Provides parsing, validation, and conversion from MAREF's internal
capability representation (flat ``list[str]``) to the structured ACS format.

Reference: AIP-ACPs-Technical-Analysis.md section 2.2 (ACS v2.00).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ACS protocol version (matches ACPs v2.00).
ACS_PROTOCOL_VERSION = "2.00"

# Well-known URL path for serving the ACS document.
ACS_WELL_KNOWN_PATH = "/.well-known/acs.json"

# Valid transport values for AgentEndPoint.
_VALID_TRANSPORTS = {"JSONRPC", "HTTP_JSON"}

# Valid security scheme types.
_VALID_SECURITY_SCHEMES = {
    "mutualTLS",
    "openIdConnect",
    "apiKey",
    "http",
    "oauth2",
}

# Valid MQ protocol names.
_VALID_MQ_PROTOCOLS = {
    "rabbitmq",
    "kafka",
    "nats",
    "redis",
    "pulsar",
}


@dataclass
class AgentProvider:
    """Organization that provides the agent."""

    organization: str
    department: str = ""
    url: str = ""
    license: str = ""
    contact: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "department": self.department,
            "url": self.url,
            "license": self.license,
            "contact": self.contact,
        }


@dataclass
class AgentSkill:
    """A single capability/skill exposed by the agent."""

    id: str
    name: str
    description: str
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "tags": list(self.tags),
            "examples": list(self.examples),
            "inputModes": list(self.input_modes),
            "outputModes": list(self.output_modes),
        }
        if self.input_schema is not None:
            result["inputSchema"] = self.input_schema
        if self.output_schema is not None:
            result["outputSchema"] = self.output_schema
        return result


@dataclass
class AgentEndPoint:
    """Network endpoint where the agent is reachable."""

    url: str
    transport: str = "HTTP_JSON"
    security: list[str] = field(default_factory=lambda: ["mutualTLS"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "transport": self.transport,
            "security": list(self.security),
        }


@dataclass
class AgentCapabilities:
    """High-level capability flags for the agent."""

    streaming: bool = False
    notification: bool = False
    message_queue: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "streaming": self.streaming,
            "notification": self.notification,
            "messageQueue": list(self.message_queue),
        }


@dataclass
class AgentCapabilitySpec:
    """Top-level ACS document.

    Combines AIC identifier, provider info, capabilities, endpoint, and skills
    into a single standardized capability declaration.
    """

    aic: str
    active: bool = True
    last_modified_time: float = field(default_factory=time.time)
    protocol_version: str = ACS_PROTOCOL_VERSION
    name: str = ""
    description: str = ""
    version: str = "1.0"
    provider: AgentProvider | None = None
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    endpoints: list[AgentEndPoint] = field(default_factory=list)
    skills: list[AgentSkill] = field(default_factory=list)
    security_schemes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "aic": self.aic,
            "active": self.active,
            "lastModifiedTime": self.last_modified_time,
            "protocolVersion": self.protocol_version,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "endpoints": [ep.to_dict() for ep in self.endpoints],
            "skills": [skill.to_dict() for skill in self.skills],
            "securitySchemes": dict(self.security_schemes),
        }
        if self.provider is not None:
            result["provider"] = self.provider.to_dict()
        return result

    def to_well_known_document(self) -> dict[str, Any]:
        """Build the document to be served at ``/.well-known/acs.json``."""
        return self.to_dict()


class ACSParseError(ValueError):
    """Raised when ACS parsing or validation fails."""


class ACSParser:
    """Parser and validator for ACS (Agent Capability Specification) documents.

    Provides:
    - :meth:`parse`: Parse a raw ACS dict into structured dataclasses.
    - :meth:`validate`: Validate a raw ACS dict against the schema rules.
    - :meth:`from_maref_capabilities`: Convert MAREF's internal
      ``list[str]`` capability representation to an :class:`AgentCapabilitySpec`.
    """

    def parse(self, raw: dict[str, Any]) -> AgentCapabilitySpec:
        """Parse a raw ACS dictionary into an :class:`AgentCapabilitySpec`.

        Args:
            raw: The raw ACS document (e.g. from ``/.well-known/acs.json``).

        Returns:
            The parsed :class:`AgentCapabilitySpec`.

        Raises:
            ACSParseError: If the document is invalid.
        """
        errors = self._collect_validation_errors(raw)
        if errors:
            raise ACSParseError(
                "Invalid ACS document: " + "; ".join(errors)
            )

        provider_raw = raw.get("provider")
        provider = None
        if isinstance(provider_raw, dict):
            provider = AgentProvider(
                organization=provider_raw.get("organization", ""),
                department=provider_raw.get("department", ""),
                url=provider_raw.get("url", ""),
                license=provider_raw.get("license", ""),
                contact=provider_raw.get("contact", ""),
            )

        caps_raw = raw.get("capabilities", {})
        capabilities = AgentCapabilities(
            streaming=caps_raw.get("streaming", False),
            notification=caps_raw.get("notification", False),
            message_queue=list(caps_raw.get("messageQueue", [])),
        )

        endpoints = [
            AgentEndPoint(
                url=ep.get("url", ""),
                transport=ep.get("transport", "HTTP_JSON"),
                security=list(ep.get("security", ["mutualTLS"])),
            )
            for ep in raw.get("endpoints", [])
            if isinstance(ep, dict)
        ]

        skills = [
            AgentSkill(
                id=skill.get("id", ""),
                name=skill.get("name", ""),
                description=skill.get("description", ""),
                version=skill.get("version", "1.0"),
                tags=list(skill.get("tags", [])),
                examples=list(skill.get("examples", [])),
                input_modes=list(skill.get("inputModes", ["text/plain"])),
                output_modes=list(skill.get("outputModes", ["application/json"])),
                input_schema=skill.get("inputSchema"),
                output_schema=skill.get("outputSchema"),
            )
            for skill in raw.get("skills", [])
            if isinstance(skill, dict)
        ]

        return AgentCapabilitySpec(
            aic=raw["aic"],
            active=raw.get("active", True),
            last_modified_time=float(raw.get("lastModifiedTime", time.time())),
            protocol_version=raw.get("protocolVersion", ACS_PROTOCOL_VERSION),
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            version=raw.get("version", "1.0"),
            provider=provider,
            capabilities=capabilities,
            endpoints=endpoints,
            skills=skills,
            security_schemes=dict(raw.get("securitySchemes", {})),
        )

    def validate(self, raw: dict[str, Any]) -> bool:
        """Validate a raw ACS dictionary.

        Args:
            raw: The raw ACS document.

        Returns:
            True if valid, False otherwise.
        """
        return not self._collect_validation_errors(raw)

    def from_maref_capabilities(
        self,
        aic: str,
        agent_name: str,
        agent_description: str,
        capabilities: list[str],
        endpoint_url: str = "",
        provider_organization: str = "MAREF",
        streaming: bool = False,
        notification: bool = False,
    ) -> AgentCapabilitySpec:
        """Convert MAREF's flat ``list[str]`` capabilities to an ACS document.

        Each capability string becomes an :class:`AgentSkill` with the
        capability as both ``id`` and ``name``.

        Args:
            aic: The agent's AIC identifier.
            agent_name: Human-readable agent name.
            agent_description: Agent description.
            capabilities: List of capability strings (MAREF internal format).
            endpoint_url: Optional endpoint URL.
            provider_organization: Provider organization name.
            streaming: Whether the agent supports streaming.
            notification: Whether the agent supports push notifications.

        Returns:
            An :class:`AgentCapabilitySpec` representing the agent.
        """
        skills = [
            AgentSkill(
                id=cap,
                name=cap,
                description=f"MAREF capability: {cap}",
                tags=["maref"],
            )
            for cap in capabilities
        ]
        endpoints: list[AgentEndPoint] = []
        if endpoint_url:
            endpoints.append(
                AgentEndPoint(
                    url=endpoint_url,
                    transport="HTTP_JSON",
                    security=["mutualTLS"],
                )
            )
        return AgentCapabilitySpec(
            aic=aic,
            name=agent_name,
            description=agent_description,
            version="1.0",
            provider=AgentProvider(organization=provider_organization),
            capabilities=AgentCapabilities(
                streaming=streaming,
                notification=notification,
            ),
            endpoints=endpoints,
            skills=skills,
            security_schemes={
                "mutualTLS": {"type": "mutualTLS"},
            },
        )

    def _collect_validation_errors(self, raw: dict[str, Any]) -> list[str]:
        """Collect all validation errors for a raw ACS document.

        Args:
            raw: The raw ACS document.

        Returns:
            A list of error messages; empty if valid.
        """
        errors: list[str] = []
        if not isinstance(raw, dict):
            errors.append("root must be an object")
            return errors

        if "aic" not in raw or not isinstance(raw["aic"], str) or not raw["aic"]:
            errors.append("aic must be a non-empty string")

        if "name" not in raw or not isinstance(raw["name"], str) or not raw["name"]:
            errors.append("name must be a non-empty string")

        if "protocolVersion" in raw:
            pv = raw["protocolVersion"]
            if not isinstance(pv, str) or not pv:
                errors.append("protocolVersion must be a non-empty string")

        endpoints = raw.get("endpoints", [])
        if not isinstance(endpoints, list):
            errors.append("endpoints must be an array")
        else:
            for i, ep in enumerate(endpoints):
                if not isinstance(ep, dict):
                    errors.append(f"endpoints[{i}] must be an object")
                    continue
                if not ep.get("url"):
                    errors.append(f"endpoints[{i}].url is required")
                transport = ep.get("transport", "HTTP_JSON")
                if transport not in _VALID_TRANSPORTS:
                    errors.append(
                        f"endpoints[{i}].transport must be one of "
                        f"{sorted(_VALID_TRANSPORTS)}, got: {transport}"
                    )
                security = ep.get("security", [])
                if not isinstance(security, list):
                    errors.append(f"endpoints[{i}].security must be an array")
                else:
                    for sec in security:
                        if sec not in _VALID_SECURITY_SCHEMES:
                            errors.append(
                                f"endpoints[{i}].security contains unknown scheme: {sec}"
                            )

        skills = raw.get("skills", [])
        if not isinstance(skills, list):
            errors.append("skills must be an array")
        else:
            for i, skill in enumerate(skills):
                if not isinstance(skill, dict):
                    errors.append(f"skills[{i}] must be an object")
                    continue
                for key in ("id", "name", "description"):
                    if not skill.get(key):
                        errors.append(f"skills[{i}].{key} is required")

        caps = raw.get("capabilities", {})
        if not isinstance(caps, dict):
            errors.append("capabilities must be an object")
        else:
            mq = caps.get("messageQueue", [])
            if not isinstance(mq, list):
                errors.append("capabilities.messageQueue must be an array")
            else:
                for proto in mq:
                    if proto not in _VALID_MQ_PROTOCOLS:
                        errors.append(
                            f"capabilities.messageQueue contains unknown protocol: {proto}"
                        )
            streaming = caps.get("streaming", False)
            if not isinstance(streaming, bool):
                errors.append("capabilities.streaming must be a boolean")
            notification = caps.get("notification", False)
            if not isinstance(notification, bool):
                errors.append("capabilities.notification must be a boolean")

        if "active" in raw and not isinstance(raw["active"], bool):
            errors.append("active must be a boolean")

        schemes = raw.get("securitySchemes", {})
        if not isinstance(schemes, dict):
            errors.append("securitySchemes must be an object")
        else:
            for name, scheme in schemes.items():
                if not isinstance(scheme, dict):
                    errors.append(f"securitySchemes.{name} must be an object")
                    continue
                scheme_type = scheme.get("type")
                if scheme_type not in _VALID_SECURITY_SCHEMES:
                    errors.append(
                        f"securitySchemes.{name}.type must be one of "
                        f"{sorted(_VALID_SECURITY_SCHEMES)}, got: {scheme_type}"
                    )

        return errors


__all__ = [
    "ACS_PROTOCOL_VERSION",
    "ACSParser",
    "ACSParseError",
    "ACS_WELL_KNOWN_PATH",
    "AgentCapabilities",
    "AgentCapabilitySpec",
    "AgentEndPoint",
    "AgentProvider",
    "AgentSkill",
]
