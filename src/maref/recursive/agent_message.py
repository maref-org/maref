from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageProtocol(str, Enum):
    HANDOFF = "handoff"
    DISCOVERY = "discovery"
    NEGOTIATION = "negotiation"
    MARKETPLACE = "marketplace"
    STIGMERGY = "stigmergy"
    DECISION = "decision"
    FEDERATION = "federation"
    GOSSIP = "gossip"


class MessagePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class AgentMessage:
    sender_id: str
    target_id: str
    protocol: MessageProtocol
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    source_agent: str = ""
    ttl: float = 30.0
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING
    nack_route: str = ""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    @property
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl

    def mark_sent(self) -> None:
        self.status = MessageStatus.SENT

    def mark_delivered(self) -> None:
        self.status = MessageStatus.DELIVERED

    def mark_failed(self, reason: str = "") -> None:
        self.status = MessageStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "protocol": self.protocol.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source_agent": self.source_agent or self.sender_id,
            "ttl": self.ttl,
            "priority": self.priority.value,
            "status": self.status.value,
            "nack_route": self.nack_route,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMessage:
        return cls(
            sender_id=data["sender_id"],
            target_id=data["target_id"],
            protocol=MessageProtocol(data["protocol"]),
            payload=data.get("payload", {}),
            message_id=data.get("message_id", ""),
            timestamp=data.get("timestamp", time.time()),
            source_agent=data.get("source_agent", data.get("sender_id", "")),
            ttl=data.get("ttl", 30.0),
            priority=MessagePriority(data.get("priority", "normal")),
            status=MessageStatus(data.get("status", "pending")),
            nack_route=data.get("nack_route", ""),
            trace_id=data.get("trace_id", ""),
        )
