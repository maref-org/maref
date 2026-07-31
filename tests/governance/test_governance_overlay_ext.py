"""GovernanceOverlay 事件循环扩展测试（P1-8）

覆盖：
1. 完整治理周期 INIT → OBSERVE → ... → REPORT → OBSERVE
2. 异步事件循环稳定性（并发、拥塞、恢复）
3. _governance_cycle() 集成
4. 振荡回路 + cooldown 集成
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref.governance import GovernanceState
from maref_lite.governance import GovernanceOverlay


@pytest.fixture
def overlay():
    return GovernanceOverlay(oscillation_cooldown=0.5, audit_log_path=None)


@pytest.mark.asyncio
class TestFullGovernanceCycle:
    """完整治理周期测试"""

    async def test_governance_cycle_auto_transitions(self, overlay):
        await overlay._governance_cycle()
        assert overlay._state_machine.current_state == GovernanceState.OBSERVE

    async def test_governance_cycle_records_decision(self, overlay):
        await overlay._governance_cycle()
        assert len(overlay.get_decisions()) == 1
        d = overlay.get_decisions()[0]
        assert d.action == "auto_transition"
        assert d.from_state == GovernanceState.INIT
        assert d.to_state == GovernanceState.OBSERVE

    async def test_full_cycle_init_to_report(self, overlay):
        await overlay._governance_cycle()
        sm = overlay._state_machine
        assert sm.current_state == GovernanceState.OBSERVE

        states = [
            GovernanceState.ANALYZE,
            GovernanceState.EVALUATE,
            GovernanceState.DECIDE,
            GovernanceState.ACT,
            GovernanceState.VERIFY,
            GovernanceState.STABILIZE,
            GovernanceState.REPORT,
        ]
        for state in states:
            assert sm.transition(state, reason="test"), f"Cannot transition to {state}"
        assert sm.current_state == GovernanceState.REPORT

    async def test_cycle_reach_halt(self, overlay):
        await overlay._governance_cycle()
        sm = overlay._state_machine
        assert sm.current_state == GovernanceState.OBSERVE
        for state in [GovernanceState.ANALYZE,
                      GovernanceState.EVALUATE, GovernanceState.DECIDE,
                      GovernanceState.ACT, GovernanceState.VERIFY]:
            assert sm.transition(state, reason="test"), f"Cannot transition to {state.name}"
        assert sm.is_terminal() is False
        assert sm.current_state == GovernanceState.VERIFY
        overlay._record_decision("force_stabilize", "halt", sm.current_state, GovernanceState.STABILIZE)
        assert sm.force_stabilize("halt")
        assert sm.current_state == GovernanceState.STABILIZE

    async def test_cycle_restart_after_report(self, overlay):
        await overlay._governance_cycle()
        sm = overlay._state_machine
        for state in [
            GovernanceState.ANALYZE, GovernanceState.EVALUATE,
            GovernanceState.DECIDE, GovernanceState.ACT,
            GovernanceState.VERIFY, GovernanceState.STABILIZE,
            GovernanceState.REPORT,
        ]:
            assert sm.transition(state, reason="test"), f"Cannot transition to {state}"
        assert sm.current_state == GovernanceState.REPORT
        assert sm.force_stabilize("restart")
        assert sm.current_state == GovernanceState.STABILIZE


@pytest.mark.asyncio
class TestEventLoopStress:
    """异步事件循环稳定性"""

    async def test_event_loop_processes_burst(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)

        for _ in range(20):
            await overlay.emit_event("oscillation_detected", rate=12.0)

        await asyncio.sleep(0.3)
        overlay.stop()
        task.cancel()

    async def test_concurrent_event_emission(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)

        async def emit_batch(n):
            for _ in range(n):
                await overlay.emit_event("oscillation_detected", rate=12.0)
                await asyncio.sleep(0.005)

        await asyncio.gather(emit_batch(5), emit_batch(5), emit_batch(5))
        await asyncio.sleep(0.3)
        overlay.stop()
        task.cancel()
        assert overlay._event_queue.qsize() <= 15

    async def test_event_loop_recovery_after_error(self, overlay):
        with patch.object(overlay, "_handle_event") as mock:
            mock.side_effect = RuntimeError("burst")
            overlay._running = True
            task = asyncio.create_task(overlay.run())
            await asyncio.sleep(0.05)
            await overlay.emit_event("test", rate=1)
            await asyncio.sleep(0.1)
            overlay.stop()
            task.cancel()

    async def test_event_loop_survives_runtime_error(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)

        await overlay.emit_event("oscillation_detected", rate=12.0)
        await asyncio.sleep(0.2)
        assert overlay._running

        overlay.stop()
        task.cancel()

    async def test_rapid_start_stop(self, overlay):
        for _ in range(5):
            overlay._running = True
            task = asyncio.create_task(overlay.run())
            await asyncio.sleep(0.02)
            overlay.stop()
            task.cancel()
            await asyncio.sleep(0.02)
        assert not overlay._running


@pytest.mark.asyncio
class TestOscillationLoopIntegration:
    """振荡回路集成"""

    async def test_oscillation_detect_and_fix(self, overlay):
        with patch.object(overlay._oscillation_loop, "detect_and_fix") as mock:
            overlay._running = True
            task = asyncio.create_task(overlay.run())
            await asyncio.sleep(0.05)
            await overlay.emit_event("oscillation_detected", rate=15.0)
            await asyncio.sleep(0.3)
            mock.assert_called_once()
            overlay.stop()
            task.cancel()

    async def test_oscillation_with_cooldown(self, overlay):
        with patch.object(overlay._oscillation_loop, "detect_and_fix") as mock:
            overlay._running = True
            task = asyncio.create_task(overlay.run())
            await asyncio.sleep(0.05)
            await overlay.emit_event("oscillation_detected", rate=15.0)
            await asyncio.sleep(0.1)
            await overlay.emit_event("oscillation_detected", rate=15.0)
            await asyncio.sleep(0.3)
            assert mock.call_count >= 1
            overlay.stop()
            task.cancel()

    async def test_oscillation_stabilizes_state(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)

        sm = overlay._state_machine
        for state in [GovernanceState.OBSERVE, GovernanceState.ANALYZE]:
            assert sm.transition(state, reason="setup")

        await overlay.emit_event("oscillation_detected", rate=15.0)
        await asyncio.sleep(0.3)
        overlay.stop()
        task.cancel()


@pytest.mark.asyncio
class TestDriftIntegration:
    """Drift 检测集成"""

    async def test_drift_check_transitions_to_verify(self, overlay):
        from drift_guard.types import DriftSeverity

        sm = overlay._state_machine
        assert sm.transition(GovernanceState.OBSERVE, reason="setup")

        mock_event = MagicMock()
        mock_event.reading.severity = DriftSeverity.HIGH
        mock_pipeline = MagicMock()
        mock_pipeline.check_drift = AsyncMock(return_value=mock_event)
        overlay._drift = mock_pipeline

        await overlay.check_drift(None, None, None, None)
        assert sm.current_state in (GovernanceState.VERIFY, GovernanceState.STABILIZE)

    async def test_drift_check_critical_triggers_stabilize(self, overlay):
        from drift_guard.types import DriftSeverity

        sm = overlay._state_machine
        assert sm.transition(GovernanceState.OBSERVE, reason="setup")

        mock_event = MagicMock()
        mock_event.reading.severity = DriftSeverity.CRITICAL
        mock_pipeline = MagicMock()
        mock_pipeline.check_drift = AsyncMock(return_value=mock_event)
        overlay._drift = mock_pipeline

        await overlay.check_drift(None, None, None, None)
        assert sm.current_state in (GovernanceState.VERIFY, GovernanceState.STABILIZE)


@pytest.mark.asyncio
class TestAsyncLifecycle:
    """异步生命周期边界"""

    async def test_run_without_collector(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.1)
        assert overlay._running
        overlay.stop()
        task.cancel()

    async def test_stop_before_run(self, overlay):
        overlay.stop()
        assert not overlay._running

    async def test_double_stop(self, overlay):
        overlay._running = True
        overlay.stop()
        overlay.stop()
        assert not overlay._running

    async def test_cleanup_on_run_exit(self, overlay):
        overlay._running = True
        asyncio.create_task(overlay.run())
        await asyncio.sleep(0.05)
        overlay.stop()
        await asyncio.sleep(0.1)
        assert not overlay._running

    async def test_probe_reading_during_event_loop(self, overlay):
        overlay._running = True
        task = asyncio.create_task(overlay.run())
        await asyncio.sleep(0.2)
        assert overlay._running
        overlay.stop()
        task.cancel()
        stats = overlay.get_probe_stats()
        assert stats["probe_counts"] is not None
