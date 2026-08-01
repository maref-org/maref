"""Compiled Truth + Timeline data model.

Implements the "mutable truth above the line, append-only evidence below" pattern
from GBrain. Each entity/topic has one TruthPage combining current best understanding
with a complete evidence trail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceEntry:
    """A single piece of evidence in the append-only trail."""

    citation_id: str
    text: str
    source: str
    confidence: float
    timestamp: float
    superseded_by: str = ""  # citation_id of newer evidence that made this obsolete

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "text": self.text,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceEntry:
        return cls(
            citation_id=data["citation_id"],
            text=data["text"],
            source=data.get("source", ""),
            confidence=data.get("confidence", 0.5),
            timestamp=data.get("timestamp", time.time()),
            superseded_by=data.get("superseded_by", ""),
        )


@dataclass
class CompiledTruth:
    """Current best understanding of a topic. Mutable."""

    entity_id: str
    current_best: str  # human-readable summary
    confidence: float
    last_updated: float
    updated_by: str  # agent_id or "human"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_best": self.current_best,
            "confidence": self.confidence,
            "last_updated": self.last_updated,
            "updated_by": self.updated_by,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompiledTruth:
        return cls(
            entity_id=data["entity_id"],
            current_best=data["current_best"],
            confidence=data.get("confidence", 0.5),
            last_updated=data.get("last_updated", time.time()),
            updated_by=data.get("updated_by", "unknown"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TruthPage:
    """One page combining mutable truth + append-only evidence trail."""

    entity_id: str
    compiled_truth: CompiledTruth
    evidence_trail: list[EvidenceEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def compile(self, new_best: str, agent_id: str, confidence: float | None = None) -> None:
        """Update the truth, pushing the old version to the evidence trail."""
        old_best = self.compiled_truth.current_best
        old_confidence = self.compiled_truth.confidence

        self.evidence_trail.append(EvidenceEntry(
            citation_id=f"ev_{int(time.time())}",
            text=old_best,
            source=self.compiled_truth.updated_by,
            confidence=old_confidence,
            timestamp=self.compiled_truth.last_updated,
            superseded_by="",
        ))

        self.compiled_truth.current_best = new_best
        self.compiled_truth.last_updated = time.time()
        self.compiled_truth.updated_by = agent_id
        if confidence is not None:
            self.compiled_truth.confidence = confidence

    def add_evidence(
        self,
        text: str,
        source: str,
        confidence: float = 0.5,
    ) -> EvidenceEntry:
        """Append a new piece of evidence to the trail."""
        entry = EvidenceEntry(
            citation_id=f"ev_{int(time.time())}_{hash(text) % 10000}",
            text=text,
            source=source,
            confidence=confidence,
            timestamp=time.time(),
        )
        self.evidence_trail.append(entry)
        return entry

    def get_timeline(self) -> list[dict[str, Any]]:
        """Chronological view of all evidence."""
        sorted_trail = sorted(self.evidence_trail, key=lambda e: e.timestamp)
        return [
            {
                "timestamp": e.timestamp,
                "text": e.text,
                "source": e.source,
                "confidence": e.confidence,
                "superseded": bool(e.superseded_by),
            }
            for e in sorted_trail
        ]

    def get_active_evidence(self) -> list[EvidenceEntry]:
        """Evidence not superseded by newer entries."""
        return [e for e in self.evidence_trail if not e.superseded_by]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "compiled_truth": self.compiled_truth.to_dict(),
            "evidence_trail": [e.to_dict() for e in self.evidence_trail],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TruthPage:
        return cls(
            entity_id=data["entity_id"],
            compiled_truth=CompiledTruth.from_dict(data["compiled_truth"]),
            evidence_trail=[EvidenceEntry.from_dict(e) for e in data.get("evidence_trail", [])],
            created_at=data.get("created_at", time.time()),
        )
