from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from maref.governance.audit import AuditLogger

DEFAULT_SILENCE_TIMEOUT = 300.0
DEFAULT_TRUST_DECAY_PER_CYCLE = 5.0
DEFAULT_CHECK_INTERVAL = 60.0


@dataclass
class MemberHealth:
    agent_id: str
    last_seen: float
    silence_timeout: float
    suspected: bool = False
    suspicion_started: float = 0.0
    trust_penalty: float = 0.0

    @property
    def silence_elapsed(self) -> float:
        return time.time() - self.last_seen

    @property
    def is_silent(self) -> bool:
        return self.silence_elapsed > self.silence_timeout

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "last_seen": self.last_seen,
            "silence_elapsed": round(self.silence_elapsed, 1),
            "silence_timeout": self.silence_timeout,
            "suspected": self.suspected,
            "suspicion_started": self.suspicion_started,
            "trust_penalty": self.trust_penalty,
        }


@dataclass
class HealthCheckResult:
    checked: int
    silent: int
    suspected: int
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "silent": self.silent,
            "suspected": self.suspected,
            "details": self.details,
        }


class FederationHealthMonitor:
    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        ed25519_signer: Any | None = None,
        silence_timeout: float = DEFAULT_SILENCE_TIMEOUT,
        trust_decay_per_cycle: float = DEFAULT_TRUST_DECAY_PER_CYCLE,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        cascade_breaker: Any | None = None,
    ) -> None:
        self._audit_logger = audit_logger
        self._signer = ed25519_signer
        self._silence_timeout = silence_timeout
        self._trust_decay = trust_decay_per_cycle
        self._check_interval = check_interval
        self._members: dict[str, MemberHealth] = {}
        self._last_check_time: float = 0.0
        # Optional :class:`~maref.federation.cascade_breaker.FederationCascadeBreaker`.
        # Kept duck-typed to avoid a hard import cycle: sustained silence feeds
        # ``record_failure`` (driving isolation + dependent degradation) and a
        # recovery probe feeds ``record_success`` (exact un-degradation).
        self._cascade_breaker = cascade_breaker

    def probe(self, agent_id: str) -> None:
        existing = self._members.get(agent_id)
        if existing is not None:
            was_suspected = existing.suspected
            existing.last_seen = time.time()
            existing.suspected = False
            existing.suspicion_started = 0.0
            existing.trust_penalty = max(0.0, existing.trust_penalty - self._trust_decay * 2)
            if was_suspected:
                self._signal_cascade_recovery(agent_id)
        else:
            self._members[agent_id] = MemberHealth(
                agent_id=agent_id,
                last_seen=time.time(),
                silence_timeout=self._silence_timeout,
            )

    def unregister(self, agent_id: str) -> None:
        self._members.pop(agent_id, None)

    def check(self) -> HealthCheckResult:
        now = time.time()
        self._last_check_time = now
        details: list[dict[str, Any]] = []

        for member in list(self._members.values()):
            if member.is_silent:
                if not member.suspected:
                    member.suspected = True
                    member.suspicion_started = now
                    if self._audit_logger is not None:
                        metadata: dict[str, Any] = {
                            "agent_id": member.agent_id,
                            "silence_elapsed": round(member.silence_elapsed, 1),
                            "silence_timeout": member.silence_timeout,
                        }
                        entry = self._audit_logger.log(
                            event_type="federation_member_suspected",
                            actor="FederationHealthMonitor",
                            action="mark_suspected",
                            details=f"Agent {member.agent_id} silent for {member.silence_elapsed:.1f}s "
                            f"(timeout {member.silence_timeout}s)",
                            metadata=metadata,
                        )
                        metadata["audit_entry_id"] = entry.id
                        metadata["audit_entry_signer"] = entry.signer_fingerprint

                member.trust_penalty = min(
                    100.0,
                    member.trust_penalty + self._trust_decay,
                )
                self._signal_cascade_failure(member.agent_id)
                details.append(member.to_dict())

        silent_count = sum(1 for m in self._members.values() if m.is_silent)
        suspected_count = sum(1 for m in self._members.values() if m.suspected)

        return HealthCheckResult(
            checked=len(self._members),
            silent=silent_count,
            suspected=suspected_count,
            details=details,
        )

    def get_applied_penalties(self) -> dict[str, float]:
        return {mid: m.trust_penalty for mid, m in self._members.items() if m.trust_penalty > 0}

    def member_snapshots(self) -> dict[str, dict[str, Any]]:
        """Return every tracked member's health snapshot keyed by agent id.

        Used by the Phase 3.1 membership layer to expose the node
        membership table (heartbeat-tracked servers) to operators.
        """
        return {mid: m.to_dict() for mid, m in self._members.items()}

    def summary(self) -> dict[str, Any]:
        return {
            "total_members": len(self._members),
            "active": sum(1 for m in self._members.values() if not m.suspected),
            "suspected": sum(1 for m in self._members.values() if m.suspected),
            "silent": sum(1 for m in self._members.values() if m.is_silent),
            "silence_timeout": self._silence_timeout,
            "trust_decay_per_cycle": self._trust_decay,
            "last_check_time": self._last_check_time,
        }

    # ── Cascade breaker linkage ──────────────────────────────────────────

    def _signal_cascade_failure(self, agent_id: str) -> None:
        """Feed a silent member into the cascade breaker.

        Called once per ``check()`` cycle while the member stays silent, so
        sustained silence accumulates consecutive failures and eventually
        isolates the agent (and degrades its dependents). Never raises.
        """
        breaker = self._cascade_breaker
        if breaker is None:
            return
        try:
            breaker.record_failure(agent_id, reason="health_monitor_silence")
        except Exception:
            return

    def _signal_cascade_recovery(self, agent_id: str) -> None:
        """Signal that a previously-suspected member has recovered.

        Permits a half-open probe first (``can_proceed``), then completes
        the recovery (``record_success``) so degraded dependents are
        un-degraded exactly. Never raises.
        """
        breaker = self._cascade_breaker
        if breaker is None:
            return
        try:
            if hasattr(breaker, "can_proceed"):
                breaker.can_proceed(agent_id)
            breaker.record_success(agent_id)
        except Exception:
            return


__all__ = [
    "FederationHealthMonitor",
    "MemberHealth",
    "HealthCheckResult",
    "DEFAULT_SILENCE_TIMEOUT",
    "DEFAULT_TRUST_DECAY_PER_CYCLE",
    "DEFAULT_CHECK_INTERVAL",
]
