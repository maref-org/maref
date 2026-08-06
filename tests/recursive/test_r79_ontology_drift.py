from __future__ import annotations

import pytest

from maref.recursive.ontology_drift import (
    ContextDecayMonitor,
    OntologyDriftDetector,
)


class TestOntologySnapshot:
    def test_create_snapshot(self) -> None:
        concepts = {
            "concept_a": [0.1, 0.2, 0.3],
            "concept_b": [0.4, 0.5, 0.6],
        }
        relations = {
            ("concept_a", "concept_b"): {"type": "relates_to", "strength": 0.8},
        }
        detector = OntologyDriftDetector()
        snapshot = detector.take_snapshot(concepts, relations)
        assert snapshot.concept_count == 2
        assert snapshot.relation_count == 1
        assert snapshot.schema_version == "1.0.0"

    def test_snapshot_ids_increment(self) -> None:
        detector = OntologyDriftDetector()
        snap1 = detector.take_snapshot({})
        snap2 = detector.take_snapshot({})
        assert snap1.snapshot_id != snap2.snapshot_id

    def test_latest_snapshot(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0]})
        detector.take_snapshot({"c2": [2.0]})
        latest = detector.latest_snapshot()
        assert latest is not None
        assert "c2" in latest.concepts


class TestSemanticDistance:
    def test_identical_snapshots(self) -> None:
        detector = OntologyDriftDetector()
        concepts = {"c1": [0.5, 0.5]}
        snap_a = detector.take_snapshot(concepts)
        snap_b = detector.take_snapshot(concepts)
        distance = detector.semantic_distance(snap_a, snap_b)
        assert distance == pytest.approx(0.0, abs=0.01)

    def test_different_snapshots(self) -> None:
        detector = OntologyDriftDetector()
        snap_a = detector.take_snapshot({"c1": [0.0, 0.0]})
        snap_b = detector.take_snapshot({"c1": [1.0, 1.0]})
        distance = detector.semantic_distance(snap_a, snap_b)
        assert distance > 0.2

    def test_disjoint_concept_sets(self) -> None:
        detector = OntologyDriftDetector()
        snap_a = detector.take_snapshot({"c1": [0.5]})
        snap_b = detector.take_snapshot({"c2": [0.5]})
        distance = detector.semantic_distance(snap_a, snap_b)
        assert distance >= 0.5


class TestConceptDrift:
    def test_stable_concept(self) -> None:
        detector = OntologyDriftDetector()
        for _ in range(5):
            detector.take_snapshot({"my_concept": [0.5, 0.5, 0.5]})
        report = detector.detect_concept_drift("my_concept")
        assert not report.is_significant
        assert report.drift_type == "stable"

    def test_drifting_concept(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"my_concept": [0.0, 0.0, 0.0]})
        detector.take_snapshot({"my_concept": [0.5, 0.5, 0.5]})
        detector.take_snapshot({"my_concept": [1.0, 1.0, 1.0]})
        report = detector.detect_concept_drift("my_concept")
        assert report.drift_score > 0.3
        assert report.is_significant

    def test_missing_concept(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.5]})
        report = detector.detect_concept_drift("nonexistent")
        assert report.drift_type == "stable"


class TestSchemaEvolution:
    def test_no_changes_single_snapshot(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.5]})
        changes = detector.detect_schema_evolution()
        assert len(changes) == 0

    def test_concept_added(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.5]})
        detector.take_snapshot({"c1": [0.5], "c2": [0.7]})
        changes = detector.detect_schema_evolution()
        added = [c for c in changes if c.change_type == "concept_added"]
        assert len(added) == 1
        assert added[0].component == "c2"

    def test_concept_removed(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.5], "c2": [0.7]})
        detector.take_snapshot({"c1": [0.5]})
        changes = detector.detect_schema_evolution()
        removed = [c for c in changes if c.change_type == "concept_removed"]
        assert len(removed) == 1
        assert removed[0].component == "c2"

    def test_schema_version_change(self) -> None:
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.5]}, schema_version="1.0.0")
        detector.take_snapshot({"c1": [0.5], "c2": [0.7]}, schema_version="2.0.0")
        changes = detector.detect_schema_evolution()
        schema_changes = [c for c in changes if c.change_type == "schema_update"]
        assert len(schema_changes) == 1
        assert schema_changes[0].before == "1.0.0"
        assert schema_changes[0].after == "2.0.0"


class TestContextDecayMonitor:
    def test_track_and_decay(self) -> None:
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.1)
        monitor.track_layer("context_a", initial_freshness=1.0)
        assert monitor.layer_status("context_a") == 1.0

    def test_refresh_restores_freshness(self) -> None:
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.1)
        monitor.track_layer("context_a", initial_freshness=1.0)
        monitor.decay("context_a")
        monitor.refresh("context_a")
        assert monitor.layer_status("context_a") == 1.0

    def test_predict_decay(self) -> None:
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.1)
        monitor.track_layer("context_a", initial_freshness=1.0)
        predicted = monitor.predict_decay("context_a", horizon_hours=10)
        assert predicted == 0.0

    def test_recommend_refresh(self) -> None:
        monitor = ContextDecayMonitor(decay_rate_per_hour=10.0)
        monitor.track_layer("urgent_ctx", initial_freshness=1.0)
        suggestions = monitor.recommend_refresh()
        assert len(suggestions) >= 1
