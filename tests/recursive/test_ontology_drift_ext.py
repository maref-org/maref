"""Tests for ontology_drift.py — snapshots, drift detection, decay monitoring."""
from __future__ import annotations

import time

import pytest

from maref.recursive.ontology_drift import (
    ConceptVector,
    ContextDecayMonitor,
    ContextRefreshSuggestion,
    DriftReport,
    OntologyDriftDetector,
    OntologySnapshot,
    RelationStrength,
)


class TestConceptVector:
    def test_hash_and_eq(self):
        cv1 = ConceptVector("c1", [1.0, 2.0])
        cv2 = ConceptVector("c1", [1.0, 2.0])
        cv3 = ConceptVector("c1", [1.0, 2.0], version="2.0.0")
        assert hash(cv1) == hash(cv2)
        assert cv1 == cv2
        assert cv1 != cv3
        assert cv1.__eq__("not_a_vector") == NotImplemented


class TestOntologySnapshot:
    def test_post_init_counts(self):
        snap = OntologySnapshot(
            snapshot_id="s1",
            concepts={"c1": ConceptVector("c1", [1.0])},
            relations={("c1", "c2"): RelationStrength("c1", "c2", "depends")},
        )
        assert snap.concept_count == 1
        assert snap.relation_count == 1


class TestDriftReport:
    def test_is_significant(self):
        assert DriftReport("c1", drift_score=0.3).is_significant is True
        assert DriftReport("c1", drift_score=0.29).is_significant is False

    def test_is_critical(self):
        assert DriftReport("c1", drift_score=0.7).is_critical is True
        assert DriftReport("c1", drift_score=0.69).is_critical is False


class TestOntologyDriftDetector:
    def test_initial_state(self):
        detector = OntologyDriftDetector()
        assert detector.snapshot_count() == 0
        assert detector.latest_snapshot() is None
        assert detector.get_mean_drift() == 0.0

    def test_take_snapshot(self):
        detector = OntologyDriftDetector()
        snap = detector.take_snapshot({"c1": [1.0, 2.0]})
        assert snap.snapshot_id.startswith("snap_")
        assert detector.snapshot_count() == 1
        assert detector.latest_snapshot() is snap

    def test_take_snapshot_with_relations(self):
        detector = OntologyDriftDetector()
        snap = detector.take_snapshot(
            {"c1": [1.0]},
            {("c1", "c2"): {"type": "depends", "strength": 0.8}},
        )
        assert len(snap.relations) == 1

    def test_semantic_distance_identical(self):
        detector = OntologyDriftDetector()
        snap1 = detector.take_snapshot({"c1": [1.0, 0.0]})
        snap2 = detector.take_snapshot({"c1": [1.0, 0.0]})
        distance = detector.semantic_distance(snap1, snap2)
        assert distance < 0.01

    def test_semantic_distance_different(self):
        detector = OntologyDriftDetector()
        snap1 = detector.take_snapshot({"c1": [0.0, 0.0]})
        snap2 = detector.take_snapshot({"c1": [1.0, 1.0]})
        distance = detector.semantic_distance(snap1, snap2)
        assert distance > 0

    def test_semantic_distance_no_common(self):
        detector = OntologyDriftDetector()
        snap1 = detector.take_snapshot({"c1": [1.0]})
        snap2 = detector.take_snapshot({"c2": [1.0]})
        assert detector.semantic_distance(snap1, snap2) == 1.0

    def test_semantic_distance_empty_embeddings(self):
        detector = OntologyDriftDetector()
        snap1 = detector.take_snapshot({"c1": []})
        snap2 = detector.take_snapshot({"c1": []})
        distance = detector.semantic_distance(snap1, snap2)
        assert distance == 0.5

    def test_detect_concept_drift_insufficient_snapshots(self):
        detector = OntologyDriftDetector()
        report = detector.detect_concept_drift("c1")
        assert report.drift_score == 0.0
        assert report.severity == "INFO"

    def test_detect_concept_drift_stable(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0, 1.0]})
        detector.take_snapshot({"c1": [1.0, 1.0]})
        report = detector.detect_concept_drift("c1")
        assert report.drift_score < 0.01
        assert report.severity == "INFO"

    def test_detect_concept_drift_significant(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.0, 0.0]})
        detector.take_snapshot({"c1": [1.0, 1.0]})
        report = detector.detect_concept_drift("c1")
        assert report.drift_score >= 0.3

    def test_detect_concept_drift_not_found(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0]})
        detector.take_snapshot({"c1": [1.0]})
        report = detector.detect_concept_drift("c2")
        assert report.severity == "INFO"

    def test_detect_concept_drift_dimension_change(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0, 0.0]})
        detector.take_snapshot({"c1": [1.0]})
        report = detector.detect_concept_drift("c1")
        assert report.severity == "WARNING"

    def test_detect_metric_drift(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"metric_x": [0.5]})
        detector.take_snapshot({"metric_x": [0.8]})
        report = detector.detect_metric_drift("metric_x")
        assert report.drift_score > 0

    def test_detect_schema_evolution_no_snapshots(self):
        detector = OntologyDriftDetector()
        assert detector.detect_schema_evolution() == []

    def test_detect_schema_evolution_version_change(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0]}, schema_version="1.0.0")
        detector.take_snapshot({"c1": [1.0]}, schema_version="2.0.0")
        changes = detector.detect_schema_evolution()
        assert any(c.change_type == "schema_update" for c in changes)

    def test_detect_schema_evolution_concept_added(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0]})
        detector.take_snapshot({"c1": [1.0], "c2": [2.0]})
        changes = detector.detect_schema_evolution()
        assert any(c.change_type == "concept_added" and c.after == "c2" for c in changes)

    def test_detect_schema_evolution_concept_removed(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [1.0], "c2": [2.0]})
        detector.take_snapshot({"c1": [1.0]})
        changes = detector.detect_schema_evolution()
        assert any(c.change_type == "concept_removed" and c.before == "c2" for c in changes)

    def test_get_mean_drift(self):
        detector = OntologyDriftDetector()
        detector.take_snapshot({"c1": [0.0, 0.0]})
        detector.take_snapshot({"c1": [1.0, 0.0]})
        mean_drift = detector.get_mean_drift()
        assert mean_drift > 0

    def test_history_window(self):
        detector = OntologyDriftDetector(history_window=3)
        for _ in range(10):
            detector.take_snapshot({"c1": [1.0]})
        assert len(detector._snapshots) == 3


class TestContextDecayMonitor:
    def test_track_layer(self):
        monitor = ContextDecayMonitor()
        monitor.track_layer("layer-1")
        assert monitor.layer_status("layer-1") == 1.0

    def test_decay_unknown_layer(self):
        monitor = ContextDecayMonitor()
        assert monitor.decay("nonexistent") == 0.0

    def test_decay_over_time(self):
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.1)
        monitor.track_layer("layer-1")
        monitor._context_layers["layer-1"].last_refresh = time.time() - 36000
        freshness = monitor.decay("layer-1")
        assert freshness < 1.0

    def test_predict_decay_unknown(self):
        monitor = ContextDecayMonitor()
        assert monitor.predict_decay("nonexistent") == 0.0

    def test_predict_decay(self):
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.1)
        monitor.track_layer("layer-1", initial_freshness=1.0)
        predicted = monitor.predict_decay("layer-1", horizon_hours=5)
        assert predicted == 0.5

    def test_recommend_refresh_empty(self):
        monitor = ContextDecayMonitor()
        assert monitor.recommend_refresh() == []

    def test_recommend_refresh(self):
        monitor = ContextDecayMonitor(decay_rate_per_hour=0.5)
        monitor.track_layer("layer-1", initial_freshness=1.0)
        monitor._context_layers["layer-1"].last_refresh = time.time() - 7200
        suggestions = monitor.recommend_refresh()
        assert len(suggestions) >= 1

    def test_refresh(self):
        monitor = ContextDecayMonitor()
        monitor.track_layer("layer-1", initial_freshness=0.2)
        monitor.refresh("layer-1")
        assert monitor.layer_status("layer-1") == 1.0

    def test_refresh_nonexistent(self):
        monitor = ContextDecayMonitor()
        monitor.refresh("nonexistent")  # should not raise
