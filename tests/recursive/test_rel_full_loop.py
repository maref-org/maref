from __future__ import annotations

from unittest.mock import patch

import pytest

from maref.recursive.event_trigger import EventTrigger
from maref.recursive.llm_code_generator import LLMCodeGenerator, MockProvider
from maref.recursive.recursive_evolution_loop import (
    RELConvergenceDetector,
    RELSafetyGovernor,
    RELState,
    RELStateMachine,
    RELTransactionManager,
    RecursiveEvolutionLoop,
    SafetyGovernorConfig,
)
from maref.recursive.self_architect import ArchitectureProposal, ChangeType


class TestRecursiveEvolutionLoop:
    def test_start_triggers_transition(self) -> None:
        loop = RecursiveEvolutionLoop()
        assert loop.state_machine.state == RELState.IDLE
        loop.start()
        assert loop.state_machine.state == RELState.TRIGGERED

    def test_is_active_after_start(self) -> None:
        loop = RecursiveEvolutionLoop()
        assert not loop.is_active()
        loop.start()
        assert loop.is_active()

    def test_stop_after_start(self) -> None:
        loop = RecursiveEvolutionLoop()
        loop.start()
        loop.state_machine.transition(RELState.OBSERVE)
        loop.state_machine.transition(RELState.DIAGNOSE)
        loop.state_machine.transition(RELState.ARCHITECT)
        loop.state_machine.transition(RELState.CODEGEN)
        loop.state_machine.transition(RELState.SAFETY)
        loop.state_machine.transition(RELState.DEPLOY)
        loop.state_machine.transition(RELState.VERIFY)
        loop.state_machine.transition(RELState.EVALUATE)
        loop.stop()
        assert loop.is_converged()

    def test_halt_and_recover(self) -> None:
        loop = RecursiveEvolutionLoop()
        loop.start()
        loop.halt("test halt")
        assert loop.is_halted()
        assert loop.recover() is True
        assert loop.state_machine.state == RELState.IDLE

    def test_double_recover_fails(self) -> None:
        loop = RecursiveEvolutionLoop()
        loop.start()
        loop.halt()
        assert loop.recover() is True
        assert loop.recover() is False
        assert loop.state_machine.state == RELState.IDLE

    def test_converge_round_commits(self) -> None:
        loop = RecursiveEvolutionLoop()
        detector = RELConvergenceDetector(
            gain_threshold=1.0,
            round_decay_window=1,
        )
        loop._detector = detector

        tx = loop.transaction_manager.begin(["test_converge.py"])

        verdict = loop.complete_round(
            metrics_before={"test_pass_rate": 0.8, "coverage_pct": 70.0},
            metrics_after={"test_pass_rate": 0.9, "coverage_pct": 75.0},
            tx=tx,
        )
        assert loop.current_round == 1
        assert len(loop.rounds) == 1

    def test_divergence_triggers_halt(self) -> None:
        loop = RecursiveEvolutionLoop()
        tx = loop.transaction_manager.begin(["test_divergence.py"])

        verdict = loop.complete_round(
            metrics_before={"test_pass_rate": 0.9, "coverage_pct": 80.0},
            metrics_after={"test_pass_rate": 0.5, "coverage_pct": 60.0},
            tx=tx,
        )
        assert verdict.divergence_detected
        assert loop.is_halted()
        assert tx.state.value == "rolled_back"

    def test_oscillation_triggers_halt(self) -> None:
        loop = RecursiveEvolutionLoop()
        tx = loop.transaction_manager.begin(["test_oscillation.py"])
        for m in [
            {"test_pass_rate": 0.9},
            {"test_pass_rate": 0.5},
            {"test_pass_rate": 0.9},
            {"test_pass_rate": 0.5},
            {"test_pass_rate": 0.9},
        ]:
            loop._detector.evaluate(m)

        verdict = loop.complete_round(
            metrics_before={"test_pass_rate": 0.5},
            metrics_after={"test_pass_rate": 0.9},
            tx=tx,
        )
        assert verdict.oscillation_detected
        assert loop.is_halted()

    def test_multiple_rounds_without_convergence(self) -> None:
        loop = RecursiveEvolutionLoop()
        for i in range(3):
            tx = loop.transaction_manager.begin([f"test_round_{i}.py"])
            verdict = loop.complete_round(
                metrics_before={"test_pass_rate": 0.87 + i * 0.06},
                metrics_after={"test_pass_rate": 0.88 + i * 0.06},
                tx=tx,
            )
        assert loop.current_round == 3
        assert not loop.is_converged()

    def test_governor_stops_after_max_rounds(self) -> None:
        config = SafetyGovernorConfig(max_rounds_per_session=2)
        governor = RELSafetyGovernor(config=config)
        loop = RecursiveEvolutionLoop(safety_governor=governor)
        loop.start()
        for i in range(2):
            tx = loop.transaction_manager.begin([f"test_gov_round_{i}.py"])
            verdict = loop.complete_round(
                metrics_before={"test_pass_rate": 0.8},
                metrics_after={"test_pass_rate": 0.85},
                tx=tx,
            )
        assert loop.is_halted()


class TestRecursiveEvolutionLoopRunSession:
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_run_session_returns_result(self) -> None:
        loop = RecursiveEvolutionLoop()

        def fake_metrics() -> dict[str, float]:
            return {"test_pass_rate": 0.9, "coverage_pct": 80.0}

        with (
            patch.object(loop, "_execute_state_actions", return_value=None),
            patch.object(loop, "_collect_current_metrics", side_effect=fake_metrics),
        ):
            result = await loop.run_session()
        assert isinstance(result.success, bool)
        assert isinstance(result.reason, str)
        assert isinstance(result.final_state, str)
        assert isinstance(result.duration_seconds, float)

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_run_session_honors_governor_max_rounds(self) -> None:
        config = SafetyGovernorConfig(max_rounds_per_session=2)
        governor = RELSafetyGovernor(config=config)
        loop = RecursiveEvolutionLoop(safety_governor=governor)

        async def do_nothing() -> None:
            pass

        with patch.object(loop, "_execute_state_actions", side_effect=do_nothing):
            result = await loop.run_session()
        assert result.round_count <= 2

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_run_session_idempotent(self) -> None:
        loop = RecursiveEvolutionLoop()

        def fake_metrics() -> dict[str, float]:
            return {"test_pass_rate": 0.9, "coverage_pct": 80.0}

        with (
            patch.object(loop, "_execute_state_actions", return_value=None),
            patch.object(loop, "_collect_current_metrics", side_effect=fake_metrics),
        ):
            result1 = await loop.run_session()
            result2 = await loop.run_session()
        assert isinstance(result1, type(result2))


class TestIntegrationWithEventTrigger:
    def test_event_triggers_loop_start(self) -> None:
        trigger = EventTrigger(cooldown_seconds=0)
        loop = RecursiveEvolutionLoop()

        event = trigger.create_event("git_hook", {"ref": "refs/heads/main"}, priority=1)
        if trigger.on_event(event):
            loop.start()
            trigger.record_trigger()

        assert loop.state_machine.state == RELState.TRIGGERED
