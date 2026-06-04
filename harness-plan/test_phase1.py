"""Phase 1 测试：UnifiedHarness 生命周期 + Governance 集成。"""

from __future__ import annotations

from maref.execution.harness.exceptions import HarnessAbortedError, HarnessExecutionError
from maref.execution.harness.governance_bridge import GovernanceBridge
from maref.execution.harness.lifecycle import HarnessLifecycleState
from maref.execution.harness.orchestration_bridge import OrchestrationBridge
from maref.execution.harness.types import HarnessConfig, HarnessStatus
from maref.execution.harness.unified import UnifiedHarness
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


# ── Task 1.1: UnifiedHarness 生命周期 ───────────────────────────────────


class TestUnifiedHarnessLifecycle:
    """验证 7 态生命周期：INIT → PREFLIGHT → READY → RUNNING → VALIDATING → REPORTING → DONE"""

    def test_initial_state(self):
        harness = UnifiedHarness()
        assert harness.lifecycle_state == HarnessLifecycleState.INIT
        assert not harness.is_terminal

    def test_full_lifecycle(self):
        harness = UnifiedHarness()
        config = HarnessConfig(harness_type="unified", level="L1")

        warnings = harness.preflight()
        assert harness.lifecycle_state == HarnessLifecycleState.READY
        assert isinstance(warnings, list)

        harness.configure(config)
        result = harness.run(round_id="test_001")

        assert harness.lifecycle_state == HarnessLifecycleState.DONE
        assert harness.is_terminal
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.passed
        assert result.harness_type == "unified"
        assert result.duration_s >= 0

    def test_transition_history_includes_all_states(self):
        harness = UnifiedHarness()
        config = HarnessConfig(harness_type="unified", level="L1")

        harness.preflight()
        harness.configure(config)
        harness.run()

        history = harness.transition_history
        expected = [
            HarnessLifecycleState.INIT,
            HarnessLifecycleState.PREFLIGHT,
            HarnessLifecycleState.READY,
            HarnessLifecycleState.RUNNING,
            HarnessLifecycleState.VALIDATING,
            HarnessLifecycleState.REPORTING,
            HarnessLifecycleState.DONE,
        ]
        assert history == expected, f"Expected {expected}, got {history}"

    def test_configure_without_preflight_errors(self):
        """验证 preflight 前未 configure 会产生警告但不会失败。"""
        harness = UnifiedHarness()
        config = HarnessConfig(harness_type="unified", level="L1")

        warnings = harness.preflight()
        assert "no configuration set" in warnings

        harness.configure(config)
        result = harness.run()
        assert result.passed

    def test_step_handlers_execute(self):
        harness = UnifiedHarness()
        config = HarnessConfig(harness_type="unified", level="L1")
        steps_run = []

        def step1():
            steps_run.append("step1")
        def step2():
            steps_run.append("step2")

        harness.add_step_handler(step1)
        harness.add_step_handler(step2)

        harness.configure(config)
        harness.preflight()
        harness.run()

        assert steps_run == ["step1", "step2"]

    def test_step_handler_failure_transitions_to_failed(self):
        harness = UnifiedHarness()
        config = HarnessConfig(harness_type="unified", level="L1")

        def failing_step():
            raise RuntimeError("step failure")

        harness.add_step_handler(failing_step)
        harness.configure(config)
        harness.preflight()
        result = harness.run()

        assert harness.lifecycle_state == HarnessLifecycleState.FAILED
        assert not result.passed
        assert "step failure" in result.errors[0]

    def test_duplicate_preflight_fails(self):
        harness = UnifiedHarness()
        harness.preflight()
        try:
            harness.preflight()
            assert False, "expected HarnessExecutionError"
        except HarnessExecutionError as e:
            assert "invalid lifecycle transition" in str(e)

    def test_duplicate_run_fails(self):
        harness = UnifiedHarness()
        harness.preflight()
        harness.configure(HarnessConfig())
        harness.run()
        try:
            harness.run()
            assert False, "expected HarnessExecutionError"
        except HarnessExecutionError as e:
            assert "invalid lifecycle transition" in str(e)


# ── Task 1.2: GovernanceBridge 集成 ────────────────────────────────────


class TestGovernanceBridge:
    """验证 GovernanceBridge 对 UnifiedHarness 的集成。"""

    def test_preflight_allowed_in_observe(self):
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "test")
        bridge = GovernanceBridge(state_machine=sm)

        assert bridge.check("preflight") is True

    def test_preflight_allowed_in_analyze(self):
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "to_observe")
        sm.transition(GovernanceState.ANALYZE, "to_analyze")
        bridge = GovernanceBridge(state_machine=sm)

        assert bridge.check("preflight") is True

    def test_preflight_blocked_in_halt(self):
        sm = GovernanceStateMachine()
        sm.force_halt("test")
        bridge = GovernanceBridge(state_machine=sm)

        assert bridge.check("preflight") is False

    def test_running_blocked_when_circuit_open(self):
        bridge = GovernanceBridge()
        bridge._circuit_breaker._trip("test_trip", 0, 0, "")

        assert bridge.check("running") is False

    def test_violation_triggers_halt(self):
        sm = GovernanceStateMachine()
        sm.force_halt("pre_test")
        bridge = GovernanceBridge(state_machine=sm)

        allowed = bridge.check("preflight")
        bridge.record("preflight", allowed)

        assert not allowed
        assert bridge.halt_triggered
        assert sm.current_state == GovernanceState.HALT

    def test_record_stores_history(self):
        bridge = GovernanceBridge()
        bridge.record("preflight", True)
        bridge.record("running", True)
        bridge.record("validating", True)
        assert len(bridge.check_history) == 3

    def test_get_stats(self):
        bridge = GovernanceBridge()
        stats = bridge.get_stats()
        assert "governance_state" in stats
        assert "circuit_breaker" in stats
        assert "halt_triggered" in stats
        assert stats["check_count"] == 0

    def test_unified_harness_rejects_halt(self):
        """集成测试：HALT 状态下 UnifiedHarness 拒绝运行。"""
        sm = GovernanceStateMachine()
        sm.force_halt("test_halt")
        bridge = GovernanceBridge(state_machine=sm)
        harness = UnifiedHarness(governance_bridge=bridge)

        harness.configure(HarnessConfig())
        try:
            harness.preflight()
            assert False, "expected HarnessAbortedError"
        except HarnessAbortedError:
            pass
        assert bridge.halt_triggered


# ── Task 1.3: OrchestrationBridge 集成 ─────────────────────────────────


class TestOrchestrationBridge:
    """验证 OrchestrationBridge 的包装功能。"""

    def test_decompose_returns_task_graph(self):
        bridge = OrchestrationBridge()
        graph = bridge.decompose("test task")
        assert graph.node_count >= 1
        assert "task_1" in graph.node_ids

    def test_execute_runs_plan(self):
        bridge = OrchestrationBridge()
        graph = bridge.decompose("hello")
        result = bridge.execute(graph)
        assert "plan_id" in result
        assert "status" in result

    def test_custom_decomposer(self):
        def my_decomposer(task: str):
            from maref.orchestration.plan_executor import Plan, PlanStep
            return Plan(
                plan_id="custom",
                steps=[PlanStep(task_id="step_1", action="execute", params={"task": task})],
            )

        bridge = OrchestrationBridge(decomposer=my_decomposer)
        graph = bridge.decompose("custom task")
        assert graph.node_count == 1
        assert "step_1" in graph.node_ids

    def test_register_handler(self):
        bridge = OrchestrationBridge()
        results = []

        def my_handler(action, params):
            results.append((action, params))

        bridge.register_handler("execute", my_handler)
        graph = bridge.decompose("test")
        bridge.execute(graph)
        assert len(results) == 1
        assert results[0][0] == "execute"

    def test_to_harness_result_success(self):
        bridge = OrchestrationBridge()
        exec_result = {
            "plan_id": "p1",
            "status": "completed",
            "total_duration_ms": 100,
            "step_count": 1,
            "success_count": 1,
            "failure_count": 0,
            "error": None,
            "steps": [],
        }
        hr = bridge.to_harness_result(exec_result, round_id="r1")
        assert hr.status == HarnessStatus.SUCCEEDED
        assert hr.passed
        assert hr.harness_type == "orchestrated"

    def test_to_harness_result_failure(self):
        bridge = OrchestrationBridge()
        exec_result = {
            "plan_id": "p1",
            "status": "failed",
            "total_duration_ms": 50,
            "step_count": 2,
            "success_count": 0,
            "failure_count": 2,
            "error": "execution error",
            "steps": [
                {"task_id": "t1", "result": "failure", "error": "step failed"},
            ],
        }
        hr = bridge.to_harness_result(exec_result, round_id="r1")
        assert hr.status == HarnessStatus.FAILED
        assert not hr.passed
        assert "execution error" in hr.errors
        assert "t1" in hr.errors[1]


# ── Task 1.4: 集成测试 ─────────────────────────────────────────────────


class TestUnifiedHarnessIntegration:
    """完整集成测试。"""

    def test_full_integration_lifecycle(self):
        """验证 UnifiedHarness + GovernanceBridge 全流程。"""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        bridge = GovernanceBridge(state_machine=sm)
        harness = UnifiedHarness(governance_bridge=bridge)
        config = HarnessConfig(harness_type="unified", level="L1")

        harness.configure(config)
        warnings = harness.preflight()
        result = harness.run(round_id="integrated")

        assert len(warnings) == 0
        assert result.passed
        assert harness.lifecycle_state == HarnessLifecycleState.DONE
        assert sm.current_state != GovernanceState.HALT

    def test_orchestration_within_harness(self):
        """验证 UnifiedHarness 可通过 OrchestrationBridge 执行任务。"""
        bridge = OrchestrationBridge()
        exec_results = []

        def handler(action, params):
            exec_results.append((action, params))

        bridge.register_handler("execute", handler)
        graph = bridge.decompose("integrated task")
        result = bridge.execute(graph)

        assert result["status"] == "completed"
        assert len(exec_results) == 1
