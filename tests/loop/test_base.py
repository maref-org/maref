from __future__ import annotations

import pytest

from maref.loop.base import ConvergentResult, LoopBase, LoopResult, LoopState
from maref.loop.protocols import LoopStopReason, ToolBoundary


class TestLoopResult:
    def test_defaults(self):
        r = LoopResult()
        assert r.output is None
        assert r.stop_reason == LoopStopReason.UNKNOWN
        assert r.rounds_completed == 0

    def test_construction(self):
        r = LoopResult(
            output="done",
            stop_reason=LoopStopReason.MAX_ROUNDS,
            rounds_completed=10,
            errors=["err1"],
        )
        assert r.output == "done"
        assert r.rounds_completed == 10


class TestConvergentResult:
    def test_inherits_loop_result(self):
        r = ConvergentResult(
            output="ok",
            stop_reason=LoopStopReason.CONVERGED,
            convergence_history=[0.5, 0.8, 1.0],
        )
        assert isinstance(r, LoopResult)
        assert r.convergence_history == [0.5, 0.8, 1.0]
        assert r.stop_reason == LoopStopReason.CONVERGED


class TestLoopState:
    def test_defaults(self):
        s = LoopState()
        assert s.round == 0
        assert s.consecutive_failures == 0
        assert s.last_score == 0.0
        assert s.scores == []

    def test_after_evaluation(self):
        s = LoopState()
        s.round = 5
        s.last_score = 0.9
        s.scores = [0.1, 0.5, 0.9]
        assert s.round == 5
        assert s.last_score == 0.9


class TestLoopBase:
    def test_init_defaults(self):
        loop = _ConcreteLoop()
        assert loop.state.round == 0
        assert isinstance(loop.tool_boundary, ToolBoundary)
        assert loop._max_rounds == 50

    def test_init_custom(self):
        tb = ToolBoundary(allowed_domains=["test"])
        loop = _ConcreteLoop(tool_boundary=tb, max_rounds=10)
        assert loop._max_rounds == 10
        assert loop.tool_boundary.allowed_domains == ["test"]

    def test_check_stop_below_max(self):
        loop = _ConcreteLoop(max_rounds=5)
        loop._state.round = 3
        assert loop._check_stop() is None

    def test_check_stop_at_max(self):
        loop = _ConcreteLoop(max_rounds=5)
        loop._state.round = 5
        assert loop._check_stop() == LoopStopReason.MAX_ROUNDS

    def test_stop_sets_running_false(self):
        loop = _ConcreteLoop()
        loop._running = True
        loop.stop()
        assert loop._running is False

    def test_finalize_creates_loop_result(self):
        loop = _ConcreteLoop()
        loop._state.round = 7
        result = loop._finalize(LoopStopReason.CONVERGED, output="result")
        assert isinstance(result, LoopResult)
        assert result.stop_reason == LoopStopReason.CONVERGED
        assert result.output == "result"
        assert result.rounds_completed == 7

    @pytest.mark.asyncio
    async def test_run_is_abstract(self):
        loop = _ConcreteLoop()
        loop._abstract = True
        with pytest.raises(TypeError):
            _ = await loop.run()


class _ConcreteLoop(LoopBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._abstract = False

    async def run(self, *args, **kwargs):
        if self._abstract:
            raise TypeError("Can't instantiate abstract class")
        return LoopResult()
