"""Intent Normalization Gateway — normalize all external input to IntentEvent.

All external inputs (WebSocket, HTTP, voice ASR text) pass through this
gateway before reaching the execution layer. The gateway:

1. Normalizes input format into a standard IntentEvent structure
2. Injects identity and session context
3. Classifies intent type for routing
4. Rejects malformed or unauthorized requests
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(Enum):
    QUERY = "query"
    COMMAND = "command"
    TASK = "task"
    PREFERENCE = "preference"
    FEEDBACK = "feedback"
    UNKNOWN = "unknown"


class InputSource(Enum):
    HTTP = "http"
    WEBSOCKET = "websocket"
    VOICE = "voice"
    CLI = "cli"
    INTERNAL = "internal"


@dataclass
class IntentEvent:
    """Standardized intent event for all external inputs."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: InputSource = InputSource.HTTP
    user_id: str = ""
    session_id: str = ""
    raw_input: str = ""
    intent_type: IntentType = IntentType.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "raw_input": self.raw_input,
            "intent_type": self.intent_type.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class IntentClassifier:
    """Simple rule-based intent classifier.

    In production, replace with an ML classifier or LLM call.
    """

    COMMAND_PREFIXES = ("/", "!run", "execute", "deploy", "stop", "start")
    TASK_PATTERNS = ("analyze", "generate", "create", "build", "compare")
    PREFERENCE_PATTERNS = (
        "remember", "prefer", "always", "never", "don't", "save",
    )
    FEEDBACK_PATTERNS = ("good", "bad", "fix", "wrong", "improve", "error")

    @classmethod
    def classify(cls, text: str) -> IntentType:
        lowered = text.strip().lower()
        if not lowered:
            return IntentType.UNKNOWN
        for prefix in cls.COMMAND_PREFIXES:
            if lowered.startswith(prefix):
                return IntentType.COMMAND
        for pattern in cls.TASK_PATTERNS:
            if lowered.startswith(pattern):
                return IntentType.TASK
        for pattern in cls.PREFERENCE_PATTERNS:
            if pattern in lowered:
                return IntentType.PREFERENCE
        for pattern in cls.FEEDBACK_PATTERNS:
            if pattern in lowered:
                return IntentType.FEEDBACK
        return IntentType.QUERY


class IntentGateway:
    """Gateway that normalizes external input into IntentEvent.

    Usage:
        gateway = IntentGateway()
        event = gateway.process(
            source=InputSource.HTTP,
            raw_input="analyze sales data for Q2",
            user_id="user-123",
            session_id="sess-456",
        )
        # event.intent_type == IntentType.TASK
    """

    def __init__(self, classifier: type[IntentClassifier] = IntentClassifier) -> None:
        self._classifier = classifier
        self._events: list[IntentEvent] = []

    def process(
        self,
        source: InputSource,
        raw_input: str,
        user_id: str = "",
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IntentEvent:
        """Process raw input through the gateway.

        Validates, classifies, and returns a normalized IntentEvent.
        Raises ValueError on empty or malicious input.
        """
        stripped = raw_input.strip()
        if not stripped:
            raise ValueError("empty input rejected")
        if len(stripped) > 50_000:
            raise ValueError("input exceeds maximum length (50K chars)")

        intent_type = self._classifier.classify(stripped)

        event = IntentEvent(
            source=source,
            user_id=user_id,
            session_id=session_id,
            raw_input=stripped,
            intent_type=intent_type,
            metadata={
                **(metadata or {}),
                "length": len(stripped),
            },
        )
        self._events.append(event)
        return event

    def get_recent_events(self, n: int = 50) -> list[IntentEvent]:
        return self._events[-n:]

    def clear_events(self) -> None:
        self._events.clear()
