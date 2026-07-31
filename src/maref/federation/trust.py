"""Federated Trust Engine.

Extends :class:`~maref.recursive.trust_engine_v2.TrustEngineV2` with
cross-organization trust propagation: trust scores from peer federation
servers are aggregated with local scores using a weighted, decay-based
scheme that respects organizational sovereignty.

Key concepts:
- **Local trust**: computed by the local :class:`TrustEngineV2`.
- **Federated trust**: weighted aggregate of peer-reported trust scores.
- **Effective trust**: ``alpha * local + (1 - alpha) * federated``, where
  ``alpha`` is the local sovereignty weight (default 0.6).
- **Trust decay**: peer reports older than ``trust_freshness_seconds``
  are discounted.

Reference: AIP-ACPs-Technical-Analysis.md section 4.3 (Federated Trust).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from math import exp
from typing import Any

from maref.federation.trust_hardening import (
    SybilTrustGuard,
    byzantine_robust_aggregate,
)
from maref.recursive.trust_engine_v2 import TrustEngineV2

# Default local sovereignty weight: 60% local, 40% federated.
DEFAULT_LOCAL_WEIGHT = 0.6

# Trust report freshness: 1 hour (reports older than this are discounted).
DEFAULT_TRUST_FRESHNESS = 3600.0

# Minimum number of peer reports required for federated aggregation.
DEFAULT_MIN_PEER_REPORTS = 1

# Maximum trust penalty for stale reports (applied multiplicatively).
DEFAULT_STALENESS_PENALTY = 0.5


@dataclass
class PeerTrustReport:
    """A trust score reported by a peer federation server.

    Attributes:
        agent_id: The agent the report concerns (DID string).
        source_server: The peer server that issued the report.
        trust_score: Reported trust score (0.0-100.0).
        tier: Reported trust tier (e.g. "AAA", "BB").
        timestamp: When the peer issued the report.
        confidence: Peer's own confidence in the score (0.0-1.0).
    """

    agent_id: str
    source_server: str
    trust_score: float
    tier: str = "B"
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "source_server": self.source_server,
            "trust_score": self.trust_score,
            "tier": self.tier,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }

    def freshness(self, now: float | None = None) -> float:
        """Return a freshness factor in [0, 1] (1 = fresh, 0 = stale)."""
        now = now if now is not None else time.time()
        age = max(0.0, now - self.timestamp)
        return exp(-age / DEFAULT_TRUST_FRESHNESS)


@dataclass
class FederatedTrustScore:
    """Aggregated trust score combining local and federated inputs.

    Attributes:
        agent_id: The agent this score concerns.
        local_score: Local trust score (or None if not assessed locally).
        federated_score: Aggregated peer trust score (or None if no reports).
        effective_score: Final weighted score.
        local_weight: Weight given to local score (alpha).
        peer_reports: List of contributing peer reports.
        confidence: Aggregate confidence in the effective score.
    """

    agent_id: str
    local_score: float | None = None
    federated_score: float | None = None
    effective_score: float = 0.0
    local_weight: float = DEFAULT_LOCAL_WEIGHT
    peer_reports: list[PeerTrustReport] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "local_score": self.local_score,
            "federated_score": self.federated_score,
            "effective_score": round(self.effective_score, 2),
            "local_weight": self.local_weight,
            "peer_report_count": len(self.peer_reports),
            "peer_sources": [r.source_server for r in self.peer_reports],
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
        }


class FederatedTrustEngine:
    """Cross-organization trust aggregation engine.

    Wraps a local :class:`TrustEngineV2` and aggregates its scores with
    peer-reported trust scores. Local scores always take precedence
    (controlled by ``local_weight``); peer scores fill gaps and provide
    cross-organizational context.

    Usage:
        local_engine = TrustEngineV2()
        fed_engine = FederatedTrustEngine(local_engine=local_engine)
        fed_engine.submit_peer_report(report)
        score = fed_engine.assess("did:maref:federated:abc123")
    """

    def __init__(
        self,
        local_engine: TrustEngineV2,
        local_weight: float = DEFAULT_LOCAL_WEIGHT,
        trust_freshness: float = DEFAULT_TRUST_FRESHNESS,
        min_peer_reports: int = DEFAULT_MIN_PEER_REPORTS,
        robust_aggregation: bool = True,
        sybil_guard: SybilTrustGuard | None = None,
    ) -> None:
        """Initialize the federated trust engine.

        Args:
            local_engine: The local :class:`TrustEngineV2` instance.
            local_weight: Weight given to local scores (``alpha``).
            trust_freshness: Seconds before a report is considered stale.
            min_peer_reports: Minimum reports (after Sybil filtering) for
                federated aggregation.
            robust_aggregation: When True (default), peer reports are
                aggregated with a Byzantine-robust scheme (weighted median
                + MAD outlier rejection) instead of a plain weighted mean.
            sybil_guard: Optional :class:`SybilTrustGuard` enabling source
                reputation (cold start + penalty/reward) for Sybil defense.
        """
        self._local = local_engine
        self._local_weight = max(0.0, min(1.0, local_weight))
        self._freshness = trust_freshness
        self._min_peer_reports = max(1, min_peer_reports)
        self._robust_aggregation = robust_aggregation
        self._sybil_guard = sybil_guard
        # agent_id → list of peer reports.
        self._peer_reports: dict[str, list[PeerTrustReport]] = {}
        # agent_id → last computed federated score.
        self._federated_scores: dict[str, FederatedTrustScore] = {}

    @property
    def local_engine(self) -> TrustEngineV2:
        return self._local

    @property
    def local_weight(self) -> float:
        return self._local_weight

    @property
    def sybil_guard(self) -> SybilTrustGuard | None:
        return self._sybil_guard

    def submit_peer_report(self, report: PeerTrustReport) -> None:
        """Submit a trust score report from a peer federation server.

        Args:
            report: The peer trust report.
        """
        if self._sybil_guard is not None:
            # Observe the source so it is tracked with cold-start reputation.
            self._sybil_guard.register_source(report.source_server)
        reports = self._peer_reports.setdefault(report.agent_id, [])
        # Replace any existing report from the same source.
        reports = [r for r in reports if r.source_server != report.source_server]
        reports.append(report)
        # Keep only the most recent 10 reports per agent.  When Sybil
        # defense is active, established (eligible) sources are never
        # evicted by a flood of fresh identities — otherwise an attacker
        # could push honest reports out of the window.
        if len(reports) > 10:
            if self._sybil_guard is not None:
                eligible = [r for r in reports if self._sybil_guard.is_eligible(r.source_server)]
                ineligible = sorted(
                    (r for r in reports if r not in eligible),
                    key=lambda r: r.timestamp,
                    reverse=True,
                )
                reports = eligible[:10]
                if len(reports) < 10:
                    reports += ineligible[: 10 - len(reports)]
            else:
                reports = sorted(reports, key=lambda r: r.timestamp, reverse=True)[:10]
        self._peer_reports[report.agent_id] = reports

    def submit_peer_reports(self, reports: list[PeerTrustReport]) -> None:
        """Submit multiple peer reports at once."""
        for report in reports:
            self.submit_peer_report(report)

    def get_peer_reports(self, agent_id: str) -> list[PeerTrustReport]:
        """Return all peer reports for an agent."""
        return list(self._peer_reports.get(agent_id, []))

    def clear_peer_reports(self, agent_id: str | None = None) -> int:
        """Clear peer reports.

        Args:
            agent_id: If provided, clear only reports for this agent.
                If None, clear all peer reports.

        Returns:
            The number of reports cleared.
        """
        if agent_id is None:
            count = sum(len(v) for v in self._peer_reports.values())
            self._peer_reports.clear()
            self._federated_scores.clear()
            return count
        reports = self._peer_reports.pop(agent_id, [])
        self._federated_scores.pop(agent_id, None)
        return len(reports)

    def assess(self, agent_id: str) -> FederatedTrustScore:
        """Compute the federated trust score for an agent.

        Falls back to local-only or federated-only scoring when one
        source is unavailable.

        Args:
            agent_id: The agent's DID string.

        Returns:
            A :class:`FederatedTrustScore` combining local and federated inputs.
        """
        local_score = self._local.get_score(agent_id)
        local_value: float | None = local_score.overall_trust if local_score is not None else None

        peer_reports = self._peer_reports.get(agent_id, [])
        federated_value, federated_confidence = self._aggregate_peer_reports(peer_reports)

        # Compute effective score based on available inputs.
        if local_value is not None and federated_value is not None:
            effective = (
                self._local_weight * local_value + (1.0 - self._local_weight) * federated_value
            )
            confidence = (
                self._local_weight * 1.0 + (1.0 - self._local_weight) * federated_confidence
            )
        elif local_value is not None:
            effective = local_value
            confidence = 1.0
        elif federated_value is not None:
            effective = federated_value
            confidence = federated_confidence
        else:
            effective = 0.0
            confidence = 0.0

        score = FederatedTrustScore(
            agent_id=agent_id,
            local_score=local_value,
            federated_score=federated_value,
            effective_score=max(0.0, min(100.0, effective)),
            local_weight=self._local_weight,
            peer_reports=peer_reports,
            confidence=confidence,
        )
        self._federated_scores[agent_id] = score
        return score

    def _aggregate_peer_reports(self, reports: list[PeerTrustReport]) -> tuple[float | None, float]:
        """Aggregate peer trust reports into a single score.

        Uses a Byzantine-robust aggregation by default (weighted median +
        MAD outlier rejection, then a confidence-weighted mean over the
        survivors).  When a :class:`SybilTrustGuard` is attached, only
        sources whose reputation clears the eligibility threshold
        participate, and outlier sources are penalized.

        Returns:
            (aggregated_score, confidence) — score is None if no reports
            meet the minimum threshold.
        """
        valid_reports = [r for r in reports if r.confidence > 0]
        if len(valid_reports) < self._min_peer_reports:
            return None, 0.0

        guard = self._sybil_guard
        if guard is not None:
            eligible = [r for r in valid_reports if guard.is_eligible(r.source_server)]
        else:
            eligible = valid_reports
        if len(eligible) < self._min_peer_reports:
            return None, 0.0

        now = time.time()

        def weight_of(report: PeerTrustReport) -> float:
            weight = report.confidence * report.freshness(now)
            if guard is not None:
                weight *= guard.source_trust(report.source_server)
            return weight

        if self._robust_aggregation:
            score, survivors, outliers = byzantine_robust_aggregate(eligible, weight_of)
            if guard is not None and outliers:
                guard.apply_outcome(
                    agent_id=eligible[0].agent_id,
                    eligible_reports=eligible,
                    survivors=survivors,
                    robust_score=score,
                )
        else:
            total_weight = 0.0
            weighted_sum = 0.0
            for report in eligible:
                weight = weight_of(report)
                weighted_sum += report.trust_score * weight
                total_weight += weight
            if total_weight <= 0:
                return None, 0.0
            score = weighted_sum / total_weight

        # Confidence: average of eligible peer confidences, scaled by coverage.
        avg_confidence = sum(r.confidence for r in eligible) / len(eligible)
        # Penalize if fewer reports than ideal (5+).
        coverage = min(1.0, len(eligible) / 5.0)
        return score, avg_confidence * coverage

    def get_score(self, agent_id: str) -> FederatedTrustScore | None:
        """Return the last computed federated score, or None."""
        return self._federated_scores.get(agent_id)

    def list_agents_with_peer_reports(self) -> list[str]:
        """List agent IDs that have at least one peer trust report."""
        return list(self._peer_reports.keys())

    def federated_summary(self) -> dict[str, Any]:
        """Return a summary of the federated trust state."""
        total_reports = sum(len(v) for v in self._peer_reports.values())
        agents_with_reports = len(self._peer_reports)
        local_agents = self._local.agent_count
        return {
            "local_agent_count": local_agents,
            "agents_with_peer_reports": agents_with_reports,
            "total_peer_reports": total_reports,
            "local_weight": self._local_weight,
            "min_peer_reports": self._min_peer_reports,
            "trust_freshness": self._freshness,
            "robust_aggregation": self._robust_aggregation,
            "sybil_guard_enabled": self._sybil_guard is not None,
            "sybil_guard": self._sybil_guard.summary() if self._sybil_guard else None,
        }


__all__ = [
    "DEFAULT_LOCAL_WEIGHT",
    "DEFAULT_TRUST_FRESHNESS",
    "DEFAULT_MIN_PEER_REPORTS",
    "DEFAULT_STALENESS_PENALTY",
    "FederatedTrustEngine",
    "FederatedTrustScore",
    "PeerTrustReport",
]
