"""Map governance audit evidence to EU AI Act obligations (P2-B).

The mapper turns append-only audit entries into a regulator-facing evidence
bundle: which obligation is covered, by which evidence ids, and with what
Merkle anchor.  It plugs directly into
``TechnicalDocumentation.set_audit_evidence``.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from maref.governance.audit import AuditEntry


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    title: str
    annex_iv_section: str


EU_AI_ACT_OBLIGATIONS: tuple[Obligation, ...] = (
    Obligation("Art.9", "Risk management system", "section_8_risk_management_system"),
    Obligation("Art.12", "Record-keeping", "section_9_post_market_monitoring"),
    Obligation("Art.14", "Human oversight", "section_5_human_oversight"),
    Obligation(
        "Art.15",
        "Accuracy, robustness and cybersecurity",
        "section_10_accuracy_robustness_cybersecurity",
    ),
    Obligation("Art.17", "Quality management system", "section_2_development_methodology"),
    Obligation("Art.72", "Post-market monitoring", "section_9_post_market_monitoring"),
)

_ACTION_RULES: tuple[tuple[str, str], ...] = (
    ("policy", "Art.17"),
    ("deploy", "Art.17"),
    ("incident", "Art.72"),
    ("state_transition", "Art.12"),
    ("audit", "Art.12"),
    ("evidence", "Art.12"),
    ("hitl", "Art.14"),
    ("human", "Art.14"),
)


@dataclass
class EvidenceClaim:
    obligation: Obligation
    evidence_ids: list[str] = field(default_factory=list)
    event_count: int = 0
    latest_timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation.obligation_id,
            "title": self.obligation.title,
            "annex_iv_section": self.obligation.annex_iv_section,
            "evidence_ids": list(self.evidence_ids),
            "event_count": self.event_count,
            "latest_timestamp": self.latest_timestamp,
        }


@dataclass
class EvidenceBundle:
    claims: list[EvidenceClaim]
    evidence_ids: list[str]
    merkle_root: str
    coverage: float
    missing_obligations: list[str]
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "merkle_root": self.merkle_root,
            "coverage": self.coverage,
            "evidence_count": len(self.evidence_ids),
            "evidence_ids": list(self.evidence_ids),
            "missing_obligations": list(self.missing_obligations),
            "claims": [claim.to_dict() for claim in self.claims],
            "annex_iv": {
                "merkle_root": self.merkle_root,
                "evidence_ids": list(self.evidence_ids),
            },
        }

    def apply_to_technical_documentation(self, docs: Any) -> None:
        """Attach the bundle to an EU AI Act TechnicalDocumentation instance."""
        docs.set_audit_evidence(self.merkle_root, list(self.evidence_ids))


class RegulatoryEvidenceMapper:
    """Builds an EU AI Act evidence bundle from governance audit entries."""

    def __init__(self, obligations: Iterable[Obligation] = EU_AI_ACT_OBLIGATIONS) -> None:
        self.obligations = tuple(obligations)

    def map_entries(self, entries: Iterable[AuditEntry]) -> EvidenceBundle:
        claims = {
            obligation.obligation_id: EvidenceClaim(obligation=obligation)
            for obligation in self.obligations
        }
        entry_list = list(entries)
        evidence_ids: list[str] = []

        for entry in entry_list:
            evidence_ids.append(entry.id)
            for obligation_id in self._obligations_for(entry):
                claim = claims.get(obligation_id)
                if claim is None:
                    continue
                claim.evidence_ids.append(entry.id)
                claim.event_count += 1
                claim.latest_timestamp = max(claim.latest_timestamp, entry.timestamp)

        ordered_claims = [claims[obligation.obligation_id] for obligation in self.obligations]
        covered = [claim.obligation.obligation_id for claim in ordered_claims if claim.event_count]
        missing = [
            obligation.obligation_id
            for obligation in self.obligations
            if obligation.obligation_id not in covered
        ]
        unique_ids = list(dict.fromkeys(evidence_ids))
        return EvidenceBundle(
            claims=ordered_claims,
            evidence_ids=unique_ids,
            merkle_root=_merkle_root(entry_list),
            coverage=(len(covered) / len(self.obligations)) if self.obligations else 0.0,
            missing_obligations=missing,
        )

    @staticmethod
    def _obligations_for(entry: AuditEntry) -> set[str]:
        verdict = str(entry.details).split(":", 1)[0].strip().upper()
        event_text = f"{entry.event_type} {entry.action}".lower()
        obligations: set[str] = set()

        if entry.event_type == "governance_decision":
            obligations.add("Art.12")
            if verdict == "DENY":
                obligations.add("Art.9")
                obligations.add("Art.15")
            elif verdict == "ASK_USER":
                obligations.add("Art.14")
        if entry.event_type == "state_transition":
            obligations.add("Art.12")
        if "hitl" in event_text or verdict == "ASK_USER":
            obligations.add("Art.14")
        if "incident" in event_text:
            obligations.add("Art.72")
        for marker, obligation_id in _ACTION_RULES:
            if marker in event_text:
                obligations.add(obligation_id)
        return obligations


def _merkle_root(entries: Iterable[AuditEntry]) -> str:
    leaves: list[str] = []
    for entry in entries:
        anchor = entry.chain_hash or entry.id
        leaves.append(hashlib.sha256(anchor.encode("utf-8")).hexdigest())
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256((leaves[index] + leaves[index + 1]).encode("utf-8")).hexdigest()
            for index in range(0, len(leaves), 2)
        ]
    return leaves[0]
