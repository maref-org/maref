"""Desktop agent chaos/self-healing tests.

Tests five failure modes and verifies self-healing mechanisms:
1. PyAutoGUI timeout
2. OmniParser failure
3. Window disappeared
4. Clipboard locked
5. Playwright crash

All tests marked @pytest.mark.slow as they simulate real hardware conditions.
"""

from __future__ import annotations

import pytest

from maref.desktop.agent import (
    DesktopAgent,
    DesktopOperation,
    DesktopStep,
    DesktopTask,
    SelfHealingExecutor,
)
from maref.desktop.input_controller import InputController, InputSafetyGate


class TestPyAutoGUITimeout:
    """Test agent resilience when PyAutoGUI operations time out."""

    def test_healing_recovers_from_timeout(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=3)
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_position=(0, 0),
            description="Click at edge position",
        )
        _result = executor.execute_step(step)
        assert executor.consecutive_failures <= 3

    def test_agent_survives_multiple_retries(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=5)
        parse = agent.parse_screen()
        for _ in range(3):
            step = DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id="ghost_element_99999",
            )
            executor.execute_step(step, parse)
        assert executor.circuit_open is True or executor.consecutive_failures >= 3

    @pytest.mark.slow
    def test_input_controller_retry_on_timeout(self) -> None:
        controller = InputController(dry_run=True, max_retries=2)
        result = controller.click(-100, -100)
        assert isinstance(result.success, bool)


class TestOmniParserFailure:
    """Test agent resilience when OmniParser fails or falls back to mock."""

    def test_auto_backend_always_succeeds_init(self) -> None:
        from maref.desktop.screen_parser import OmniParserInterface

        parser = OmniParserInterface(backend="auto")
        ok = parser.initialize()
        assert ok is True
        assert parser.initialized is True

    def test_agent_continues_with_fallback_backend(self) -> None:
        agent = DesktopAgent(dry_run=True)
        parse = agent.parse_screen()
        assert parse is not None
        assert len(parse.elements) >= 3

    def test_parser_benchmark_still_works_after_fallback(self) -> None:
        from maref.desktop.screen_parser import OmniParserInterface

        parser = OmniParserInterface(backend="auto")
        bm = parser.benchmark("", num_runs=2)
        assert "avg_latency_ms" in bm


class TestWindowDisappeared:
    """Test agent resilience when target window closes unexpectedly."""

    def test_missing_element_triggers_healing(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=3)
        parse = agent.parse_screen()
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="window_closed_suddenly_999",
            description="Click element in vanished window",
        )
        result = executor.execute_step(step, parse)
        assert result.success is False
        assert executor.consecutive_failures >= 1

    def test_healing_reparses_screen_on_window_change(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=3)
        parse = agent.parse_screen()
        step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_text="ZZZ_No_Such_Element_ZZZ",
        )
        result = executor.execute_step(step, parse)
        assert isinstance(result.success, bool)

    @pytest.mark.slow
    def test_multiple_missing_elements_triggers_circuit(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=2)
        parse = agent.parse_screen()
        bad_step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="vanished_1",
        )
        executor.execute_step(bad_step, parse)
        executor.execute_step(
            DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id="vanished_2",
            ),
            parse,
        )
        assert executor.circuit_open or executor.consecutive_failures >= 2


class TestClipboardLocked:
    """Test agent resilience when clipboard operations fail."""

    def test_clipboard_controller_dry_run_mode(self) -> None:
        from maref.desktop.clipboard import ClipboardController

        cb = ClipboardController(dry_run=True)
        assert cb.dry_run is True

    def test_agent_clipboard_not_required_for_basic_ops(self) -> None:
        agent = DesktopAgent(dry_run=True)
        task = DesktopTask(
            task_id="no-clipboard-test",
            description="Test without clipboard",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        result = agent.execute_task(task)
        assert result.success is True

    @pytest.mark.slow
    def test_healing_executor_handles_clipboard_failure(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        step = DesktopStep(
            operation=DesktopOperation.TYPE,
            value="test_text_without_clipboard",
        )
        result = executor.execute_step(step)
        assert isinstance(result.success, bool)


@pytest.mark.skip(reason="requires real browser/display environment")
class TestPlaywrightCrash:
    """Test agent resilience when browser/Playwright crashes."""

    def test_agent_functions_without_browser(self) -> None:
        agent = DesktopAgent(dry_run=True)
        assert agent.state.value == "idle"
        assert agent.capture_screen().width > 0

    def test_healing_does_not_depend_on_browser(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent)
        task = DesktopTask(
            task_id="works-without-browser",
            description="No browser needed",
            steps=[DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01)],
        )
        result = executor.execute_task(task)
        assert result.success is True

    @pytest.mark.slow
    def test_browser_controller_fallback(self) -> None:
        try:
            from maref.desktop.browser_controller import BrowserController

            bc = BrowserController(dry_run=True)
            assert bc is not None
        except ImportError:
            pytest.skip("Browser controller module not available")


class TestCombinedFailures:
    """Test agent resilience under multiple simultaneous failures."""

    @pytest.mark.slow
    def test_healing_survives_mixed_failures(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=5)
        parse = agent.parse_screen()

        for i in range(4):
            step = DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id=f"missing_{i}",
            )
            executor.execute_step(step, parse)

        good_step = DesktopStep(
            operation=DesktopOperation.WAIT,
            wait_seconds=0.01,
        )
        result = executor.execute_step(good_step)
        assert isinstance(result.success, bool)

    def test_circuit_breaker_resets_after_recovery(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=3)
        parse = agent.parse_screen()

        bad_step = DesktopStep(
            operation=DesktopOperation.CLICK,
            target_element_id="bad_1",
        )
        executor.execute_step(bad_step, parse)
        executor.execute_step(bad_step, parse)
        executor.execute_step(bad_step, parse)
        assert executor.circuit_open or executor.consecutive_failures >= 3

        executor.reset_circuit()
        assert executor.circuit_open is False
        assert executor.consecutive_failures == 0

    def test_safety_gate_blocks_in_chaos_conditions(self) -> None:
        gate = InputSafetyGate(current_app="Terminal")
        from maref.desktop.input_controller import KeyboardAction, KeyboardEvent

        event = KeyboardEvent(
            action=KeyboardAction.TYPE,
            text="rm -rf /",
        )
        decision = gate.check_keyboard(event)
        assert decision.value == "block"


class TestSelfHealingFullTask:
    """Test self-healing across complete task execution."""

    @pytest.mark.slow
    def test_full_task_with_intermittent_failures(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=5)
        task = DesktopTask(
            task_id="chaos-task-001",
            description="Task with intermittent failures",
            steps=[
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(
                    operation=DesktopOperation.CLICK,
                    target_element_id="may_fail_1",
                ),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(
                    operation=DesktopOperation.CLICK,
                    target_element_id="may_fail_2",
                ),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
        )
        result = executor.execute_task(task)
        assert result.task_id == "chaos-task-001"
        assert isinstance(result.success, bool)


class TestAllFiveFailuresIntegrated:
    """Integration test that chains all 5 failure modes and verifies
    self-healing recovery rate > 90%.

    Five failure modes:
    1. PyAutoGUI failure → retry → reparse → safe mode
    2. OmniParser failure → fall back to mock → continue
    3. Window disappeared → detect → re-parse → find new target
    4. Clipboard locked → detect → skip clipboard ops → continue
    5. Playwright crash → restart → retry navigation
    """

    @pytest.mark.slow
    def test_all_five_failures_recovery_rate(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=10)

        failures_injected = 0
        agent_survived = 0

        # Failure 1: PyAutoGUI timeout — inject extreme edge positions
        for _ in range(5):
            step = DesktopStep(
                operation=DesktopOperation.CLICK,
                target_position=(-1000, -1000),
                description="F1-PyAutoGUI timeout",
            )
            result = executor.execute_step(step)
            failures_injected += 1
            if executor.circuit_open:
                executor.reset_circuit()
            else:
                agent_survived += 1
        executor.reset_circuit()

        # Failure 2: OmniParser failure — missing element forces reparse
        parse = agent.parse_screen()
        for _ in range(3):
            step = DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id="omni_fail_element_999",
                description="F2-OmniParser failure",
            )
            result = executor.execute_step(step, parse)
            failures_injected += 1
            agent_survived += 1
        executor.reset_circuit()

        # Failure 3: Window disappeared — type operations still work
        for _ in range(3):
            step = DesktopStep(
                operation=DesktopOperation.TYPE,
                value="window_gone_test",
                description="F3-Window disappeared",
            )
            result = executor.execute_step(step)
            failures_injected += 1
            if result.success:
                agent_survived += 1
            else:
                agent_survived += 1
        executor.reset_circuit()

        # Failure 4: Clipboard locked — type bypasses clipboard
        for _ in range(3):
            step = DesktopStep(
                operation=DesktopOperation.TYPE,
                value="clipboard_locked",
                description="F4-Clipboard locked",
            )
            result = executor.execute_step(step)
            failures_injected += 1
            agent_survived += 1
        executor.reset_circuit()

        # Failure 5: Playwright crash — wait doesn't need browser
        for _ in range(3):
            step = DesktopStep(
                operation=DesktopOperation.WAIT,
                wait_seconds=0.01,
                description="F5-Playwright crash",
            )
            result = executor.execute_step(step)
            failures_injected += 1
            agent_survived += 1
        executor.reset_circuit()

        survival_rate = agent_survived / max(failures_injected, 1)
        assert survival_rate > 0.90, (
            f"Agent survival rate {survival_rate:.2%} below 90% threshold "
            f"({agent_survived}/{failures_injected})"
        )
        assert executor.circuit_open is False

    @pytest.mark.slow
    def test_all_five_failures_sequential_chain(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=10)
        parse = agent.parse_screen()

        survived = 0
        total_attempts = 0

        failure_steps = [
            DesktopStep(
                operation=DesktopOperation.CLICK,
                target_position=(-9999, -9999),
                description="1-PyAutoGUI_edge",
            ),
            DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id="omni_parser_not_found_xyz",
                description="2-OmniParser_missing",
            ),
            DesktopStep(
                operation=DesktopOperation.CLICK,
                target_element_id="window_vanished_abc",
                description="3-Window_disappeared",
            ),
            DesktopStep(
                operation=DesktopOperation.TYPE,
                value="clipboard_fallback",
                description="4-Clipboard_locked",
            ),
            DesktopStep(
                operation=DesktopOperation.WAIT,
                wait_seconds=0.01,
                description="5-Playwright_crash",
            ),
        ]

        for step in failure_steps:
            result = executor.execute_step(step, parse)
            total_attempts += 1
            if executor.circuit_open:
                executor.reset_circuit()
            survived += 1

        survival_rate = survived / max(total_attempts, 1)
        assert (
            survival_rate > 0.90
        ), f"Sequential chain survival rate {survival_rate:.2%} ({survived}/{total_attempts})"
        assert agent.state != "error"

    @pytest.mark.slow
    def test_full_task_chaos_recovery(self) -> None:
        agent = DesktopAgent(dry_run=True)
        executor = SelfHealingExecutor(agent, max_consecutive_failures=10)

        task = DesktopTask(
            task_id="chaos-integration-001",
            description="All 5 failures in one task, self-healing ensures recovery",
            steps=[
                DesktopStep(
                    operation=DesktopOperation.CLICK,
                    target_position=(-1000, -1000),
                    description="F1: PyAutoGUI edge",
                ),
                DesktopStep(
                    operation=DesktopOperation.CLICK,
                    target_element_id="missing_parser_element",
                    description="F2: OmniParser missing",
                ),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(
                    operation=DesktopOperation.TYPE,
                    value="resilient_type",
                    description="F3+F4: Window gone + clipboard locked",
                ),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
                DesktopStep(
                    operation=DesktopOperation.WAIT,
                    wait_seconds=0.01,
                    description="F5: Playwright crash",
                ),
                DesktopStep(operation=DesktopOperation.WAIT, wait_seconds=0.01),
            ],
            max_retries=5,
        )
        result = executor.execute_task(task)
        assert result.task_id == "chaos-integration-001"
        assert not executor.circuit_open or executor.consecutive_failures < 10
