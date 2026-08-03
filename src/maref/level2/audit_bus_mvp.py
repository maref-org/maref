"""Level 2 — Distributed Audit Bus MVP (v0.48.0 L3, TP-08 T8.3).

Cross-framework audit consistency: three agent frameworks (langgraph /
crewai / autogen) each produce audit events; the bus normalises them to a
canonical event and verifies that the *same underlying action* yields an
identical canonical digest across frameworks.

Canonicalisation excludes the ``framework`` field so the digest is
framework-agnostic — this is the consistency guarantee: if two frameworks
report the same action with the same core fields, their digests match.

This is a design-prototype (MVP); production transport (Gossip, L5) is out
of scope for v0.48.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Framework identifiers aligned with TP-08 §2.3.
FRAMEWORK_LANGGRAPH = "langgraph"
FRAMEWORK_CREWAI = "crewai"
FRAMEWORK_AUTOGEN = "autogen"

# Core fields that define the canonical digest (framework excluded).
_CANONICAL_FIELDS = ("event_type", "actor", "action", "timestamp", "metadata")


@dataclass
class FrameworkAuditEvent:
    """A canonical cross-framework audit event."""

    event_type: str
    actor: str
    action: str
    framework: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    signature: str = ""

    def canonical_payload(self) -> bytes:
        """Bytes the canonical digest is computed over (framework excluded)."""
        return json.dumps(
            {
                "event_type": self.event_type,
                "actor": self.actor,
                "action": self.action,
                "timestamp": self.timestamp,
                "metadata": self.metadata,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def canonical_digest(self) -> str:
        """SHA-256 digest of the canonical payload."""
        return hashlib.sha256(self.canonical_payload()).hexdigest()

    def sign(self, secret_key: bytes) -> str:
        """HMAC-SHA256 signature over the canonical payload."""
        return hmac.new(secret_key, self.canonical_payload(), hashlib.sha256).hexdigest()


class FrameworkAdapter(ABC):
    """Adapter translating a framework's audit format to the canonical event."""

    framework: str = ""

    @abstractmethod
    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        """Build a canonical event for this framework."""


class LangGraphAdapter(FrameworkAdapter):
    framework = FRAMEWORK_LANGGRAPH

    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        return FrameworkAuditEvent(
            event_type=event_type, actor=actor, action=action,
            framework=self.framework, metadata=dict(metadata),
        )


class CrewAIAdapter(FrameworkAdapter):
    framework = FRAMEWORK_CREWAI

    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        return FrameworkAuditEvent(
            event_type=event_type, actor=actor, action=action,
            framework=self.framework, metadata=dict(metadata),
        )


class AutoGenAdapter(FrameworkAdapter):
    framework = FRAMEWORK_AUTOGEN
    _tamper_action: str | None = None  # test hook for divergence

    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        if self._tamper_action is not None:
            action = self._tamper_action
        return FrameworkAuditEvent(
            event_type=event_type, actor=actor, action=action,
            framework=self.framework, metadata=dict(metadata),
        )


class DistributedAuditBus:
    """Normalises + verifies cross-framework audit consistency.

    Args:
        secret_key: HMAC key for event signing (required for tamper-evident log).
    """

    def __init__(self, secret_key: bytes) -> None:
        self._secret_key = secret_key
        self._adapters: dict[str, FrameworkAdapter] = {}
        self._audit_log: list[dict[str, Any]] = []

    def register_adapter(self, adapter: FrameworkAdapter) -> None:
        self._adapters[adapter.framework] = adapter

    def publish(self, event: FrameworkAuditEvent) -> None:
        """Record a single framework event with an HMAC signature."""
        event.signature = event.sign(self._secret_key)
        self._audit_log.append(
            {
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "actor": event.actor,
                "action": event.action,
                "framework": event.framework,
                "digest": event.canonical_digest(),
                "signature": event.signature,
            }
        )

    def verify_event_signature(self, event: FrameworkAuditEvent) -> bool:
        """Verify an event's HMAC against the bus secret key."""
        if not event.signature:
            return False
        expected = event.sign(self._secret_key)
        return hmac.compare_digest(expected, event.signature)

    def publish_cross_framework(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish the same action through every registered framework adapter
        and verify canonical-digest consistency across frameworks.

        Returns:
            ``{"consistent": bool, "frameworks": {fw: {"digest", "action"}}}``.
        """
        metadata = metadata or {}
        # Same underlying action → same canonical timestamp so digests align
        # across frameworks.
        ts = time.time()
        frameworks: dict[str, dict[str, Any]] = {}
        for name, adapter in self._adapters.items():
            event = adapter.build_event(event_type, actor, action, metadata)
            event.timestamp = ts
            self.publish(event)
            frameworks[name] = {
                "digest": event.canonical_digest(),
                "action": event.action,
            }
        digests = {f["digest"] for f in frameworks.values()}
        return {
            "consistent": len(digests) == 1,
            "frameworks": frameworks,
        }

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)


__all__ = [
    "FRAMEWORK_LANGGRAPH",
    "FRAMEWORK_CREWAI",
    "FRAMEWORK_AUTOGEN",
    "FrameworkAuditEvent",
    "FrameworkAdapter",
    "LangGraphAdapter",
    "CrewAIAdapter",
    "AutoGenAdapter",
    "DistributedAuditBus",
]
