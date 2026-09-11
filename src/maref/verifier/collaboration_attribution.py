"""CooperBench-style collaboration failure attribution.

Classifies failures in agent-to-agent message exchanges into the three
capability gaps identified by CooperBench: EXPECTATION (wrong mental
model of what a partner knows or will deliver), COMMITMENT (agreed to
act but did not follow through), and COMMUNICATION (missing or
low-value messages).

The analyzer is pure and side-effect free: it reads message records
(compatible with AgentMessage dicts), returns a CollaborationReport,
and never mutates the message source.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

DEFAULT_REPEAT_THRESHOLD = 3


class CollaborationFailureType(str, Enum):
    EXPECTATION = "expectation"
    COMMITMENT = "commitment"
    COMMUNICATION = "communication"


@dataclass
class CollaborationIssue:
    type: CollaborationFailureType
    sender_id: str
    target_id: str
    protocol: str
    evidence: str
    severity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "protocol": self.protocol,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass
class CollaborationReport:
    issues: list[CollaborationIssue] = field(default_factory=list)
    score: float = 1.0
    trace_id: str = ""

    @property
    def counts(self) -> dict[CollaborationFailureType, int]:
        return dict(Counter(i.type for i in self.issues))

    def to_dict(self) -> dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "score": round(self.score, 3),
            "counts": {t.value: c for t, c in self.counts.items()},
            "trace_id": self.trace_id,
        }


def _issue(
    failure_type: CollaborationFailureType,
    msg: Mapping[str, Any],
    evidence: str,
    severity: float = 1.0,
) -> CollaborationIssue:
    return CollaborationIssue(
        type=failure_type,
        sender_id=msg.get("sender_id", ""),
        target_id=msg.get("target_id", ""),
        protocol=msg.get("protocol", ""),
        evidence=evidence,
        severity=severity,
    )


def analyze(
    messages: Sequence[Mapping[str, Any]],
    repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
    trace_id: str = "",
) -> CollaborationReport:
    """Classify collaboration failures across a batch of messages.

    Each message yields at most one issue, checked in priority order
    EXPECTATION -> COMMITMENT -> COMMUNICATION (empty payload) ->
    COMMUNICATION (low-value repetition).
    """
    issues: list[CollaborationIssue] = []
    repeat_counts: Counter[tuple[str, str, str]] = Counter()

    for msg in messages:
        payload = msg.get("payload")
        expectation = msg.get("expectation")

        if isinstance(expectation, list):
            payload_keys = set(payload) if isinstance(payload, Mapping) else set()
            missing = [k for k in expectation if k not in payload_keys]
            if missing:
                issues.append(
                    _issue(CollaborationFailureType.EXPECTATION, msg, f"missing keys {missing}")
                )
                continue

        status = msg.get("status", "")
        if status == "failed" or msg.get("nack_route"):
            issues.append(
                _issue(
                    CollaborationFailureType.COMMITMENT,
                    msg,
                    f"status={status} nack={msg.get('nack_route', '')}",
                )
            )
            continue

        if not isinstance(payload, Mapping) or not payload:
            issues.append(_issue(CollaborationFailureType.COMMUNICATION, msg, "empty payload"))
            continue

        key = (msg.get("sender_id", ""), msg.get("target_id", ""), msg.get("protocol", ""))
        repeat_counts[key] += 1
        if repeat_counts[key] > repeat_threshold:
            issues.append(
                _issue(
                    CollaborationFailureType.COMMUNICATION,
                    msg,
                    f"repeated {repeat_counts[key]}x",
                )
            )

    denominator = max(1, len(messages))
    score = max(0.0, 1.0 - len(issues) / denominator)
    return CollaborationReport(issues=issues, score=score, trace_id=trace_id)


def attach(result: Any, report: CollaborationReport) -> None:
    """Attach a collaboration report to a cross-validation result."""
    result.collaboration = report.to_dict()
