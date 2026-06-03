"""Life State Messaging — inter-entity communication protocol.

C34: Message passing between life state entities.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    """Canonical message types."""

    HEARTBEAT = "heartbeat"
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ALERT = "alert"


class Priority(int, Enum):
    """Message priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class LifeStateMessage:
    """A message exchanged between life state entities."""

    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    msg_type: MessageType = MessageType.EVENT
    sender_id: str = ""
    recipient_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    timestamp: float = field(default_factory=time.time)
    timeout_ms: float = 5000.0

    def is_expired(self) -> bool:
        elapsed_ms = (time.time() - self.timestamp) * 1000
        return elapsed_ms > self.timeout_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "payload": self.payload,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "timeout_ms": self.timeout_ms,
        }


class MessageBus:
    """In-memory message bus for life state entities.

    Supports 1:1 (direct) and 1:N (broadcast) messaging.
    """

    def __init__(self) -> None:
        self._messages: list[LifeStateMessage] = []
        self._handlers: dict[str, list[Callable[[LifeStateMessage], None]]] = {}
        self._global_handlers: list[Callable[[LifeStateMessage], None]] = []

    def send(self, message: LifeStateMessage) -> None:
        self._messages.append(message)
        if message.recipient_id:
            for handler in self._handlers.get(message.recipient_id, []):
                try:
                    handler(message)
                except Exception:
                    pass
        else:
            for _state_id, handlers in self._handlers.items():
                for handler in handlers:
                    try:
                        handler(message)
                    except Exception:
                        pass
        for handler in self._global_handlers:
            try:
                handler(message)
            except Exception:
                pass

    def broadcast(
        self, sender_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> LifeStateMessage:
        msg = LifeStateMessage(
            msg_type=msg_type,
            sender_id=sender_id,
            recipient_id="",
            payload=payload,
        )
        self.send(msg)
        return msg

    def request(
        self, sender_id: str, recipient_id: str, payload: dict[str, Any]
    ) -> LifeStateMessage:
        msg = LifeStateMessage(
            msg_type=MessageType.REQUEST,
            sender_id=sender_id,
            recipient_id=recipient_id,
            payload=payload,
        )
        self.send(msg)
        return msg

    def subscribe(self, state_id: str, handler: Callable[[LifeStateMessage], None]) -> None:
        self._handlers.setdefault(state_id, []).append(handler)

    def unsubscribe(self, state_id: str, handler: Callable[[LifeStateMessage], None]) -> None:
        handlers = self._handlers.get(state_id, [])
        if handler in handlers:
            handlers.remove(handler)

    def subscribe_global(self, handler: Callable[[LifeStateMessage], None]) -> None:
        self._global_handlers.append(handler)

    def unsubscribe_global(self, handler: Callable[[LifeStateMessage], None]) -> None:
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    def get_messages(self, state_id: str | None = None) -> list[LifeStateMessage]:
        if state_id is None:
            return list(self._messages)
        return [
            m
            for m in self._messages
            if m.recipient_id == state_id or m.sender_id == state_id or m.recipient_id == ""
        ]

    def get_messages_by_type(self, msg_type: MessageType) -> list[LifeStateMessage]:
        return [m for m in self._messages if m.msg_type == msg_type]

    def clear(self) -> None:
        self._messages.clear()

    def count(self) -> int:
        return len(self._messages)
