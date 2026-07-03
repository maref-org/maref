from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.execution.harness import UnifiedHarness
from maref.execution.harness.exceptions import HarnessAbortedError, HarnessExecutionError
from maref.execution.harness.lifecycle import HarnessLifecycleState
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus


class TestUnifiedHarness:
    def test_initial_state(self) -> None:
        h = UnifiedHarness()
        assert h.lifecycle_state == HarnessLifecycleState.INIT
        assert not h.is_terminal
        assert h.transition_history == [HarnessLifecycleState.INIT]

    def test_configure(self) -> None:
        h = UnifiedHarness()
        config = HarnessConfig(harness_type="stress", level="L3")
        h.configure(config)
        assert h._config is not None
        assert h._config.harness_type == "stress"

    def test_configure_with_governance(self) -> None:
        bridge = MagicMock()
        h = UnifiedHarness(governance_bridge=bridge)
        config = HarnessConfig(level="L5")
        h.configure(config)
        bridge.configure.assert_called_once_with(config)

    def test_preflight_transitions_to_ready(self) -> None:
        h = UnifiedHarness()
        warnings = h.preflight()
        assert h.lifecycle_state == HarnessLifecycleState.READY
        assert isinstance(warnings, list)

    def test_preflight_warns_no_config(self) -> None:
        h = UnifiedHarness()
        warnings = h.preflight()
        assert "no configuration set" in warnings

    def test_preflight_with_config(self) -> None:
        h = UnifiedHarness()
        h.configure(HarnessConfig())
        warnings = h.preflight()
        assert "no configuration set" not in warnings

    def test_preflight_with_audit_logger(self) -> None:
        audit = MagicMock()
        h = UnifiedHarness(audit_logger=audit)
        h.configure(HarnessConfig())
        h.preflight()
        audit.log_preflight.assert_called_once()

    def test_preflight_governance_block(self) -> None:
        bridge = MagicMock()
        bridge.check.return_value = False
        bridge.state_name = "blocked"
        h = UnifiedHarness(governance_bridge=bridge)
        h.configure(HarnessConfig())
        with pytest.raises(HarnessAbortedError, match="governance block"):
            h.preflight()
        assert h.lifecycle_state == HarnessLifecycleState.FAILED

    def test_run_no_config(self) -> None:
        h = UnifiedHarness()
        h.configure(HarnessConfig())
        h.preflight()
        h._config = None
        result = h.run(round_id="test-1")
        assert result.status == HarnessStatus.FAILED
        assert "no configuration set" in result.errors

    def test_run_with_step_handler(self) -> None:
        h = UnifiedHarness()
        h.configure(HarnessConfig())
        h.preflight()

        tracker: list[int] = []
        h.add_step_handler(lambda: tracker.append(1))
        h.add_step_handler(lambda: tracker.append(2))

        result = h.run(round_id="test-2")
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.passed
        assert tracker == [1, 2]

    def test_run_step_handler_exception(self) -> None:
        h = UnifiedHarness()
        h.configure(HarnessConfig())
        h.preflight()

        def failing() -> None:
            raise ValueError("step error")

        h.add_step_handler(failing)
        result = h.run(round_id="test-3")
        assert result.status == HarnessStatus.FAILED
        assert "step error" in result.errors

    def test_run_governance_block_on_step(self) -> None:
        bridge = MagicMock()
        bridge.check.side_effect = [True, False]
        bridge.state_name = "blocked"
        h = UnifiedHarness(governance_bridge=bridge)
        h.configure(HarnessConfig())
        h.preflight()

        h.add_step_handler(lambda: None)
        with pytest.raises(HarnessAbortedError, match="governance block"):
            h.run(round_id="test-4")

    def test_run_with_hook_registry(self) -> None:
        hook_registry = MagicMock()
        hook_result = MagicMock()
        hook_result.passed = True
        hook_registry.fire.return_value = hook_result

        h = UnifiedHarness(hook_registry=hook_registry)
        h.configure(HarnessConfig())
        h.preflight()
        result = h.run(round_id="test-5")
        assert result.status == HarnessStatus.SUCCEEDED

    def test_run_with_hook_block(self) -> None:
        hook_registry = MagicMock()

        def fire(topic: str, data: dict) -> MagicMock:
            result = MagicMock()
            if topic == "harness.start":
                result.passed = False
                result.verdict = "denied"
                result.error = "hook blocked"
            else:
                result.passed = True
            return result

        hook_registry.fire.side_effect = fire

        h = UnifiedHarness(hook_registry=hook_registry)
        h.configure(HarnessConfig())
        h.preflight()
        with pytest.raises(HarnessAbortedError, match="hook"):
            h.run(round_id="test-6")

    def test_run_with_run_hook(self) -> None:
        run_hook = MagicMock()
        h = UnifiedHarness(run_hook=run_hook)
        h.configure(HarnessConfig())
        h.preflight()
        h.add_step_handler(lambda: None)
        result = h.run(round_id="test-7")
        assert result.status == HarnessStatus.SUCCEEDED
        run_hook.assert_called_once()

    def test_run_with_memory_hub(self) -> None:
        memory_hub = MagicMock()
        h = UnifiedHarness(memory_hub=memory_hub)
        config = HarnessConfig()
        config.extra = {"memory_recording_enabled": True}
        h.configure(config)
        h.preflight()
        h.add_step_handler(lambda: None)
        result = h.run(round_id="test-8")
        assert result.status == HarnessStatus.SUCCEEDED
        memory_hub.record_decision.assert_called_once()

    def test_context_property(self) -> None:
        h = UnifiedHarness()
        h._context = {"k1": "v1"}
        ctx = h.context
        assert ctx == {"k1": "v1"}
        ctx["k1"] = "modified"
        assert h._context["k1"] == "v1"

    def test_add_step_handler(self) -> None:
        h = UnifiedHarness()
        fn = lambda: None
        h.add_step_handler(fn)
        assert fn in h._step_handlers

    def test_is_terminal(self) -> None:
        h = UnifiedHarness()
        assert not h.is_terminal
        h._lifecycle_state = HarnessLifecycleState.DONE
        assert h.is_terminal
        h._lifecycle_state = HarnessLifecycleState.FAILED
        assert h.is_terminal

    def test_invalid_transition(self) -> None:
        h = UnifiedHarness()
        with pytest.raises(HarnessExecutionError, match="invalid lifecycle transition"):
            h._transition(HarnessLifecycleState.RUNNING)

    def test_validate_delegate(self) -> None:
        h = UnifiedHarness()
        result = HarnessResult(passed=True)
        assert h.validate(result)

        result2 = HarnessResult(passed=False)
        assert not h.validate(result2)
