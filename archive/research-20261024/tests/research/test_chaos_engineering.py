"""
Tests for chaos_engineering.py module.

Test requirements:
1. Test all dataclass construction and default values
2. Test all enum values and properties
3. Test all public functions/methods with edge cases
4. Mock any external dependencies or I/O operations
5. Test chaos injection logic, fault simulation, recovery testing
6. Test configuration validation and edge cases
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.research.chaos_engineering import ChaosInjector, ChaosResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeLLM:
    """Fake LLM client for latency injection tests."""

    def __init__(self):
        self.chat_completion = AsyncMock(return_value={"content": "ok"})
        self.close = AsyncMock()


# ---------------------------------------------------------------------------
# TestChaosResult
# ---------------------------------------------------------------------------


class TestChaosResult:
    """Test ChaosResult dataclass construction and defaults."""

    def test_construction_with_all_args(self):
        result = ChaosResult(
            scenario="latency_injection",
            duration_sec=1.23,
            success=True,
            system_stable=True,
            metrics_before={"a": 1.0},
            metrics_after={"a": 2.0},
            findings=["finding1", "finding2"],
        )
        assert result.scenario == "latency_injection"
        assert result.duration_sec == 1.23
        assert result.success is True
        assert result.system_stable is True
        assert result.metrics_before == {"a": 1.0}
        assert result.metrics_after == {"a": 2.0}
        assert result.findings == ["finding1", "finding2"]

    def test_construction_with_defaults(self):
        result = ChaosResult(
            scenario="error_response",
            duration_sec=0.5,
            success=False,
            system_stable=False,
            metrics_before={},
            metrics_after={},
        )
        assert result.findings == []

    def test_mutable_findings_default(self):
        """Each instance should get its own findings list."""
        r1 = ChaosResult(
            scenario="s1", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        r2 = ChaosResult(
            scenario="s2", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        r1.findings.append("x")
        assert r2.findings == []

    def test_equality(self):
        a = ChaosResult(
            scenario="s", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        b = ChaosResult(
            scenario="s", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        c = ChaosResult(
            scenario="t", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        assert a == b
        assert a != c


# ---------------------------------------------------------------------------
# TestChaosInjectorInitialization
# ---------------------------------------------------------------------------


class TestChaosInjectorInitialization:
    """Test ChaosInjector class initialization."""

    def test_default_initialization(self):
        injector = ChaosInjector()
        assert injector._llm is None
        assert injector._results == []

    def test_initialization_with_llm(self):
        fake = FakeLLM()
        injector = ChaosInjector(llm_client=fake)  # type: ignore[arg-type]
        assert injector._llm is fake


# ---------------------------------------------------------------------------
# TestPrivateHelpers
# ---------------------------------------------------------------------------


class TestPrivateHelpers:
    """Test _with_latency and _with_error helpers."""

    @pytest.mark.asyncio
    async def test_with_latency_default_params(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="result")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("random.uniform", return_value=500.0):
            result = await injector._with_latency(mock_fn)

        assert result == "result"
        # actual_delay = max(0, 5000 + 500) = 5500ms => 5.5s
        mock_sleep.assert_awaited_once_with(5.5)
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_latency_zero_jitter(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value=42)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("random.uniform", return_value=0.0):
            result = await injector._with_latency(mock_fn, delay_ms=1000.0, jitter_ms=0.0)

        assert result == 42
        mock_sleep.assert_awaited_once_with(1.0)

    @pytest.mark.asyncio
    async def test_with_latency_negative_delay_clamped(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="ok")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("random.uniform", return_value=-2000.0):
            result = await injector._with_latency(mock_fn, delay_ms=1000.0, jitter_ms=2000.0)

        # max(0, 1000 - 2000) = 0 => 0s
        mock_sleep.assert_awaited_once_with(0.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_with_latency_custom_delay_and_jitter(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="ok")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("random.uniform", return_value=-1000.0):
            result = await injector._with_latency(mock_fn, delay_ms=3000.0, jitter_ms=1000.0)

        # max(0, 3000 - 1000) = 2000ms => 2.0s
        mock_sleep.assert_awaited_once_with(2.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_with_error_injects_error(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="result")

        with patch("random.random", return_value=0.1):  # 0.1 < 0.3 => error
            with pytest.raises(RuntimeError, match="Injected chaos error"):
                await injector._with_error(mock_fn, error_rate=0.3)

        mock_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_error_no_error(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="result")

        with patch("random.random", return_value=0.5):  # 0.5 >= 0.3 => no error
            result = await injector._with_error(mock_fn, error_rate=0.3)

        assert result == "result"
        mock_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_error_zero_rate(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="result")

        with patch("random.random", return_value=0.0):
            result = await injector._with_error(mock_fn, error_rate=0.0)

        assert result == "result"

    @pytest.mark.asyncio
    async def test_with_error_full_rate(self):
        injector = ChaosInjector()
        mock_fn = AsyncMock(return_value="result")

        with patch("random.random", return_value=0.0):
            with pytest.raises(RuntimeError, match="Injected chaos error"):
                await injector._with_error(mock_fn, error_rate=1.0)


# ---------------------------------------------------------------------------
# TestScenarioLatencyInjection
# ---------------------------------------------------------------------------


class TestScenarioLatencyInjection:
    """Test scenario_latency_injection."""

    @pytest.mark.asyncio
    async def test_without_llm(self):
        injector = ChaosInjector()

        with patch("time.time", side_effect=[100.0, 105.0]):
            result = await injector.scenario_latency_injection()

        assert isinstance(result, ChaosResult)
        assert result.scenario == "latency_injection"
        assert result.duration_sec == 5.0
        assert result.success is True
        assert result.system_stable is False  # no findings when llm is None
        assert result.metrics_before == {"response_time_ms": 200.0, "timeout_count": 0.0}
        assert result.metrics_after == {"response_time_ms": 5000.0, "timeout_count": 1.0}
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_with_llm_success(self):
        fake_llm = FakeLLM()
        injector = ChaosInjector(llm_client=fake_llm)  # type: ignore[arg-type]

        with patch("time.time", side_effect=[100.0, 108.5]):
            result = await injector.scenario_latency_injection()

        assert result.scenario == "latency_injection"
        assert result.duration_sec == 8.5
        assert result.success is True
        assert result.system_stable is True
        assert len(result.findings) == 1
        assert "System handled 8s latency gracefully" in result.findings[0]
        fake_llm.chat_completion.assert_awaited_once_with(
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10,
        )

    @pytest.mark.asyncio
    async def test_with_llm_timeout_error(self):
        fake_llm = FakeLLM()
        fake_llm.chat_completion = AsyncMock(side_effect=asyncio.TimeoutError("timed out"))
        injector = ChaosInjector(llm_client=fake_llm)  # type: ignore[arg-type]

        with patch("time.time", side_effect=[100.0, 108.0]):
            result = await injector.scenario_latency_injection()

        assert result.success is True
        assert result.system_stable is True
        assert len(result.findings) == 1
        assert "Timeout detected - circuit breaker should activate" in result.findings[0]

    @pytest.mark.asyncio
    async def test_with_llm_generic_exception(self):
        fake_llm = FakeLLM()
        fake_llm.chat_completion = AsyncMock(side_effect=RuntimeError("boom"))
        injector = ChaosInjector(llm_client=fake_llm)  # type: ignore[arg-type]

        with patch("time.time", side_effect=[100.0, 108.0]):
            result = await injector.scenario_latency_injection()

        assert result.success is True
        assert result.system_stable is True
        assert len(result.findings) == 1
        assert "Error under latency: boom" in result.findings[0]


# ---------------------------------------------------------------------------
# TestScenarioErrorResponse
# ---------------------------------------------------------------------------


class TestScenarioErrorResponse:
    """Test scenario_error_response."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        injector = ChaosInjector()

        with patch("random.random", return_value=0.5), \
             patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_error_response()

        assert result.scenario == "error_response"
        assert result.success is True
        assert result.system_stable is True  # error_count=0 <= max_retries=3
        assert result.findings == ["Success after 0 retries"]
        assert result.metrics_before == {"error_rate": 0.0, "retry_count": 0.0}
        assert result.metrics_after == {"error_rate": 0.0, "retry_count": 0.0}

    @pytest.mark.asyncio
    async def test_retries_then_success(self):
        injector = ChaosInjector()

        # First two calls error, third succeeds
        with patch("random.random", side_effect=[0.1, 0.1, 0.5]), \
             patch("time.time", side_effect=[100.0, 100.1, 100.2, 100.3]), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await injector.scenario_error_response()

        assert result.success is True
        assert result.system_stable is True  # error_count=2 <= max_retries=3
        assert result.findings == ["Success after 2 retries"]
        assert result.metrics_after["error_rate"] == 2 / 4
        assert result.metrics_after["retry_count"] == 2.0

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        injector = ChaosInjector()

        # All 4 attempts (max_retries+1) fail
        with patch("random.random", side_effect=[0.1, 0.1, 0.1, 0.1]), \
             patch("time.time", side_effect=[100.0, 100.1, 100.2, 100.3, 100.4]), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await injector.scenario_error_response()

        assert result.success is True
        assert result.system_stable is False  # error_count=4 > max_retries=3
        assert "Max retries exceeded - fallback activated" in result.findings
        assert result.metrics_after["error_rate"] == 4 / 4
        assert result.metrics_after["retry_count"] == 4.0


# ---------------------------------------------------------------------------
# TestScenarioPacketLoss
# ---------------------------------------------------------------------------


class TestScenarioPacketLoss:
    """Test scenario_packet_loss."""

    @pytest.mark.asyncio
    async def test_zero_drop_rate(self):
        injector = ChaosInjector()

        with patch("random.random", return_value=0.5), \
             patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_packet_loss()

        assert result.scenario == "packet_loss"
        assert result.success is True
        assert result.system_stable is True  # drop_rate=0 < 0.5
        assert result.findings[0] == "Packet loss simulation: 0/10 dropped (0%)"
        assert result.metrics_after == {"drop_rate": 0.0, "success_rate": 1.0}

    @pytest.mark.asyncio
    async def test_high_drop_rate(self):
        injector = ChaosInjector()

        # 4 out of 10 dropped (40%) => triggers high packet loss finding
        with patch("random.random", side_effect=[0.1, 0.5, 0.1, 0.5, 0.1, 0.1, 0.5, 0.5, 0.5, 0.5]), \
             patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_packet_loss()

        assert result.success is True
        assert result.system_stable is True  # 0.4 < 0.5
        assert "Packet loss simulation: 4/10 dropped (40%)" in result.findings[0]
        assert "High packet loss detected - system should queue or buffer" in result.findings[1]
        assert result.metrics_after["drop_rate"] == 0.4
        assert result.metrics_after["success_rate"] == 0.6

    @pytest.mark.asyncio
    async def test_all_dropped(self):
        injector = ChaosInjector()

        with patch("random.random", return_value=0.0), \
             patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_packet_loss()

        assert result.system_stable is False  # drop_rate=1.0 >= 0.5
        assert result.metrics_after == {"drop_rate": 1.0, "success_rate": 0.0}

    @pytest.mark.asyncio
    async def test_half_dropped(self):
        injector = ChaosInjector()

        # Exactly 5/10 dropped => drop_rate=0.5 => system_stable=False
        with patch("random.random", side_effect=[0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5]), \
             patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_packet_loss()

        assert result.metrics_after["drop_rate"] == 0.5
        assert result.system_stable is False


# ---------------------------------------------------------------------------
# TestScenarioEntropyStorm
# ---------------------------------------------------------------------------


class TestScenarioEntropyStorm:
    """Test scenario_entropy_storm."""

    @pytest.mark.asyncio
    async def test_basic_run(self):
        injector = ChaosInjector()

        with patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_entropy_storm()

        assert result.scenario == "entropy_storm"
        assert result.success is True
        assert result.system_stable is False  # simulated_entropy=10.0 is not < 10.0 => False
        assert result.findings[0] == "Processed 100 messages in burst mode"
        assert result.metrics_before == {"message_rate": 1.0, "entropy_level": 2.0}
        assert result.metrics_after["message_rate"] == 100 / 0.5
        assert result.metrics_after["entropy_level"] == 10.0

    @pytest.mark.asyncio
    async def test_entropy_threshold_exceeded(self):
        """Entropy threshold is 5.0; simulated_entropy = burst_messages / 10 = 10.0."""
        injector = ChaosInjector()

        with patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_entropy_storm()

        # simulated_entropy = 100 / 10 = 10.0 > 5.0
        assert "Entropy threshold exceeded - governance should intervene" in result.findings

    @pytest.mark.asyncio
    async def test_stability_boundary(self):
        """system_stable is True only when simulated_entropy < 10.0."""
        injector = ChaosInjector()

        # Hard to reach < 10 with 100 messages, so system_stable should be False
        with patch("time.time", side_effect=[100.0, 100.1]):
            result = await injector.scenario_entropy_storm()

        assert result.metrics_after["entropy_level"] == 10.0
        assert result.system_stable is False


# ---------------------------------------------------------------------------
# TestScenarioStateOscillation
# ---------------------------------------------------------------------------


class FakeStateMachine:
    """Fake GovernanceStateMachine for testing."""

    def __init__(self):
        self._state = "INIT"
        self.transitions: list[tuple[str, str]] = []

    def transition(self, state, reason=""):
        self.transitions.append((state.name, reason))
        # Simulate some transitions failing
        if self._state == state.name:
            raise ValueError("Already in state")
        self._state = state.name


class TestScenarioStateOscillation:
    """Test scenario_state_oscillation."""

    @pytest.fixture(autouse=True)
    def patch_state_machine(self):
        """Patch GovernanceStateMachine and GovernanceState imports."""
        self.fake_states = []

        class FakeGovernanceState:
            OBSERVE = MagicMock(name="OBSERVE")
            OBSERVE.name = "OBSERVE"
            ANALYZE = MagicMock(name="ANALYZE")
            ANALYZE.name = "ANALYZE"
            EVALUATE = MagicMock(name="EVALUATE")
            EVALUATE.name = "EVALUATE"

        class FakeGovernanceStateMachine:
            def __init__(self):
                self._state = None
                self.transitions = []

            def transition(self, state, reason=""):
                self.transitions.append((state.name, reason))
                # Simulate ValueError for some transitions
                if state.name == "ANALYZE" and len(self.transitions) == 2:
                    raise ValueError("Invalid transition")
                self._state = state.name

        with patch("maref_lite.state_machine.GovernanceStateMachine", FakeGovernanceStateMachine), \
             patch("maref_lite.state_machine.GovernanceState", FakeGovernanceState):
            yield

    @pytest.mark.asyncio
    async def test_basic_run(self):
        injector = ChaosInjector()

        # deterministic state choices: cycle OBSERVE, ANALYZE, EVALUATE
        with patch("random.choice", side_effect=lambda seq: seq[0]), \
             patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_state_oscillation()

        assert result.scenario == "state_oscillation"
        assert result.success is True
        assert result.findings[0] == "State transitions: 20"
        # All same state => no oscillation
        assert "Oscillation detected: 0 times" in result.findings[1]

    @pytest.mark.asyncio
    async def test_oscillation_detection(self):
        injector = ChaosInjector()

        # Create a deterministic oscillation pattern: O, A, O, A, O, A, ...
        choices = []
        states = [MagicMock(), MagicMock(), MagicMock()]
        states[0].name = "OBSERVE"
        states[1].name = "ANALYZE"
        states[2].name = "EVALUATE"

        for i in range(20):
            if i % 2 == 0:
                choices.append(states[0])
            else:
                choices.append(states[1])

        with patch("random.choice", side_effect=choices), \
             patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_state_oscillation()

        # transitions = [O, O, A, O, A, O, A, ...] (first A fails)
        # i=3: O==O(at1) and O!=A(at2) => +1, then every index matches => 16 total
        assert "Oscillation detected: 16 times" in result.findings[1]
        assert "CRITICAL: High oscillation rate - governance should stabilize" in result.findings[2]
        assert result.system_stable is False  # 16 >= 10

    @pytest.mark.asyncio
    async def test_invalid_transitions_ignored(self):
        injector = ChaosInjector()

        # All choices lead to ValueError except first
        class BadState:
            name = "BAD"

        bad_state = BadState()

        # First call succeeds, rest fail
        call_count = 0

        def chooser(seq):
            nonlocal call_count
            call_count += 1
            return bad_state

        with patch("random.choice", side_effect=chooser), \
             patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_state_oscillation()

        # First transition may succeed or fail depending on implementation,
        # but len(transitions) should be <= 20
        assert result.scenario == "state_oscillation"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_low_oscillation_stable(self):
        injector = ChaosInjector()

        states = [MagicMock(), MagicMock(), MagicMock()]
        states[0].name = "OBSERVE"
        states[1].name = "ANALYZE"
        states[2].name = "EVALUATE"

        # Minimal oscillation: mostly same state
        choices = [states[0]] * 18 + [states[1], states[0]]

        with patch("random.choice", side_effect=choices), \
             patch("time.time", side_effect=[100.0, 100.5]):
            result = await injector.scenario_state_oscillation()

        assert result.system_stable is True  # oscillation_count should be < 10


# ---------------------------------------------------------------------------
# TestRunAllScenarios
# ---------------------------------------------------------------------------


class TestRunAllScenarios:
    """Test run_all_scenarios orchestration."""

    @pytest.mark.asyncio
    async def test_runs_all_five(self):
        injector = ChaosInjector()
        results = await injector.run_all_scenarios()

        assert len(results) == 5
        scenarios = [r.scenario for r in results]
        assert scenarios == [
            "latency_injection",
            "error_response",
            "packet_loss",
            "entropy_storm",
            "state_oscillation",
        ]

    @pytest.mark.asyncio
    async def test_results_stored_internally(self):
        injector = ChaosInjector()
        await injector.run_all_scenarios()
        assert len(injector._results) == 5

    @pytest.mark.asyncio
    async def test_logging(self):
        injector = ChaosInjector()

        with patch("src.research.chaos_engineering.logger") as mock_logger:
            await injector.run_all_scenarios()

        mock_logger.info.assert_any_call("Starting chaos engineering test suite")
        mock_logger.debug.assert_any_call("Total scenarios: %s", 5)


# ---------------------------------------------------------------------------
# TestGenerateReport
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Test generate_report."""

    def test_empty_results(self):
        injector = ChaosInjector()
        report = injector.generate_report()

        assert report["total_scenarios"] == 0
        assert report["stable_scenarios"] == 0
        assert report["stability_rate"] == 0
        assert report["scenarios"] == []

    def test_with_results(self):
        injector = ChaosInjector()
        injector._results = [
            ChaosResult(
                scenario="s1", duration_sec=1.0, success=True,
                system_stable=True, metrics_before={}, metrics_after={},
                findings=["f1"],
            ),
            ChaosResult(
                scenario="s2", duration_sec=2.0, success=True,
                system_stable=False, metrics_before={}, metrics_after={},
                findings=["f2", "f3"],
            ),
            ChaosResult(
                scenario="s3", duration_sec=3.0, success=True,
                system_stable=True, metrics_before={}, metrics_after={},
                findings=[],
            ),
        ]

        report = injector.generate_report()

        assert report["total_scenarios"] == 3
        assert report["stable_scenarios"] == 2
        assert report["stability_rate"] == 2 / 3
        assert len(report["scenarios"]) == 3

        s1 = report["scenarios"][0]
        assert s1["name"] == "s1"
        assert s1["duration_sec"] == 1.0
        assert s1["stable"] is True
        assert s1["findings"] == ["f1"]

    def test_all_stable(self):
        injector = ChaosInjector()
        injector._results = [
            ChaosResult(
                scenario="s", duration_sec=1.0, success=True,
                system_stable=True, metrics_before={}, metrics_after={},
            ),
        ]

        report = injector.generate_report()
        assert report["stability_rate"] == 1.0

    def test_all_unstable(self):
        injector = ChaosInjector()
        injector._results = [
            ChaosResult(
                scenario="s", duration_sec=1.0, success=True,
                system_stable=False, metrics_before={}, metrics_after={},
            ),
        ]

        report = injector.generate_report()
        assert report["stability_rate"] == 0.0


# ---------------------------------------------------------------------------
# TestMainCLI
# ---------------------------------------------------------------------------


class TestMainCLI:
    """Test main() CLI entry point."""

    @pytest.mark.asyncio
    async def test_main_without_llm(self, tmp_path):
        output_path = tmp_path / "chaos_report.json"

        with patch("sys.argv", ["chaos_engineering", "--output", str(output_path)]):
            await self._run_main_and_assert(output_path)

    @pytest.mark.asyncio
    async def test_main_with_llm_but_no_key(self, tmp_path):
        output_path = tmp_path / "chaos_report.json"

        with patch("sys.argv", ["chaos_engineering", "--with-llm", "--output", str(output_path)]), \
             patch("src.research.chaos_engineering.DashScopeClient", side_effect=ValueError("no key")):
            await self._run_main_and_assert(output_path)

    @pytest.mark.asyncio
    async def test_main_with_llm_success(self, tmp_path):
        output_path = tmp_path / "chaos_report.json"
        fake_llm = FakeLLM()

        with patch("sys.argv", ["chaos_engineering", "--with-llm", "--output", str(output_path)]), \
             patch("src.research.chaos_engineering.DashScopeClient", return_value=fake_llm):
            await self._run_main_and_assert(output_path)

        fake_llm.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_main_creates_parent_dirs(self, tmp_path):
        output_path = tmp_path / "nested" / "dir" / "report.json"

        with patch("sys.argv", ["chaos_engineering", "--output", str(output_path)]):
            await self._run_main_and_assert(output_path)

        assert output_path.parent.exists()

    async def _run_main_and_assert(self, output_path: Path):
        from src.research.chaos_engineering import main

        with patch("src.research.chaos_engineering.logger"):
            await main()

        assert output_path.exists()
        import json
        with open(output_path) as f:
            report = json.load(f)
        assert "total_scenarios" in report
        assert "stable_scenarios" in report
        assert "stability_rate" in report
        assert "scenarios" in report


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.asyncio
    async def test_run_all_scenarios_idempotent(self):
        """Running twice should append results."""
        injector = ChaosInjector()
        await injector.run_all_scenarios()
        await injector.run_all_scenarios()
        assert len(injector._results) == 10

    @pytest.mark.asyncio
    async def test_with_latency_awaitable_check(self):
        """_with_latency should await the coroutine returned by fn."""
        injector = ChaosInjector()
        called = False

        async def my_fn():
            nonlocal called
            called = True
            return "value"

        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.uniform", return_value=0.0):
            result = await injector._with_latency(my_fn)

        assert called is True
        assert result == "value"

    @pytest.mark.asyncio
    async def test_error_response_backoff_timing(self):
        """Verify exponential backoff sleep durations in error_response."""
        injector = ChaosInjector()

        with patch("random.random", side_effect=[0.1, 0.1, 0.1, 0.1]), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("time.time", side_effect=[100.0, 100.1, 100.2, 100.3, 100.4]):
            await injector.scenario_error_response()

        # Backoff sleeps on attempts 0,1,2 (attempt < max_retries=3)
        assert mock_sleep.await_count == 3
        calls = [call.args[0] for call in mock_sleep.await_args_list]
        assert calls[0] == pytest.approx(0.1)
        assert calls[1] == pytest.approx(0.2)
        assert calls[2] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_packet_loss_simulated_sleeps(self):
        """Verify successful requests sleep."""
        injector = ChaosInjector()

        with patch("random.random", return_value=0.5), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("time.time", side_effect=[100.0, 100.1]):
            await injector.scenario_packet_loss()

        # 10 successful requests, each sleeps 0.01
        assert mock_sleep.await_count == 10
        for call in mock_sleep.await_args_list:
            assert call.args[0] == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_entropy_storm_sleeps(self):
        """Verify burst processing sleeps."""
        injector = ChaosInjector()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("time.time", side_effect=[100.0, 100.1]):
            await injector.scenario_entropy_storm()

        # 100 messages, each sleeps 0.001
        assert mock_sleep.await_count == 100
        for call in mock_sleep.await_args_list:
            assert call.args[0] == pytest.approx(0.001)

    def test_chaos_result_str_conversion(self):
        """Ensure ChaosResult can be converted to string/repr."""
        result = ChaosResult(
            scenario="test", duration_sec=1.0, success=True,
            system_stable=True, metrics_before={}, metrics_after={},
        )
        repr_str = repr(result)
        assert "ChaosResult" in repr_str
