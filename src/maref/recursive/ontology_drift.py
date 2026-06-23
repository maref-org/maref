from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConceptVector:
    concept_id: str
    embedding: list[float]
    version: str = "1.0.0"

    def __hash__(self) -> int:
        return hash((self.concept_id, self.version))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConceptVector):
            return NotImplemented
        return self.concept_id == other.concept_id and self.version == other.version


@dataclass
class RelationStrength:
    source: str
    target: str
    relation_type: str
    strength: float = 1.0


@dataclass
class OntologySnapshot:
    snapshot_id: str
    timestamp: float = field(default_factory=time.time)
    concepts: dict[str, ConceptVector] = field(default_factory=dict)
    relations: dict[tuple[str, str], RelationStrength] = field(default_factory=dict)
    schema_version: str = "1.0.0"
    concept_count: int = 0
    relation_count: int = 0

    def __post_init__(self) -> None:
        self.concept_count = len(self.concepts)
        self.relation_count = len(self.relations)


@dataclass
class DriftReport:
    component: str
    drift_score: float = 0.0
    drift_type: str = "stable"
    details: str = ""
    severity: str = "INFO"

    @property
    def is_significant(self) -> bool:
        return self.drift_score >= 0.3

    @property
    def is_critical(self) -> bool:
        return self.drift_score >= 0.7


@dataclass
class SchemaChange:
    change_type: str
    component: str
    before: str
    after: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ContextRefreshSuggestion:
    context_layer: str
    decay_score: float
    suggested_action: str
    urgency: str = "LOW"


class OntologyDriftDetector:
    def __init__(self, history_window: int = 50) -> None:
        self._snapshots: list[OntologySnapshot] = []
        self._history_window = history_window

    def take_snapshot(
        self,
        concepts: dict[str, list[float]],
        relations: dict[tuple[str, str], dict[str, Any]] | None = None,
        schema_version: str = "1.0.0",
    ) -> OntologySnapshot:
        concept_vectors: dict[str, ConceptVector] = {}
        for cid, emb in concepts.items():
            concept_vectors[cid] = ConceptVector(
                concept_id=cid,
                embedding=list(emb),
            )
        rel_strengths: dict[tuple[str, str], RelationStrength] = {}
        if relations:
            for (src, tgt), rdata in relations.items():
                rel_strengths[(src, tgt)] = RelationStrength(
                    source=src,
                    target=tgt,
                    relation_type=rdata.get("type", "unknown"),
                    strength=rdata.get("strength", 1.0),
                )

        snapshot = OntologySnapshot(
            snapshot_id=f"snap_{len(self._snapshots)}_{int(time.time())}",
            concepts=concept_vectors,
            relations=rel_strengths,
            schema_version=schema_version,
        )
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._history_window:
            self._snapshots = self._snapshots[-self._history_window :]
        return snapshot

    def semantic_distance(self, snap_a: OntologySnapshot, snap_b: OntologySnapshot) -> float:
        common_concepts = set(snap_a.concepts.keys()) & set(snap_b.concepts.keys())
        if not common_concepts:
            return 1.0

        total_distance = 0.0
        count = 0
        for cid in common_concepts:
            emb_a = snap_a.concepts[cid].embedding
            emb_b = snap_b.concepts[cid].embedding
            if len(emb_a) != len(emb_b):
                continue
            if len(emb_a) > 0:
                vec_dist = sum((a - b) ** 2 for a, b in zip(emb_a, emb_b, strict=False)) ** 0.5
                max_dist = (4 * len(emb_a)) ** 0.5
                normalized = min(1.0, vec_dist / max_dist) if max_dist > 0 else 0.0
                total_distance += normalized
                count += 1

        concept_dist = total_distance / count if count > 0 else 1.0

        rel_a = set(snap_a.relations.keys())
        rel_b = set(snap_b.relations.keys())
        union_size = len(rel_a | rel_b)
        if union_size > 0:
            intersection_size = len(rel_a & rel_b)
            jaccard = intersection_size / union_size
            rel_dist = 1.0 - jaccard
        else:
            rel_dist = 0.0

        return (concept_dist + rel_dist) / 2.0

    def detect_concept_drift(self, concept_id: str, window: int = 10) -> DriftReport:
        if len(self._snapshots) < 2:
            return DriftReport(
                component=concept_id,
                drift_score=0.0,
                drift_type="stable",
                details="Insufficient snapshots for drift analysis",
                severity="INFO",
            )

        recent = self._snapshots[-min(window, len(self._snapshots)) :]
        vectors: list[list[float]] = []
        for snap in recent:
            cv = snap.concepts.get(concept_id)
            if cv is not None:
                vectors.append(cv.embedding)

        if len(vectors) < 2:
            return DriftReport(
                component=concept_id,
                drift_score=0.0,
                drift_type="stable",
                details="Concept not found in sufficient snapshots",
                severity="INFO",
            )

        first = vectors[0]
        last = vectors[-1]
        if len(first) != len(last):
            return DriftReport(
                component=concept_id,
                drift_score=0.0,
                drift_type="stable",
                details="Embedding dimension changed",
                severity="WARNING",
            )

        if len(first) > 0:
            raw_dist = sum((a - b) ** 2 for a, b in zip(first, last, strict=False)) ** 0.5
            max_dist = (4 * len(first)) ** 0.5
            drift_score = min(1.0, raw_dist / max_dist) if max_dist > 0 else 0.0
        else:
            drift_score = 0.0

        drift_type = "stable"
        severity = "INFO"
        if drift_score >= 0.7:
            drift_type = "significant_drift"
            severity = "HIGH"
        elif drift_score >= 0.3:
            drift_type = "moderate_drift"
            severity = "WARNING"

        return DriftReport(
            component=concept_id,
            drift_score=drift_score,
            drift_type=drift_type,
            details=f"Drift measured over {len(vectors)} snapshots",
            severity=severity,
        )

    def detect_metric_drift(self, metric_name: str) -> DriftReport:
        return self.detect_concept_drift(metric_name)

    def detect_schema_evolution(self) -> list[SchemaChange]:
        changes: list[SchemaChange] = []
        if len(self._snapshots) < 2:
            return changes
        for i in range(1, len(self._snapshots)):
            prev = self._snapshots[i - 1]
            curr = self._snapshots[i]
            if prev.schema_version != curr.schema_version:
                changes.append(
                    SchemaChange(
                        change_type="schema_update",
                        component="ontology",
                        before=prev.schema_version,
                        after=curr.schema_version,
                        timestamp=curr.timestamp,
                    )
                )
            prev_ids = set(prev.concepts.keys())
            curr_ids = set(curr.concepts.keys())
            added = curr_ids - prev_ids
            removed = prev_ids - curr_ids
            for cid in added:
                changes.append(
                    SchemaChange(
                        change_type="concept_added",
                        component=cid,
                        before="",
                        after=cid,
                        timestamp=curr.timestamp,
                    )
                )
            for cid in removed:
                changes.append(
                    SchemaChange(
                        change_type="concept_removed",
                        component=cid,
                        before=cid,
                        after="",
                        timestamp=curr.timestamp,
                    )
                )
        return changes

    def get_mean_drift(self, window: int = 5) -> float:
        """计算最近 N 个快照间所有概念的平均漂移 (供 SemanticConvergenceDetected 消费)。"""
        if len(self._snapshots) < 2:
            return 0.0
        recent = self._snapshots[-min(window, len(self._snapshots)) :]
        if len(recent) < 2:
            return 0.0
        drifts: list[float] = []
        for i in range(1, len(recent)):
            d = self.semantic_distance(recent[i - 1], recent[i])
            drifts.append(d)
        return sum(drifts) / len(drifts) if drifts else 0.0

    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def latest_snapshot(self) -> OntologySnapshot | None:
        return self._snapshots[-1] if self._snapshots else None


class ContextDecayMonitor:
    def __init__(self, decay_rate_per_hour: float = 0.01) -> None:
        self._decay_rate = decay_rate_per_hour
        self._context_layers: dict[str, ContextLayerStatus] = {}

    def track_layer(self, layer_id: str, initial_freshness: float = 1.0) -> None:
        self._context_layers[layer_id] = ContextLayerStatus(
            layer_id=layer_id,
            freshness=initial_freshness,
            last_refresh=time.time(),
        )

    def decay(self, layer_id: str) -> float:
        status = self._context_layers.get(layer_id)
        if status is None:
            return 0.0
        hours_elapsed = (time.time() - status.last_refresh) / 3600.0
        decay = hours_elapsed * self._decay_rate
        status.freshness = max(0.0, status.freshness - decay)
        return status.freshness

    def predict_decay(self, layer_id: str, horizon_hours: int = 24) -> float:
        status = self._context_layers.get(layer_id)
        if status is None:
            return 0.0
        predicted = status.freshness - horizon_hours * self._decay_rate
        return max(0.0, predicted)

    def recommend_refresh(self) -> list[ContextRefreshSuggestion]:
        suggestions: list[ContextRefreshSuggestion] = []
        for layer_id, _status in self._context_layers.items():
            current = self.decay(layer_id)
            predicted = self.predict_decay(layer_id, 1)
            if current < 0.3:
                suggestions.append(
                    ContextRefreshSuggestion(
                        context_layer=layer_id,
                        decay_score=current,
                        suggested_action="IMMEDIATE refresh required",
                        urgency="HIGH",
                    )
                )
            elif current < 0.6:
                suggestions.append(
                    ContextRefreshSuggestion(
                        context_layer=layer_id,
                        decay_score=current,
                        suggested_action="Schedule refresh soon",
                        urgency="MEDIUM",
                    )
                )
            elif predicted < 0.3:
                suggestions.append(
                    ContextRefreshSuggestion(
                        context_layer=layer_id,
                        decay_score=current,
                        suggested_action="Preemptive refresh recommended",
                        urgency="LOW",
                    )
                )
        return suggestions

    def refresh(self, layer_id: str) -> None:
        status = self._context_layers.get(layer_id)
        if status:
            status.freshness = 1.0
            status.last_refresh = time.time()

    def layer_status(self, layer_id: str) -> float:
        status = self._context_layers.get(layer_id)
        return status.freshness if status else 0.0


@dataclass
class ContextLayerStatus:
    layer_id: str
    freshness: float = 1.0
    last_refresh: float = field(default_factory=time.time)
