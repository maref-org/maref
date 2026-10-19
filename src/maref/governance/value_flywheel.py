"""Governance data flywheel: KPI collection, feedback, and tuning loop (P1-C).

The flywheel turns audit traffic into measurable governance outcomes and
feeds reviewer decisions back into policy tuning.  It intentionally works on
plain audit entries so it can be used by the sidecar, CLI, or tests without a
database.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.audit import AuditEntry


@dataclass
class GovernanceKPIs:
    decisions: int = 0
    allow: int = 0
    deny: int = 0
    ask_user: int = 0
    signed: int = 0
    deny_rate: float = 0.0
    hitl_rate: float = 0.0
    evidence_coverage: float = 0.0
    policy_versions: dict[str, int] = field(default_factory=dict)
    top_denied_actions: list[tuple[str, int]] = field(default_factory=list)
    top_deny_reasons: list[tuple[str, int]] = field(default_factory=list)
    deny_rate_trend: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["top_denied_actions"] = [list(item) for item in self.top_denied_actions]
        data["top_deny_reasons"] = [list(item) for item in self.top_deny_reasons]
        return data


@dataclass
class FlywheelReport:
    window_start: float
    window_end: float
    kpis: GovernanceKPIs
    feedback: dict[str, Any] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "kpis": self.kpis.to_dict(),
            "feedback": dict(self.feedback),
            "recommendations": [dict(item) for item in self.recommendations],
        }


class GovernanceFlywheel:
    """Collects KPIs, stores reviewer feedback, and emits tuning actions."""

    def __init__(self, feedback_path: str | Path | None = None) -> None:
        self.feedback_path = Path(feedback_path) if feedback_path is not None else None
        self._lock = threading.RLock()

    def collect(
        self,
        entries: Iterable[AuditEntry],
        *,
        since: float | None = None,
        now: float | None = None,
    ) -> GovernanceKPIs:
        current = time.time() if now is None else now
        decisions = [
            entry
            for entry in entries
            if entry.event_type == "governance_decision"
            and (since is None or entry.timestamp >= since)
        ]
        kpis = GovernanceKPIs(decisions=len(decisions))
        denied_actions: dict[str, int] = {}
        deny_reasons: dict[str, int] = {}
        first_half: list[bool] = []
        second_half: list[bool] = []
        midpoint = (since + current) / 2 if since is not None else None

        for entry in decisions:
            verdict = str(entry.details).split(":", 1)[0].strip().upper()
            denied = verdict == "DENY"
            if verdict == "ALLOW":
                kpis.allow += 1
            elif denied:
                kpis.deny += 1
                denied_actions[entry.action] = denied_actions.get(entry.action, 0) + 1
                reason = str(entry.details).split(":", 1)[1].strip() if ":" in entry.details else ""
                if reason:
                    deny_reasons[reason] = deny_reasons.get(reason, 0) + 1
            elif verdict == "ASK_USER":
                kpis.ask_user += 1
            if entry.signature_type != "unsigned":
                kpis.signed += 1
            version = str(entry.metadata.get("policy_version", "") or "")
            if version:
                kpis.policy_versions[version] = kpis.policy_versions.get(version, 0) + 1
            if midpoint is not None:
                (first_half if entry.timestamp < midpoint else second_half).append(denied)

        if kpis.decisions:
            kpis.deny_rate = kpis.deny / kpis.decisions
            kpis.hitl_rate = kpis.ask_user / kpis.decisions
            kpis.evidence_coverage = kpis.signed / kpis.decisions
        kpis.top_denied_actions = _top(denied_actions)
        kpis.top_deny_reasons = _top(deny_reasons)
        if first_half and second_half:
            kpis.deny_rate_trend = _rate(second_half) - _rate(first_half)
        return kpis

    def record_feedback(
        self,
        evidence_id: str,
        outcome: str,
        *,
        reviewer: str = "",
        score: float | None = None,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if outcome not in {"approve", "reject", "override", "false_positive", "false_negative"}:
            raise ValueError(f"unsupported feedback outcome: {outcome}")
        record = {
            "evidence_id": evidence_id,
            "outcome": outcome,
            "reviewer": reviewer,
            "score": score,
            "notes": notes,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        with self._lock:
            if self.feedback_path is not None:
                self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
                with self.feedback_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
            return record

    def feedback_summary(self) -> dict[str, Any]:
        with self._lock:
            records = self._load_feedback()
            counts: dict[str, int] = {}
            scores: list[float] = []
            for record in records:
                outcome = str(record.get("outcome", ""))
                counts[outcome] = counts.get(outcome, 0) + 1
                if isinstance(record.get("score"), (int, float)):
                    scores.append(float(record["score"]))
            return {
                "count": len(records),
                "outcomes": counts,
                "average_score": sum(scores) / len(scores) if scores else 0.0,
            }

    def run_cycle(
        self,
        entries: Iterable[AuditEntry],
        *,
        since: float | None = None,
        now: float | None = None,
        deny_rate_threshold: float = 0.35,
        evidence_coverage_threshold: float = 0.95,
    ) -> FlywheelReport:
        current = time.time() if now is None else now
        kpis = self.collect(entries, since=since, now=current)
        feedback = self.feedback_summary()
        recommendations = self._recommend(
            kpis,
            feedback,
            deny_rate_threshold=deny_rate_threshold,
            evidence_coverage_threshold=evidence_coverage_threshold,
        )
        return FlywheelReport(
            window_start=since if since is not None else 0.0,
            window_end=current,
            kpis=kpis,
            feedback=feedback,
            recommendations=recommendations,
        )

    def _recommend(
        self,
        kpis: GovernanceKPIs,
        feedback: dict[str, Any],
        *,
        deny_rate_threshold: float,
        evidence_coverage_threshold: float,
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        if kpis.decisions == 0:
            return [{"action": "collect_more_traffic", "reason": "no governance decisions in window"}]
        if kpis.deny_rate > deny_rate_threshold:
            recommendations.append(
                {
                    "action": "review_deny_policy",
                    "reason": f"deny rate {kpis.deny_rate:.1%} exceeds {deny_rate_threshold:.1%}",
                    "priority": "high",
                }
            )
        if kpis.evidence_coverage < evidence_coverage_threshold:
            recommendations.append(
                {
                    "action": "enable_signed_audit",
                    "reason": f"evidence coverage {kpis.evidence_coverage:.1%} below {evidence_coverage_threshold:.1%}",
                    "priority": "high",
                }
            )
        outcomes = feedback.get("outcomes", {})
        overrides = outcomes.get("override", 0) + outcomes.get("false_positive", 0)
        if feedback.get("count") and overrides / feedback["count"] > 0.2:
            recommendations.append(
                {
                    "action": "tighten_false_positive_loop",
                    "reason": f"{overrides} override/false-positive reviews in feedback",
                    "priority": "medium",
                }
            )
        if kpis.deny_rate_trend > 0.1:
            recommendations.append(
                {
                    "action": "investigate_deny_spike",
                    "reason": f"deny-rate trend increased by {kpis.deny_rate_trend:.1%}",
                    "priority": "medium",
                }
            )
        return recommendations

    def _load_feedback(self) -> list[dict[str, Any]]:
        if self.feedback_path is None or not self.feedback_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.feedback_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records


def _top(counts: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]


def _rate(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0
