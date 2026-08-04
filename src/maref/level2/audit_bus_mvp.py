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
from enum import Enum
from typing import Any

# Framework identifiers aligned with TP-08 §2.3.
FRAMEWORK_LANGGRAPH = "langgraph"
FRAMEWORK_CREWAI = "crewai"
FRAMEWORK_AUTOGEN = "autogen"

# Core fields that define the canonical digest (framework excluded).
_CANONICAL_FIELDS = ("event_type", "actor", "action", "timestamp", "metadata")

# v0.49 P1: framework-runtime noise keys. These are per-framework bookkeeping
# fields (call IDs, run IDs, checkpoint ids) that carry no semantic content and
# would otherwise cause cross-framework digest divergence for the *same* action.
# Adapters strip these before the event reaches canonical digest computation.
_FRAMEWORK_NOISE_KEYS: dict[str, frozenset[str]] = {
    FRAMEWORK_LANGGRAPH: frozenset(
        {"tool_call_id", "node_id", "run_id", "checkpoint_id", "thread_id"}
    ),
    FRAMEWORK_CREWAI: frozenset(
        {"task_id", "crew_id", "iteration", "async_execution"}
    ),
    FRAMEWORK_AUTOGEN: frozenset(
        {"conversation_id", "agent_id", "chat_id", "session_id"}
    ),
}

# Union of every framework's runtime keys: stripped from metadata before
# canonical digest computation so the *same action* yields the *same digest*
# regardless of which framework reported it (v0.49 P1).
_ALL_NOISE_KEYS = frozenset().union(*_FRAMEWORK_NOISE_KEYS.values())


def normalise_metadata(value: Any) -> Any:
    """Recursively normalise a metadata value into a canonical, JSON-serialisable
    form so that *semantically identical* metadata always yields the same
    canonical digest (v0.49 P1).

    Normalisation rules:
    - ``dict`` keys are sorted and values normalised recursively.
    - ``tuple`` → ``list``; ``set`` → sorted ``list``; ``bytes`` → hex string.
    - ``Enum`` members → their ``value``.
    - Other non-JSON types are stringified.

    Idempotent: normalising already-normal metadata is a no-op, so existing
    (v0.48) events keep their digest.
    """
    if isinstance(value, dict):
        return {
            str(k): normalise_metadata(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalise_metadata(v) for v in value]
    if isinstance(value, set):
        return [normalise_metadata(v) for v in sorted(value, key=str)]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


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
    # v0.49 P2: signature scheme. ``v2`` signs ``canonical + framework`` so a
    # signature cannot be replayed across frameworks; ``v1`` is the legacy
    # canonical-only scheme (verified for backward compatibility).
    signature_scheme: str = "v2"

    def canonical_payload(self) -> bytes:
        """Bytes the canonical digest is computed over (framework excluded).

        ``metadata`` is normalised (v0.49 P1) before serialisation so that
        equivalent metadata (type or key-order variants) yields the same digest.
        """
        return json.dumps(
            {
                "event_type": self.event_type,
                "actor": self.actor,
                "action": self.action,
                "timestamp": self.timestamp,
                "metadata": normalise_metadata(self.metadata),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def canonical_digest(self) -> str:
        """SHA-256 digest of the canonical payload."""
        return hashlib.sha256(self.canonical_payload()).hexdigest()

    def signed_payload(self, framework: str | None = None) -> bytes:
        """Bytes signed under scheme ``v2``: canonical payload + the framework
        the signature is attributed to.

        Including the framework makes a signature unforgeable across
        frameworks: an event carrying another framework's signature fails
        verification (v0.49 P2).
        """
        fw = framework if framework is not None else self.framework
        return self.canonical_payload() + b"\x00framework:" + fw.encode()

    def sign(self, secret_key: bytes) -> str:
        """HMAC-SHA256 signature over the framework-attributed payload (v2)."""
        return hmac.new(
            secret_key, self.signed_payload(self.framework), hashlib.sha256
        ).hexdigest()

    def sign_legacy(self, secret_key: bytes) -> str:
        """v1 legacy HMAC-SHA256 over the canonical payload only.

        Kept for verifying events signed by v0.48 (canonical-only scheme).
        """
        return hmac.new(
            secret_key, self.canonical_payload(), hashlib.sha256
        ).hexdigest()


class FrameworkAdapter(ABC):
    """Adapter translating a framework's audit format to the canonical event."""

    framework: str = ""
    noise_keys: frozenset[str] = frozenset()

    @abstractmethod
    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        """Build a canonical event for this framework."""

    def _clean_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Strip framework-runtime noise keys then normalise (v0.49 P1).

        The *union* of all frameworks' runtime keys is stripped so the same
        underlying action yields the same canonical digest no matter which
        framework reported it.
        """
        cleaned = {
            k: v for k, v in metadata.items() if k not in _ALL_NOISE_KEYS
        }
        normalised = normalise_metadata(cleaned)
        assert isinstance(normalised, dict)
        return normalised


class LangGraphAdapter(FrameworkAdapter):
    framework = FRAMEWORK_LANGGRAPH
    noise_keys = _FRAMEWORK_NOISE_KEYS[FRAMEWORK_LANGGRAPH]

    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        return FrameworkAuditEvent(
            event_type=event_type, actor=actor, action=action,
            framework=self.framework, metadata=self._clean_metadata(metadata),
        )


class CrewAIAdapter(FrameworkAdapter):
    framework = FRAMEWORK_CREWAI
    noise_keys = _FRAMEWORK_NOISE_KEYS[FRAMEWORK_CREWAI]

    def build_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        metadata: dict[str, Any],
    ) -> FrameworkAuditEvent:
        return FrameworkAuditEvent(
            event_type=event_type, actor=actor, action=action,
            framework=self.framework, metadata=self._clean_metadata(metadata),
        )


class AutoGenAdapter(FrameworkAdapter):
    framework = FRAMEWORK_AUTOGEN
    noise_keys = _FRAMEWORK_NOISE_KEYS[FRAMEWORK_AUTOGEN]
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
            framework=self.framework, metadata=self._clean_metadata(metadata),
        )


class DistributedAuditBus:
    """Normalises + verifies cross-framework audit consistency.

    Args:
        secret_key: HMAC key for event signing (required for tamper-evident log).
        store: Optional :class:`maref.level2.audit_store.PersistentAuditStore`;
            when provided every published event is also persisted (v0.49 P4).
    """

    def __init__(self, secret_key: bytes, store: Any | None = None) -> None:
        self._secret_key = secret_key
        self._adapters: dict[str, FrameworkAdapter] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._store = store

    def register_adapter(self, adapter: FrameworkAdapter) -> None:
        self._adapters[adapter.framework] = adapter

    @property
    def store(self) -> Any | None:
        """The attached persistent store, if any."""
        return self._store

    def publish(self, event: FrameworkAuditEvent) -> None:
        """Record a single framework event with an HMAC signature."""
        event.signature_scheme = "v2"
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
        if self._store is not None:
            self._store.append(event)

    def verify_event_signature(
        self,
        event: FrameworkAuditEvent,
        framework: str | None = None,
    ) -> bool:
        """Verify an event's HMAC against the bus secret key.

        Under scheme ``v2`` (v0.49 P2) the signature is bound to the event's
        framework: a signature copied from another framework fails here.
        Legacy ``v1`` (canonical-only) signatures are accepted **only** for
        events explicitly marked ``signature_scheme == "v1"`` (backward
        compatibility for v0.48 events). A v1 signature is never accepted for a
        v2 event, so a canonical-only signature cannot downgrade/sidestep a v2
        event's framework binding.
        """
        if not event.signature:
            return False
        if event.signature_scheme == "v2":
            fw = framework if framework is not None else event.framework
            expected = hmac.new(
                self._secret_key, event.signed_payload(fw), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, event.signature)
        # Legacy v1 scheme (canonical-only signature). Verifies only when the
        # event is explicitly marked v1 — the framework parameter is ignored
        # because a v1 signature carries no framework binding by design.
        expected_legacy = event.sign_legacy(self._secret_key)
        return hmac.compare_digest(expected_legacy, event.signature)

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
    "normalise_metadata",
]
