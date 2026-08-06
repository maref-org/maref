from __future__ import annotations

import pytest

from maref.loop.convergent import ConvergentLoop
from maref.loop.protocols import EvaluationResult, LoopStopReason


class TestConvergentLoop:
    def test_noop_stabilize(self):
        assert ConvergentLoop._noop_stabilize() is True

    def test_perturb_string_low_score(self):
        perturbed = ConvergentLoop._perturb("hello world test case", 0.3)
        assert isinstance(perturbed, str)
        assert perturbed != "hello world test case"

    def test_perturb_high_score_no_change(self):
        original = "hello world"
        result = ConvergentLoop._perturb(original, 0.9)
        assert result == original

    def test_perturb_non_string(self):
        result = ConvergentLoop._perturb(42, 0.3)
        assert result == 42

    @pytest.mark.asyncio
    async def test_run_converges(self, mock_execute_fn, mock_evaluator):
        loop = ConvergentLoop(
            execute_fn=mock_execute_fn,
            evaluator=mock_evaluator,
            max_rounds=50,
            convergence_threshold=0.01,
        )
        result = await loop.run("input data")
        assert result.stop_reason == LoopStopReason.CONVERGED
        assert result.rounds_completed >= 0

    @pytest.mark.asyncio
    async def test_run_with_state_machine(self, mock_execute_fn, mock_evaluator, mock_state_machine):
        loop = ConvergentLoop(
            execute_fn=mock_execute_fn,
            evaluator=mock_evaluator,
            max_rounds=5,
        )
        result = await loop.run("input", state_machine=mock_state_machine)
        assert mock_state_machine.transition.called
        assert result.stop_reason == LoopStopReason.CONVERGED

    @pytest.mark.asyncio
    async def test_circuit_breaker_on_failures(self, mock_evaluator):
        def failing_fn(_):
            raise RuntimeError("execution failed")

        loop = ConvergentLoop(
            execute_fn=failing_fn,
            evaluator=mock_evaluator,
            max_rounds=50,
            circuit_breaker_trips=1,
        )
        result = await loop.run("input")
        assert result.stop_reason == LoopStopReason.CIRCUIT_BREAKER

    @pytest.mark.asyncio
    async def test_max_rounds(self, mock_evaluator):
        def slow_fn(_):
            return EvaluationResult(score=0.5)

        loop = ConvergentLoop(
            execute_fn=lambda x: x,
            evaluator=mock_evaluator,
            max_rounds=2,
            convergence_threshold=0.001,
        )
        result = await loop.run("input")
        assert result.stop_reason == LoopStopReason.CONVERGED or result.rounds_completed <= 2

    @pytest.mark.asyncio
    async def test_manual_stop(self, mock_evaluator):
        def partial_score(_):
            return EvaluationResult(score=0.5)

        def stopping_fn(input_data):
            loop.stop()
            return {"result": "ok"}

        loop = ConvergentLoop(
            execute_fn=stopping_fn,
            evaluator=partial_score,
            max_rounds=50,
            convergence_threshold=0.01,
            convergence_window=3,
        )
        result = await loop.run("input")
        assert result.stop_reason == LoopStopReason.MANUAL_STOP

    def test_evaluate_with_callable(self, mock_evaluator):
        loop = ConvergentLoop(
            execute_fn=lambda x: x,
            evaluator=mock_evaluator,
        )
        result = loop._evaluate("test")
        assert result.score == 1.0

    def test_evaluate_without_evaluator(self):
        loop = ConvergentLoop(execute_fn=lambda x: x, evaluator=None)
        result = loop._evaluate("test")
        assert result.score == 1.0

    def test_check_circuit_breaker(self):
        loop = ConvergentLoop(execute_fn=lambda x: x, max_rounds=5)
        loop._state.consecutive_failures = 5
        loop._cb_trip_threshold = 3
        assert loop._check_circuit_breaker() == LoopStopReason.CIRCUIT_BREAKER

    def test_check_convergence_perfect_score(self):
        loop = ConvergentLoop(execute_fn=lambda x: x)
        result = loop._check_convergence(EvaluationResult(score=1.0))
        assert result == LoopStopReason.CONVERGED

    def test_check_convergence_window(self):
        loop = ConvergentLoop(execute_fn=lambda x: x, convergence_window=3, convergence_threshold=0.1)
        loop._convergence_history = [0.5, 0.52, 0.51]
        result = loop._check_convergence(EvaluationResult(score=0.52))
        assert result == LoopStopReason.CONVERGED

    def test_check_convergence_not_met(self):
        loop = ConvergentLoop(execute_fn=lambda x: x, convergence_window=3, convergence_threshold=0.1)
        loop._convergence_history = [0.5, 0.7, 0.9]
        result = loop._check_convergence(EvaluationResult(score=0.9))
        assert result is None

    def test_finalize_creates_convergent_result(self):
        loop = ConvergentLoop(execute_fn=lambda x: x)
        loop._convergence_history = [0.1, 0.5]
        result = loop._finalize(LoopStopReason.MAX_ROUNDS, output="done")
        assert isinstance(result.convergence_history, list)
        assert result.stop_reason == LoopStopReason.MAX_ROUNDS
