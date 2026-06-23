from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from maref.loop.protocols import EvaluationResult, LoopStopReason, ToolBoundary

T = TypeVar("T")


@dataclass
class LoopResult(Generic[T]):
    output: T | None = None
    stop_reason: LoopStopReason = LoopStopReason.UNKNOWN
    rounds_completed: int = 0
    evaluations: list[EvaluationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvergentResult(LoopResult[Any]):
    convergence_history: list[float] = field(default_factory=list)


@dataclass
class LoopState:
    round: int = 0
    consecutive_failures: int = 0
    last_score: float = 0.0
    scores: list[float] = field(default_factory=list)
    improvements: list[float] = field(default_factory=list)


class LoopBase(ABC):
    def __init__(
        self,
        evaluator: Any | None = None,
        tool_boundary: ToolBoundary | None = None,
        max_rounds: int = 50,
    ):
        self._evaluator = evaluator
        self._tool_boundary = tool_boundary or ToolBoundary()
        self._max_rounds = max_rounds
        self._state = LoopState()
        self._running = False

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def tool_boundary(self) -> ToolBoundary:
        return self._tool_boundary

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> LoopResult[Any]:
        ...

    def _check_stop(self) -> LoopStopReason | None:
        if self._state.round >= self._max_rounds:
            return LoopStopReason.MAX_ROUNDS
        return None

    def stop(self) -> None:
        self._running = False

    def _finalize(
        self,
        stop_reason: LoopStopReason,
        output: Any = None,
    ) -> LoopResult[Any]:
        return LoopResult(
            output=output,
            stop_reason=stop_reason,
            rounds_completed=self._state.round,
        )
