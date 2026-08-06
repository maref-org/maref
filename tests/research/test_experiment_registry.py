"""
MAREF Experiment Registry Tests

Comprehensive tests for experiment_registry.py
"""
import time
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research.experiment_registry import ExperimentMetadata, ExperimentRegistry


class TestExperimentMetadata:
    """Tests for ExperimentMetadata dataclass."""

    def test_dataclass_construction(self):
        """Test basic dataclass construction with required fields."""
        meta = ExperimentMetadata(
            name="test_experiment",
            phase=8,
            description="Test experiment description",
            expected_duration_ms=100.0,
        )
        assert meta.name == "test_experiment"
        assert meta.phase == 8
        assert meta.description == "Test experiment description"
        assert meta.expected_duration_ms == 100.0
        assert meta.novelty_score == 0.5
        assert meta.success_rate == 0.8
        assert meta.last_run == 0.0
        assert meta.run_count == 0
        assert meta.finding_count == 0

    def test_dataclass_with_custom_defaults(self):
        """Test dataclass construction with custom default values."""
        meta = ExperimentMetadata(
            name="custom_experiment",
            phase=9,
            description="Custom experiment",
            expected_duration_ms=200.0,
            novelty_score=0.7,
            success_rate=0.9,
            last_run=1234567890.0,
            run_count=5,
            finding_count=3,
        )
        assert meta.name == "custom_experiment"
        assert meta.phase == 9
        assert meta.expected_duration_ms == 200.0
        assert meta.novelty_score == 0.7
        assert meta.success_rate == 0.9
        assert meta.last_run == 1234567890.0
        assert meta.run_count == 5
        assert meta.finding_count == 3

    def test_dataclass_immutability(self):
        """Test that dataclass fields can be modified (frozen=False)."""
        meta = ExperimentMetadata(
            name="mutable_experiment",
            phase=8,
            description="Mutable test",
            expected_duration_ms=50.0,
        )
        meta.run_count = 10
        meta.finding_count = 5
        meta.last_run = time.time()
        assert meta.run_count == 10
        assert meta.finding_count == 5
        assert meta.last_run > 0

    def test_dataclass_repr(self):
        """Test dataclass string representation."""
        meta = ExperimentMetadata(
            name="repr_test",
            phase=10,
            description="Repr test",
            expected_duration_ms=150.0,
        )
        repr_str = repr(meta)
        assert "repr_test" in repr_str
        assert "phase=10" in repr_str
        assert "expected_duration_ms=150.0" in repr_str


class TestExperimentRegistry:
    """Tests for ExperimentRegistry class."""

    def test_registry_initialization(self):
        """Test registry initialization with default experiments."""
        registry = ExperimentRegistry()
        assert registry._experiments is not None
        assert len(registry._experiments) > 0

    def test_register_experiment(self):
        """Test registering a new experiment."""
        registry = ExperimentRegistry()
        initial_count = len(registry._experiments)

        async def mock_experiment(exp_id: int) -> Any:
            return {"result": "test"}

        metadata = ExperimentMetadata(
            name="new_experiment",
            phase=8,
            description="New test experiment",
            expected_duration_ms=100.0,
        )

        registry.register("new_experiment", mock_experiment, metadata)
        assert len(registry._experiments) == initial_count + 1
        assert "new_experiment" in registry._experiments

    def test_register_overwrites_existing(self):
        """Test that register overwrites existing experiment."""
        registry = ExperimentRegistry()

        async def mock_experiment1(exp_id: int) -> Any:
            return {"result": "first"}

        async def mock_experiment2(exp_id: int) -> Any:
            return {"result": "second"}

        metadata1 = ExperimentMetadata(
            name="overwrite_test",
            phase=8,
            description="First version",
            expected_duration_ms=100.0,
        )
        metadata2 = ExperimentMetadata(
            name="overwrite_test",
            phase=9,
            description="Second version",
            expected_duration_ms=200.0,
        )

        registry.register("overwrite_test", mock_experiment1, metadata1)
        fn1, meta1 = registry._experiments["overwrite_test"]
        assert meta1.phase == 8

        registry.register("overwrite_test", mock_experiment2, metadata2)
        fn2, meta2 = registry._experiments["overwrite_test"]
        assert meta2.phase == 9
        assert meta2.description == "Second version"

    def test_get_experiment_existing(self):
        """Test getting an existing experiment."""
        registry = ExperimentRegistry()
        result = registry.get_experiment("random_walk")
        assert result is not None
        fn, meta = result
        assert meta.name == "random_walk"
        assert meta.phase == 8
        assert isinstance(fn, Callable)

    def test_get_experiment_nonexistent(self):
        """Test getting a non-existent experiment returns None."""
        registry = ExperimentRegistry()
        result = registry.get_experiment("nonexistent_experiment")
        assert result is None

    def test_list_experiments(self):
        """Test listing all experiment names."""
        registry = ExperimentRegistry()
        experiments = registry.list_experiments()
        assert isinstance(experiments, list)
        assert len(experiments) > 0
        assert "random_walk" in experiments
        assert all(isinstance(name, str) for name in experiments)

    def test_update_metadata_existing(self):
        """Test updating metadata for existing experiment."""
        registry = ExperimentRegistry()
        fn, meta = registry._experiments["random_walk"]

        initial_run_count = meta.run_count
        initial_finding_count = meta.finding_count
        initial_success_rate = meta.success_rate

        registry.update_metadata("random_walk", findings=3, duration_ms=50.0)

        assert meta.run_count == initial_run_count + 1
        assert meta.finding_count == initial_finding_count + 3
        assert meta.last_run > 0
        if meta.run_count > 0:
            expected_success_rate = meta.finding_count / meta.run_count
            assert meta.success_rate == expected_success_rate

    def test_update_metadata_nonexistent(self):
        """Test updating metadata for non-existent experiment does nothing."""
        registry = ExperimentRegistry()
        initial_experiments = dict(registry._experiments)

        registry.update_metadata("nonexistent", findings=5, duration_ms=100.0)

        assert registry._experiments == initial_experiments

    def test_update_metadata_novelty_score_decay(self):
        """Test that novelty score decays after update."""
        registry = ExperimentRegistry()
        fn, meta = registry._experiments["random_walk"]

        initial_novelty = meta.novelty_score
        registry.update_metadata("random_walk", findings=1, duration_ms=50.0)

        assert meta.novelty_score == max(0.1, initial_novelty * 0.95)

    def test_update_metadata_novelty_score_minimum(self):
        """Test that novelty score doesn't go below 0.1."""
        registry = ExperimentRegistry()
        fn, meta = registry._experiments["random_walk"]

        meta.novelty_score = 0.11
        registry.update_metadata("random_walk", findings=1, duration_ms=50.0)

        assert meta.novelty_score == max(0.1, 0.11 * 0.95)

    def test_get_all_metadata(self):
        """Test getting metadata for all experiments."""
        registry = ExperimentRegistry()
        all_metadata = registry.get_all_metadata()

        assert isinstance(all_metadata, dict)
        assert len(all_metadata) == len(registry._experiments)
        assert all(isinstance(name, str) for name in all_metadata.keys())
        assert all(isinstance(meta, ExperimentMetadata) for meta in all_metadata.values())

        for name, meta in all_metadata.items():
            assert meta.name == name

    def test_default_experiments_registered(self):
        """Verify all default experiments are registered."""
        registry = ExperimentRegistry()

        expected_experiments = [
            "random_walk",
            "gray_code_fault_tolerance",
            "self_observation",
            "adaptive_threshold",
            "emergence_detection",
            "policy_lifecycle",
            "rollback_safety",
            "ab_test_winner",
            "degradation_prevention",
            "meta_learning_convergence",
            "weight_stability",
            "recursive_safety",
            "reward_shaping",
        ]

        for exp_name in expected_experiments:
            assert exp_name in registry._experiments
            fn, meta = registry._experiments[exp_name]
            assert meta.name == exp_name
            assert meta.phase in [8, 9, 10]
            assert meta.description
            assert meta.expected_duration_ms > 0

    def test_default_experiment_phases(self):
        """Verify experiments are registered with correct phases."""
        registry = ExperimentRegistry()

        phase8_experiments = ["random_walk", "gray_code_fault_tolerance", "self_observation",
                             "adaptive_threshold", "emergence_detection"]
        phase9_experiments = ["policy_lifecycle", "rollback_safety", "ab_test_winner",
                             "degradation_prevention"]
        phase10_experiments = ["meta_learning_convergence", "weight_stability",
                              "recursive_safety", "reward_shaping"]

        for exp_name in phase8_experiments:
            fn, meta = registry._experiments[exp_name]
            assert meta.phase == 8

        for exp_name in phase9_experiments:
            fn, meta = registry._experiments[exp_name]
            assert meta.phase == 9

        for exp_name in phase10_experiments:
            fn, meta = registry._experiments[exp_name]
            assert meta.phase == 10

    @pytest.mark.asyncio
    async def test_run_methods_are_async(self):
        """Test that all _run_* methods are async functions."""
        registry = ExperimentRegistry()

        run_methods = [
            "_run_random_walk",
            "_run_gray_code_test",
            "_run_self_observation",
            "_run_adaptive_threshold",
            "_run_emergence_detection",
            "_run_policy_lifecycle",
            "_run_rollback_safety",
            "_run_ab_test",
            "_run_degradation_prevention",
            "_run_meta_convergence",
            "_run_weight_stability",
            "_run_recursive_safety",
            "_run_reward_shaping",
        ]

        for method_name in run_methods:
            method = getattr(registry, method_name)
            assert callable(method)

    def test_registry_singleton_pattern_not_enforced(self):
        """Test that registry doesn't enforce singleton pattern (can create multiple)."""
        registry1 = ExperimentRegistry()
        registry2 = ExperimentRegistry()

        assert registry1 is not registry2
        assert registry1._experiments is not registry2._experiments

    def test_empty_registry_after_clear(self):
        """Test that we can create an empty registry for testing."""
        class TestRegistry(ExperimentRegistry):
            def _register_default_experiments(self) -> None:
                pass

        registry = TestRegistry()
        assert len(registry._experiments) == 0
        assert registry.list_experiments() == []

    def test_metadata_edge_cases(self):
        """Test metadata edge cases."""
        # Zero duration
        meta = ExperimentMetadata(
            name="zero_duration",
            phase=8,
            description="Zero duration test",
            expected_duration_ms=0.0,
        )
        assert meta.expected_duration_ms == 0.0

        # Very high duration
        meta = ExperimentMetadata(
            name="long_duration",
            phase=8,
            description="Long duration test",
            expected_duration_ms=1000000.0,
        )
        assert meta.expected_duration_ms == 1000000.0

        # Zero novelty score
        meta = ExperimentMetadata(
            name="zero_novelty",
            phase=8,
            description="Zero novelty test",
            expected_duration_ms=100.0,
            novelty_score=0.0,
        )
        assert meta.novelty_score == 0.0

        # Zero success rate
        meta = ExperimentMetadata(
            name="zero_success",
            phase=8,
            description="Zero success test",
            expected_duration_ms=100.0,
            success_rate=0.0,
        )
        assert meta.success_rate == 0.0

    def test_update_metadata_with_zero_findings(self):
        """Test updating metadata with zero findings."""
        registry = ExperimentRegistry()
        fn, meta = registry._experiments["random_walk"]

        initial_run_count = meta.run_count
        initial_finding_count = meta.finding_count

        registry.update_metadata("random_walk", findings=0, duration_ms=50.0)

        assert meta.run_count == initial_run_count + 1
        assert meta.finding_count == initial_finding_count
        assert meta.last_run > 0

    def test_update_metadata_negative_findings(self):
        """Test updating metadata with negative findings (edge case)."""
        registry = ExperimentRegistry()
        fn, meta = registry._experiments["random_walk"]

        initial_finding_count = meta.finding_count

        registry.update_metadata("random_walk", findings=-2, duration_ms=50.0)

        assert meta.finding_count == initial_finding_count - 2

    def test_success_rate_calculation(self):
        """Test success rate calculation logic."""
        registry = ExperimentRegistry()

        # Create a test registry without default experiments
        class TestRegistry(ExperimentRegistry):
            def _register_default_experiments(self) -> None:
                pass

        test_registry = TestRegistry()

        async def mock_experiment(exp_id: int) -> Any:
            return {"result": "test"}

        metadata = ExperimentMetadata(
            name="test_calc",
            phase=8,
            description="Success rate calculation test",
            expected_duration_ms=100.0,
            success_rate=0.8,
            run_count=0,
            finding_count=0,
        )

        test_registry.register("test_calc", mock_experiment, metadata)
        fn, meta = test_registry._experiments["test_calc"]

        # First run with findings
        test_registry.update_metadata("test_calc", findings=1, duration_ms=50.0)
        assert meta.run_count == 1
        assert meta.finding_count == 1
        assert meta.success_rate == 1.0

        # Second run without findings
        test_registry.update_metadata("test_calc", findings=0, duration_ms=50.0)
        assert meta.run_count == 2
        assert meta.finding_count == 1
        assert meta.success_rate == 0.5

        # Third run with multiple findings
        test_registry.update_metadata("test_calc", findings=2, duration_ms=50.0)
        assert meta.run_count == 3
        assert meta.finding_count == 3
        assert meta.success_rate == 1.0