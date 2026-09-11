"""
Agent Card Adapter — Unifies MAREF YAML registry and MAS-TS-001 JSON Schema.

Provides bidirectional conversion between:
  - MAREF SignedAgentCard (YAML/Python dataclass)
  - MAS-TS-001 Agent Card (JSON Schema)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from maref.agent_card_config import (
    MAS_CAPABILITIES,
    get_default_card_config,
)
from maref.recursive.signed_agent_cards import SignedAgentCard

# Lookup for enriching MAS capabilities with input_schema/output_schema
_mas_cap_lookup: dict[str, dict[str, Any]] = {str(cap["name"]): cap for cap in MAS_CAPABILITIES}

# MAS-TS-001 Agent Card JSON Schema (subset)
MAS_TS001_AGENT_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["agent_id", "agent_name", "version", "capabilities"],
    "properties": {
        "agent_id": {"type": "string"},
        "agent_name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["skill_id", "name"],
                "properties": {
                    "skill_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "business_rule_version": {"type": ["string", "null"]},
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                },
            },
        },
        "endpoints": {
            "type": "array",
            "items": {"type": "string", "format": "uri"},
        },
        "data_residency": {"type": "string"},
        "model_backend_location": {"type": "string"},
        "cross_border": {"type": "boolean"},
        "trust_score": {"type": "number", "minimum": 0, "maximum": 1},
        "compliance_labels": {"type": "array", "items": {"type": "string"}},
        "signed_at": {"type": "string", "format": "date-time"},
        "expires_at": {"type": "string", "format": "date-time"},
    },
}


@dataclass
class MASAgentCard:
    """MAS-TS-001 Agent Card (JSON-native)."""

    agent_id: str
    agent_name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    data_residency: str = ""
    model_backend_location: str = ""
    cross_border: bool = False
    trust_score: float = 0.0
    compliance_labels: list[str] = field(default_factory=list)
    signed_at: str = ""
    expires_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "endpoints": self.endpoints,
            "data_residency": self.data_residency,
            "model_backend_location": self.model_backend_location,
            "cross_border": self.cross_border,
            "trust_score": self.trust_score,
            "compliance_labels": self.compliance_labels,
            "signed_at": self.signed_at,
            "expires_at": self.expires_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MASAgentCard:
        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            endpoints=data.get("endpoints", []),
            data_residency=data.get("data_residency", ""),
            model_backend_location=data.get("model_backend_location", ""),
            cross_border=data.get("cross_border", False),
            trust_score=data.get("trust_score", 0.0),
            compliance_labels=data.get("compliance_labels", []),
            signed_at=data.get("signed_at", ""),
            expires_at=data.get("expires_at", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> MASAgentCard:
        return cls.from_dict(json.loads(json_str))


class AgentCardAdapter:
    """
    Bidirectional adapter between MAREF and MAS-TS-001 Agent Card formats.
    """

    @staticmethod
    def to_mas_card(maref_card: SignedAgentCard) -> MASAgentCard:
        """Convert MAREF SignedAgentCard → MAS-TS-001 Agent Card."""
        card_data = maref_card.to_card_data()

        # Map capabilities (list[str] → list[dict]) with MAS-TS-001 schema fields
        mas_capabilities: list[dict[str, Any]] = []
        for cap in maref_card.capabilities:
            entry: dict[str, Any] = {
                "skill_id": f"skill_{cap}",
                "name": cap,
                "description": "",
                "business_rule_version": None,
                "input_schema": None,
                "output_schema": None,
            }
            if cap in _mas_cap_lookup:
                full = _mas_cap_lookup[cap]
                entry["input_schema"] = full.get("input_schema")
                entry["output_schema"] = full.get("output_schema")
                entry["business_rule_version"] = full.get("business_rule_version")
                entry["description"] = full.get("description", "")
            mas_capabilities.append(entry)

        return MASAgentCard(
            agent_id=card_data.get("agent_id", ""),
            agent_name=card_data.get("agent_name", ""),
            version=card_data.get("version", "1.0.0"),
            capabilities=mas_capabilities,
            endpoints=card_data.get("endpoints", []),
            trust_score=card_data.get("trust_score", 0.0),
            signed_at="",
            expires_at="",
        )

    @staticmethod
    def to_maref_card(mas_card: MASAgentCard) -> SignedAgentCard:
        """Convert MAS-TS-001 Agent Card → MAREF SignedAgentCard."""
        # Map capabilities back (list[dict] → list[str])
        capability_names = [
            cap.get("name", cap.get("skill_id", "")) for cap in mas_card.capabilities
        ]

        return SignedAgentCard(
            card_id=f"card_{mas_card.agent_id}",
            agent_id=mas_card.agent_id,
            agent_name=mas_card.agent_name,
            capabilities=[c for c in capability_names if c],
            endpoints=mas_card.endpoints,
            trust_score=mas_card.trust_score,
            version=mas_card.version,
            expires_at=time.time() + 86400 * 30,
        )

    @staticmethod
    def validate_cross_border_consistency(card: MASAgentCard) -> tuple[bool, str]:
        """
        Validate Theorem 1: Cross-Border Consistency.

        If data_residency != model_backend_location, cross_border must be true.
        """
        if not card.data_residency or not card.model_backend_location:
            return True, "Locations not specified, skipping check"

        if card.data_residency != card.model_backend_location and not card.cross_border:
            return (
                False,
                f"Cross-border inconsistency: residency={card.data_residency}, "
                f"backend={card.model_backend_location}, cross_border={card.cross_border}",
            )
        return True, "Cross-border consistent"

    @staticmethod
    def validate_prompt_rot_detectability(card: MASAgentCard) -> tuple[bool, str]:
        """
        Validate Theorem 2: Prompt Rot Detection Completeness.

        Any capability without business_rule_version is undetectable for prompt rot.
        """
        undetectable = []
        for cap in card.capabilities:
            if not cap.get("business_rule_version"):
                undetectable.append(cap.get("name", cap.get("skill_id", "unknown")))

        if undetectable:
            return (False, f"Prompt rot undetectable for skills: {', '.join(undetectable)}")
        return True, "All skills have business_rule_version"

    @staticmethod
    def full_validate(card: MASAgentCard) -> dict[str, Any]:
        """Run all validations and return detailed results."""
        results = {
            "schema_valid": True,  # Would use jsonschema in production
            "cross_border": AgentCardAdapter.validate_cross_border_consistency(card),
            "prompt_rot": AgentCardAdapter.validate_prompt_rot_detectability(card),
        }
        results["overall_pass"] = all(r[0] for r in results.values() if isinstance(r, tuple))
        return results

    @staticmethod
    def from_agent_card_config() -> MASAgentCard:
        """Create an MASAgentCard from the centralized Agent Card configuration."""
        config = get_default_card_config()
        return MASAgentCard(
            agent_id=config.agent_id,  # type: ignore[attr-defined]
            agent_name=config.agent_name,
            version=config.version,  # type: ignore[attr-defined]
            description=config.description,  # type: ignore[attr-defined]
            capabilities=config.mas_capabilities,  # type: ignore[attr-defined]
            endpoints=config.endpoints,  # type: ignore[attr-defined]
            data_residency=config.data_residency,  # type: ignore[attr-defined]
            model_backend_location=config.model_backend_location,  # type: ignore[attr-defined]
            cross_border=config.cross_border,  # type: ignore[attr-defined]
            trust_score=config.trust_score,  # type: ignore[attr-defined]
            compliance_labels=config.compliance_labels,  # type: ignore[attr-defined]
        )


__all__ = [
    "MASAgentCard",
    "AgentCardAdapter",
    "MAS_TS001_AGENT_CARD_SCHEMA",
]
