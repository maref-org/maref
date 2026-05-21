"""Unit tests for the MAREF DriftGuard pipeline."""

import asyncio
from datetime import datetime

import numpy as np
import pytest

from drift_guard.metrics import (
    DriftMetricsCollector,
    compute_drift_metrics,
    hellinger_distance,
    js_divergence,
    kl_divergence,
    weights_to_distribution,
)
from drift_guard.pipeline import (
    BaseModelReset,
    DriftDetectionPipeline,
    HumanArbitrationGate,
)
from drift_guard.types import (
    DriftAction,
    DriftEvent,
    DriftReading,
    DriftSeverity,
    GateStatus,
    ModelSignature,
    PipelineConfig,
)


class TestKLDivergence:
    """Tests for KL divergence computation."""

    def test_identical_distributions(self) -> None:
        p = np.array([0.5, 0.5])
        q = np.array([0.5, 0.5])
        assert kl_divergence(p, q) == pytest.approx(0.0, abs=1e-6)

    def test_different_distributions(self) -> None:
        p = np.array([0.9, 0.1])
        q = np.array([0.1, 0.9])
        kl = kl_divergence(p, q)
        assert kl > 0.0

    def test_non_symmetric(self) -> None:
        # Use highly asymmetric distributions to demonstrate non-symmetry
        p = np.array([0.95, 0.03, 0.02])
        q = np.array([0.05, 0.3, 0.65])
        kl_pq = kl_divergence(p, q)
        kl_qp = kl_divergence(q, p)
        # KL is non-symmetric: D_KL(P||Q) != D_KL(Q||P)
        assert kl_pq > 0
        assert kl_qp > 0
        assert abs(kl_pq - kl_qp) > 0.001


class TestJSDivergence:
    """Tests for JS divergence computation."""

    def test_identical_distributions(self) -> None:
        p = np.array([0.5, 0.5])
        q = np.array([0.5, 0.5])
        assert js_divergence(p, q) == pytest.approx(0.0, abs=1e-6)

    def test_symmetric(self) -> None:
        p = np.array([0.7, 0.3])
        q = np.array([0.3, 0.7])
        js_pq = js_divergence(p, q)
        js_qp = js_divergence(q, p)
        assert js_pq == pytest.approx(js_qp, abs=1e-6)

    def test_bounded(self) -> None:
        p = np.array([0.9, 0.1])
        q = np.array([0.1, 0.9])
        js = js_divergence(p, q)
        assert 0.0 <= js <= np.log(2)


class TestHellingerDistance:
    """Tests for Hellinger distance computation."""

    def test_identical_distributions(self) -> None:
        p = np.array([0.5, 0.5])
        q = np.array([0.5, 0.5])
        assert hellinger_distance(p, q) == pytest.approx(0.0, abs=1e-6)

    def test_max_distance(self) -> None:
        p = np.array([1.0, 0.0])
        q = np.array([0.0, 1.0])
        h = hellinger_distance(p, q)
        assert h == pytest.approx(1.0, abs=1e-6)

    def test_bounded(self) -> None:
        p = np.array([0.7, 0.3])
        q = np.array([0.3, 0.7])
        h = hellinger_distance(p, q)
        assert 0.0 <= h <= 1.0


class TestWeightsToDistribution:
    """Tests for weight distribution conversion."""

    def test_basic_conversion(self) -> None:
        weights = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        dist = weights_to_distribution(weights, num_bins=5)
        assert len(dist) == 5
        assert np.sum(dist) == pytest.approx(1.0, abs=1e-6)
        assert np.all(dist >= 0)

    def test_empty_weights(self) -> None:
        weights = np.array([])
        dist = weights_to_distribution(weights, num_bins=5)
        assert len(dist) == 5
        assert np.sum(dist) == pytest.approx(1.0, abs=1e-6)


class TestComputeDriftMetrics:
    """Tests for drift metrics computation."""

    def test_identical_weights(self) -> None:
        weights = np.random.randn(100)
        metrics = compute_drift_metrics(weights, weights)
        assert metrics["kl_divergence"] < 0.1
        assert metrics["js_divergence"] < 0.1
        assert metrics["hellinger_distance"] < 0.1

    def test_different_weights(self) -> None:
        baseline = np.random.randn(100)
        current = np.random.randn(100) + 5.0  # Shifted distribution
        metrics = compute_drift_metrics(baseline, current)
        assert metrics["kl_divergence"] > 0.1
        assert metrics["hellinger_distance"] > 0.1


class TestDriftMetricsCollector:
    """Tests for drift metrics collector."""

    def test_record_and_history(self) -> None:
        collector = DriftMetricsCollector()
        collector.record({"kl_divergence": 0.1, "hellinger_distance": 0.2})
        collector.record({"kl_divergence": 0.2, "hellinger_distance": 0.3})
        history = collector.get_history()
        assert len(history) == 2

    def test_window_size(self) -> None:
        collector = DriftMetricsCollector(window_size=3)
        for i in range(5):
            collector.record({"kl_divergence": float(i) * 0.1})
        history = collector.get_history()
        assert len(history) == 3

    def test_trend_increasing(self) -> None:
        collector = DriftMetricsCollector()
        for i in range(10):
            collector.record({"kl_divergence": float(i) * 0.1})
        assert collector.is_increasing("kl_divergence")

    def test_trend_decreasing(self) -> None:
        collector = DriftMetricsCollector()
        for i in range(10):
            collector.record({"kl_divergence": 1.0 - float(i) * 0.1})
        assert not collector.is_increasing("kl_divergence")


class TestHumanArbitrationGate:
    """Tests for human arbitration gate."""

    @pytest.fixture
    def gate(self) -> HumanArbitrationGate:
        return HumanArbitrationGate(timeout_seconds=1.0)

    @pytest.fixture
    def low_event(self) -> DriftEvent:
        return DriftEvent(
            event_id="test-1",
            timestamp=datetime.now(),
            reading=DriftReading(
                timestamp=datetime.now(),
                kl_divergence=0.05,
                js_divergence=0.03,
                hellinger_distance=0.1,
                severity=DriftSeverity.LOW,
                threshold=0.5,
                model=ModelSignature("model", "v1"),
                baseline=ModelSignature("base", "v1"),
            ),
            action_taken=DriftAction.ALERT,
            gate_status=GateStatus.PENDING_REVIEW,
            reason="test",
        )

    @pytest.fixture
    def high_event(self) -> DriftEvent:
        return DriftEvent(
            event_id="test-2",
            timestamp=datetime.now(),
            reading=DriftReading(
                timestamp=datetime.now(),
                kl_divergence=0.6,
                js_divergence=0.4,
                hellinger_distance=0.6,
                severity=DriftSeverity.HIGH,
                threshold=0.5,
                model=ModelSignature("model", "v1"),
                baseline=ModelSignature("base", "v1"),
            ),
            action_taken=DriftAction.BASE_RESET,
            gate_status=GateStatus.PENDING_REVIEW,
            reason="test",
        )

    @pytest.mark.asyncio
    async def test_auto_approve_low(self, gate: HumanArbitrationGate, low_event: DriftEvent) -> None:
        status = await gate.submit(low_event)
        assert status == GateStatus.AUTO

    @pytest.mark.asyncio
    async def test_human_approve(self, gate: HumanArbitrationGate, high_event: DriftEvent) -> None:
        task = asyncio.create_task(gate.submit(high_event))
        await asyncio.sleep(0.1)
        gate.approve(high_event.event_id)
        status = await task
        assert status == GateStatus.APPROVED

    @pytest.mark.asyncio
    async def test_human_reject(self, gate: HumanArbitrationGate, high_event: DriftEvent) -> None:
        task = asyncio.create_task(gate.submit(high_event))
        await asyncio.sleep(0.1)
        gate.reject(high_event.event_id)
        status = await task
        assert status == GateStatus.REJECTED

    @pytest.mark.asyncio
    async def test_timeout(self, gate: HumanArbitrationGate, high_event: DriftEvent) -> None:
        status = await gate.submit(high_event)
        assert status == GateStatus.TIMEOUT


class TestBaseModelReset:
    """Tests for base model reset mechanism."""

    @pytest.fixture
    def reset(self) -> BaseModelReset:
        return BaseModelReset(cooldown_seconds=0.5)

    @pytest.mark.asyncio
    async def test_first_reset(self, reset: BaseModelReset) -> None:
        result = await reset.reset(
            ModelSignature("model", "v1"),
            ModelSignature("base", "v1"),
        )
        assert result is True
        assert reset.get_stats()["reset_count"] == 1

    @pytest.mark.asyncio
    async def test_cooldown(self, reset: BaseModelReset) -> None:
        await reset.reset(ModelSignature("model", "v1"), ModelSignature("base", "v1"))
        result = await reset.reset(
            ModelSignature("model", "v1"),
            ModelSignature("base", "v1"),
        )
        assert result is False

    def test_can_reset_initially(self, reset: BaseModelReset) -> None:
        assert reset.can_reset() is True


class TestDriftDetectionPipeline:
    """Tests for the full drift detection pipeline."""

    @pytest.fixture
    def pipeline(self) -> DriftDetectionPipeline:
        config = PipelineConfig(
            kl_warning=0.1,
            kl_critical=0.5,
            kl_max=1.0,
            hellinger_warning=0.2,
            hellinger_critical=0.5,
            review_timeout_seconds=1.0,
        )
        return DriftDetectionPipeline(config)

    @pytest.mark.asyncio
    async def test_no_drift(self, pipeline: DriftDetectionPipeline) -> None:
        weights = np.random.randn(100)
        event = await pipeline.check_drift(
            baseline_weights=weights,
            current_weights=weights,
            model=ModelSignature("model", "v1"),
            baseline=ModelSignature("base", "v1"),
        )
        assert event is None

    @pytest.mark.asyncio
    async def test_low_drift(self, pipeline: DriftDetectionPipeline) -> None:
        # Use very similar distributions to trigger LOW severity
        np.random.seed(42)
        baseline = np.random.randn(1000)
        current = baseline + np.random.randn(1000) * 0.05  # Tiny noise
        event = await pipeline.check_drift(
            baseline_weights=baseline,
            current_weights=current,
            model=ModelSignature("model", "v1"),
            baseline=ModelSignature("base", "v1"),
        )
        assert event is not None
        assert event.reading.severity in (DriftSeverity.LOW, DriftSeverity.MEDIUM)
        assert event.action_taken in (DriftAction.ALERT, DriftAction.QUARANTINE)

    @pytest.mark.asyncio
    async def test_critical_drift(self, pipeline: DriftDetectionPipeline) -> None:
        baseline = np.random.randn(100)
        current = np.random.randn(100) + 10.0  # Large shift
        event = await pipeline.check_drift(
            baseline_weights=baseline,
            current_weights=current,
            model=ModelSignature("model", "v1"),
            baseline=ModelSignature("base", "v1"),
        )
        assert event is not None
        assert event.reading.severity == DriftSeverity.CRITICAL
        assert event.action_taken == DriftAction.EMERGENCY_HALT

    def test_get_events(self, pipeline: DriftDetectionPipeline) -> None:
        assert len(pipeline.get_events()) == 0

    def test_get_stats(self, pipeline: DriftDetectionPipeline) -> None:
        stats = pipeline.get_stats()
        assert "total_events" in stats
        assert "config" in stats
        assert stats["total_events"] == 0
