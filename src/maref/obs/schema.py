"""Pydantic models for MAREF Obs governance events."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ObsEventType(str, Enum):
    """Canonical governance event types tracked by MarefObs."""

    STATE_TRANSITION = "state_transition"
    BREAKER_TRIP = "breaker_trip"
    OSCILLATION_DETECTED = "oscillation_detected"
    OSCILLATION_RESOLVED = "oscillation_resolved"
    ANOMALY_DETECTED = "anomaly_detected"
    ADAPTER_INVOCATION = "adapter_invocation"
    TOOL_EXECUTION = "tool_execution"
    TRUST_BOUNDARY_VIOLATION = "trust_boundary_violation"
    SANCTION = "sanction"
    COST_BREACH = "cost_breach"
    CONSTITUTION_VIOLATION = "constitution_violation"
    GOVERNANCE_BYPASS = "governance_bypass"


class ObsEvent(BaseModel):
    """A single governance observation event.

    All potentially identifying metadata fields are hashed via ObsHasher.
    The ``metadata`` dict contains only the fields appropriate for the
    configured ``TelemetryLevel``.
    """

    event_type: ObsEventType
    version: str = ""
    timestamp: float = 0.0
    event_sequence: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    """Batch of events for local disk serialization."""

    session_id: str
    salt: str
    level: str
    events: list[ObsEvent]
