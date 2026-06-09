"""
Tests for Policy Sandbox and A/B Testing Framework

Phase 9: Validates that self-modification does not cause policy degradation.
"""

from __future__ import annotations

from drift_guard.ab_testing import ABTestFramework
from drift_guard.policy_sandbox import (
    PolicyChangeType,
    PolicySandbox,
    PolicyStatus,
)
from drift_guard.types import PipelineConfig


class TestPolicySandbox:
    """Test suite for safe policy modification."""

    def test_baseline_initialization(self) -> None:
        """Verify baseline is properly initialized."""
        sandbox = PolicySandbox()
        config = sandbox.get_active_config()

        assert config.kl_warning == 0.1
        assert config.kl_critical == 0.5
        assert sandbox._active_version == "baseline"

    def test_propose_change(self) -> None:
        """Test proposing a new policy change."""
        sandbox = PolicySandbox()
        new_config = PipelineConfig(kl_warning=0.2, kl_critical=0.6)

        change = sandbox.propose_change(
            change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
            description="Increase warning threshold",
            new_config=new_config,
        )

        assert change.status == PolicyStatus.PROPOSED
        assert change.change_type == PolicyChangeType.THRESHOLD_ADJUSTMENT
        assert change.change_id in sandbox._changes

    def test_a_b_test_lifecycle(self) -> None:
        """Test complete A/B test lifecycle."""
        sandbox = PolicySandbox()
        new_config = PipelineConfig(kl_warning=0.2)

        change = sandbox.propose_change(
            change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
            description="Test higher threshold",
            new_config=new_config,
        )

        # Start A/B test
        assert sandbox.start_a_b_test(change.change_id) is True
        assert change.status == PolicyStatus.A_B_TESTING

        # Record test results
        results = {"fpr": 0.03, "fnr": 0.01, "f1": 0.92}
        assert sandbox.record_test_results(change.change_id, results) is True

        # Approve change
        assert sandbox.approve_change(change.change_id, reviewer="test") is True
        assert change.status == PolicyStatus.APPROVED
        assert sandbox._active_version == change.version_id

    def test_rollback(self) -> None:
        sandbox = PolicySandbox()
        original_config = sandbox.get_active_config()

        new_config = PipelineConfig(kl_warning=0.99)
        change = sandbox.propose_change(
            change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
            description="Extreme threshold",
            new_config=new_config,
        )
        sandbox.start_a_b_test(change.change_id)
        sandbox.approve_change(change.change_id, reviewer="test")

        assert sandbox.get_active_config().kl_warning == 0.99

        assert sandbox.rollback() is True
        assert sandbox.get_active_config().kl_warning == original_config.kl_warning

    def test_reject_change(self) -> None:
        """Test rejecting a proposed change."""
        sandbox = PolicySandbox()
        new_config = PipelineConfig(kl_warning=0.2)

        change = sandbox.propose_change(
            change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
            description="Bad idea",
            new_config=new_config,
        )

        assert sandbox.reject_change(change.change_id, "Too risky") is True
        assert change.status == PolicyStatus.REJECTED

    def test_no_degradation_after_rollback(self) -> None:
        """
        Critical test: Verify that after rollback, system returns
        to exact baseline performance.
        """
        sandbox = PolicySandbox()
        baseline_config = sandbox.get_active_config()

        # Apply a series of changes
        for i in range(5):
            new_config = PipelineConfig(kl_warning=0.1 + i * 0.05)
            change = sandbox.propose_change(
                change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
                description=f"Change {i}",
                new_config=new_config,
            )
            sandbox.start_a_b_test(change.change_id)
            sandbox.approve_change(change.change_id, reviewer="test")

        # Rollback all changes
        for _ in range(5):
            sandbox.rollback()

        # Verify we're back to baseline
        final_config = sandbox.get_active_config()
        assert final_config.kl_warning == baseline_config.kl_warning
        assert final_config.kl_critical == baseline_config.kl_critical
        assert final_config.kl_max == baseline_config.kl_max

    def test_version_history_integrity(self) -> None:
        """Verify version history maintains correct order."""
        sandbox = PolicySandbox()

        # Create multiple versions
        for i in range(3):
            new_config = PipelineConfig(kl_warning=0.1 + i * 0.1)
            change = sandbox.propose_change(
                change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
                description=f"Version {i}",
                new_config=new_config,
            )
            sandbox.start_a_b_test(change.change_id)
            sandbox.approve_change(change.change_id, reviewer="test")

        history = sandbox.get_version_history()
        assert len(history) == 4  # baseline + 3 changes
        assert history[0]["version_id"] == "baseline"


class TestABTestFramework:
    """Test suite for A/B testing framework."""

    def test_create_test(self) -> None:
        """Test creating an A/B test."""
        framework = ABTestFramework()
        baseline = PipelineConfig(kl_warning=0.1)
        variant = PipelineConfig(kl_warning=0.2)

        assert framework.create_test("test_1", baseline, variant, min_samples=50) is True
        status = framework.get_test_status("test_1")
        assert status is not None
        assert status["baseline_samples"] == 0
        assert status["variant_samples"] == 0

    def test_record_samples(self) -> None:
        """Test recording samples for A/B test."""
        framework = ABTestFramework()
        baseline = PipelineConfig()
        variant = PipelineConfig(kl_warning=0.2)

        framework.create_test("test_2", baseline, variant, min_samples=10)

        # Record baseline samples
        for _ in range(5):
            framework.record_sample("test_2", "baseline", True, True, 100.0)
            framework.record_sample("test_2", "baseline", False, False, 80.0)

        # Record variant samples
        for _ in range(5):
            framework.record_sample("test_2", "variant", True, True, 90.0)
            framework.record_sample("test_2", "variant", False, False, 70.0)

        status = framework.get_test_status("test_2")
        assert status["baseline_samples"] == 10
        assert status["variant_samples"] == 10

    def test_evaluate_test(self) -> None:
        """Test evaluating A/B test results."""
        framework = ABTestFramework()
        baseline = PipelineConfig()
        variant = PipelineConfig(kl_warning=0.2)

        framework.create_test("test_3", baseline, variant, min_samples=20)

        # Baseline: moderate performance
        for _ in range(10):
            framework.record_sample("test_3", "baseline", True, True, 100.0)
            framework.record_sample("test_3", "baseline", False, False, 100.0)

        # Variant: better performance (lower latency, same accuracy)
        for _ in range(10):
            framework.record_sample("test_3", "variant", True, True, 80.0)
            framework.record_sample("test_3", "variant", False, False, 80.0)

        result = framework.evaluate_test("test_3")
        assert result is not None
        assert result.winner in ("baseline", "variant", "tie")
        assert 0.0 <= result.confidence <= 1.0

    def test_variant_wins_with_better_f1(self) -> None:
        """Test that variant with better F1 score is selected."""
        framework = ABTestFramework()
        baseline = PipelineConfig()
        variant = PipelineConfig(kl_warning=0.15)

        framework.create_test("test_4", baseline, variant, min_samples=20)

        # Baseline: some false positives
        for _ in range(10):
            framework.record_sample("test_4", "baseline", True, True, 100.0)
            framework.record_sample("test_4", "baseline", True, False, 100.0)  # FP

        # Variant: fewer false positives
        for _ in range(10):
            framework.record_sample("test_4", "variant", True, True, 100.0)
            framework.record_sample("test_4", "variant", False, False, 100.0)

        result = framework.evaluate_test("test_4")
        assert result is not None
        # Variant should win due to better precision/F1
        assert result.winner == "variant"
        assert result.confidence > 0.5

    def test_tie_when_no_clear_winner(self) -> None:
        """Test tie when performance is similar."""
        framework = ABTestFramework()
        baseline = PipelineConfig()
        variant = PipelineConfig(kl_warning=0.1001)  # Almost identical

        framework.create_test("test_5", baseline, variant, min_samples=20)

        # Identical performance
        for _ in range(10):
            framework.record_sample("test_5", "baseline", True, True, 100.0)
            framework.record_sample("test_5", "variant", True, True, 100.0)

        result = framework.evaluate_test("test_5")
        assert result is not None
        assert result.winner == "tie"

    def test_prevent_degradation_via_ab_test(self) -> None:
        """
        Critical test: Verify A/B testing prevents deploying
        a policy that would degrade performance.
        """
        framework = ABTestFramework()
        baseline = PipelineConfig(kl_warning=0.1)
        bad_variant = PipelineConfig(kl_warning=0.9)  # Very insensitive

        framework.create_test("degradation_test", baseline, bad_variant, min_samples=20)

        # Baseline: catches most drift
        for _ in range(10):
            framework.record_sample("degradation_test", "baseline", True, True, 100.0)
            framework.record_sample("degradation_test", "baseline", False, False, 100.0)

        # Bad variant: misses actual drift (false negatives)
        for _ in range(10):
            framework.record_sample("degradation_test", "variant", False, True, 100.0)  # FN
            framework.record_sample("degradation_test", "variant", False, False, 100.0)

        result = framework.evaluate_test("degradation_test")
        assert result is not None
        assert result.winner == "baseline"
        assert "Baseline performs better" in result.recommendation
