from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maref.loop.base import LoopBase, LoopResult, LoopState
from maref.loop.budgets import TimeBudget, TokenBudget
from maref.loop.protocols import (
    Discovery,
    ExplorationResult,
    LoopStopReason,
    ToolBoundary,
)


class ExploratoryLoop(LoopBase):
    def __init__(
        self,
        generator: Callable[[list[Discovery], int], list[Discovery]],
        diversity_evaluator: Callable[[Discovery, list[Discovery]], float] | None = None,
        tool_boundary: ToolBoundary | None = None,
        max_rounds: int = 20,
        max_tokens: int = 100_000,
        max_time_seconds: int = 300,
        diversity_threshold: float = 0.3,
        coverage_target: float = 0.8,
        branch_factor: int = 3,
        explore_restart_threshold: float = 0.1,
    ):
        super().__init__(None, tool_boundary, max_rounds)
        self._generator = generator
        self._diversity_evaluator = diversity_evaluator or self._default_diversity
        self._token_budget = TokenBudget(max_tokens)
        self._time_budget = TimeBudget(max_time_seconds)
        self._diversity_threshold = diversity_threshold
        self._coverage_target = coverage_target
        self._branch_factor = branch_factor
        self._explore_restart_threshold = explore_restart_threshold
        self._discoveries: list[Discovery] = []
        self._stale_rounds = 0

    @staticmethod
    def _default_diversity(discovery: Discovery, existing: list[Discovery]) -> float:
        if not existing:
            return 1.0
        tags_existing = {t for d in existing for t in d.tags}
        if not discovery.tags or not tags_existing:
            return 0.5
        overlap = len(set(discovery.tags) & tags_existing)
        return 1.0 - (overlap / max(len(set(discovery.tags) | tags_existing), 1))

    async def explore(self, seed: str) -> ExplorationResult:
        self._running = True
        self._state = LoopState()
        self._discoveries = []
        self._stale_rounds = 0
        self._time_budget.start()

        if seed:
            self._discoveries.append(
                Discovery(content=seed, source_round=0, novelty=1.0, tags=["seed"])
            )

        while not self._token_budget.exhausted and not self._time_budget.exhausted:
            if not self._running:
                return self._finalize_exploration(LoopStopReason.MANUAL_STOP)

            if self._state.round >= self._max_rounds:
                return self._finalize_exploration(LoopStopReason.MAX_ROUNDS)

            token_estimate = 1000
            if not self._token_budget.consume(token_estimate):
                return self._finalize_exploration(LoopStopReason.TOKEN_EXHAUSTED)

            new_discoveries = self._generator(self._discoveries, self._branch_factor)
            novel_discoveries: list[Discovery] = []

            for d in new_discoveries:
                d.source_round = self._state.round
                novelty = self._diversity_evaluator(d, self._discoveries)
                d.novelty = novelty
                if novelty >= self._diversity_threshold:
                    novel_discoveries.append(d)

            if novel_discoveries:
                self._discoveries.extend(novel_discoveries)
                self._stale_rounds = 0
            else:
                self._stale_rounds += 1

            self._state.round += 1

            if self._check_coverage():
                return self._finalize_exploration(LoopStopReason.COVERAGE_MET)

            if self._stale_rounds >= 5:
                return self._finalize_exploration(LoopStopReason.NO_NOVELTY)

        if self._token_budget.exhausted:
            return self._finalize_exploration(LoopStopReason.TOKEN_EXHAUSTED)
        if self._time_budget.exhausted:
            return self._finalize_exploration(LoopStopReason.TIME_EXHAUSTED)

        return self._finalize_exploration(LoopStopReason.MAX_ROUNDS)

    def _check_coverage(self) -> bool:
        if not self._discoveries:
            return False
        tagged = [d for d in self._discoveries if d.tags]
        if not tagged:
            return False
        all_tags = {t for d in tagged for t in d.tags}
        coverage = len(all_tags) / max(len(all_tags) + 1, 1)
        return coverage >= self._coverage_target

    def _finalize_exploration(self, reason: LoopStopReason) -> ExplorationResult:
        novelty_scores = [d.novelty for d in self._discoveries]
        histogram: dict[str, float] = {}
        for d in self._discoveries:
            for tag in d.tags:
                histogram[tag] = histogram.get(tag, 0) + 1
        if histogram:
            total = sum(histogram.values())
            histogram = {k: v / total for k, v in histogram.items()}

        return ExplorationResult(
            discoveries=list(self._discoveries),
            novelty_scores=novelty_scores,
            coverage=len(self._discoveries) / max(self._max_rounds, 1),
            diversity_histogram=histogram,
            metadata={
                "stop_reason": reason.value,
                "rounds": self._state.round,
                "tokens_used": self._token_budget.used,
                "time_elapsed": self._time_budget.elapsed,
                "total_discoveries": len(self._discoveries),
            },
        )

    async def run(self, *args: Any, **kwargs: Any) -> LoopResult[Any]:
        seed = args[0] if args else kwargs.get("seed", "")
        result = await self.explore(seed)
        return LoopResult(
            output=result,
            stop_reason=LoopStopReason.COVERAGE_MET
            if result.coverage >= self._coverage_target
            else LoopStopReason.UNKNOWN,
            rounds_completed=self._state.round,
        )
