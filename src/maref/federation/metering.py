"""MAREF Federated Task Metering Engine

Records per-task execution metrics across organizational boundaries and
computes agent contribution scores for multi-agent collaborations.

This is the federation-level metering layer that feeds into the
cross-org settlement protocol.  It complements (but does not replace)
the tenant-scoped :class:`maref.gaas.billing.BillingService`, which
tracks per-tenant resource usage for quota enforcement.

References:
    - Plan §7 Phase 3: 任务计量引擎 ``metering.py``
    - Plan §4.2 workflow step 12: 任务计量
    - Existing pattern: :mod:`maref.gaas.billing`
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.db import DatabaseManager


@dataclass(frozen=True)
class TaskMetric:
    """A single task execution metric record.

    Captures the information needed to compute cross-org billing and
    agent contribution.  ``provider_org`` is the organization that owns
    the agent; ``consumer_org`` is the organization that requested the
    task.
    """

    metric_id: str
    task_id: str
    agent_did: str
    agent_aic: str
    provider_org: str
    consumer_org: str
    duration_ms: float
    token_count: int
    success: bool
    complexity_score: float
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    caller_did: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "task_id": self.task_id,
            "agent_did": self.agent_did,
            "agent_aic": self.agent_aic,
            "provider_org": self.provider_org,
            "consumer_org": self.consumer_org,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "success": self.success,
            "complexity_score": self.complexity_score,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "caller_did": self.caller_did,
        }


@dataclass(frozen=True)
class ContributionScore:
    """Computed contribution of a single agent within a multi-agent task.

    ``contribution`` is normalised to ``[0.0, 1.0]`` and represents the
    agent's share of the total task work.  ``weight`` is the raw weighted
    score before normalisation.
    """

    task_id: str
    agent_did: str
    contribution: float
    weight: float
    factors: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_did": self.agent_did,
            "contribution": round(self.contribution, 4),
            "weight": round(self.weight, 4),
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
        }


# Contribution weights — sum to 1.0.
_CONTRIBUTION_WEIGHTS: dict[str, float] = {
    "duration": 0.30,   # longer work = more contribution
    "tokens": 0.25,     # more tokens processed = more contribution
    "complexity": 0.30, # higher complexity = more contribution
    "success": 0.15,    # successful completion bonus
}


class TaskMeteringEngine:
    """Records task metrics and computes contribution scores.

    The engine is deliberately storage-agnostic: it keeps an in-memory
    list of metrics.  Production deployments should plug in a persistent
    backend by subclassing and overriding :meth:`_persist`.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db: DatabaseManager | None = None
        self._metrics: list[TaskMetric] = []
        self._index_by_task: dict[str, list[int]] = {}
        self._index_by_org: dict[str, list[int]] = {}
        self._index_by_metric_id: dict[str, int] = {}
        if db_path is not None:
            self._db = DatabaseManager(db_path)
            self._init_schema()
            self._load_from_disk()

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_metrics (
                metric_id        TEXT PRIMARY KEY,
                task_id          TEXT NOT NULL,
                agent_did        TEXT NOT NULL,
                agent_aic        TEXT NOT NULL,
                provider_org     TEXT NOT NULL,
                consumer_org     TEXT NOT NULL,
                duration_ms      REAL NOT NULL,
                token_count      INTEGER NOT NULL,
                success          INTEGER NOT NULL,
                complexity_score REAL NOT NULL,
                timestamp        REAL NOT NULL,
                metadata         TEXT NOT NULL,
                caller_did       TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_task
                ON task_metrics(task_id);
            CREATE INDEX IF NOT EXISTS idx_metrics_org
                ON task_metrics(provider_org, consumer_org);
            """
        )

    def _load_from_disk(self) -> None:
        assert self._db is not None
        rows = self._db.fetchall("SELECT * FROM task_metrics ORDER BY timestamp")
        for row in rows:
            metric = TaskMetric(
                metric_id=row["metric_id"],
                task_id=row["task_id"],
                agent_did=row["agent_did"],
                agent_aic=row["agent_aic"],
                provider_org=row["provider_org"],
                consumer_org=row["consumer_org"],
                duration_ms=row["duration_ms"],
                token_count=row["token_count"],
                success=bool(row["success"]),
                complexity_score=row["complexity_score"],
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]),
                caller_did=row.get("caller_did", ""),  # type: ignore[attr-defined]
            )
            idx = len(self._metrics)
            self._metrics.append(metric)
            self._index_by_task.setdefault(metric.task_id, []).append(idx)
            self._index_by_org.setdefault(metric.provider_org, []).append(idx)
            if metric.consumer_org != metric.provider_org:
                self._index_by_org.setdefault(metric.consumer_org, []).append(idx)
            self._index_by_metric_id[metric.metric_id] = idx

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        task_id: str,
        agent_did: str,
        agent_aic: str,
        provider_org: str,
        consumer_org: str,
        duration_ms: float,
        token_count: int,
        success: bool,
        complexity_score: float,
        metadata: dict[str, Any] | None = None,
        caller_did: str = "",
    ) -> TaskMetric:
        """Record a single task execution metric.

        ``complexity_score`` is clamped to ``[0.0, 1.0]``.

        ``caller_did`` binds the metric to the identity that submitted it
        (v0.47 S5 source binding).  Defaults to "" for backward
        compatibility with existing callers.
        """
        complexity = max(0.0, min(1.0, complexity_score))
        metric = TaskMetric(
            metric_id=f"met_{uuid.uuid4().hex}",
            task_id=task_id,
            agent_did=agent_did,
            agent_aic=agent_aic,
            provider_org=provider_org,
            consumer_org=consumer_org,
            duration_ms=max(0.0, duration_ms),
            token_count=max(0, token_count),
            success=success,
            complexity_score=complexity,
            metadata=metadata or {},
            caller_did=caller_did,
        )
        idx = len(self._metrics)
        self._metrics.append(metric)
        self._index_by_task.setdefault(task_id, []).append(idx)
        # Index by both provider and consumer org for efficient lookup.
        self._index_by_org.setdefault(provider_org, []).append(idx)
        if consumer_org != provider_org:
            self._index_by_org.setdefault(consumer_org, []).append(idx)
        self._index_by_metric_id[metric.metric_id] = idx
        self._persist(metric)
        return metric

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_task_metrics(self, task_id: str) -> list[TaskMetric]:
        """Return all metrics recorded for a given task."""
        indices = self._index_by_task.get(task_id, [])
        return [self._metrics[i] for i in indices]

    def get_org_metrics(
        self, org: str, since: float | None = None
    ) -> list[TaskMetric]:
        """Return all metrics involving ``org`` (as provider or consumer).

        If ``since`` is given, only metrics at or after that timestamp
        are returned.
        """
        indices = self._index_by_org.get(org, [])
        metrics = [self._metrics[i] for i in indices]
        if since is not None:
            metrics = [m for m in metrics if m.timestamp >= since]
        return metrics

    def get_metric(self, metric_id: str) -> TaskMetric | None:
        """Look up a single metric by ID (O(1) via index)."""
        idx = self._index_by_metric_id.get(metric_id)
        if idx is None:
            return None
        return self._metrics[idx]

    def iter_all_metrics(self) -> list[TaskMetric]:
        """Return all recorded metrics as a list.

        Exposed as the public iteration API so downstream consumers
        (e.g. :class:`~maref.federation.settlement.FederatedSettlement`)
        do not need to reach into private attributes.
        """
        return list(self._metrics)

    @property
    def metric_count(self) -> int:
        return len(self._metrics)

    @property
    def task_count(self) -> int:
        return len(self._index_by_task)

    # ------------------------------------------------------------------
    # Contribution scoring
    # ------------------------------------------------------------------

    def compute_contribution(self, task_id: str) -> list[ContributionScore]:
        """Compute each agent's contribution share for a multi-agent task.

        Returns a list of :class:`ContributionScore` sorted by
        contribution descending.  If only one agent participated, its
        contribution is 1.0.
        """
        metrics = self.get_task_metrics(task_id)
        if not metrics:
            return []

        # Aggregate per agent (an agent may have multiple sub-metrics).
        per_agent: dict[str, list[TaskMetric]] = {}
        for m in metrics:
            per_agent.setdefault(m.agent_did, []).append(m)

        raw_weights: dict[str, float] = {}
        factor_breakdown: dict[str, dict[str, float]] = {}

        for did, agent_metrics in per_agent.items():
            total_duration = sum(m.duration_ms for m in agent_metrics)
            total_tokens = sum(m.token_count for m in agent_metrics)
            avg_complexity = sum(m.complexity_score for m in agent_metrics) / len(agent_metrics)
            any_success = any(m.success for m in agent_metrics)

            # Normalise each factor to [0, 1] relative to the task's max.
            factors_raw = {
                "duration": total_duration,
                "tokens": float(total_tokens),
                "complexity": avg_complexity,
                "success": 1.0 if any_success else 0.0,
            }
            factor_breakdown[did] = factors_raw
            raw_weights[did] = sum(
                factors_raw[f] * _CONTRIBUTION_WEIGHTS[f] for f in factors_raw
            )

        # Normalise weights so they sum to 1.0 across all agents.
        total_weight = sum(raw_weights.values())
        scores: list[ContributionScore] = []
        for did, weight in raw_weights.items():
            contribution = weight / total_weight if total_weight > 0 else 0.0
            scores.append(
                ContributionScore(
                    task_id=task_id,
                    agent_did=did,
                    contribution=contribution,
                    weight=weight,
                    factors=factor_breakdown[did],
                )
            )

        scores.sort(key=lambda s: -s.contribution)
        return scores

    # ------------------------------------------------------------------
    # Usage summaries
    # ------------------------------------------------------------------

    def generate_usage_summary(
        self, org: str, period_start: float, period_end: float
    ) -> dict[str, Any]:
        """Generate a usage summary for an org within a billing period.

        Returns a dict with total metrics, success rate, total duration,
        total tokens, and per-task breakdown — separated by whether the
        org was provider or consumer.
        """
        metrics = [
            m
            for m in self.get_org_metrics(org)
            if period_start <= m.timestamp <= period_end
        ]

        provided = [m for m in metrics if m.provider_org == org]
        consumed = [m for m in metrics if m.consumer_org == org]

        def _summary(items: list[TaskMetric]) -> dict[str, Any]:
            if not items:
                return {
                    "count": 0,
                    "success_count": 0,
                    "success_rate": 0.0,
                    "total_duration_ms": 0.0,
                    "total_tokens": 0,
                    "unique_tasks": 0,
                    "unique_agents": 0,
                }
            return {
                "count": len(items),
                "success_count": sum(1 for m in items if m.success),
                "success_rate": round(sum(1 for m in items if m.success) / len(items), 4),
                "total_duration_ms": round(sum(m.duration_ms for m in items), 2),
                "total_tokens": sum(m.token_count for m in items),
                "unique_tasks": len({m.task_id for m in items}),
                "unique_agents": len({m.agent_did for m in items}),
            }

        return {
            "org": org,
            "period_start": period_start,
            "period_end": period_end,
            "as_provider": _summary(provided),
            "as_consumer": _summary(consumed),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def metering_summary(self) -> dict[str, Any]:
        """Return a global summary of the metering engine state."""
        all_orgs = set(self._index_by_org.keys())
        return {
            "total_metrics": self.metric_count,
            "total_tasks": self.task_count,
            "total_orgs": len(all_orgs),
            "orgs": sorted(all_orgs),
        }

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def _persist(self, metric: TaskMetric) -> None:
        """Persist a metric to the SQLite backend.  No-op in memory mode."""
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO task_metrics "
            "(metric_id, task_id, agent_did, agent_aic, provider_org, "
            "consumer_org, duration_ms, token_count, success, "
            "complexity_score, timestamp, metadata, caller_did) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.metric_id,
                metric.task_id,
                metric.agent_did,
                metric.agent_aic,
                metric.provider_org,
                metric.consumer_org,
                metric.duration_ms,
                metric.token_count,
                int(metric.success),
                metric.complexity_score,
                metric.timestamp,
                json.dumps(metric.metadata),
                metric.caller_did,
            ),
        )
