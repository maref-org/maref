"""Tests for MAREF observation probe system."""

from __future__ import annotations

from maref.observation.detector import DualThresholdConfig, DualThresholdDetector, FNRFPRSnapshot
from maref.observation.probes import (
    AnomalyProbe,
    EntropyProbe,
    KGProbe,
    LatencyProbe,
    OscillationProbe,
    ProbeReading,
    ProbeSeverity,
)
from maref.observation.registry import ProbeRegistry
from maref.observation.store import ObservationStore


class TestProbeThresholds:
    def test_entropy_probe_primary(self) -> None:
        probe = EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0)
        readings = probe.read(entropy=4)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_entropy_probe_shadow(self) -> None:
        probe = EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0)
        readings = probe.read(entropy=2)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.WARNING

    def test_entropy_probe_normal(self) -> None:
        probe = EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0)
        readings = probe.read(entropy=1)
        assert len(readings) == 0

    def test_entropy_probe_below_all(self) -> None:
        probe = EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0)
        readings = probe.read(entropy=1)
        assert readings == []

    def test_anomaly_probe_critical(self) -> None:
        probe = AnomalyProbe(primary_threshold=10.0, shadow_threshold=3.0)
        readings = probe.read(anomaly_count=15)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_anomaly_probe_warning(self) -> None:
        probe = AnomalyProbe(primary_threshold=10.0, shadow_threshold=3.0)
        readings = probe.read(anomaly_count=5)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.WARNING

    def test_latency_probe(self) -> None:
        probe = LatencyProbe(primary_threshold=5.0, shadow_threshold=1.0)
        readings = probe.read(latency_ms=6.0)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_kg_probe_orphaned(self) -> None:
        probe = KGProbe(primary_threshold=0.95)
        readings = probe.read(total_nodes=100, orphaned_nodes=98)
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_kg_probe_healthy(self) -> None:
        probe = KGProbe(primary_threshold=0.95)
        readings = probe.read(total_nodes=100, orphaned_nodes=10)
        assert len(readings) == 0

    def test_kg_probe_empty(self) -> None:
        probe = KGProbe(primary_threshold=0.95)
        readings = probe.read(total_nodes=0, orphaned_nodes=0)
        assert len(readings) == 0

    def test_oscillation_probe_critical(self) -> None:
        probe = OscillationProbe(primary_threshold=10.0, shadow_threshold=4.0)
        for _ in range(15):
            probe.record_change()
        readings = probe.read()
        assert len(readings) == 1
        assert readings[0].severity == ProbeSeverity.CRITICAL

    def test_oscillation_probe_normal(self) -> None:
        probe = OscillationProbe(primary_threshold=10.0, shadow_threshold=4.0)
        for _ in range(3):
            probe.record_change()
        readings = probe.read()
        assert readings == []

    def test_reading_count_accumulates(self) -> None:
        probe = EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0)
        probe.read(entropy=4)
        probe.read(entropy=2)
        probe.read(entropy=4)
        assert probe.reading_count == 3


class TestProbeRegistry:
    def test_register_and_list(self) -> None:
        registry = ProbeRegistry()
        registry.register(EntropyProbe())
        registry.register(AnomalyProbe())
        assert sorted(registry.list_probes()) == sorted(["entropy", "anomaly"])

    def test_unregister(self) -> None:
        registry = ProbeRegistry()
        registry.register(EntropyProbe())
        assert registry.unregister("entropy")
        assert registry.list_probes() == []

    def test_read_all_dispatches(self) -> None:
        registry = ProbeRegistry()
        registry.register(EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0))
        registry.register(AnomalyProbe(primary_threshold=10.0, shadow_threshold=3.0))

        readings = registry.read_all(entropy=4, anomaly_count=15)
        assert len(readings) >= 2

    def test_severity_counts(self) -> None:
        registry = ProbeRegistry()
        registry.register(EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0))
        registry.read_all(entropy=4)
        registry.read_all(entropy=2)
        registry.read_all(entropy=1)

        counts = registry.get_counts_by_severity()
        assert counts["critical"] >= 1
        assert counts["warning"] >= 1

    def test_get_counts_by_probe(self) -> None:
        registry = ProbeRegistry()
        registry.register(EntropyProbe(primary_threshold=4.0, shadow_threshold=2.0))
        registry.register(AnomalyProbe(primary_threshold=10.0, shadow_threshold=3.0))
        registry.read_all(entropy=4, anomaly_count=15)
        registry.read_all(entropy=4, anomaly_count=5)

        counts = registry.get_counts_by_probe()
        assert counts["entropy"] >= 2
        assert counts["anomaly"] >= 2


class TestDualThresholdDetector:
    def test_primary_triggers(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
            )
        )
        result = detector.evaluate(4.0)
        assert result["primary_triggered"]
        assert not result["shadow_triggered"]

    def test_shadow_triggers(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
            )
        )
        result = detector.evaluate(2.5)
        assert not result["primary_triggered"]
        assert result["shadow_triggered"]

    def test_below_all(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
            )
        )
        result = detector.evaluate(1.0)
        assert not result["primary_triggered"]
        assert not result["shadow_triggered"]

    def test_confusion_matrix(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
            )
        )
        detector.evaluate(4.0, ground_truth_is_anomaly=True)
        detector.evaluate(4.0, ground_truth_is_anomaly=False)
        detector.evaluate(1.0, ground_truth_is_anomaly=False)
        detector.evaluate(1.0, ground_truth_is_anomaly=True)

        stats = detector.get_stats()["fnr_fpr"]
        assert stats["true_positives"] == 1
        assert stats["false_positives"] == 1
        assert stats["true_negatives"] == 1
        assert stats["false_negatives"] == 1

    def test_trend_rising(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
                trend_window=3,
            )
        )
        detector.evaluate(1.0)
        detector.evaluate(2.0)
        result = detector.evaluate(3.0)
        assert result["trend_rising"]

    def test_trend_not_rising(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
                trend_window=3,
            )
        )
        detector.evaluate(3.0)
        detector.evaluate(2.0)
        result = detector.evaluate(1.0)
        assert not result["trend_rising"]

    def test_oscillation_detected(self) -> None:
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                oscillation_max_rate=5.0,
            )
        )
        for _ in range(10):
            detector.record_change()
        result = detector.evaluate(3.0)
        assert result["oscillating"]


class TestObservationStore:
    def test_insert_and_read(self) -> None:
        store = ObservationStore(db_path=":memory:")
        reading = ProbeReading(
            probe_name="entropy",
            severity=ProbeSeverity.CRITICAL,
            value=4.0,
            threshold=4.0,
            context={"entropy": 4},
        )
        store.insert_reading(reading)
        results = store.get_readings(probe_name="entropy", limit=10)
        assert len(results) == 1
        assert results[0]["probe_name"] == "entropy"
        assert results[0]["severity"] == "critical"

    def test_insert_batch(self) -> None:
        store = ObservationStore(db_path=":memory:")
        readings = [
            ProbeReading("entropy", ProbeSeverity.CRITICAL, 4.0, 4.0),
            ProbeReading("entropy", ProbeSeverity.WARNING, 2.0, 4.0),
            ProbeReading("anomaly", ProbeSeverity.WARNING, 5.0, 10.0),
        ]
        count = store.insert_batch(readings)
        assert count == 3
        assert store.get_counts()["total"] == 3

    def test_fnr_fpr_log(self) -> None:
        store = ObservationStore(db_path=":memory:")
        store.log_fnr_fpr("batch_001", fnr=0.667, fpr=0.082, tp=10, fp=5, tn=50, fn_count=20)
        history = store.get_fnr_fpr_history(limit=1)
        assert len(history) == 1
        assert history[0]["batch_id"] == "batch_001"
        assert history[0]["fnr"] == 0.667

    def test_filter_by_severity(self) -> None:
        store = ObservationStore(db_path=":memory:")
        store.insert_reading(ProbeReading("entropy", ProbeSeverity.CRITICAL, 4.0, 4.0))
        store.insert_reading(ProbeReading("entropy", ProbeSeverity.WARNING, 2.0, 4.0))
        critical = store.get_readings(severity="critical")
        assert len(critical) == 1
        warning = store.get_readings(severity="warning")
        assert len(warning) == 1


class TestFNRFPRSnapshot:
    def test_empty_zero(self) -> None:
        snap = FNRFPRSnapshot()
        assert snap.fnr == 0.0
        assert snap.fpr == 0.0

    def test_all_true_positives(self) -> None:
        snap = FNRFPRSnapshot(true_positives=10)
        assert snap.fnr == 0.0
        assert snap.recall == 1.0

    def test_all_false_negatives(self) -> None:
        snap = FNRFPRSnapshot(false_negatives=10)
        assert snap.fnr == 1.0
        assert snap.recall == 0.0

    def test_mixed(self) -> None:
        snap = FNRFPRSnapshot(
            true_positives=8,
            false_positives=2,
            true_negatives=85,
            false_negatives=5,
        )
        assert abs(snap.fnr - 5 / 13) < 0.01
        assert abs(snap.fpr - 2 / 87) < 0.01

    def test_to_dict(self) -> None:
        snap = FNRFPRSnapshot(
            true_positives=8, false_positives=2, true_negatives=85, false_negatives=5
        )
        d = snap.to_dict()
        assert d["true_positives"] == 8
        assert d["false_positives"] == 2
        assert "fnr" in d
        assert "fpr" in d
