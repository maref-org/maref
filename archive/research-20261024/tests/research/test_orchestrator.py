"""
MAREF Experiment Orchestrator Tests

Comprehensive tests for orchestrator.py
"""
from __future__ import annotations

import random
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from research.experiment_registry import ExperimentMetadata, ExperimentRegistry
from research.orchestrator import ExperimentOrchestrator, StoppingCriteria
from research.vector_store import SearchResult, VectorKnowledgeStore


class TestStoppingCriteria:
    """Tests for StoppingCriteria dataclass."""

    def test_default_values(self) -> None:
        """Test default values for StoppingCriteria."""
        criteria = StoppingCriteria()
        assert criteria.max_consecutive_no_findings == 5
        assert criteria.min_novelty_threshold == 0.1
        assert criteria.max_experiments_per_batch == 100
        assert criteria.min_experiments_per_batch == 10

    def test_custom_values(self) -> None:
        """Test StoppingCriteria with custom values."""
        criteria = StoppingCriteria(
            max_consecutive_no_findings=10,
            min_novelty_threshold=0.2,
            max_experiments_per_batch=200,
            min_experiments_per_batch=20,
        )
        assert criteria.max_consecutive_no_findings == 10
        assert criteria.min_novelty_threshold == 0.2
        assert criteria.max_experiments_per_batch == 200
        assert criteria.min_experiments_per_batch == 20

    def test_edge_case_zero_values(self) -> None:
        """Test StoppingCriteria with zero values."""
        criteria = StoppingCriteria(
            max_consecutive_no_findings=0,
            min_novelty_threshold=0.0,
            max_experiments_per_batch=0,
            min_experiments_per_batch=0,
        )
        assert criteria.max_consecutive_no_findings == 0
        assert criteria.min_novelty_threshold == 0.0
        assert criteria.max_experiments_per_batch == 0
        assert criteria.min_experiments_per_batch == 0

    def test_edge_case_negative_values(self) -> None:
        """Test StoppingCriteria with negative values (allowed by dataclass)."""
        criteria = StoppingCriteria(
            max_consecutive_no_findings=-1,
            min_novelty_threshold=-0.5,
            max_experiments_per_batch=-10,
            min_experiments_per_batch=-5,
        )
        assert criteria.max_consecutive_no_findings == -1
        assert criteria.min_novelty_threshold == -0.5
        assert criteria.max_experiments_per_batch == -10
        assert criteria.min_experiments_per_batch == -5

    def test_partial_custom_values(self) -> None:
        """Test StoppingCriteria with partial custom values."""
        criteria = StoppingCriteria(max_consecutive_no_findings=3)
        assert criteria.max_consecutive_no_findings == 3
        assert criteria.min_novelty_threshold == 0.1
        assert criteria.max_experiments_per_batch == 100
        assert criteria.min_experiments_per_batch == 10

    def test_repr(self) -> None:
        """Test string representation."""
        criteria = StoppingCriteria()
        repr_str = repr(criteria)
        assert "StoppingCriteria" in repr_str
        assert "max_consecutive_no_findings=5" in repr_str


class TestExperimentOrchestratorInit:
    """Tests for ExperimentOrchestrator initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization creates internal objects."""
        orchestrator = ExperimentOrchestrator()
        assert orchestrator._registry is not None
        assert isinstance(orchestrator._registry, ExperimentRegistry)
        assert orchestrator._criteria is not None
        assert isinstance(orchestrator._criteria, StoppingCriteria)
        assert orchestrator._consecutive_no_findings == 0
        assert orchestrator._batch_results == []
        assert orchestrator._vector_store is None

    def test_custom_registry(self) -> None:
        """Test initialization with custom registry."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        assert orchestrator._registry is registry

    def test_custom_criteria(self) -> None:
        """Test initialization with custom criteria."""
        criteria = StoppingCriteria(max_consecutive_no_findings=3)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        assert orchestrator._criteria is criteria
        assert orchestrator._criteria.max_consecutive_no_findings == 3

    def test_custom_vector_store(self) -> None:
        """Test initialization with custom vector store."""
        store = MagicMock(spec=VectorKnowledgeStore)
        orchestrator = ExperimentOrchestrator(vector_store=store)
        assert orchestrator._vector_store is store

    def test_all_none_parameters(self) -> None:
        """Test initialization with all None parameters."""
        orchestrator = ExperimentOrchestrator(
            registry=None, criteria=None, vector_store=None
        )
        assert isinstance(orchestrator._registry, ExperimentRegistry)
        assert isinstance(orchestrator._criteria, StoppingCriteria)
        assert orchestrator._vector_store is None

    def test_all_custom_parameters(self) -> None:
        """Test initialization with all custom parameters."""
        registry = MagicMock(spec=ExperimentRegistry)
        criteria = MagicMock(spec=StoppingCriteria)
        store = MagicMock(spec=VectorKnowledgeStore)
        orchestrator = ExperimentOrchestrator(
            registry=registry, criteria=criteria, vector_store=store
        )
        assert orchestrator._registry is registry
        assert orchestrator._criteria is criteria
        assert orchestrator._vector_store is store


class TestSelectNextExperiment:
    """Tests for select_next_experiment method."""

    def test_empty_registry(self) -> None:
        """Test selection when registry has no metadata."""
        registry = MagicMock(spec=ExperimentRegistry)
        registry.get_all_metadata.return_value = {}
        orchestrator = ExperimentOrchestrator(registry=registry)

        name, func = orchestrator.select_next_experiment()
        assert name == "random_walk"
        assert func is None

    def test_single_experiment(self) -> None:
        """Test selection with a single experiment."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta = ExperimentMetadata(
            name="test_exp",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
        )
        registry.get_all_metadata.return_value = {"test_exp": meta}
        registry.get_experiment.return_value = (lambda x: x, meta)

        orchestrator = ExperimentOrchestrator(registry=registry)
        name, func = orchestrator.select_next_experiment()
        assert name == "test_exp"
        assert func is not None

    def test_weighted_selection(self) -> None:
        """Test weighted selection based on scores."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta1 = ExperimentMetadata(
            name="exp1",
            phase=8,
            description="Test 1",
            expected_duration_ms=100.0,
            novelty_score=1.0,
        )
        meta2 = ExperimentMetadata(
            name="exp2",
            phase=8,
            description="Test 2",
            expected_duration_ms=100.0,
            novelty_score=0.1,
        )
        registry.get_all_metadata.return_value = {"exp1": meta1, "exp2": meta2}
        registry.get_experiment.return_value = (lambda x: x, meta1)

        orchestrator = ExperimentOrchestrator(registry=registry)

        # Patch random.uniform to force selection of exp1
        with patch("research.orchestrator.random.uniform", return_value=0.5):
            with patch("research.orchestrator.random.choice") as mock_choice:
                name, _ = orchestrator.select_next_experiment()
                assert name == "exp1"
                mock_choice.assert_not_called()

    def test_zero_total_score_random_selection(self) -> None:
        """Test random selection when all scores are zero."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta = ExperimentMetadata(
            name="exp1",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        registry.get_all_metadata.return_value = {"exp1": meta}
        registry.get_experiment.return_value = (lambda x: x, meta)

        orchestrator = ExperimentOrchestrator(registry=registry)

        # Force _compute_score to return 0 for all experiments
        with patch.object(orchestrator, "_compute_score", return_value=0.0):
            with patch("research.orchestrator.random.choice", return_value="exp1") as mock_choice:
                name, _ = orchestrator.select_next_experiment()
                assert name == "exp1"
                mock_choice.assert_called_once()

    def test_experiment_not_found_after_selection(self) -> None:
        """Test when selected experiment is not found in registry."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta = ExperimentMetadata(
            name="exp1",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
        )
        registry.get_all_metadata.return_value = {"exp1": meta}
        registry.get_experiment.return_value = None

        orchestrator = ExperimentOrchestrator(registry=registry)
        name, func = orchestrator.select_next_experiment()
        assert name == "exp1"
        assert func is None

    def test_multiple_experiments_cumulative_selection(self) -> None:
        """Test cumulative selection across multiple experiments."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta1 = ExperimentMetadata(
            name="exp1",
            phase=8,
            description="Test 1",
            expected_duration_ms=100.0,
            novelty_score=0.5,
        )
        meta2 = ExperimentMetadata(
            name="exp2",
            phase=8,
            description="Test 2",
            expected_duration_ms=100.0,
            novelty_score=0.5,
        )
        registry.get_all_metadata.return_value = {"exp1": meta1, "exp2": meta2}
        registry.get_experiment.return_value = (lambda x: x, meta1)

        orchestrator = ExperimentOrchestrator(registry=registry)

        # Force _compute_score to return known values for predictable selection
        def mock_score(meta):
            if meta.name == "exp1":
                return 1.0
            return 2.0

        with patch.object(orchestrator, "_compute_score", side_effect=mock_score):
            # total_score = 3.0; r=2.5 > cumulative_after_exp1 (1.0), so select exp2
            with patch("research.orchestrator.random.uniform", return_value=2.5):
                name, _ = orchestrator.select_next_experiment()
                assert name == "exp2"

    def test_multiple_experiments_cumulative_selects_first(self) -> None:
        """Test cumulative selection selects first experiment."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta1 = ExperimentMetadata(
            name="exp1",
            phase=8,
            description="Test 1",
            expected_duration_ms=100.0,
            novelty_score=0.5,
        )
        meta2 = ExperimentMetadata(
            name="exp2",
            phase=8,
            description="Test 2",
            expected_duration_ms=100.0,
            novelty_score=0.5,
        )
        registry.get_all_metadata.return_value = {"exp1": meta1, "exp2": meta2}
        registry.get_experiment.return_value = (lambda x: x, meta1)

        orchestrator = ExperimentOrchestrator(registry=registry)

        def mock_score(meta):
            if meta.name == "exp1":
                return 1.0
            return 2.0

        with patch.object(orchestrator, "_compute_score", side_effect=mock_score):
            # total_score = 3.0; r=0.5 < cumulative_after_exp1 (1.0), so select exp1
            with patch("research.orchestrator.random.uniform", return_value=0.5):
                name, _ = orchestrator.select_next_experiment()
                assert name == "exp1"

    def test_select_next_experiment_with_real_registry(self) -> None:
        """Test with a real ExperimentRegistry."""
        registry = ExperimentRegistry()
        orchestrator = ExperimentOrchestrator(registry=registry)
        name, func = orchestrator.select_next_experiment()
        assert isinstance(name, str)
        assert name in registry.list_experiments()


class TestComputeScore:
    """Tests for _compute_score method."""

    def test_base_score_novelty(self) -> None:
        """Test base score from novelty."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.5,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        assert score >= 0.1
        # novelty * 2.0 = 1.0
        assert score >= 1.0

    def test_success_rate_bonus(self) -> None:
        """Test success rate bonus."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=1.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        # success_rate * 1.5 = 1.5
        assert score >= 1.5

    def test_recency_bonus_not_run_recently(self) -> None:
        """Test recency bonus when not run in last hour."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time() - 7200.0,  # 2 hours ago
        )
        score = orchestrator._compute_score(meta)
        # Should include recency bonus of 0.5
        assert score >= 0.5

    def test_recency_bonus_run_recently(self) -> None:
        """Test no recency bonus when run recently."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),  # Just now
        )
        score = orchestrator._compute_score(meta)
        # Should NOT include recency bonus
        assert score < 0.5

    def test_phase_bonus(self) -> None:
        """Test phase bonus."""
        orchestrator = ExperimentOrchestrator()
        meta_low = ExperimentMetadata(
            name="test_low",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        meta_high = ExperimentMetadata(
            name="test_high",
            phase=10,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score_low = orchestrator._compute_score(meta_low)
        score_high = orchestrator._compute_score(meta_high)
        assert score_high > score_low
        # phase bonus difference: (10-8) * 0.05 = 0.1
        assert score_high == pytest.approx(score_low + 0.1, abs=1e-9)

    def test_run_count_penalty(self) -> None:
        """Test penalty for experiments run too frequently."""
        orchestrator = ExperimentOrchestrator()
        meta_low = ExperimentMetadata(
            name="test_low",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
            run_count=10,
        )
        meta_high = ExperimentMetadata(
            name="test_high",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
            run_count=60,
        )
        score_low = orchestrator._compute_score(meta_low)
        score_high = orchestrator._compute_score(meta_high)
        # High run count should be penalized (0.8 multiplier)
        assert score_high == pytest.approx(score_low * 0.8, abs=1e-9)

    def test_minimum_score_floor(self) -> None:
        """Test that score is floored at 0.1."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        # Even with zero novelty/success, phase bonus gives 8*0.05=0.4
        # The max(0.1, ...) floor means score is at least 0.1
        assert score >= 0.1

    def test_minimum_score_floor_with_zero_phase(self) -> None:
        """Test that score is floored at 0.1 with phase=0."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=0,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        assert score == 0.1

    def test_vector_store_novelty_high_similarity(self) -> None:
        """Test semantic novelty with high similarity (low novelty)."""
        store = MagicMock(spec=VectorKnowledgeStore)
        store.count.return_value = 10
        # High similarity = low distance (close to 0) = low novelty
        store.search.return_value = [
            MagicMock(score=0.1),
            MagicMock(score=0.2),
            MagicMock(score=0.3),
        ]

        orchestrator = ExperimentOrchestrator(vector_store=store)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test description",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score_without_store = ExperimentOrchestrator()._compute_score(meta)
        score_with_store = orchestrator._compute_score(meta)

        # avg_distance = (0.1+0.2+0.3)/3 = 0.2
        # novelty = 0.2/2.0 = 0.1
        # multiplier = 0.5 + 0.5 * 0.1 = 0.55
        # Score should be lower due to high similarity
        assert score_with_store < score_without_store
        store.search.assert_called_once_with("Test description", n_results=3)

    def test_vector_store_novelty_low_similarity(self) -> None:
        """Test semantic novelty with low similarity (high novelty)."""
        store = MagicMock(spec=VectorKnowledgeStore)
        store.count.return_value = 10
        # Low similarity = high distance (close to 2) = high novelty
        store.search.return_value = [
            MagicMock(score=1.8),
            MagicMock(score=1.9),
            MagicMock(score=2.0),
        ]

        orchestrator = ExperimentOrchestrator(vector_store=store)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test description",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score_without_store = ExperimentOrchestrator()._compute_score(meta)
        score_with_store = orchestrator._compute_score(meta)

        # avg_distance = (1.8+1.9+2.0)/3 = 1.9
        # novelty = 1.9/2.0 = 0.95
        # multiplier = 0.5 + 0.5 * 0.95 = 0.975
        # Score should be close to original
        assert score_with_store == pytest.approx(score_without_store * 0.975, abs=1e-9)

    def test_vector_store_no_results(self) -> None:
        """Test when vector store returns no results."""
        store = MagicMock(spec=VectorKnowledgeStore)
        store.count.return_value = 10
        store.search.return_value = []

        orchestrator = ExperimentOrchestrator(vector_store=store)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        # No results means no novelty adjustment
        assert score >= 2.0  # novelty_score * 2.0 = 2.0

    def test_vector_store_count_too_low(self) -> None:
        """Test that semantic check is skipped when store count <= 5."""
        store = MagicMock(spec=VectorKnowledgeStore)
        store.count.return_value = 5

        orchestrator = ExperimentOrchestrator(vector_store=store)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=1.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        store.search.assert_not_called()
        assert score >= 2.0

    def test_vector_store_none(self) -> None:
        """Test that score is computed without vector store."""
        orchestrator = ExperimentOrchestrator(vector_store=None)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.5,
            success_rate=0.5,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        # novelty * 2.0 + success_rate * 1.5 = 1.0 + 0.75 = 1.75
        assert score >= 1.75

    def test_combined_score_calculation(self) -> None:
        """Test combined score with all factors."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=10,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.5,
            success_rate=0.5,
            last_run=time.time() - 7200.0,
            run_count=60,
        )
        score = orchestrator._compute_score(meta)
        # Base: 0.5*2.0 + 0.5*1.5 + 0.5(recency) + 10*0.05 = 1.0 + 0.75 + 0.5 + 0.5 = 2.75
        # After penalty: 2.75 * 0.8 = 2.2
        assert score == pytest.approx(2.2, abs=1e-9)


class TestShouldStop:
    """Tests for should_stop method."""

    def test_default_should_stop(self) -> None:
        """Test should_stop with default state."""
        orchestrator = ExperimentOrchestrator()
        assert orchestrator.should_stop() is False

    def test_consecutive_no_findings_exceeded(self) -> None:
        """Test stopping when consecutive no findings exceeds max."""
        criteria = StoppingCriteria(max_consecutive_no_findings=3)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._consecutive_no_findings = 3
        assert orchestrator.should_stop() is True

    def test_consecutive_no_findings_below_max(self) -> None:
        """Test not stopping when consecutive no findings below max."""
        criteria = StoppingCriteria(max_consecutive_no_findings=5)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._consecutive_no_findings = 4
        assert orchestrator.should_stop() is False

    def test_batch_size_exceeds_max(self) -> None:
        """Test stopping when batch size exceeds max."""
        criteria = StoppingCriteria(max_experiments_per_batch=5)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._batch_results = [MagicMock() for _ in range(5)]
        assert orchestrator.should_stop() is True

    def test_batch_size_below_max(self) -> None:
        """Test not stopping when batch size below max."""
        criteria = StoppingCriteria(max_experiments_per_batch=100)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # Use objects with explicit novelty attribute to avoid MagicMock comparison issues
        orchestrator._batch_results = [
            type("Result", (), {"novelty": 0.5})() for _ in range(50)
        ]
        assert orchestrator.should_stop() is False

    def test_min_batch_size_not_met(self) -> None:
        """Test not stopping when min batch size not met."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=10,
            max_consecutive_no_findings=200,
            max_experiments_per_batch=200,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._batch_results = [
            type("Result", (), {"novelty": 0.5})() for _ in range(5)
        ]
        orchestrator._consecutive_no_findings = 100  # Would stop if min met
        assert orchestrator.should_stop() is False

    def test_average_novelty_below_threshold(self) -> None:
        """Test stopping when average novelty is below threshold."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.5,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # Create results with low novelty
        low_novelty_results = [MagicMock(novelty=0.1) for _ in range(10)]
        orchestrator._batch_results = low_novelty_results
        assert orchestrator.should_stop() is True

    def test_average_novelty_above_threshold(self) -> None:
        """Test not stopping when average novelty is above threshold."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.1,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # Create results with high novelty
        high_novelty_results = [MagicMock(novelty=0.8) for _ in range(10)]
        orchestrator._batch_results = high_novelty_results
        assert orchestrator.should_stop() is False

    def test_empty_batch_results(self) -> None:
        """Test should_stop with empty batch results."""
        orchestrator = ExperimentOrchestrator()
        assert orchestrator.should_stop() is False

    def test_result_without_novelty_attribute(self) -> None:
        """Test handling results without novelty attribute."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.6,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # Results without novelty attribute default to 0.5 via getattr default
        results = [type("Result", (), {})() for _ in range(10)]
        orchestrator._batch_results = results
        # Average novelty = 0.5 < 0.6, should stop
        assert orchestrator.should_stop() is True

    def test_result_with_novelty_attribute_none(self) -> None:
        """Test handling results with None novelty."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.6,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # Create objects with novelty=None explicitly
        results = [type("Result", (), {"novelty": None})() for _ in range(10)]
        orchestrator._batch_results = results
        # getattr(result, "novelty", 0.5) returns None, then sum([None, ...]) fails
        # This is an edge case in the source code; test documents the behavior
        with pytest.raises(TypeError):
            orchestrator.should_stop()

    def test_exact_threshold_boundary(self) -> None:
        """Test exact threshold boundary condition."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.5,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        results = [MagicMock(novelty=0.5) for _ in range(10)]
        orchestrator._batch_results = results
        # avg_novelty == threshold, should NOT stop (strict <)
        assert orchestrator.should_stop() is False

    def test_batch_results_less_than_ten(self) -> None:
        """Test novelty check uses last 10 results only."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.5,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # First 5 results have low novelty, next 5 have high
        results = [MagicMock(novelty=0.1) for _ in range(5)]
        results.extend([MagicMock(novelty=0.9) for _ in range(5)])
        orchestrator._batch_results = results
        # Last 10 have avg 0.5, should not stop
        assert orchestrator.should_stop() is False

    def test_batch_results_more_than_ten(self) -> None:
        """Test novelty check only considers last 10 results."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.5,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        # 15 results: first 5 high, next 5 low, last 5 high
        results = [MagicMock(novelty=0.9) for _ in range(5)]
        results.extend([MagicMock(novelty=0.1) for _ in range(5)])
        results.extend([MagicMock(novelty=0.9) for _ in range(5)])
        orchestrator._batch_results = results
        # Last 10 have avg 0.5, should not stop
        assert orchestrator.should_stop() is False


class TestRecordResult:
    """Tests for record_result method."""

    def test_record_result_with_findings(self) -> None:
        """Test recording result with findings."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        result = MagicMock(findings=[1, 2, 3], duration_ms=150.0)

        orchestrator.record_result("test_exp", result)
        assert len(orchestrator._batch_results) == 1
        assert orchestrator._consecutive_no_findings == 0
        registry.update_metadata.assert_called_once_with("test_exp", 3, 150.0)

    def test_record_result_without_findings(self) -> None:
        """Test recording result without findings."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        result = MagicMock(findings=[], duration_ms=100.0)

        orchestrator.record_result("test_exp", result)
        assert len(orchestrator._batch_results) == 1
        assert orchestrator._consecutive_no_findings == 1
        registry.update_metadata.assert_called_once_with("test_exp", 0, 100.0)

    def test_consecutive_no_findings_accumulation(self) -> None:
        """Test consecutive no findings counter accumulation."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        result = MagicMock(findings=[], duration_ms=100.0)
        for i in range(3):
            orchestrator.record_result("test_exp", result)
            assert orchestrator._consecutive_no_findings == i + 1

    def test_consecutive_no_findings_reset(self) -> None:
        """Test consecutive no findings counter reset on findings."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        # Record 2 without findings
        no_finding_result = MagicMock(findings=[], duration_ms=100.0)
        orchestrator.record_result("test_exp", no_finding_result)
        orchestrator.record_result("test_exp", no_finding_result)
        assert orchestrator._consecutive_no_findings == 2

        # Record with findings - should reset
        finding_result = MagicMock(findings=[1], duration_ms=150.0)
        orchestrator.record_result("test_exp", finding_result)
        assert orchestrator._consecutive_no_findings == 0

    def test_record_result_without_findings_attribute(self) -> None:
        """Test recording result without findings attribute."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        result = MagicMock(duration_ms=100.0)
        del result.findings

        orchestrator.record_result("test_exp", result)
        assert len(orchestrator._batch_results) == 1
        assert orchestrator._consecutive_no_findings == 1
        registry.update_metadata.assert_called_once_with("test_exp", 0, 100.0)

    def test_record_result_without_duration_attribute(self) -> None:
        """Test recording result without duration attribute."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        result = MagicMock(findings=[1])
        del result.duration_ms

        orchestrator.record_result("test_exp", result)
        registry.update_metadata.assert_called_once_with("test_exp", 1, 100.0)

    def test_record_result_batch_growth(self) -> None:
        """Test batch results grow with each record."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        for i in range(5):
            result = MagicMock(findings=[1], duration_ms=100.0)
            orchestrator.record_result("test_exp", result)
            assert len(orchestrator._batch_results) == i + 1


class TestResetBatch:
    """Tests for reset_batch method."""

    def test_reset_clears_state(self) -> None:
        """Test reset clears all batch state."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        # Add some state
        orchestrator._consecutive_no_findings = 5
        orchestrator._batch_results = [MagicMock(), MagicMock()]

        orchestrator.reset_batch()
        assert orchestrator._consecutive_no_findings == 0
        assert orchestrator._batch_results == []

    def test_reset_on_empty_batch(self) -> None:
        """Test reset on already empty batch."""
        orchestrator = ExperimentOrchestrator()
        orchestrator.reset_batch()
        assert orchestrator._consecutive_no_findings == 0
        assert orchestrator._batch_results == []


class TestGetStats:
    """Tests for get_stats method."""

    def test_empty_stats(self) -> None:
        """Test stats with empty state."""
        orchestrator = ExperimentOrchestrator()
        stats = orchestrator.get_stats()
        assert stats["batch_size"] == 0
        assert stats["consecutive_no_findings"] == 0
        assert stats["should_stop"] is False
        assert stats["experiment_scores"] == {}

    def test_stats_with_results(self) -> None:
        """Test stats with batch results."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        orchestrator._batch_results = [MagicMock(), MagicMock()]
        orchestrator._consecutive_no_findings = 3

        stats = orchestrator.get_stats()
        assert stats["batch_size"] == 2
        assert stats["consecutive_no_findings"] == 3

    def test_stats_with_experiment_scores(self) -> None:
        """Test stats include experiment scores for run experiments."""
        meta = ExperimentMetadata(
            name="test_exp",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            run_count=1,
            last_run=time.time(),
        )
        registry = MagicMock(spec=ExperimentRegistry)
        registry.get_all_metadata.return_value = {"test_exp": meta}
        orchestrator = ExperimentOrchestrator(registry=registry)

        stats = orchestrator.get_stats()
        assert "test_exp" in stats["experiment_scores"]
        assert stats["experiment_scores"]["test_exp"] > 0

    def test_stats_filters_zero_run_count(self) -> None:
        """Test stats filter out experiments with run_count == 0."""
        meta = ExperimentMetadata(
            name="test_exp",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            run_count=0,
        )
        registry = MagicMock(spec=ExperimentRegistry)
        registry.get_all_metadata.return_value = {"test_exp": meta}
        orchestrator = ExperimentOrchestrator(registry=registry)

        stats = orchestrator.get_stats()
        assert "test_exp" not in stats["experiment_scores"]

    def test_stats_calls_should_stop(self) -> None:
        """Test that stats includes should_stop value."""
        orchestrator = ExperimentOrchestrator()
        with patch.object(orchestrator, "should_stop", return_value=True) as mock_should_stop:
            stats = orchestrator.get_stats()
            assert stats["should_stop"] is True
            mock_should_stop.assert_called_once()


class TestOrchestratorIntegration:
    """Integration-style tests for orchestrator workflow."""

    def test_full_batch_workflow(self) -> None:
        """Test a full batch workflow: select, record, check stop."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta = ExperimentMetadata(
            name="test_exp",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
        )
        registry.get_all_metadata.return_value = {"test_exp": meta}
        registry.get_experiment.return_value = (lambda x: x, meta)

        criteria = StoppingCriteria(
            max_consecutive_no_findings=2,
            min_experiments_per_batch=1,
            max_experiments_per_batch=5,
        )
        orchestrator = ExperimentOrchestrator(registry=registry, criteria=criteria)

        # Run experiments until stop
        for _ in range(5):
            name, func = orchestrator.select_next_experiment()
            assert name == "test_exp"
            # Use simple object with explicit novelty to avoid MagicMock issues
            result = type("Result", (), {"findings": [], "duration_ms": 100.0, "novelty": 0.5})()
            orchestrator.record_result(name, result)
            if orchestrator.should_stop():
                break

        assert orchestrator._consecutive_no_findings >= 2 or len(orchestrator._batch_results) >= 5

    def test_reset_and_restart(self) -> None:
        """Test reset and restart workflow."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)

        # Run some experiments
        for _ in range(3):
            result = MagicMock(findings=[1], duration_ms=100.0)
            orchestrator.record_result("test_exp", result)

        assert len(orchestrator._batch_results) == 3

        # Reset
        orchestrator.reset_batch()
        assert len(orchestrator._batch_results) == 0
        assert orchestrator._consecutive_no_findings == 0

        # Restart
        result = MagicMock(findings=[1], duration_ms=100.0)
        orchestrator.record_result("test_exp", result)
        assert len(orchestrator._batch_results) == 1

    def test_novelty_driven_stop(self) -> None:
        """Test stopping driven by low novelty."""
        criteria = StoppingCriteria(
            min_experiments_per_batch=1,
            min_novelty_threshold=0.8,
            max_experiments_per_batch=100,
            max_consecutive_no_findings=100,
        )
        orchestrator = ExperimentOrchestrator(criteria=criteria)

        # Add results with low novelty
        for _ in range(5):
            result = MagicMock(novelty=0.1)
            orchestrator._batch_results.append(result)

        assert orchestrator.should_stop() is True

    def test_batch_size_driven_stop(self) -> None:
        """Test stopping driven by batch size."""
        criteria = StoppingCriteria(max_experiments_per_batch=3)
        orchestrator = ExperimentOrchestrator(criteria=criteria)

        for _ in range(3):
            result = MagicMock()
            orchestrator._batch_results.append(result)

        assert orchestrator.should_stop() is True


class TestEdgeCases:
    """Edge case tests."""

    def test_compute_score_with_extreme_phase(self) -> None:
        """Test compute score with very high phase."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=100,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        score = orchestrator._compute_score(meta)
        # Phase bonus = 100 * 0.05 = 5.0
        assert score >= 5.0

    def test_compute_score_with_very_old_last_run(self) -> None:
        """Test compute score with very old last_run."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=0.0,  # Epoch
        )
        score = orchestrator._compute_score(meta)
        # Should still get recency bonus
        assert score >= 0.5

    def test_compute_score_with_future_last_run(self) -> None:
        """Test compute score with future last_run."""
        orchestrator = ExperimentOrchestrator()
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time() + 3600.0,  # 1 hour in future
        )
        score = orchestrator._compute_score(meta)
        # time_since_last will be negative, no recency bonus
        assert score < 0.5

    def test_select_with_single_zero_score(self) -> None:
        """Test selection when single experiment has zero score."""
        registry = MagicMock(spec=ExperimentRegistry)
        meta = ExperimentMetadata(
            name="test",
            phase=8,
            description="Test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
            success_rate=0.0,
            last_run=time.time(),
        )
        registry.get_all_metadata.return_value = {"test": meta}
        registry.get_experiment.return_value = (lambda x: x, meta)

        orchestrator = ExperimentOrchestrator(registry=registry)
        with patch("research.orchestrator.random.choice", return_value="test"):
            name, _ = orchestrator.select_next_experiment()
            assert name == "test"

    def test_record_result_with_none_findings(self) -> None:
        """Test recording result with None findings raises TypeError."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        # Create an object with findings=None explicitly
        result = type("Result", (), {"findings": None, "duration_ms": 100.0})()

        # len(None) raises TypeError - this documents a potential edge case
        with pytest.raises(TypeError):
            orchestrator.record_result("test_exp", result)

    def test_should_stop_with_exactly_max_consecutive(self) -> None:
        """Test should_stop at exact max consecutive boundary."""
        criteria = StoppingCriteria(max_consecutive_no_findings=5)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._consecutive_no_findings = 5
        assert orchestrator.should_stop() is True

    def test_should_stop_with_exactly_max_batch_size(self) -> None:
        """Test should_stop at exact max batch size boundary."""
        criteria = StoppingCriteria(max_experiments_per_batch=10)
        orchestrator = ExperimentOrchestrator(criteria=criteria)
        orchestrator._batch_results = [MagicMock() for _ in range(10)]
        assert orchestrator.should_stop() is True

    def test_get_stats_with_none_registry(self) -> None:
        """Test get_stats handles None registry gracefully."""
        # This tests the default initialization path
        orchestrator = ExperimentOrchestrator()
        stats = orchestrator.get_stats()
        assert isinstance(stats, dict)
        assert "batch_size" in stats
        assert "consecutive_no_findings" in stats
        assert "should_stop" in stats
        assert "experiment_scores" in stats

    def test_record_result_with_invalid_experiment_name(self) -> None:
        """Test recording result with invalid experiment name."""
        registry = MagicMock(spec=ExperimentRegistry)
        orchestrator = ExperimentOrchestrator(registry=registry)
        result = MagicMock(findings=[1], duration_ms=100.0)

        orchestrator.record_result("nonexistent", result)
        registry.update_metadata.assert_called_once_with("nonexistent", 1, 100.0)
