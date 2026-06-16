#!/usr/bin/env python3
"""Phase 2.3 BlastRadiusController tests."""

from __future__ import annotations

from maref.recursive.blast_radius import (
    BlastRadiusConfig,
    BlastRadiusController,
    CompensationStrategy,
)
from maref.recursive.saga_orchestrator import (
    Saga,
    SagaOrchestrator,
    SagaStep,
    StepResult,
)


def test_full_strategy_compensates_all():
    ctrl = BlastRadiusController(BlastRadiusConfig(strategy=CompensationStrategy.FULL))
    dec = ctrl.decide("step_3", ["step_1", "step_2"])
    assert set(dec.steps_to_compensate) == {"step_1", "step_2"}
    assert not dec.requires_human_confirm
    print("  full_strategy OK")


def test_partial_strategy_limits_radius():
    ctrl = BlastRadiusController(
        BlastRadiusConfig(strategy=CompensationStrategy.PARTIAL, max_radius=1)
    )
    dec = ctrl.decide("step_3", ["step_1", "step_2"])
    # Most recent step only
    assert dec.steps_to_compensate == ["step_2"]
    assert dec.skipped_steps == ["step_1"]
    print("  partial_strategy OK")


def test_skip_non_critical():
    ctrl = BlastRadiusController(
        BlastRadiusConfig(strategy=CompensationStrategy.SKIP_NON_CRITICAL, max_radius=2)
    )
    dec = ctrl.decide(
        "step_4",
        ["step_1", "step_2", "step_3"],
        criticality_map={"step_1": False, "step_2": True, "step_3": False},
    )
    # Reverse order: step_3(non-critical,skip), step_2(critical,compensate)
    assert dec.steps_to_compensate == ["step_2"]
    assert "step_3" in dec.skipped_steps
    print("  skip_non_critical OK")


def test_human_confirm_threshold():
    ctrl = BlastRadiusController(
        BlastRadiusConfig(strategy=CompensationStrategy.FULL, confirm_radius_threshold=2)
    )
    dec = ctrl.decide("step_3", ["step_1", "step_2"])
    assert dec.requires_human_confirm
    print("  human_confirm_threshold OK")


def test_saga_with_blast_radius():
    """Saga with 3 steps; step 3 fails; blast radius = 1 → only step 2 compensated."""
    ctrl = BlastRadiusController(
        BlastRadiusConfig(strategy=CompensationStrategy.PARTIAL, max_radius=1)
    )
    orch = SagaOrchestrator(blast_radius=ctrl)

    def ok(ctx):
        return StepResult(step_id="s1", success=True)

    def fail(ctx):
        return StepResult(step_id="s3", success=False, error="boom")

    saga = Saga(
        steps=[
            SagaStep("s1", "first", execute_fn=ok, compensate_fn=ok),
            SagaStep("s2", "second", execute_fn=ok, compensate_fn=ok),
            SagaStep("s3", "third", execute_fn=fail, compensate_fn=ok),
        ]
    )

    result = orch.execute(saga)
    assert result.state == "failed"
    assert result.steps_compensated == 1
    print("  saga_with_blast_radius OK")


def test_saga_without_blast_radius():
    """Default behaviour: compensate everything."""
    orch = SagaOrchestrator()

    def ok(ctx):
        return StepResult(step_id="s1", success=True)

    def fail(ctx):
        return StepResult(step_id="s3", success=False, error="boom")

    saga = Saga(
        steps=[
            SagaStep("s1", "first", execute_fn=ok, compensate_fn=ok),
            SagaStep("s2", "second", execute_fn=ok, compensate_fn=ok),
            SagaStep("s3", "third", execute_fn=fail, compensate_fn=ok),
        ]
    )

    result = orch.execute(saga)
    assert result.state == "failed"
    assert result.steps_compensated == 2
    print("  saga_without_blast_radius OK")


if __name__ == "__main__":
    test_full_strategy_compensates_all()
    test_partial_strategy_limits_radius()
    test_skip_non_critical()
    test_human_confirm_threshold()
    test_saga_with_blast_radius()
    test_saga_without_blast_radius()
    print("All BlastRadius tests passed")
