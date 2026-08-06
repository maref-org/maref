from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.loop.exploratory import ExploratoryLoop
from maref.loop.protocols import Discovery, ExplorationResult, LoopStopReason


class TestExploratoryLoop:
    def test_default_diversity_empty(self):
        d = Discovery(content="a", tags=["x"])
        score = ExploratoryLoop._default_diversity(d, [])
        assert score == 1.0

    def test_default_diversity_no_tags(self):
        d = Discovery(content="a", tags=[])
        existing = [Discovery(content="b", tags=["x"])]
        score = ExploratoryLoop._default_diversity(d, existing)
        assert score == 0.5

    def test_default_diversity_overlap(self):
        d = Discovery(content="a", tags=["x", "y"])
        existing = [Discovery(content="b", tags=["x", "z"])]
        score = ExploratoryLoop._default_diversity(d, existing)
        assert 0.0 < score < 1.0

    @pytest.mark.asyncio
    async def test_explore_with_seed(self, mock_generator):
        loop = ExploratoryLoop(generator=mock_generator, max_rounds=3)
        result = await loop.explore("seed_topic")
        assert isinstance(result, ExplorationResult)
        assert len(result.discoveries) > 0

    @pytest.mark.asyncio
    async def test_explore_stops_at_max_rounds(self, mock_generator):
        loop = ExploratoryLoop(generator=mock_generator, max_rounds=10, max_tokens=1_000_000)
        loop._diversity_evaluator = MagicMock(return_value=0.0)
        result = await loop.explore("seed")
        assert result.metadata["stop_reason"] == "no_novelty"

    @pytest.mark.asyncio
    async def test_explore_manual_stop(self, mock_generator):
        def stopping_gen(existing, branch_factor):
            loop.stop()
            return [Discovery(content=f"x_{i}") for i in range(branch_factor)]

        loop = ExploratoryLoop(generator=stopping_gen)
        result = await loop.explore("seed")
        assert result.metadata["stop_reason"] == "manual_stop"

    @pytest.mark.asyncio
    async def test_run_wraps_explore(self, mock_generator):
        loop = ExploratoryLoop(generator=mock_generator, max_rounds=2)
        result = await loop.run(seed="hello")
        assert isinstance(result.output, ExplorationResult)

    @pytest.mark.asyncio
    async def test_check_coverage(self, mock_generator):
        loop = ExploratoryLoop(generator=mock_generator, coverage_target=0.8)
        loop._discoveries = [
            Discovery(content="a", tags=["t1"]),
            Discovery(content="b", tags=["t2"]),
            Discovery(content="c", tags=["t3"]),
            Discovery(content="d", tags=["t4"]),
        ]
        assert loop._check_coverage() is True

    @pytest.mark.asyncio
    async def test_check_coverage_no_discoveries(self, mock_generator):
        loop = ExploratoryLoop(generator=mock_generator)
        assert loop._check_coverage() is False

    def test_finalize_exploration_creates_histogram(self):
        loop = ExploratoryLoop(generator=lambda e, b: [], max_rounds=10)
        loop._discoveries = [
            Discovery(content="a", tags=["x"]),
            Discovery(content="b", tags=["y", "z"]),
        ]
        result = loop._finalize_exploration(LoopStopReason.COVERAGE_MET)
        assert "x" in result.diversity_histogram
        assert "y" in result.diversity_histogram
