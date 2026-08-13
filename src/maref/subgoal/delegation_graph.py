from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelegationEvent:
    from_agent: str
    to_agent: str
    permissions: set[str]
    timestamp: float
    reason: str


@dataclass
class CreepReport:
    agent_id: str
    current_permissions: set[str]
    original_permissions: set[str]
    new_permissions: set[str]
    creep_score: float
    requires_cooldown: bool
    findings: list[str] = field(default_factory=list)


@dataclass
class EnforcementResult:
    """Result of an enforced delegation.

    Attributes:
        allowed: Whether the delegation was permitted.
        requested_permissions: The permissions requested by the delegator.
        granted_permissions: The permissions actually granted (trimmed to scope).
        trimmed_permissions: Permissions that were trimmed (out of scope).
        reason: Human-readable explanation.
    """

    allowed: bool
    requested_permissions: set[str]
    granted_permissions: set[str]
    trimmed_permissions: set[str]
    reason: str


class DelegationGraph:
    def __init__(self, max_depth: int = 5, cooldown_threshold: float = 0.5) -> None:
        self._events: list[DelegationEvent] = []
        self._permissions: dict[str, set[str]] = {}
        self._baselines: dict[str, set[str]] = {}
        self._max_depth = max_depth
        self._cooldown_threshold = cooldown_threshold
        self._cooldowns: dict[str, float] = {}
        self._cooldown_times: dict[str, float] = {}

    def record_delegation(
        self, from_agent: str, to_agent: str, permissions: set[str], reason: str = ""
    ) -> None:
        event = DelegationEvent(
            from_agent=from_agent,
            to_agent=to_agent,
            permissions=permissions,
            timestamp=time.time(),
            reason=reason,
        )
        self._events.append(event)
        if to_agent not in self._baselines:
            self._baselines[to_agent] = set(permissions)
        self._permissions.setdefault(to_agent, set()).update(permissions)

    def detect_scope_creep(self, agent_id: str, window: float = 3600) -> CreepReport:
        baseline = self._baselines.get(agent_id, set())
        current = self._permissions.get(agent_id, set())
        new_perms = current - baseline

        now = time.time()
        recent = [
            e for e in self._events if e.to_agent == agent_id and (now - e.timestamp) < window
        ]

        creep_score = self._compute_creep_score(baseline, current, recent)
        requires_cooldown = creep_score > self._cooldown_threshold

        findings: list[str] = []
        if baseline:
            ratio = len(current) / (len(baseline) or 1)
            if ratio > 2:
                findings.append(f"permission_multiple:{ratio:.1f}x")
        if new_perms:
            findings.append(f"new_permissions:{','.join(sorted(new_perms))}")
        if requires_cooldown:
            findings.append(f"creep_score:{creep_score:.2f}>=threshold:{self._cooldown_threshold}")

        return CreepReport(
            agent_id=agent_id,
            current_permissions=current,
            original_permissions=baseline,
            new_permissions=new_perms,
            creep_score=creep_score,
            requires_cooldown=requires_cooldown,
            findings=findings,
        )

    def transitive_closure(self, agent_id: str) -> set[str]:
        effective: set[str] = set()
        visited: set[str] = set()
        queue = [agent_id]
        while queue and len(visited) < self._max_depth:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            perms = self._permissions.get(current, set())
            effective.update(perms)
            children = [
                e.to_agent
                for e in self._events
                if e.from_agent == current and e.to_agent not in visited
            ]
            queue.extend(children)
        return effective

    def apply_cooldown(self, agent_id: str, duration: float) -> None:
        self._cooldowns[agent_id] = self._cooldown_threshold
        self._cooldown_times[agent_id] = time.time() + duration

    def is_in_cooldown(self, agent_id: str) -> bool:
        if agent_id not in self._cooldown_times:
            return False
        if time.time() > self._cooldown_times[agent_id]:
            del self._cooldowns[agent_id]
            del self._cooldown_times[agent_id]
            return False
        return True

    def get_effective_permissions(self, agent_id: str) -> dict[str, Any]:
        direct = self._permissions.get(agent_id, set())
        transitive = self.transitive_closure(agent_id)
        return {
            "agent_id": agent_id,
            "direct_permissions": sorted(direct),
            "transitive_permissions": sorted(transitive),
            "in_cooldown": self.is_in_cooldown(agent_id),
        }

    def _compute_creep_score(
        self, baseline: set[str], current: set[str], recent: list[DelegationEvent]
    ) -> float:
        if not baseline:
            return len(current) * 0.1

        size_ratio = len(current) / len(baseline)
        rate = len(recent) / max(len(baseline), 1)
        score = (min(size_ratio / 3, 1.0) * 0.5) + (min(rate, 1.0) * 0.5)
        return min(score, 1.0)

    def enforce_delegation(
        self,
        from_agent: str,
        to_agent: str,
        requested_permissions: set[str],
        reason: str = "",
    ) -> EnforcementResult:
        """Enforce that delegated permissions don't exceed the delegator's scope.

        Unlike :meth:`record_delegation` (which records any delegation),
        this method enforces a hard constraint: only permissions within
        the delegator's transitive closure are granted. Out-of-scope
        permissions are silently trimmed. If *all* requested permissions
        are out of scope, the delegation is refused.

        Args:
            from_agent: The delegating agent.
            to_agent: The receiving agent.
            requested_permissions: The permissions requested for delegation.
            reason: Optional reason for the delegation.

        Returns:
            An :class:`EnforcementResult` describing what was granted,
            what was trimmed, and whether the delegation was allowed.
        """
        delegator_perms = self.transitive_closure(from_agent)

        in_scope = requested_permissions & delegator_perms
        out_of_scope = requested_permissions - delegator_perms

        if not in_scope:
            return EnforcementResult(
                allowed=False,
                requested_permissions=requested_permissions,
                granted_permissions=set(),
                trimmed_permissions=out_of_scope,
                reason="all requested permissions are out of delegator scope",
            )

        self.record_delegation(from_agent, to_agent, in_scope, reason)

        if out_of_scope:
            return EnforcementResult(
                allowed=True,
                requested_permissions=requested_permissions,
                granted_permissions=in_scope,
                trimmed_permissions=out_of_scope,
                reason=f"trimmed {len(out_of_scope)} out-of-scope permissions",
            )

        return EnforcementResult(
            allowed=True,
            requested_permissions=requested_permissions,
            granted_permissions=in_scope,
            trimmed_permissions=set(),
            reason="all permissions in scope",
        )

    def check_permission(self, agent_id: str, permission: str) -> bool:
        """Check if an agent has a specific permission (including transitive).

        Args:
            agent_id: The agent to check.
            permission: The permission to verify.

        Returns:
            True if the permission is in the agent's transitive closure.
        """
        effective = self.transitive_closure(agent_id)
        return permission in effective
