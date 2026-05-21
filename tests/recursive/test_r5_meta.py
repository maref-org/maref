from __future__ import annotations

import time

import pytest

from maref.recursive.meta_governance import (
    MetaBreakerState,
    MetaCircuitBreaker,
    MetaGovernance,
    RecursionDepthExceededError,
)


class TestMetaGovernance:
    @pytest.fixture
    def meta(self) -> MetaGovernance:
        MetaGovernance.reset_depth_registry()
        return MetaGovernance()

    def test_create_with_depth_zero(self) -> None:
        mg = MetaGovernance(depth=0)
        assert mg.depth == 0

    def test_create_with_depth_three(self) -> None:
        mg = MetaGovernance(depth=3)
        assert mg.depth == 3

    def test_depth_four_raises(self) -> None:
        with pytest.raises(RecursionDepthExceededError, match="递归深度超出限制"):
            MetaGovernance(depth=4)

    def test_wrap_stores_inner(self, meta: MetaGovernance) -> None:
        inner = object()
        meta.wrap(inner)
        assert meta.inner is inner

    def test_wrap_creates_audit_entry(self, meta: MetaGovernance) -> None:
        inner = object()
        meta.wrap(inner)
        assert len(meta.audit_trail) == 1
        assert meta.audit_trail[0].event == "wrap_inner_governance"

    def test_meta_cb_starts_closed(self, meta: MetaGovernance) -> None:
        assert meta.meta_cb.state == MetaBreakerState.CLOSED

    def test_inner_trips_once_does_not_open(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        assert meta.meta_cb.state == MetaBreakerState.CLOSED
        assert meta.meta_cb.inner_trip_count == 1

    def test_inner_trips_three_times_opens_outer(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        assert meta.meta_cb.state == MetaBreakerState.OPEN

    def test_outer_open_halt_system(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        assert meta.is_halted is True

    def test_half_open_recovery(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.meta_cb.last_open_time = meta.meta_cb.last_open_time - 31
        recovered = meta.try_recover()
        assert recovered is True
        assert meta.is_halted is False

    def test_confirm_recovery_closes_cb(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.meta_cb.last_open_time = meta.meta_cb.last_open_time - 31
        meta.try_recover()
        confirmed = meta.confirm_recovery()
        assert confirmed is True
        assert meta.meta_cb.state == MetaBreakerState.CLOSED
        assert meta.meta_cb.inner_trip_count == 0

    def test_fail_half_open_reopens(self, meta: MetaGovernance) -> None:
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.meta_cb.cooldown_seconds = 0
        meta.try_recover()
        meta.meta_cb.fail_half_open()
        assert meta.meta_cb.state == MetaBreakerState.OPEN

    def test_cross_layer_audit_traceability(self, meta: MetaGovernance) -> None:
        inner = object()
        meta.wrap(inner)
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        meta.signal_inner_trip()
        entries = meta.audit_trail
        layers = {e.layer for e in entries}
        assert f"depth_{meta.depth}" in layers
        events = [e.event for e in entries]
        assert "wrap_inner_governance" in events
        assert "inner_cb_trip" in events
        assert "outer_open_inner_halt" in events

    def test_max_depth_class_method(self) -> None:
        assert MetaGovernance.max_depth() == 3

    def test_set_get_inner_state(self, meta: MetaGovernance) -> None:
        meta.set_inner_state("RUNNING")
        assert meta.get_inner_state() == "RUNNING"


class TestMetaCircuitBreaker:
    def test_initial_state_closed(self) -> None:
        cb = MetaCircuitBreaker()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_record_trip_increments_count(self) -> None:
        cb = MetaCircuitBreaker()
        cb.record_trip()
        assert cb.inner_trip_count == 1

    def test_record_trip_opens_after_threshold(self) -> None:
        cb = MetaCircuitBreaker(inner_trip_threshold=2)
        cb.record_trip()
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

    def test_try_half_open_before_cooldown_fails(self) -> None:
        cb = MetaCircuitBreaker()
        cb.state = MetaBreakerState.OPEN
        cb.last_open_time = time.time()
        assert cb.try_half_open() is False

    def test_try_half_open_after_cooldown(self) -> None:
        cb = MetaCircuitBreaker()
        cb.state = MetaBreakerState.OPEN
        cb.last_open_time = time.time() - 31
        assert cb.try_half_open() is True
        assert cb.state == MetaBreakerState.HALF_OPEN

    def test_close_resets(self) -> None:
        cb = MetaCircuitBreaker(inner_trip_threshold=1)
        cb.record_trip()
        cb.close()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_fail_half_open(self) -> None:
        cb = MetaCircuitBreaker()
        cb.state = MetaBreakerState.HALF_OPEN
        cb.fail_half_open()
        assert cb.state == MetaBreakerState.OPEN
