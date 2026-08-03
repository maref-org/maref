"""MAREF Level 2 — 治理 Agent 组织（设计阶段，v0.48）。

Level 2 组件当前为设计文档 + MVP 原型（TP-08，2026 年仅设计不生产化）：
- ``audit_bus_mvp``: 分布式审计总线 MVP（跨框架一致性验证，v0.48 L3）。
"""

from __future__ import annotations

from maref.level2.audit_bus_mvp import (
    AutoGenAdapter,
    CrewAIAdapter,
    DistributedAuditBus,
    FrameworkAdapter,
    FrameworkAuditEvent,
    LangGraphAdapter,
)

__all__ = [
    "AutoGenAdapter",
    "CrewAIAdapter",
    "DistributedAuditBus",
    "FrameworkAdapter",
    "FrameworkAuditEvent",
    "LangGraphAdapter",
]
