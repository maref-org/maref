from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from maref.loop.budgets import TimeBudget, TokenBudget


class TestTokenBudget:
    def test_default_state(self):
        b = TokenBudget(max_tokens=100)
        assert b.used == 0
        assert b.remaining == 100
        assert b.exhausted is False

    def test_consume_happy_path(self):
        b = TokenBudget(max_tokens=100)
        assert b.consume(40) is True
        assert b.used == 40
        assert b.remaining == 60

    def test_consume_exact_max(self):
        b = TokenBudget(max_tokens=100)
        assert b.consume(100) is True
        assert b.exhausted is True

    def test_consume_over_max_clamps(self):
        b = TokenBudget(max_tokens=100)
        assert b.consume(150) is False
        assert b.used == 100
        assert b.exhausted is True

    def test_reset(self):
        b = TokenBudget(max_tokens=100)
        b.consume(50)
        b.reset()
        assert b.used == 0
        assert b.exhausted is False

    def test_snapshot(self):
        b = TokenBudget(max_tokens=200)
        b.consume(50)
        s = b.snapshot()
        assert s["max_tokens"] == 200
        assert s["used"] == 50
        assert s["remaining"] == 150
        assert s["exhausted"] is False


class TestTimeBudget:
    def test_default_state_before_start(self):
        b = TimeBudget(max_seconds=60)
        assert b.elapsed == 0.0
        assert b.remaining == 60.0
        assert b.exhausted is False

    def test_elapsed_after_start(self):
        b = TimeBudget(max_seconds=60)
        with patch.object(time, "time", return_value=100.0):
            b.start()
        with patch.object(time, "time", return_value=110.0):
            assert b.elapsed == pytest.approx(10.0, rel=0.5)
        with patch.object(time, "time", return_value=170.0):
            assert b.exhausted is True

    def test_reset(self):
        b = TimeBudget(max_seconds=60)
        b._elapsed = 30.0
        b.reset()
        assert b._start == 0.0
        assert b._elapsed == 0.0

    def test_snapshot(self):
        b = TimeBudget(max_seconds=60)
        b._elapsed = 25.0
        s = b.snapshot()
        assert s["max_seconds"] == 60
        assert s["remaining"] == 35.0
