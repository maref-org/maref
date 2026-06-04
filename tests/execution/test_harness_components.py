"""Harness 组件测试 — 生命周期、GovernanceBridge、OrchestrationBridge、UnifiedHarness。"""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.execution.harness.exceptions import HarnessAbortedError, HarnessExecutionError
from maref.execution.harness.governance_bridge import GovernanceBridge
from maref.execution.harness.lifecycle import HarnessLifecycleState, _VALID_TRANSITIONS
from maref.execution.harness.orchestration_bridge import OrchestrationBridge
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.execution.harness.unified import UnifiedHarness
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.orchestration.plan_executor import ActionHandler, Plan, PlanStep, RouteResolver


# ── HarnessLifecycleState ────────────────────────────────────────────────

class TestHarnessLifecycleState:
    def test_init_transitions_to_preflight(self) -> None:
        assert HarnessLifecycleState.PREFLIGHT in _VALID_TRANSITIONS[HarnessLifecycleState.INIT]

    def test_preflight_transitions_to_ready_or_failed(self) -> None:
        targets = _VALID_TRANSITIONS[HarnessLifecycleState.PREFLIGHT]
        assert HarnessLifecycleState.READY in targets
        assert HarnessLifecycleState.FAILED in targets

    def test_ready_transitions_to_running(self) -> None:
        assert HarnessLifecycleState.RUNNING in _VALID_TRANSITIONS[HarnessLifecycleState.READY]

    def test_running_transitions_to_validating_or_failed(self) -> None:
        targets = _VALID_TRANSITIONS[HarnessLifecycleState.RUNNING]
        assert HarnessLifecycleState.VALIDATING in targets
        assert HarnessLifecycleState.FAILED in targets

    def test_done_is_absorbing(self) -> None:
        assert _VALID_TRANSITIONS[HarnessLifecycleState.DONE] == []

    def test_failed_is_absorbing(self) -> None:
        assert _VALID_TRANSITIONS[HarnessLifecycleState.FAILED] == []

    def test_invalid_transition_raises(self) -> None:
        harness = UnifiedHarness()
        from maref.execution.harness.exceptions import HarnessExecutionError
        with pytest.raises(HarnessExecutionError):
            harness._transition(HarnessLifecycleState.DONE)  # from INIT -> DONE is invalid


# ── GovernanceBridge ─────────────────────────────────────────────────────

class TestGovernanceBridge:
    def test_preflight_allows_valid_states(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, reason="test")
        bridge = GovernanceBridge(state_machine=sm)
        assert bridge.check("preflight") is True

    def test_preflight_blocks_invalid_state(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, reason="test")
        sm.transition(GovernanceState.ANALYZE, reason="test")
        sm.transition(GovernanceState.EVALUATE, reason="test")
        sm.transition(GovernanceState.DECIDE, reason="test")
        bridge = GovernanceBridge(state_machine=sm)
        assert bridge.check("preflight") is False

    def test_running_checks_circuit_breaker(self) -> None:
        bridge = GovernanceBridge()
        assert bridge.check("running") is True
        # record_failure trips at max_consecutive_failures=5
        for _ in range(5):
            bridge.record_failure()
        assert bridge.check("running") is False

    def test_halt_state_blocks_all(self) -> None:
        sm = GovernanceStateMachine()
        sm.force_halt(reason="test")
        bridge = GovernanceBridge(state_machine=sm)
        assert bridge.check("preflight") is False
        assert bridge.check("running") is False
        assert bridge.check("validating") is False

    def test_record_triggers_halt_on_violation(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.DECIDE, reason="test")
        bridge = GovernanceBridge(state_machine=sm)
        bridge.record("preflight", allowed=False)
        assert bridge.halt_triggered is True
        assert sm.current_state == GovernanceState.HALT

    def test_record_does_not_trigger_halt_if_allowed(self) -> None:
        bridge = GovernanceBridge()
        bridge.record("preflight", allowed=True)
        assert bridge.halt_triggered is False

    def test_configure_sets_max_depth(self) -> None:
        bridge = GovernanceBridge()
        bridge.configure(HarnessConfig(extra={"max_depth": 5}))
        # depth=3 <= max_depth=5 → allowed
        assert bridge.circuit_breaker.check_depth(3) is True
        # depth=6 > max_depth=5 → blocked (trips breaker)
        assert bridge.circuit_breaker.check_depth(6) is False

    def test_stats_returns_dict(self) -> None:
        bridge = GovernanceBridge()
        stats = bridge.get_stats()
        assert "governance_state" in stats
        assert "circuit_breaker" in stats
        assert "halt_triggered" in stats
        assert "check_count" in stats


# ── OrchestrationBridge ──────────────────────────────────────────────────

class TestOrchestrationBridge:
    def test_default_decomposer_creates_single_step_plan(self) -> None:
        bridge = OrchestrationBridge()
        graph = bridge.decompose("test task")
        assert graph.node_count == 1

    def test_custom_decomposer(self) -> None:
        def custom_decomposer(task: str) -> Plan:
            steps = [
                PlanStep(task_id="step_1", action="execute", params={"task": task}),
                PlanStep(task_id="step_2", action="verify", depends_on=["step_1"]),
            ]
            return Plan(plan_id="custom", steps=steps)

        bridge = OrchestrationBridge(decomposer=custom_decomposer)
        graph = bridge.decompose("test task")
        assert graph.node_count == 2

    def test_handler_registration(self) -> None:
        bridge = OrchestrationBridge()
        called = []

        def handler(ctx: dict[str, Any]) -> dict[str, Any]:
            called.append(True)
            return {"status": "ok"}

        bridge.register_handler("test_action", handler)
        assert "test_action" in bridge.executor._handlers

    def test_multiple_handler_registration(self) -> None:
        bridge = OrchestrationBridge()
        handlers: dict[str, ActionHandler] = {
            "a": lambda ctx: {"status": "a"},
            "b": lambda ctx: {"status": "b"},
        }
        bridge.register_handlers(handlers)
        assert "a" in bridge.executor._handlers
        assert "b" in bridge.executor._handlers

    def test_route_resolver_registration(self) -> None:
        bridge = OrchestrationBridge()
        resolver: RouteResolver = lambda step, ctx: "default_agent"
        bridge.register_route_resolver("rule_1", resolver)

    def test_execute_empty_graph(self) -> None:
        bridge = OrchestrationBridge()
        graph = bridge.decompose("noop")
        result = bridge.execute(graph)
        assert "plan_id" in result
        assert "status" in result

    def test_to_harness_result_success(self) -> None:
        bridge = OrchestrationBridge()
        result = bridge.to_harness_result(
            {"status": "completed", "total_duration_ms": 500, "step_count": 2,
             "success_count": 2, "failure_count": 0, "error": None, "steps": []},
            round_id="round_1",
        )
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.round_id == "round_1"

    def test_to_harness_result_failure(self) -> None:
        bridge = OrchestrationBridge()
        result = bridge.to_harness_result(
            {"status": "failed", "total_duration_ms": 100, "step_count": 1,
             "success_count": 0, "failure_count": 1, "error": "boom", "steps": []},
        )
        assert result.status == HarnessStatus.FAILED

    def test_set_decomposer_replaces_default(self) -> None:
        bridge = OrchestrationBridge()
        def three_step(task: str) -> Plan:
            steps = [
                PlanStep(task_id="s1", action="a"),
                PlanStep(task_id="s2", action="b", depends_on=["s1"]),
                PlanStep(task_id="s3", action="c", depends_on=["s2"]),
            ]
            return Plan(plan_id="p", steps=steps)
        bridge.set_decomposer(three_step)
        graph = bridge.decompose("x")
        assert graph.node_count == 3


# ── UnifiedHarness ───────────────────────────────────────────────────────

class TestUnifiedHarness:
    def test_init_state_is_init(self) -> None:
        harness = UnifiedHarness()
        assert harness.lifecycle_state == HarnessLifecycleState.INIT
        assert not harness.is_terminal

    def test_preflight_succeeds(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        warnings = harness.preflight()
        assert harness.lifecycle_state == HarnessLifecycleState.READY
        assert isinstance(warnings, list)

    def test_run_without_config_fails(self) -> None:
        harness = UnifiedHarness()
        harness.preflight()  # succeeds with warning
        result = harness.run()
        assert result.status == HarnessStatus.FAILED
        assert "no configuration set" in result.errors

    def test_full_lifecycle_success(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig(harness_type="unified", level="L1"))
        harness.preflight()
        result = harness.run(round_id="test_full")
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.passed
        assert harness.lifecycle_state == HarnessLifecycleState.DONE

    def test_transition_history_records_all_steps(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        harness.preflight()
        harness.run()
        history = harness.transition_history
        assert HarnessLifecycleState.INIT in history
        assert HarnessLifecycleState.DONE in history or HarnessLifecycleState.FAILED in history

    def test_step_handlers_execute(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        harness.preflight()
        calls: list[int] = []
        harness.add_step_handler(lambda: calls.append(1))
        harness.add_step_handler(lambda: calls.append(2))
        harness.run()
        assert calls == [1, 2]

    def test_exception_in_step_handler_fails(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        harness.preflight()
        def crash() -> None:
            raise RuntimeError("step crash")
        harness.add_step_handler(crash)
        result = harness.run()
        assert result.status == HarnessStatus.FAILED
        assert "step crash" in result.errors

    def test_governance_bridge_halts_execution(self) -> None:
        sm = GovernanceStateMachine()
        sm.force_halt(reason="halt test")
        bridge = GovernanceBridge(state_machine=sm)
        harness = UnifiedHarness(governance_bridge=bridge)
        harness.configure(HarnessConfig())
        with pytest.raises(HarnessAbortedError):
            harness.preflight()

    def test_terminal_after_failure(self) -> None:
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        harness.preflight()
        def crash() -> None:
            raise RuntimeError("fail")
        harness.add_step_handler(crash)
        harness.run()
        assert harness.is_terminal

    def test_validate_passed_result(self) -> None:
        harness = UnifiedHarness()
        result = HarnessResult(status=HarnessStatus.SUCCEEDED)
        assert harness.validate(result) is True

    def test_validate_failed_result(self) -> None:
        harness = UnifiedHarness()
        result = HarnessResult(status=HarnessStatus.FAILED, errors=["x"])
        assert harness.validate(result) is False

    def test_rich_result_display(self) -> None:
        """Verify format_harness_result works (smoke test)."""
        harness = UnifiedHarness()
        harness.configure(HarnessConfig())
        harness.preflight()
        result = harness.run()
        from maref.execution.harness.display import format_harness_result
        from maref.execution.harness.governance_bridge import GovernanceBridge
        bridge = GovernanceBridge()
        format_harness_result(
            result=result,
            lifecycle_history=[s.value for s in harness.transition_history],
            lifecycle_terminal=harness.is_terminal,
            governance_state=bridge.state_name,
            circuit_breaker_state=bridge.circuit_breaker.state.value,
            halt_triggered=bridge.halt_triggered,
            check_count=len(bridge.check_history),
        )


# ── HALT 阻断测试 ────────────────────────────────────────────────────────

class TestHALTBlocking:
    def test_halt_blocks_preflight(self) -> None:
        sm = GovernanceStateMachine()
        sm.force_halt("test")
        bridge = GovernanceBridge(state_machine=sm)
        with pytest.raises(HarnessAbortedError) as exc:
            harness = UnifiedHarness(governance_bridge=bridge)
            harness.configure(HarnessConfig())
            harness.preflight()
        assert "governance block" in str(exc.value).lower()

    def test_halt_blocks_run_via_preflight_check(self) -> None:
        """HALT 状态下 preflight 被阻止 → run 不应执行。"""
        sm = GovernanceStateMachine()
        sm.force_halt("test")
        bridge = GovernanceBridge(state_machine=sm)
        harness = UnifiedHarness(governance_bridge=bridge)
        harness.configure(HarnessConfig())
        with pytest.raises(HarnessAbortedError):
            harness.preflight()

    def test_halt_during_running_via_step_check(self) -> None:
        """运行中治理变为 HALT → step check 应抛出 HarnessAbortedError。"""
        sm = GovernanceStateMachine()
        bridge = GovernanceBridge(state_machine=sm)
        harness = UnifiedHarness(governance_bridge=bridge)
        harness.configure(HarnessConfig())
        harness.preflight()

        # 在 step handler 中触发 HALT
        def trigger_halt(_ctx: Any = None) -> None:
            sm.force_halt("simulated halt during step")
        harness.add_step_handler(trigger_halt)

        # step handler 被执行 → check_governance 抛出 HarnessAbortedError
        with pytest.raises(HarnessAbortedError):
            harness.run()

    def test_halt_triggers_governance_state_change(self) -> None:
        """验证 GovernanceBridge 在违规时确实修改了治理状态机。"""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, reason="test")
        sm.transition(GovernanceState.ANALYZE, reason="test")
        sm.transition(GovernanceState.EVALUATE, reason="test")
        sm.transition(GovernanceState.DECIDE, reason="test")
        bridge = GovernanceBridge(state_machine=sm)
        bridge.record("preflight", allowed=False)
        assert sm.current_state == GovernanceState.HALT
        assert bridge.halt_triggered


# ── Orchestration 集成测试 ────────────────────────────────────────────────

class TestOrchestrationIntegration:
    def test_decompose_and_execute(self) -> None:
        bridge = OrchestrationBridge()
        graph = bridge.decompose("simple task")
        result = bridge.execute(graph)
        assert result["status"] in ("completed", "partially_completed", "failed")

    def test_harness_with_orchestration(self) -> None:
        """验证 UnifiedHarness + OrchestrationBridge 集成。"""
        orb = OrchestrationBridge()
        harness = UnifiedHarness(orchestration_bridge=orb)
        harness.configure(HarnessConfig())
        harness.preflight()
        harness.add_step_handler(lambda: None)
        result = harness.run()
        assert result.status in (HarnessStatus.SUCCEEDED, HarnessStatus.FAILED)

    def test_orchestration_result_conversion(self) -> None:
        orb = OrchestrationBridge()
        result = orb.to_harness_result(
            {"status": "completed", "total_duration_ms": 1000, "step_count": 3,
             "success_count": 3, "failure_count": 0, "error": None, "steps": []},
        )
        assert result.harness_type == "orchestrated"
        assert result.passed
        assert result.metrics["step_count"] == 3

    def test_custom_handler_integration(self) -> None:
        orb = OrchestrationBridge()
        results: list[str] = []
        def handler(action: str, ctx: dict[str, Any]) -> dict[str, Any]:
            results.append(action)
            return {"status": "ok"}
        orb.register_handler("custom_action", handler)
        plan = Plan(
            plan_id="handler_test",
            steps=[PlanStep(task_id="t1", action="custom_action")],
        )
        report = orb.executor.execute(plan)
        assert report.success_count == 1
        assert results == ["custom_action"]
