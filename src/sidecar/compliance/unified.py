from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CheckActionResult:
    decision: str = "allow"
    reason: str = ""
    risk_score: float = 0.0


@dataclass
class GovernanceDecision:
    decision: str = "allow"
    reason: str = ""
    policy_version: str = ""
    policy_epoch: str = ""


_POLICY_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
_HIGH_RISK = {"high", "critical"}


def _policy_path() -> Path:
    env_path = os.environ.get("MAREF_PHOENIX_POLICY")
    if env_path:
        return Path(env_path).resolve()
    return (Path(__file__).resolve().parents[3] / "configs" / "phoenix_policy.yaml").resolve()


def _load_policy(path: Path) -> dict[str, Any]:
    """Load and cache the Phoenix policy by (path, mtime, size)."""
    try:
        stat = path.stat()
    except OSError:
        return {"_error": f"policy file missing: {path}"}
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _POLICY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {"_error": "policy root must be a mapping"}
    except Exception as exc:  # invalid YAML must fail closed for high risk
        data = {"_error": f"policy parse error: {exc}"}
    _POLICY_CACHE.clear()
    _POLICY_CACHE[key] = data
    return data


def _matches(rule: dict[str, Any], tool_name: str, scope: str, risk: str, multi_party: bool) -> bool:
    match = rule.get("match") or {}
    tools = match.get("tools")
    if tools:
        if isinstance(tools, str):
            tools = [tools]
        if not any(fnmatch.fnmatch(tool_name, str(pattern)) for pattern in tools):
            return False
    risks = match.get("risk")
    if risks:
        if isinstance(risks, str):
            risks = [risks]
        if risk.lower() not in {str(r).lower() for r in risks}:
            return False
    if "multi_party" in match and bool(match["multi_party"]) != multi_party:
        return False
    prefix = match.get("scope_prefix")
    if prefix:
        prefixes = [prefix] if isinstance(prefix, str) else list(prefix)
        if not scope or not any(scope.startswith(str(p)) for p in prefixes):
            return False
    blocked_prefix = match.get("scope_not_prefix")
    if blocked_prefix and scope:
        prefixes = [blocked_prefix] if isinstance(blocked_prefix, str) else list(blocked_prefix)
        if any(scope.startswith(str(p)) for p in prefixes):
            return False
    return True


def check_if_governed(
    tool_name: str,
    scope: str = "",
    risk: str = "low",
    multi_party: bool = False,
) -> GovernanceDecision | None:
    """Evaluate the Phoenix policy for a tool call.

    Returns ``None`` when the action is outside the policy domain (low risk
    and no matching rule). High/critical risk or multi-party actions are
    fail-closed: missing/invalid policy or no matching allow rule denies.
    """
    risk_norm = (risk or "low").lower()
    path = _policy_path()
    policy = _load_policy(path)
    policy_version = str(policy.get("version", ""))
    policy_epoch = str(policy.get("epoch", ""))

    if "_error" in policy:
        if risk_norm in _HIGH_RISK or multi_party:
            return GovernanceDecision(
                decision="deny",
                reason=f"Phoenix policy unavailable ({policy['_error']}); fail-closed for high risk",
                policy_version=policy_version,
                policy_epoch=policy_epoch,
            )
        return None

    for rule in policy.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if not _matches(rule, tool_name, scope, risk_norm, multi_party):
            continue
        decision = str(rule.get("decision", "deny")).lower()
        if decision not in {"allow", "deny", "require_approval"}:
            decision = "deny"
        return GovernanceDecision(
            decision=decision,
            reason=str(rule.get("reason") or f"matched Phoenix rule: {rule.get('name', 'unnamed')}"),
            policy_version=policy_version,
            policy_epoch=policy_epoch,
        )

    if risk_norm in _HIGH_RISK or multi_party:
        return GovernanceDecision(
            decision="deny",
            reason="no Phoenix policy permits this high-risk or multi-party action (fail-closed)",
            policy_version=policy_version,
            policy_epoch=policy_epoch,
        )
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
