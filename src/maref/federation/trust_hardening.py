"""Cross-domain trust hardening — Sybil defense + Byzantine-robust aggregation.

Phase 3.3 hardens :class:`~maref.federation.trust.FederatedTrustEngine`
against adversarial peer reports:

- **Byzantine-robust aggregation**: instead of a plain confidence-weighted
  mean (which a single extreme report can skew arbitrarily), reports are
  aggregated with a weighted-median + MAD-outlier-rejection scheme.  The
  median is reliable while fewer than half the reports are malicious.
- **Sybil defense** (:class:`SybilTrustGuard`): every reporting *source*
  (peer server) carries a reputation that starts at a low cold-start value
  and only grows through sustained honest participation.  Sources below the
  eligibility threshold are excluded from aggregation, so an attacker
  flooding the network with fresh identities cannot sway the score.
- **Penalty/reward loop**: sources whose reports are repeatedly rejected as
  outliers lose reputation; surviving sources gain it.

The guard deliberately does not import :mod:`maref.federation.trust` to
avoid a circular import — it only relies on report objects exposing
``trust_score``, ``source_server``, ``confidence`` and ``timestamp``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Cold-start reputation of a newly observed reporting source.
COLD_START_SOURCE_TRUST = 0.3

# Sources below this reputation are excluded from aggregation.
DEFAULT_ELIGIBILITY_THRESHOLD = 0.5

# Minimum absolute score deviation before a report counts as an outlier
# (guards against MAD == 0 over-triggering on tightly clustered honest reports).
DEFAULT_MIN_DEVIATION = 15.0

# Median absolute deviation scale factor (1.4826 ≈ 1σ for normal data).
MAD_SCALE = 1.4826

# Lower bound for source reputation (persistent misbehaviour bottoms out here).
SOURCE_TRUST_FLOOR = 0.05

# Multiplicative factors for the penalty/reward loop.
PENALTY_FACTOR = 0.5
REWARD_FACTOR = 2.0


# ── Peer trust report signing (v0.47 S4) ─────────────────────────────────


def peer_report_payload(report: Any) -> bytes:
    """Return the canonical bytes a trust report is signed over.

    The payload covers every field that is meaningful to the recipient so
    a tampered score / source / tier invalidates the signature:

    ``agent_id\\nsource_server\\ntrust_score\\ntier\\ntimestamp\\nconfidence``

    Field order and formatting must never change after release — any
    change breaks verification of previously issued reports.
    """
    return (
        f"{report.agent_id}\n"
        f"{report.source_server}\n"
        f"{report.trust_score!r}\n"
        f"{report.tier}\n"
        f"{report.timestamp!r}\n"
        f"{report.confidence!r}"
    ).encode()


def sign_peer_report(report: Any, signing_key: Any, key_id: str) -> Any:
    """Sign a peer trust report in place and return it.

    Args:
        report: A :class:`~maref.federation.trust.PeerTrustReport` (or a
            report-like object exposing the canonical fields plus mutable
            ``signature`` / ``signer_key_id`` attributes).
        signing_key: A :class:`~maref.signing.signing_key.ReportSigningKey`.
        key_id: Identifier the recipient uses to look up the public key
            (usually the source server id).

    Returns:
        The same report with ``signature`` and ``signer_key_id`` set.
    """
    payload = peer_report_payload(report)
    report.signature = signing_key.sign_report(payload)
    report.signer_key_id = key_id
    return report


def verify_report_signature(
    report: Any,
    trusted_public_keys: Mapping[str, str],
) -> bool:
    """Verify a peer trust report's signature against trusted keys.

    Args:
        report: The submitted report carrying ``signature`` and
            ``signer_key_id``.
        trusted_public_keys: Mapping of ``key_id`` → Ed25519 public key PEM
            for the peer servers this engine trusts.

    Returns:
        True only if the report is signed by a trusted key over the exact
        canonical payload.  Never raises.
    """
    signature = getattr(report, "signature", "")
    key_id = getattr(report, "signer_key_id", "") or getattr(report, "source_server", "")
    if not signature or not key_id:
        return False
    public_key_pem = trusted_public_keys.get(key_id)
    if public_key_pem is None:
        return False
    from maref.signing.signing_key import ReportSigningKey

    return ReportSigningKey.verify_signature(
        public_key_pem,
        signature,
        peer_report_payload(report),
    )


@dataclass
class SourceReputation:
    """Ongoing reputation state of a reporting source (peer server).

    Attributes:
        source_server: Peer server identifier.
        trust: Current reputation in ``[SOURCE_TRUST_FLOOR, 1.0]``.
        penalties: Number of times this source was flagged as anomalous.
        rewards: Number of times this source survived aggregation.
        first_seen: Unix timestamp of first observed report.
        last_seen: Unix timestamp of most recent observed report.
    """

    source_server: str
    trust: float = COLD_START_SOURCE_TRUST
    penalties: int = 0
    rewards: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_server": self.source_server,
            "trust": round(self.trust, 3),
            "penalties": self.penalties,
            "rewards": self.rewards,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass
class AnomalyRecord:
    """A single detected anomalous report (kept for auditability)."""

    agent_id: str
    source_server: str
    reported_score: float
    robust_score: float
    deviation: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "source_server": self.source_server,
            "reported_score": round(self.reported_score, 2),
            "robust_score": round(self.robust_score, 2),
            "deviation": round(self.deviation, 2),
            "timestamp": self.timestamp,
        }


def byzantine_robust_aggregate(
    reports: list[Any],
    weight_of: Callable[[Any], float],
    mad_scale: float = MAD_SCALE,
    min_deviation: float = DEFAULT_MIN_DEVIATION,
) -> tuple[float, list[Any], list[Any]]:
    """Aggregate trust reports with Byzantine-robust statistics.

    Pipeline:
        1. Weighted median (reliable while <50% of *weight* is malicious).
        2. Median absolute deviation (MAD) of scores around the median.
        3. Reject reports farther than ``max(mad_scale * MAD, min_deviation)``
           from the median.
        4. Confidence-weighted mean over the surviving reports.

    Args:
        reports: Non-empty list of report-like objects exposing
            ``trust_score``.
        weight_of: Callable returning a report's aggregation weight
            (e.g. confidence × freshness × source reputation).
        mad_scale: MAD multiplier for the outlier cutoff.
        min_deviation: Floor on the outlier cutoff, so a MAD of 0 (all
            identical honest reports) does not discard anything.

    Returns:
        ``(aggregated_score, survivors, outliers)``.
    """
    if not reports:
        raise ValueError("reports must not be empty")

    weights = [max(0.0, weight_of(r)) for r in reports]
    if sum(weights) <= 0:
        weights = [1.0] * len(reports)

    # ── Step 1: weighted median ──────────────────────────────────────
    ordered = sorted(
        zip(reports, weights, strict=True),
        key=lambda rw: rw[0].trust_score,
    )
    total_weight = sum(weights)
    accumulated = 0.0
    median_score = ordered[-1][0].trust_score
    for report, weight in ordered:
        accumulated += weight
        if accumulated >= total_weight / 2:
            median_score = report.trust_score
            break

    # ── Step 2+3: MAD-based outlier rejection ────────────────────────
    deviations = [abs(r.trust_score - median_score) for r in reports]
    sorted_deviations = sorted(deviations)
    # Lower median — for even-sized lists this keeps the cutoff small,
    # so a genuine minority of extreme outliers is still rejected.
    mad = sorted_deviations[(len(sorted_deviations) - 1) // 2]
    cutoff = max(mad_scale * mad, min_deviation)

    survivors = [r for r in reports if abs(r.trust_score - median_score) <= cutoff]
    if not survivors:
        # Degenerate case: everything was flagged. Keep the closest report.
        survivors = [min(reports, key=lambda r: abs(r.trust_score - median_score))]
    outlier_set = [r for r in reports if r not in survivors]

    # ── Step 4: weighted mean over survivors ──────────────────────────
    survivor_weights = [max(0.0, weight_of(r)) for r in survivors]
    if sum(survivor_weights) <= 0:
        survivor_weights = [1.0] * len(survivors)
    score = sum(r.trust_score * w for r, w in zip(survivors, survivor_weights, strict=True)) / sum(
        survivor_weights
    )

    return score, survivors, outlier_set


class SybilTrustGuard:
    """Source-reputation Sybil defense for federated trust reports.

    Each reporting source starts with a cold-start reputation and must
    earn its way above :attr:`eligibility_threshold` through sustained
    honest participation.  Fresh attacker identities therefore never get
    a vote; established sources that begin reporting anomalies lose
    reputation and drop out of aggregation.
    """

    def __init__(
        self,
        cold_start_trust: float = COLD_START_SOURCE_TRUST,
        eligibility_threshold: float = DEFAULT_ELIGIBILITY_THRESHOLD,
        min_deviation: float = DEFAULT_MIN_DEVIATION,
        penalty_factor: float = PENALTY_FACTOR,
        reward_factor: float = REWARD_FACTOR,
        trust_floor: float = SOURCE_TRUST_FLOOR,
        anomaly_cap: int = 50,
    ) -> None:
        self._cold_start = max(0.0, min(1.0, cold_start_trust))
        self._eligibility = max(0.0, min(1.0, eligibility_threshold))
        self._min_deviation = min_deviation
        self._penalty_factor = max(0.0, min(1.0, penalty_factor))
        self._reward_factor = max(1.0, reward_factor)
        self._trust_floor = max(0.0, min(1.0, trust_floor))
        self._sources: dict[str, SourceReputation] = {}
        self._anomalies: list[AnomalyRecord] = []
        self._anomaly_cap = max(1, anomaly_cap)

    # ── Source reputation ────────────────────────────────────────────

    def register_source(self, source_server: str) -> SourceReputation:
        """Observe a source; unknown sources get the cold-start reputation."""
        now = time.time()
        existing = self._sources.get(source_server)
        if existing is not None:
            existing.last_seen = now
            return existing
        reputation = SourceReputation(
            source_server=source_server,
            trust=self._cold_start,
            first_seen=now,
            last_seen=now,
        )
        self._sources[source_server] = reputation
        return reputation

    def source_trust(self, source_server: str) -> float:
        """Return the source's current reputation (registering it if new)."""
        return self.register_source(source_server).trust

    def is_eligible(self, source_server: str) -> bool:
        """Whether a source's reports may participate in aggregation."""
        return self.source_trust(source_server) >= self._eligibility

    def effective_weight(self, report: Any) -> float:
        """Aggregation weight for a report: confidence × source reputation.

        Freshness discounting is applied by the engine (it owns the
        freshness window); this guard only layers source reputation on top.
        """
        return report.confidence * self.source_trust(report.source_server)

    def penalize_source(self, source_server: str, reason: str = "") -> float:
        """Halve a source's reputation (floor at ``trust_floor``)."""
        reputation = self.register_source(source_server)
        reputation.trust = max(self._trust_floor, reputation.trust * self._penalty_factor)
        reputation.penalties += 1
        return reputation.trust

    def reward_source(self, source_server: str) -> float:
        """Double a source's reputation (capped at 1.0)."""
        reputation = self.register_source(source_server)
        reputation.trust = min(1.0, reputation.trust * self._reward_factor)
        reputation.rewards += 1
        return reputation.trust

    def apply_outcome(
        self,
        agent_id: str,
        eligible_reports: list[Any],
        survivors: list[Any],
        robust_score: float,
    ) -> dict[str, Any]:
        """Reward surviving sources and penalize outlier sources.

        Non-eligible sources are never rewarded (they stay in cold start),
        which is the core Sybil defense: fresh identities cannot bootstrap
        reputation without being accepted into an aggregation.

        Returns:
            Summary of applied outcomes: ``{penalized, rewarded}``.
        """
        survivor_sources = {r.source_server for r in survivors}
        outcome = {"penalized": [], "rewarded": []}
        for report in eligible_reports:
            source = report.source_server
            if source in survivor_sources:
                self.reward_source(source)
                outcome["rewarded"].append(source)
            else:
                deviation = abs(report.trust_score - robust_score)
                self._record_anomaly(
                    agent_id=agent_id,
                    source_server=source,
                    reported_score=report.trust_score,
                    robust_score=robust_score,
                    deviation=deviation,
                )
                self.penalize_source(source, reason="outlier report")
                outcome["penalized"].append(source)
        return outcome

    # ── Anomaly audit trail ──────────────────────────────────────────

    def _record_anomaly(
        self,
        agent_id: str,
        source_server: str,
        reported_score: float,
        robust_score: float,
        deviation: float,
    ) -> None:
        self._anomalies.append(
            AnomalyRecord(
                agent_id=agent_id,
                source_server=source_server,
                reported_score=reported_score,
                robust_score=robust_score,
                deviation=deviation,
            )
        )
        if len(self._anomalies) > self._anomaly_cap:
            self._anomalies = self._anomalies[-self._anomaly_cap :]

    def anomalies(self, source_server: str | None = None) -> list[AnomalyRecord]:
        """Recent anomaly records (optionally filtered by source)."""
        if source_server is None:
            return list(self._anomalies)
        return [a for a in self._anomalies if a.source_server == source_server]

    def penalized_sources(self) -> list[str]:
        """Sources that have been penalized at least once."""
        return sorted(s for s, r in self._sources.items() if r.penalties > 0)

    def summary(self) -> dict[str, Any]:
        """Summary of the guard's defensive state."""
        return {
            "sources_tracked": len(self._sources),
            "eligible_sources": sum(
                1 for r in self._sources.values() if r.trust >= self._eligibility
            ),
            "penalized_sources": len(self.penalized_sources()),
            "anomaly_count": len(self._anomalies),
            "cold_start_trust": self._cold_start,
            "eligibility_threshold": self._eligibility,
        }


__all__ = [
    "COLD_START_SOURCE_TRUST",
    "DEFAULT_ELIGIBILITY_THRESHOLD",
    "DEFAULT_MIN_DEVIATION",
    "MAD_SCALE",
    "SOURCE_TRUST_FLOOR",
    "PENALTY_FACTOR",
    "REWARD_FACTOR",
    "peer_report_payload",
    "sign_peer_report",
    "verify_report_signature",
    "SourceReputation",
    "AnomalyRecord",
    "byzantine_robust_aggregate",
    "SybilTrustGuard",
]
