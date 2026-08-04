"""MAREF Level 2 — 治理 Agent 组织（v0.48 设计 + v0.49 生产化原型）。

Level 2 组件：
- ``audit_bus_mvp``: 分布式审计总线（跨框架一致性 + v0.49 规范化/签名归属）。
- ``audit_store``: 审计事件 SQLite 持久化（v0.49 P4）。
- ``gossip_protocol``: Gossip 传输原型（v0.49 P6）。
"""

from __future__ import annotations

from maref.level2.audit_bus_mvp import (
    AutoGenAdapter,
    CrewAIAdapter,
    DistributedAuditBus,
    FrameworkAdapter,
    FrameworkAuditEvent,
    LangGraphAdapter,
    normalise_metadata,
)
from maref.level2.gossip_protocol import (
    DEFAULT_FANOUT,
    DEFAULT_TTL,
    GossipMessage,
    GossipMessageKind,
    GossipNode,
    build_ring,
)

__all__ = [
    "AutoGenAdapter",
    "CrewAIAdapter",
    "DEFAULT_FANOUT",
    "DEFAULT_TTL",
    "DistributedAuditBus",
    "FrameworkAdapter",
    "FrameworkAuditEvent",
    "GossipMessage",
    "GossipMessageKind",
    "GossipNode",
    "LangGraphAdapter",
    "build_ring",
    "normalise_metadata",
]
