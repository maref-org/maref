from __future__ import annotations

import random as _random
from collections.abc import Callable
from typing import Any

from maref.governance import (
    CircuitBreaker,
    GovernanceStateMachine,
    OscillationFixLoop,
)
from maref.governance.types import GovernanceState
from maref.governance.verifier_consensus import VerifierConsensus
from maref.loop.base import ConvergentResult, LoopBase, LoopState
from maref.loop.protocols import (
    EvaluationResult,
    LoopStopReason,
    ToolBoundary,
)


class ConvergentLoop(LoopBase):
    def __init__(
        self,
        execute_fn: Callable[[Any], Any],
        evaluator: Callable[[Any], EvaluationResult] | VerifierConsensus | None = None,
        tool_boundary: ToolBoundary | None = None,
        max_rounds: int = 50,
        convergence_threshold: float = 0.01,
        convergence_window: int = 5,
        circuit_breaker_trips: int = 3,
        oscillation_max_rate: float = 10.0,
        random_restart_every: int = 20,
    ):
        super().__init__(evaluator, tool_boundary, max_rounds)
        self._execute_fn = execute_fn
        self._convergence_threshold = convergence_threshold
        self._convergence_window = convergence_window
        self._convergence_history: list[float] = []
        self._cb_trip_threshold = circuit_breaker_trips
        self._circuit_breaker = CircuitBreaker(
            max_depth=0,
            max_consecutive_failures=circuit_breaker_trips,
            cooldown_seconds=30.0,
        )
        self._oscillation = OscillationFixLoop(
            stabilize_fn=self._noop_stabilize,
            get_state_fn=lambda: {"state": "ACT", "entropy": 3},
            cooldown_seconds=30.0,
            max_rate=oscillation_max_rate,
        )
        self._random_restart_every = random_restart_every

    @staticmethod
    def _noop_stabilize(reason: str = "") -> bool:
        return True

    @staticmethod
    def _perturb(input_data: Any, current_score: float) -> Any:
        if isinstance(input_data, str):
            words = input_data.split()
            if len(words) > 3 and current_score < 0.5:
                idx = _random.randint(0, len(words) - 1)
                words[idx] = words[idx].swapcase()
                return " ".join(words)
        return input_data

    async def run(
        self,
        initial_input: Any,
        state_machine: GovernanceStateMachine | None = None,
    ) -> ConvergentResult:
        self._running = True
        self._state = LoopState()
        self._convergence_history = []
        evaluations: list[EvaluationResult] = []
        errors: list[str] = []

        if state_machine:
            state_machine.transition(GovernanceState.OBSERVE, "convergent_loop_start")

        for round_num in range(self._max_rounds):
            if not self._running:
                return self._finalize(LoopStopReason.MANUAL_STOP, None)

            self._state.round = round_num

            if state_machine:
                state_machine.transition(GovernanceState.ACT, f"convergent_round_{round_num}")

            try:
                output = self._execute_fn(initial_input)
            except Exception as e:
                errors.append(str(e))
                self._state.consecutive_failures += 1
                self._circuit_breaker.record_failure()
                score = EvaluationResult(score=0.0, errors=[str(e)])
                self._record_evaluation(score, evaluations)
                stop = self._check_circuit_breaker()
                if stop:
                    return self._finalize(stop, output=None)
                continue

            result = self._evaluate(output)
            self._record_evaluation(result, evaluations)
            self._convergence_history.append(result.score)
            self._circuit_breaker.record_success()

            if state_machine:
                state_machine.transition(GovernanceState.EVALUATE, f"score_{result.score:.3f}")

            stop = self._check_convergence(result)
            if stop:
                return self._finalize(stop, output)

            stop = self._check_circuit_breaker()
            if stop:
                return self._finalize(stop, output)

            if round_num > 0 and round_num % self._random_restart_every == 0:
                if result.score < 1.0:
                    initial_input = self._perturb(initial_input, result.score)

        if state_machine:
            state_machine.transition(GovernanceState.REPORT, "convergent_loop_complete")
            state_machine.transition(GovernanceState.HALT, "normal_completion")

        return ConvergentResult(
            output=initial_input,
            stop_reason=LoopStopReason.MAX_ROUNDS,
            rounds_completed=self._state.round,
            evaluations=evaluations,
            errors=errors,
            convergence_history=list(self._convergence_history),
        )

    def _evaluate(self, output: Any) -> EvaluationResult:
        if isinstance(self._evaluator, VerifierConsensus):
            # v0.47 S13: 装配法官后，对输出构造 Trace 走真实仲裁；
            # 否则保持向后兼容的 dict 仿真表决。
            if self._evaluator.has_judges:
                from maref.governance.trace import Trace, TraceStep

                trace = Trace(
                    trace_id=f"convergent-{self._state.round}",
                    agent_id="convergent-loop",
                )
                trace.add_step(
                    TraceStep(
                        agent_id="convergent-loop",
                        action=str(output)[:200],
                        decision="evaluate",
                    )
                )
                result = self._evaluator.evaluate(trace)
            else:
                result = self._evaluator.evaluate({"output": output})
            return EvaluationResult(
                score=result.agreement,
                errors=[],
                improvement=result.agreement - self._state.last_score,
            )
        if callable(self._evaluator):
            return self._evaluator(output)
        return EvaluationResult(score=1.0)

    def _record_evaluation(
        self,
        result: EvaluationResult,
        evaluations: list[EvaluationResult],
    ) -> None:
        evaluations.append(result)
        self._state.scores.append(result.score)
        self._state.improvements.append(result.improvement)
        self._state.last_score = result.score

    def _check_convergence(self, result: EvaluationResult) -> LoopStopReason | None:
        if result.score >= 1.0:
            return LoopStopReason.CONVERGED
        if len(self._convergence_history) >= self._convergence_window:
            recent = self._convergence_history[-self._convergence_window :]
            if max(recent) - min(recent) < self._convergence_threshold:
                return LoopStopReason.CONVERGED
        return None

    def _check_circuit_breaker(self) -> LoopStopReason | None:
        if self._state.consecutive_failures >= self._cb_trip_threshold:
            return LoopStopReason.CIRCUIT_BREAKER
        if self._circuit_breaker.is_open:
            return LoopStopReason.CIRCUIT_BREAKER
        return None

    def _finalize(
        self,
        stop_reason: LoopStopReason,
        output: Any = None,
    ) -> ConvergentResult:
        return ConvergentResult(
            output=output,
            stop_reason=stop_reason,
            rounds_completed=self._state.round,
            convergence_history=list(self._convergence_history),
        )
