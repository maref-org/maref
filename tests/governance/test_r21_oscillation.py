from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from src.maref.governance.oscillation import (
    OscillationEvent,
    OscillationFixLoop,
    OscillationStage,
)


class TestOscillationEvent:
    def test_event_creation_with_defaults(self):
        event = OscillationEvent(
            timestamp=1000.0,
            initial_rate=5.0,
            entropy_before=3,
            state_before="ACT",
        )
        assert event.timestamp == 1000.0
        assert event.initial_rate == 5.0
        assert event.entropy_before == 3
        assert event.state_before == "ACT"
        assert event.stabilized_at == 0.0
        assert event.cooldown_duration == 0.0
        assert event.verification_passed is False
        assert event.threshold_adjusted is False
        assert event.resolved is False

    def test_event_full_cycle(self):
        event = OscillationEvent(
            timestamp=1000.0,
            initial_rate=15.0,
            entropy_before=5,
            state_before="ACT",
            stabilized_at=1000.5,
            cooldown_duration=5.0,
            verification_passed=True,
            threshold_adjusted=True,
            resolved=True,
        )
        assert event.resolved is True
        assert event.threshold_adjusted is True
        assert event.verification_passed is True


class TestOscillationFixLoop:
    @pytest.fixture
    def stabilize_fn(self):
        return MagicMock()

    @pytest.fixture
    def get_state_fn(self):
        def _get_state():
            return {"state": "STABILIZE", "entropy": 2}

        return _get_state

    @pytest.fixture
    def loop(self, stabilize_fn):
        return OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=None,
            cooldown_seconds=0.01,
            max_rate=10.0,
        )

    @pytest.fixture
    def loop_with_state(self, stabilize_fn, get_state_fn):
        return OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=get_state_fn,
            cooldown_seconds=0.01,
            max_rate=10.0,
        )

    def test_initialization_defaults(self, stabilize_fn):
        loop = OscillationFixLoop(stabilize_fn=stabilize_fn)
        assert loop.stage == OscillationStage.IDLE
        assert loop.get_stats()["total_events"] == 0

    def test_stage_property(self, loop):
        assert loop.stage == OscillationStage.IDLE

    def test_rate_below_max_returns_normal(self, loop):
        result = asyncio.run(loop.detect_and_fix(rate=5.0, entropy=3, current_state="ACT"))
        assert result["resolved"] is True
        assert result["message"] == "rate_normal"
        assert loop.stage == OscillationStage.IDLE

    def test_already_in_progress_returns_early(self, loop):
        loop._stage = OscillationStage.STABILIZING
        result = asyncio.run(loop.detect_and_fix(rate=15.0, entropy=3, current_state="ACT"))
        assert result["resolved"] is True
        assert result["message"] == "already in progress"

    def test_detect_and_fix_high_rate_oscillation_resolved(self, loop_with_state):
        result = asyncio.run(
            loop_with_state.detect_and_fix(rate=15.0, entropy=4, current_state="ACT")
        )
        assert result["resolved"] is True
        assert result["message"] == "oscillation_resolved"
        assert "event" in result
        event = result["event"]
        assert event.resolved is True
        assert event.threshold_adjusted is True

    def test_detect_and_fix_stabilize_called(self, stabilize_fn):
        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=lambda: {"state": "STABILIZE"},
            cooldown_seconds=0.01,
            max_rate=10.0,
        )
        asyncio.run(loop.detect_and_fix(rate=15.0, entropy=4, current_state="ACT"))
        stabilize_fn.assert_called_once_with(reason="oscillation_fix_loop")

    def test_get_stats_with_events(self, loop_with_state):
        asyncio.run(loop_with_state.detect_and_fix(rate=15.0, entropy=4, current_state="ACT"))
        stats = loop_with_state.get_stats()
        assert stats["total_events"] == 1
        assert stats["resolved_count"] == 1
        assert stats["unresolved_count"] == 0
        assert stats["last_event"] is not None
        assert stats["last_event"]["resolved"] is True

    def test_get_stats_no_events(self, loop):
        stats = loop.get_stats()
        assert stats["total_events"] == 0
        assert stats["resolved_count"] == 0
        assert stats["unresolved_count"] == 0
        assert stats["last_event"] is None

    def test_reset(self, loop):
        loop._stage = OscillationStage.DETECTED
        loop.reset()
        assert loop.stage == OscillationStage.IDLE

    def test_verification_failure_persists(self, stabilize_fn):
        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=lambda: "UNSTABLE_123",
            cooldown_seconds=0.01,
            max_rate=10.0,
        )
        result = asyncio.run(loop.detect_and_fix(rate=15.0, entropy=4, current_state="ACT"))
        assert result["resolved"] is False

    def test_verify_stability_no_get_state(self, loop):
        stable = asyncio.run(loop._verify_stability())
        assert stable is True

    def test_verify_stability_with_get_state_stabilized(self, loop_with_state):
        stable = asyncio.run(loop_with_state._verify_stability())
        assert stable is True

    def test_verify_stability_get_state_returns_non_stabilize(self, stabilize_fn):
        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=lambda: {"state": "RUNNING"},
            cooldown_seconds=0.01,
            max_rate=10.0,
        )
        stable = asyncio.run(loop._verify_stability())
        assert stable is False

    def test_verify_stability_get_state_raises_exception(self, stabilize_fn):
        def _failing_state():
            raise RuntimeError("state fetch failed")

        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=_failing_state,
            cooldown_seconds=0.01,
            max_rate=10.0,
        )
        stable = asyncio.run(loop._verify_stability())
        assert stable is False

    def test_verify_stability_with_partial_stabilize_string(self, stabilize_fn):
        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            get_state_fn=lambda: {"state": "STABILIZE"},
            cooldown_seconds=0.01,
            max_rate=10.0,
        )
        stable = asyncio.run(loop._verify_stability())
        assert stable is True

    def test_multiple_events_accumulate(self, loop_with_state):
        asyncio.run(loop_with_state.detect_and_fix(rate=15.0, entropy=4, current_state="ACT"))
        asyncio.run(loop_with_state.detect_and_fix(rate=15.0, entropy=5, current_state="STABILIZE"))
        stats = loop_with_state.get_stats()
        assert stats["total_events"] == 2
        assert stats["resolved_count"] == 2

    def test_oscillation_stage_enum_values(self):
        assert OscillationStage.IDLE.value == "idle"
        assert OscillationStage.DETECTED.value == "detected"
        assert OscillationStage.STABILIZING.value == "stabilizing"
        assert OscillationStage.COOLDOWN.value == "cooldown"
        assert OscillationStage.VERIFYING.value == "verifying"
        assert OscillationStage.ADJUSTING.value == "adjusting"
