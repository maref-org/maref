"""
Tests for fault_recovery.py module.

Test requirements:
1. Test all dataclass construction and default values
2. Test all enum values and properties
3. Test all public functions/methods with edge cases
4. Mock any external dependencies or I/O operations
5. Test state machines, recovery logic, error handling
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.research.fault_recovery import FaultRecovery, RecoveryResult


class TestRecoveryResult:
    """Test RecoveryResult dataclass."""

    def test_construction_with_all_args(self):
        """Test constructing RecoveryResult with all arguments."""
        result = RecoveryResult(
            success=True,
            result="test_result",
            error="test_error",
            strategy_used="retry",
            attempts=3,
        )
        assert result.success is True
        assert result.result == "test_result"
        assert result.error == "test_error"
        assert result.strategy_used == "retry"
        assert result.attempts == 3

    def test_construction_with_defaults(self):
        """Test constructing RecoveryResult with default values."""
        result = RecoveryResult(success=False)
        assert result.success is False
        assert result.result is None
        assert result.error == ""
        assert result.strategy_used == ""
        assert result.attempts == 0

    def test_equality(self):
        """Test equality comparison between RecoveryResult instances."""
        result1 = RecoveryResult(success=True, result="data", attempts=2)
        result2 = RecoveryResult(success=True, result="data", attempts=2)
        result3 = RecoveryResult(success=False, attempts=2)
        
        assert result1 == result2
        assert result1 != result3

    def test_repr(self):
        """Test string representation of RecoveryResult."""
        result = RecoveryResult(success=True, result=42, error="", strategy_used="retry", attempts=1)
        repr_str = repr(result)
        assert "RecoveryResult" in repr_str
        assert "success=True" in repr_str
        assert "result=42" in repr_str
        assert "strategy_used='retry'" in repr_str


class TestFaultRecoveryInitialization:
    """Test FaultRecovery class initialization."""

    def test_default_initialization(self):
        """Test FaultRecovery with default parameters."""
        fr = FaultRecovery()
        assert fr._max_retries == 3
        assert fr._backoff_base == 1.0
        assert fr._alert_threshold == 5
        assert fr._consecutive_failures == 0
        assert fr._failure_log == []

    def test_custom_initialization(self):
        """Test FaultRecovery with custom parameters."""
        fr = FaultRecovery(max_retries=5, backoff_base=2.0, alert_threshold=10)
        assert fr._max_retries == 5
        assert fr._backoff_base == 2.0
        assert fr._alert_threshold == 10
        assert fr._consecutive_failures == 0
        assert fr._failure_log == []

    def test_invalid_initialization(self):
        """Test FaultRecovery with invalid parameters."""
        # Python doesn't enforce types in constructor, so these won't raise TypeError
        # They'll fail later when used. We'll test that they accept any type.
        fr1 = FaultRecovery(max_retries="invalid")  # type: ignore
        assert fr1._max_retries == "invalid"
        
        fr2 = FaultRecovery(backoff_base="invalid")  # type: ignore
        assert fr2._backoff_base == "invalid"
        
        fr3 = FaultRecovery(alert_threshold="invalid")  # type: ignore
        assert fr3._alert_threshold == "invalid"


class TestFaultRecoveryBackoff:
    """Test backoff mechanism."""

    @pytest.mark.asyncio
    async def test_backoff_calculation(self):
        """Test exponential backoff calculation."""
        fr = FaultRecovery(backoff_base=2.0)
        
        # Mock asyncio.sleep to not actually sleep
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await fr._backoff(0)
            mock_sleep.assert_awaited_once_with(2.0)  # 2.0 * 2^0 = 2.0
            
            mock_sleep.reset_mock()
            await fr._backoff(1)
            mock_sleep.assert_awaited_once_with(4.0)  # 2.0 * 2^1 = 4.0
            
            mock_sleep.reset_mock()
            await fr._backoff(2)
            mock_sleep.assert_awaited_once_with(8.0)  # 2.0 * 2^2 = 8.0

    @pytest.mark.asyncio
    async def test_backoff_with_default_base(self):
        """Test backoff with default base value."""
        fr = FaultRecovery()  # backoff_base=1.0
        
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await fr._backoff(0)
            mock_sleep.assert_awaited_once_with(1.0)  # 1.0 * 2^0 = 1.0
            
            mock_sleep.reset_mock()
            await fr._backoff(3)
            mock_sleep.assert_awaited_once_with(8.0)  # 1.0 * 2^3 = 8.0


class TestFaultRecoveryLogFailure:
    """Test failure logging mechanism."""

    def test_log_failure(self):
        """Test logging a failure."""
        fr = FaultRecovery()
        fr._consecutive_failures = 1  # Set before logging
        
        # Mock time.time to return a fixed timestamp
        with patch("time.time", return_value=1234567890.0):
            fr._log_failure("test_error", "test_experiment")
        
        assert len(fr._failure_log) == 1
        log_entry = fr._failure_log[0]
        assert log_entry["timestamp"] == 1234567890.0
        assert log_entry["experiment"] == "test_experiment"
        assert log_entry["error"] == "test_error"
        assert log_entry["consecutive_failures"] == 1

    def test_log_failure_multiple(self):
        """Test logging multiple failures."""
        fr = FaultRecovery()
        fr._consecutive_failures = 3
        
        with patch("time.time", return_value=1234567890.0):
            fr._log_failure("error1", "exp1")
            fr._log_failure("error2", "exp2")
        
        assert len(fr._failure_log) == 2
        assert fr._failure_log[0]["consecutive_failures"] == 3
        assert fr._failure_log[1]["consecutive_failures"] == 3  # consecutive_failures is set before logging


class TestFaultRecoveryAlertHuman:
    """Test human alert mechanism."""

    def test_alert_human_logging(self):
        """Test that alert_human logs at error level."""
        fr = FaultRecovery()
        fr._consecutive_failures = 5  # At threshold
        
        with patch("src.research.fault_recovery.logger") as mock_logger:
            fr._alert_human()
            
            # Check that error was logged with correct message
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "ALERT" in call_args
            assert "5 consecutive failures" in call_args
            assert "Human intervention may be required" in call_args

    def test_alert_human_below_threshold(self):
        """Test alert_human when below threshold (should still log)."""
        fr = FaultRecovery()
        fr._consecutive_failures = 3  # Below threshold
        
        with patch("src.research.fault_recovery.logger") as mock_logger:
            fr._alert_human()
            mock_logger.error.assert_called_once()


class TestFaultRecoveryRunWithRecovery:
    """Test the main run_with_recovery method."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test successful execution on first attempt."""
        fr = FaultRecovery(max_retries=3)
        
        # Create a mock that succeeds immediately
        mock_experiment = AsyncMock(return_value="success_result")
        mock_experiment.__name__ = "test_experiment"
        
        result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is True
        assert result.result == "success_result"
        assert result.strategy_used == "retry"
        assert result.attempts == 1
        assert result.error == ""
        assert fr._consecutive_failures == 0
        mock_experiment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_on_retry(self):
        """Test successful execution after retries."""
        fr = FaultRecovery(max_retries=3)
        
        # Create a mock that fails twice then succeeds
        mock_experiment = AsyncMock(
            side_effect=[Exception("error1"), Exception("error2"), "success_result"]
        )
        mock_experiment.__name__ = "test_experiment"
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock):
            result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is True
        assert result.result == "success_result"
        assert result.strategy_used == "retry"
        assert result.attempts == 3
        assert result.error == ""
        assert fr._consecutive_failures == 0
        assert mock_experiment.await_count == 3

    @pytest.mark.asyncio
    async def test_failure_then_degrade_success(self):
        """Test failure of main experiment but success with degraded version."""
        fr = FaultRecovery(max_retries=2)
        
        # Main experiment always fails
        mock_experiment = AsyncMock(side_effect=Exception("main_error"))
        mock_experiment.__name__ = "test_experiment"
        
        # Degraded experiment succeeds
        mock_degrade = AsyncMock(return_value="degraded_result")
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock):
            result = await fr.run_with_recovery(mock_experiment, mock_degrade)
        
        assert result.success is True
        assert result.result == "degraded_result"
        assert result.strategy_used == "degrade"
        assert result.attempts == 3  # max_retries + 1
        assert result.error == ""
        assert fr._consecutive_failures == 0
        assert mock_experiment.await_count == 2
        mock_degrade.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_failure_without_degrade(self):
        """Test complete failure when no degrade function provided."""
        fr = FaultRecovery(max_retries=2)
        
        mock_experiment = AsyncMock(side_effect=Exception("fatal_error"))
        mock_experiment.__name__ = "test_experiment"
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock), \
             patch.object(fr, "_log_failure") as mock_log_failure, \
             patch.object(fr, "_alert_human") as mock_alert:
            
            result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is False
        assert result.result is None
        assert result.strategy_used == "skip"
        assert result.attempts == 2
        assert result.error == "fatal_error"
        assert fr._consecutive_failures == 1
        assert mock_experiment.await_count == 2
        mock_log_failure.assert_called_once_with("fatal_error", "test_experiment")
        mock_alert.assert_not_called()  # Only 1 failure, below threshold

    @pytest.mark.asyncio
    async def test_complete_failure_with_degrade_failure(self):
        """Test complete failure when degrade function also fails."""
        fr = FaultRecovery(max_retries=1)
        
        mock_experiment = AsyncMock(side_effect=Exception("main_error"))
        mock_experiment.__name__ = "test_experiment"
        
        mock_degrade = AsyncMock(side_effect=Exception("degrade_error"))
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock), \
             patch.object(fr, "_log_failure") as mock_log_failure:
            
            result = await fr.run_with_recovery(mock_experiment, mock_degrade)
        
        assert result.success is False
        assert result.result is None
        assert result.strategy_used == "skip"
        assert result.attempts == 2  # max_retries + 1 (for degrade attempt)
        assert result.error == "main_error"  # Should be last_error from main experiment
        assert fr._consecutive_failures == 1
        mock_log_failure.assert_called_once_with("main_error", "test_experiment")

    @pytest.mark.asyncio
    async def test_alert_threshold_reached(self):
        """Test that alert is triggered when threshold reached."""
        fr = FaultRecovery(max_retries=1, alert_threshold=2)
        fr._consecutive_failures = 1  # Already has 1 failure
        
        mock_experiment = AsyncMock(side_effect=Exception("error"))
        mock_experiment.__name__ = "test_experiment"
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock), \
             patch.object(fr, "_log_failure") as mock_log_failure, \
             patch.object(fr, "_alert_human") as mock_alert:
            
            result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is False
        assert fr._consecutive_failures == 2  # Now at threshold
        mock_alert.assert_called_once()  # Should trigger alert

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_on_success(self):
        """Test that consecutive_failures resets on successful retry."""
        fr = FaultRecovery(max_retries=3)
        fr._consecutive_failures = 5  # Simulate previous failures
        
        mock_experiment = AsyncMock(return_value="success")
        mock_experiment.__name__ = "test_experiment"
        
        result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is True
        assert fr._consecutive_failures == 0  # Should be reset

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_on_degrade_success(self):
        """Test that consecutive_failures resets on successful degrade."""
        fr = FaultRecovery(max_retries=2)
        fr._consecutive_failures = 3  # Simulate previous failures
        
        mock_experiment = AsyncMock(side_effect=Exception("error"))
        mock_experiment.__name__ = "test_experiment"
        
        mock_degrade = AsyncMock(return_value="degraded_success")
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock):
            result = await fr.run_with_recovery(mock_experiment, mock_degrade)
        
        assert result.success is True
        assert fr._consecutive_failures == 0  # Should be reset

    @pytest.mark.asyncio
    async def test_experiment_without_name_attribute(self):
        """Test with experiment function that doesn't have __name__ attribute."""
        fr = FaultRecovery(max_retries=1)
        
        # Create a lambda/coroutine without __name__
        async def experiment():
            raise Exception("error")
        
        # Remove __name__ attribute
        experiment.__name__ = ""
        
        with patch.object(fr, "_backoff", new_callable=AsyncMock), \
             patch.object(fr, "_log_failure") as mock_log_failure:
            
            result = await fr.run_with_recovery(experiment)
        
        # Should still work, __name__ will be empty string
        mock_log_failure.assert_called_once()
        call_args = mock_log_failure.call_args[0]
        assert call_args[1] == ""  # experiment_name should be empty string


class TestFaultRecoveryGetStats:
    """Test get_stats method."""

    def test_get_stats_no_failures(self):
        """Test get_stats with no failures."""
        fr = FaultRecovery()
        
        stats = fr.get_stats()
        
        assert stats["consecutive_failures"] == 0
        assert stats["total_failures"] == 0
        assert stats["alert_threshold"] == 5
        assert stats["needs_attention"] is False
        assert stats["recent_failures"] == []

    def test_get_stats_with_failures(self):
        """Test get_stats with failures logged."""
        fr = FaultRecovery(alert_threshold=3)
        fr._consecutive_failures = 2
        
        # Add some failures
        with patch("time.time", return_value=1000.0):
            fr._log_failure("error1", "exp1")
        with patch("time.time", return_value=2000.0):
            fr._log_failure("error2", "exp2")
        with patch("time.time", return_value=3000.0):
            fr._log_failure("error3", "exp3")
        with patch("time.time", return_value=4000.0):
            fr._log_failure("error4", "exp4")
        with patch("time.time", return_value=5000.0):
            fr._log_failure("error5", "exp5")
        with patch("time.time", return_value=6000.0):
            fr._log_failure("error6", "exp6")
        
        stats = fr.get_stats()
        
        assert stats["consecutive_failures"] == 2
        assert stats["total_failures"] == 6
        assert stats["alert_threshold"] == 3
        assert stats["needs_attention"] is False  # 2 < 3
        
        # Should return last 5 failures
        recent = stats["recent_failures"]
        assert len(recent) == 5
        assert recent[0]["timestamp"] == 2000.0  # exp2 (skipped exp1)
        assert recent[4]["timestamp"] == 6000.0  # exp6

    def test_get_stats_needs_attention(self):
        """Test get_stats when attention is needed."""
        fr = FaultRecovery(alert_threshold=2)
        fr._consecutive_failures = 3  # Above threshold
        
        stats = fr.get_stats()
        
        assert stats["needs_attention"] is True

    def test_get_stats_with_empty_failure_log(self):
        """Test get_stats with empty failure log (edge case)."""
        fr = FaultRecovery()
        fr._failure_log = []  # Explicitly empty
        
        stats = fr.get_stats()
        
        assert stats["recent_failures"] == []


class TestFaultRecoveryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_zero_max_retries(self):
        """Test with max_retries=0 (should skip retry and go directly to degrade/skip)."""
        fr = FaultRecovery(max_retries=0)
        
        mock_experiment = AsyncMock(side_effect=Exception("error"))
        mock_experiment.__name__ = "test_experiment"
        
        mock_degrade = AsyncMock(return_value="degraded")
        
        with patch.object(fr, "_log_failure") as mock_log_failure:
            result = await fr.run_with_recovery(mock_experiment, mock_degrade)
        
        assert result.success is True  # Should succeed via degrade
        assert result.strategy_used == "degrade"
        assert result.attempts == 1  # max_retries + 1 = 0 + 1 = 1
        mock_experiment.assert_not_awaited()  # Should not be called with 0 retries
        mock_degrade.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_experiment_returns_none(self):
        """Test experiment that returns None."""
        fr = FaultRecovery()
        
        mock_experiment = AsyncMock(return_value=None)
        mock_experiment.__name__ = "test_experiment"
        
        result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is True
        assert result.result is None
        assert result.strategy_used == "retry"

    @pytest.mark.asyncio
    async def test_experiment_raises_base_exception(self):
        """Test experiment that raises BaseException (not Exception)."""
        fr = FaultRecovery(max_retries=1)
        
        mock_experiment = AsyncMock(side_effect=KeyboardInterrupt("user interrupt"))
        mock_experiment.__name__ = "test_experiment"
        
        # KeyboardInterrupt is a BaseException, not Exception
        # Should still be caught by generic Exception handler
        with patch.object(fr, "_backoff", new_callable=AsyncMock), \
             patch.object(fr, "_log_failure") as mock_log_failure:
            
            result = await fr.run_with_recovery(mock_experiment)
        
        assert result.success is False
        assert "user interrupt" in result.error
        mock_log_failure.assert_called_once()

    def test_backoff_with_negative_attempt(self):
        """Test backoff with negative attempt number."""
        fr = FaultRecovery(backoff_base=2.0)
        
        # _backoff is private, but we can test edge cases
        # Negative attempt should still work mathematically
        # 2.0 * 2^(-1) = 2.0 * 0.5 = 1.0
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Need to run async
            asyncio.run(fr._backoff(-1))
            mock_sleep.assert_awaited_once_with(1.0)

    def test_get_stats_after_many_failures(self):
        """Test get_stats with very large number of failures."""
        fr = FaultRecovery()
        
        # Simulate many failures
        for i in range(100):
            fr._failure_log.append({
                "timestamp": i * 1000.0,
                "experiment": f"exp_{i}",
                "error": f"error_{i}",
                "consecutive_failures": i + 1,
            })
        
        stats = fr.get_stats()
        
        assert stats["total_failures"] == 100
        assert len(stats["recent_failures"]) == 5  # Should only return last 5
        assert stats["recent_failures"][0]["timestamp"] == 95000.0  # exp_95
        assert stats["recent_failures"][4]["timestamp"] == 99000.0  # exp_99