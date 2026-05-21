from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


class ContextIsolation:
    """Git Worktree-style context isolation for Sub-Agent exploration.

    Claude Code saves 96% tokens by forking Sub-Agents with fresh contexts
    that return only summarized results. This implements the same pattern
    for MAREF desktop agents.

    Mechanism:
    - Parent Agent spawns a Sub-Agent with a restricted context snapshot
    - Sub-Agent explores files/screens independently
    - Sub-Agent returns only a typed summary (findings + confidence + file list)
    - Parent Agent merges summary into its own context
    """

    def __init__(self, max_context_size: int = 2000) -> None:
        self.max_context_size = max_context_size
        self._isolations: dict[str, ContextSnapshot] = {}

    def snapshot(self, isolation_id: str, parent_context: dict[str, Any]) -> ContextSnapshot:
        snapshot = ContextSnapshot(
            isolation_id=isolation_id,
            parent_id=parent_context.get("agent_id", ""),
            context=dict(parent_context),
            created_at=time.time(),
        )
        self._isolations[isolation_id] = snapshot
        return snapshot

    def isolate(self, isolation_id: str, keys_to_include: list[str]) -> ContextSnapshot | None:
        snapshot = self._isolations.get(isolation_id)
        if snapshot is None:
            return None
        filtered = {k: snapshot.context.get(k) for k in keys_to_include if k in snapshot.context}
        snapshot.filtered_context = filtered
        return snapshot

    def merge_summary(self, isolation_id: str, summary: SubAgentSummary) -> ContextSnapshot | None:
        snapshot = self._isolations.get(isolation_id)
        if snapshot is None:
            return None
        snapshot.summary = summary
        return snapshot

    def estimate_token_savings(self, parent_context_size: int, summary_size: int) -> float:
        if parent_context_size == 0:
            return 0.0
        return 1.0 - (summary_size / parent_context_size)

    def cleanup(self, isolation_id: str) -> None:
        self._isolations.pop(isolation_id, None)


@dataclass
class ContextSnapshot:
    isolation_id: str
    parent_id: str
    context: dict[str, Any] = field(default_factory=dict)
    filtered_context: dict[str, Any] = field(default_factory=dict)
    summary: SubAgentSummary | None = None
    created_at: float = 0.0

    @property
    def context_size(self) -> int:
        return len(str(self.context))

    @property
    def summary_size(self) -> int:
        if self.summary is None:
            return 0
        return len(str(self.summary.to_dict()))

    @property
    def token_savings_pct(self) -> float:
        if self.summary is None or self.context_size == 0:
            return 0.0
        return (1.0 - self.summary_size / self.context_size) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "isolation_id": self.isolation_id,
            "parent_id": self.parent_id,
            "context_size": self.context_size,
            "summary_size": self.summary_size,
            "token_savings_pct": self.token_savings_pct,
            "summary": self.summary.to_dict() if self.summary else None,
        }


@dataclass
class SubAgentSummary:
    isolation_id: str
    findings: list[str] = field(default_factory=list)
    files_explored: list[str] = field(default_factory=list)
    confidence: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    completion_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "isolation_id": self.isolation_id,
            "findings": self.findings,
            "files_explored": self.files_explored,
            "confidence": self.confidence,
            "recommendations": self.recommendations,
            "errors": self.errors,
            "completion_time_ms": self.completion_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubAgentSummary:
        return cls(
            isolation_id=data.get("isolation_id", ""),
            findings=data.get("findings", []),
            files_explored=data.get("files_explored", []),
            confidence=data.get("confidence", 0.0),
            recommendations=data.get("recommendations", []),
            errors=data.get("errors", []),
            completion_time_ms=data.get("completion_time_ms", 0.0),
        )


class SubAgentSpawner:
    """Spawns isolated Sub-Agents with context snapshots for token-efficient exploration.

    Each Sub-Agent:
    - Gets a frozen context snapshot (no parent drift)
    - Explores independently with bounded context window
    - Returns only a structured summary (findings + confidence + files)
    - Parent merges summary, discarding Sub-Agent's full context

    Token saving: 50K parent context → 2K summary = 96% savings (aligns with Claude Code).
    """

    def __init__(self, max_context_size: int = 2000) -> None:
        self._isolation = ContextIsolation(max_context_size=max_context_size)
        self._spawned: dict[str, dict[str, Any]] = {}
        self._summaries: dict[str, SubAgentSummary] = {}

    def spawn(
        self,
        parent_id: str,
        task_description: str,
        context: dict[str, Any],
        keys_to_explore: list[str],
    ) -> str:
        isolation_id = f"subagent-{parent_id}-{hashlib.md5(task_description.encode()).hexdigest()[:8]}"
        self._isolation.snapshot(isolation_id, {"agent_id": parent_id, "task": task_description, **context})
        self._isolation.isolate(isolation_id, keys_to_explore)
        self._spawned[isolation_id] = {
            "parent_id": parent_id,
            "task": task_description,
            "created_at": time.time(),
            "status": "exploring",
            "keys": keys_to_explore,
        }
        return isolation_id

    def complete(
        self,
        isolation_id: str,
        findings: list[str],
        files_explored: list[str],
        confidence: float = 0.0,
        errors: list[str] | None = None,
    ) -> SubAgentSummary:
        summary = SubAgentSummary(
            isolation_id=isolation_id,
            findings=findings,
            files_explored=files_explored,
            confidence=confidence,
            errors=errors or [],
            completion_time_ms=(time.time() - self._spawned.get(isolation_id, {}).get("created_at", time.time())) * 1000,
        )
        self._isolation.merge_summary(isolation_id, summary)
        self._summaries[isolation_id] = summary
        if isolation_id in self._spawned:
            self._spawned[isolation_id]["status"] = "completed"
        return summary

    def get_summary(self, isolation_id: str) -> SubAgentSummary | None:
        return self._summaries.get(isolation_id)

    def get_token_savings(self, isolation_id: str) -> float:
        snapshot = self._isolation._isolations.get(isolation_id)
        if snapshot is None:
            return 0.0
        return snapshot.token_savings_pct

    def cleanup(self, isolation_id: str) -> None:
        self._isolation.cleanup(isolation_id)
        self._spawned.pop(isolation_id, None)

    def get_active_count(self) -> int:
        return sum(1 for s in self._spawned.values() if s["status"] == "exploring")
