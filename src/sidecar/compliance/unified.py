from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CheckActionResult:
    decision: str = "allow"
    reason: str = ""
    risk_score: float = 0.0


@dataclass
class GovernanceDecision:
    decision: str = "allow"
    reason: str = ""


def check_if_governed(
    tool_name: str,
    scope: str = "",
    risk: str = "low",
    multi_party: bool = False,
) -> Optional[GovernanceDecision]:
    """Phoenix 策略门禁检查（公共仓存根：无闭源策略引擎，恒返回 None 即放行）。"""
    return None


class UnifiedSidecar:
    """Unified compliance sidecar for agent action governance."""

    def __init__(self, agent_id: str = "", phase: str = "") -> None:
        self.agent_id = agent_id
        self.phase = phase
        self.routes: dict[str, Any] = {}
        self._audit_log: list[dict[str, Any]] = []

    def check_action(self, action: str, action_type: str = "") -> CheckActionResult:
        import time

        result = CheckActionResult(
            decision="allow" if "write" not in action else "block",
            reason=f"action={action} type={action_type} phase={self.phase}",
        )
        self._audit_log.append({
            "timestamp": time.time(),
            "agent_id": self.agent_id,
            "action": action,
            "action_type": action_type,
            "decision": result.decision,
        })
        return result

    def register(self, path: str, handler: Any) -> None:
        self.routes[path] = handler

    def handle(self, path: str, request: Any) -> Any:
        handler = self.routes.get(path)
        if handler is None:
            return None
        return handler(request)
