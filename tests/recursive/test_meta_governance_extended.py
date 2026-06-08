"""
MetaGovernance 扩展测试

补充覆盖：wrap 存储 inner、audit_trail 内容、
confirm_recovery 失败路径、set_inner_state/get_inner_state、
max_depth classmethod、reset_depth_registry、
CrossLayerAuditEntry.to_unified、MetaCircuitBreaker 边界。
"""

from __future__ import annotations

import time

import pytest

from maref.recursive.meta_governance import (
    CrossLayerAuditEntry,
    MetaBreakerState,
    MetaCircuitBreaker,
    MetaGovernance,
    RecursionDepthExceededError,
)


class TestMetaGovernanceInit:
    def test_depth_zero(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance(depth=0)
        assert mg.depth == 0

    def test_depth_three(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance(depth=3)
        assert mg.depth == 3

    def test_depth_four_raises(self) -> None:
        MetaGovernance.reset_depth_registry()
        with pytest.raises(RecursionDepthExceededError, match="递归深度超出限制"):
            MetaGovernance(depth=4)

    def test_depth_registry(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg1 = MetaGovernance(depth=0)
        mg2 = MetaGovernance(depth=1)
        assert len(MetaGovernance._depth_registry) == 2


class TestWrap:
    def test_wrap_stores_inner(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        inner = object()
        mg.wrap(inner)
        assert mg.inner is inner

    def test_wrap_creates_audit_entry(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.wrap(object())
        assert len(mg.audit_trail) == 1
        assert mg.audit_trail[0].event == "wrap_inner_governance"


class TestSignalInnerTrip:
    def test_single_trip_does_not_open(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        assert mg.meta_cb.state == MetaBreakerState.CLOSED
        assert mg.meta_cb.inner_trip_count == 1

    def test_three_trips_opens(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        assert mg.meta_cb.state == MetaBreakerState.OPEN

    def test_open_triggers_halt(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        assert mg.is_halted is True

    def test_audit_trail_after_trips(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.wrap(object())
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        events = [e.event for e in mg.audit_trail]
        assert "wrap_inner_governance" in events
        assert "inner_cb_trip" in events
        assert "outer_open_inner_halt" in events


class TestRecovery:
    def test_try_recover_before_cooldown_fails(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        assert mg.try_recover() is False
        assert mg.is_halted is True

    def test_try_recover_after_cooldown(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.meta_cb.last_open_time = mg.meta_cb.last_open_time - 31
        assert mg.try_recover() is True
        assert mg.is_halted is False

    def test_confirm_recovery_success(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.meta_cb.last_open_time = mg.meta_cb.last_open_time - 31
        mg.try_recover()
        assert mg.confirm_recovery() is True
        assert mg.meta_cb.state == MetaBreakerState.CLOSED
        assert mg.meta_cb.inner_trip_count == 0

    def test_confirm_recovery_fails_when_not_half_open(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        assert mg.confirm_recovery() is False

    def test_confirm_recovery_fails_when_still_halted(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.signal_inner_trip()
        mg.meta_cb.last_open_time = mg.meta_cb.last_open_time - 31
        mg.try_recover()
        mg._halted = True
        assert mg.confirm_recovery() is False


class TestInnerState:
    def test_set_get_inner_state(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        mg.set_inner_state("RUNNING")
        assert mg.get_inner_state() == "RUNNING"

    def test_default_inner_state(self) -> None:
        MetaGovernance.reset_depth_registry()
        mg = MetaGovernance()
        assert mg.get_inner_state() == "IDLE"


class TestMaxDepth:
    def test_max_depth(self) -> None:
        assert MetaGovernance.max_depth() == 3


class TestResetDepthRegistry:
    def test_reset_clears_registry(self) -> None:
        MetaGovernance.reset_depth_registry()
        MetaGovernance()
        MetaGovernance()
        assert len(MetaGovernance._depth_registry) > 0
        MetaGovernance.reset_depth_registry()
        assert len(MetaGovernance._depth_registry) == 0
        assert MetaGovernance._next_depth_id == 0


class TestCrossLayerAuditEntry:
    def test_default_creation(self) -> None:
        entry = CrossLayerAuditEntry()
        assert entry.layer == ""
        assert entry.event == ""
        assert entry.timestamp > 0

    def test_to_unified_success(self) -> None:
        entry = CrossLayerAuditEntry(
            layer="depth_0",
            inner_state="RECOVERED",
            outer_state="closed",
            event="recovery_confirmed",
        )
        record = entry.to_unified(round_num=5)
        assert record.layer == "depth_0"
        assert record.round == 5
        assert record.outcome == "success"
        assert "recovery" in record.event_type

    def test_to_unified_failure(self) -> None:
        entry = CrossLayerAuditEntry(
            layer="depth_0",
            inner_state="HALTED",
            outer_state="open",
            event="outer_open_inner_halt",
        )
        record = entry.to_unified()
        assert record.outcome == "failure"

    def test_to_unified_neutral(self) -> None:
        entry = CrossLayerAuditEntry(
            layer="depth_0",
            inner_state="wrapped",
            outer_state="closed",
            event="wrap_inner_governance",
        )
        record = entry.to_unified()
        assert record.outcome is None


class TestMetaCircuitBreaker:
    def test_initial_state(self) -> None:
        cb = MetaCircuitBreaker()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_record_trip_increments(self) -> None:
        cb = MetaCircuitBreaker()
        cb.record_trip()
        assert cb.inner_trip_count == 1

    def test_record_trip_opens_at_threshold(self) -> None:
        cb = MetaCircuitBreaker(inner_trip_threshold=2)
        cb.record_trip()
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN
        assert cb.last_open_time > 0

    def test_try_half_open_before_cooldown(self) -> None:
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
        assert cb.last_open_time > 0
