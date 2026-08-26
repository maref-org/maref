"""AuditBus → ObsEvent 双向映射桥接。

将 AuditBus 中的 12 类治理违规事件注入 ObsEvent 遥测管线，
使治理违规行为进入 telemetry 仪表盘可观测。

用法::

    bridge = AuditObsBridge()
    bridge.start()    # 订阅 AuditBus 并开始转发
    bridge.stop()     # 取消订阅
"""

from __future__ import annotations

import logging
from typing import Any

from maref.obs.client import MarefObsClient
from maref.obs.schema import ObsEventType

logger = logging.getLogger(__name__)

_EVENT_TYPE_MAP: dict[str, ObsEventType] = {
    "trust_boundary_check": ObsEventType.TRUST_BOUNDARY_VIOLATION,
    "agent_sanctioned": ObsEventType.SANCTION,
    "cost_breach": ObsEventType.COST_BREACH,
    "constitution_violation": ObsEventType.CONSTITUTION_VIOLATION,
    "bypass_detected": ObsEventType.GOVERNANCE_BYPASS,
    "state_transition": ObsEventType.STATE_TRANSITION,
    "breaker_trip": ObsEventType.BREAKER_TRIP,
    "oscillation_detected": ObsEventType.OSCILLATION_DETECTED,
    "oscillation_resolved": ObsEventType.OSCILLATION_RESOLVED,
    "anomaly_detected": ObsEventType.ANOMALY_DETECTED,
    "adapter_invocation": ObsEventType.ADAPTER_INVOCATION,
    "tool_execution": ObsEventType.TOOL_EXECUTION,
}


class AuditObsBridge:
    """订阅 AuditBus 事件并转发到 ObsEvent 遥测管线。

    每个审计事件通过 _EVENT_TYPE_MAP 映射到 ObsEventType，
    然后通过 MarefObsClient 写入 ndjson 缓冲区。
    """

    def __init__(
        self,
        obs_client: MarefObsClient | None = None,
        audit_bus: Any | None = None,
    ) -> None:
        self._obs = obs_client or MarefObsClient.get_default()
        self._audit_bus = audit_bus
        self._subscribed = False
        self._callback: Any = None

    def start(self) -> None:
        if self._audit_bus is None:
            logger.warning("AuditObsBridge: no audit_bus provided, "
                           "events will not be forwarded")
            return
        if self._subscribed:
            return
        self._callback = self._make_callback()
        if hasattr(self._audit_bus, "subscribe"):
            self._audit_bus.subscribe(self._callback)
            self._subscribed = True
            logger.info("AuditObsBridge started: subscribed to AuditBus")
        else:
            logger.warning("AuditObsBridge: audit_bus has no subscribe() method")

    def stop(self) -> None:
        if not self._subscribed or self._audit_bus is None:
            return
        if self._callback is not None and hasattr(self._audit_bus, "unsubscribe"):
            try:
                self._audit_bus.unsubscribe(self._callback)
            except Exception:
                pass
        self._subscribed = False
        logger.info("AuditObsBridge stopped")

    def _make_callback(self):
        def _on_audit_event(event: dict[str, Any]) -> None:
            self._forward(event)
        return _on_audit_event

    def _forward(self, event: dict[str, Any]) -> None:
        event_type_str = event.get("event_type", "")
        obs_type = _EVENT_TYPE_MAP.get(event_type_str)
        if obs_type is None:
            return
        metadata = dict(event)
        metadata.pop("event_type", None)
        self._obs.log_event(obs_type, metadata=metadata)

    def forward_single(self, event_type: str, metadata: dict | None = None) -> None:
        """直接转发一条事件到 ObsEvent 管线（不经过 AuditBus 订阅）。"""
        obs_type = _EVENT_TYPE_MAP.get(event_type)
        if obs_type is None:
            return
        self._obs.log_event(obs_type, metadata=metadata)