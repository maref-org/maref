from __future__ import annotations

from maref.recursive.blast_radius import (
    BlastRadiusConfig,
    BlastRadiusController,
    CompensationDecision,
    CompensationStrategy,
)


class TestBlastRadiusConfig:
    def test_default_config(self) -> None:
        cfg = BlastRadiusConfig()
        assert cfg.strategy == CompensationStrategy.FULL
        assert cfg.max_radius == 2
        assert cfg.confirm_radius_threshold == 3
        assert cfg.skip_on_partial_failure is True
        assert cfg.select_predicate is None

    def test_custom_config(self) -> None:
        cfg = BlastRadiusConfig(
            strategy=CompensationStrategy.PARTIAL,
            max_radius=5,
            confirm_radius_threshold=10,
        )
        assert cfg.strategy == CompensationStrategy.PARTIAL
        assert cfg.max_radius == 5
        assert cfg.confirm_radius_threshold == 10


class TestCompensationDecision:
    def test_to_dict(self) -> None:
        decision = CompensationDecision(
            steps_to_compensate=["step-1", "step-2"],
            skipped_steps=["step-3"],
            strategy=CompensationStrategy.PARTIAL,
            requires_human_confirm=True,
            reason="test",
        )
        d = decision.to_dict()
        assert d["steps_to_compensate"] == ["step-1", "step-2"]
        assert d["skipped_steps"] == ["step-3"]
        assert d["strategy"] == "partial"
        assert d["requires_human_confirm"] is True
        assert d["reason"] == "test"


class TestBlastRadiusController:
    def test_default_config(self) -> None:
        ctrl = BlastRadiusController()
        assert ctrl.config.strategy == CompensationStrategy.FULL

    def test_initialized_with_config(self) -> None:
        cfg = BlastRadiusConfig(strategy=CompensationStrategy.SELECTIVE)
        ctrl = BlastRadiusController(config=cfg)
        assert ctrl.config.strategy == CompensationStrategy.SELECTIVE

    def test_full_compensation(self) -> None:
        ctrl = BlastRadiusController()
        decision = ctrl.decide(
            failed_step_id="step-3",
            completed_step_ids=["step-1", "step-2", "step-3"],
        )
        assert decision.steps_to_compensate == ["step-3", "step-2", "step-1"]
        assert decision.skipped_steps == []
        assert decision.strategy == CompensationStrategy.FULL
        assert decision.requires_human_confirm is True  # radius 3 >= threshold 3

    def test_partial_compensation_respects_max_radius(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.PARTIAL,
                max_radius=2,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-5",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4", "step-5"],
        )
        # Most recent 2 reversed: step-5, step-4 → but reversed back → step-4, step-5
        assert decision.steps_to_compensate == ["step-4", "step-5"]
        assert decision.skipped_steps == ["step-1", "step-2", "step-3"]

    def test_partial_within_radius_compensates_all(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.PARTIAL,
                max_radius=10,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-2",
            completed_step_ids=["step-1", "step-2"],
        )
        assert decision.steps_to_compensate == ["step-1", "step-2"]
        assert decision.skipped_steps == []

    def test_selective_with_predicate(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.SELECTIVE,
                max_radius=3,
                select_predicate=lambda sid: "critical" in sid,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-4",
            completed_step_ids=[
                "step-1",
                "step-critical-a",
                "step-3",
                "step-critical-b",
                "step-4",
            ],
        )
        # Reversed: step-4, step-critical-b, step-3, step-critical-a, step-1
        # Selective picks from reversed: step-critical-b, step-critical-a
        assert "critical" in decision.steps_to_compensate[0]
        assert len(decision.steps_to_compensate) == 2

    def test_selective_no_predicate_falls_back_to_partial(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.SELECTIVE,
                max_radius=2,
                select_predicate=None,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-4",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4"],
        )
        assert decision.steps_to_compensate == ["step-3", "step-4"]

    def test_skip_non_critical(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.SKIP_NON_CRITICAL,
                max_radius=5,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-5",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4", "step-5"],
            criticality_map={
                "step-1": False,
                "step-2": True,
                "step-3": False,
                "step-4": True,
                "step-5": True,
            },
        )
        assert "step-2" in decision.steps_to_compensate
        assert "step-4" in decision.steps_to_compensate
        assert "step-5" in decision.steps_to_compensate
        assert "step-1" in decision.skipped_steps
        assert "step-3" in decision.skipped_steps

    def test_skip_non_critical_respects_max_radius(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.SKIP_NON_CRITICAL,
                max_radius=1,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-4",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4"],
            criticality_map={"step-1": False, "step-2": False, "step-3": False, "step-4": True},
        )
        assert len(decision.steps_to_compensate) == 1
        assert "step-4" in decision.steps_to_compensate

    def test_human_confirmation_threshold(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.FULL,
                confirm_radius_threshold=5,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-3",
            completed_step_ids=["step-1", "step-2", "step-3"],
        )
        assert decision.requires_human_confirm is False  # radius 3 < threshold 5

    def test_human_confirmation_triggered(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(
                strategy=CompensationStrategy.PARTIAL,
                max_radius=10,
                confirm_radius_threshold=3,
            )
        )
        decision = ctrl.decide(
            failed_step_id="step-5",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4", "step-5"],
        )
        assert decision.requires_human_confirm is True  # radius 5 >= threshold 3

    def test_empty_completed_steps(self) -> None:
        ctrl = BlastRadiusController()
        decision = ctrl.decide(
            failed_step_id="step-1",
            completed_step_ids=[],
        )
        assert decision.steps_to_compensate == []
        assert decision.skipped_steps == []
        assert decision.requires_human_confirm is False

    def test_single_step(self) -> None:
        ctrl = BlastRadiusController()
        decision = ctrl.decide(
            failed_step_id="step-1",
            completed_step_ids=["step-1"],
        )
        assert decision.steps_to_compensate == ["step-1"]

    def test_decision_contains_reason(self) -> None:
        ctrl = BlastRadiusController(
            config=BlastRadiusConfig(strategy=CompensationStrategy.PARTIAL, max_radius=2)
        )
        decision = ctrl.decide(
            failed_step_id="step-5",
            completed_step_ids=["step-1", "step-2", "step-3", "step-4", "step-5"],
        )
        assert "failed_step=step-5" in decision.reason
        assert "radius=2" in decision.reason

    def test_config_property_matches(self) -> None:
        cfg = BlastRadiusConfig(strategy=CompensationStrategy.FULL)
        ctrl = BlastRadiusController(config=cfg)
        assert ctrl.config is cfg
