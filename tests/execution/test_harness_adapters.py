"""Harness Phase 0 适配器单元测试。

测试 StressHarnessAdapter / DistributedHarnessAdapter / EmergenceHarnessAdapter
的配置、执行、错误处理逻辑。内部 StressHarness 等使用 mock 隔离。
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maref.execution.harness.adapters.stress_adapter import (
    StressHarnessAdapter,
    _parse_level,
)
from maref.execution.harness.adapters.distributed_adapter import (
    DistributedHarnessAdapter,
)
from maref.execution.harness.adapters.emergence_adapter import (
    EmergenceHarnessAdapter,
)
from maref.execution.harness.types import HarnessConfig, HarnessStatus


# =============================================================================
# _parse_level
# =============================================================================

class TestParseLevel:
    def test_numeric_l1(self):
        assert _parse_level("L1") is not None

    def test_numeric_l5(self):
        assert _parse_level("L5") is not None

    def test_name_low(self):
        assert _parse_level("low") is not None

    def test_name_moderate(self):
        assert _parse_level("moderate") is not None

    def test_name_extreme(self):
        assert _parse_level("extreme") is not None

    def test_invalid_falls_back_to_l1(self):
        """无效级别降级到 L1，不崩溃。"""
        assert _parse_level("bogus") is not None


# =============================================================================
# StressHarnessAdapter
# =============================================================================

class TestStressHarnessAdapter:
    def test_configure_sets_level(self):
        adapter = StressHarnessAdapter()
        cfg = HarnessConfig(level="L3")
        adapter.configure(cfg)
        assert adapter._config is not None
        assert adapter._config.level == "L3"

    @patch("maref.execution.harness.adapters.stress_adapter.StressHarness")
    def test_run_returns_harness_result(self, MockStress):
        mock = MagicMock()
        mock.run.return_value = _mock_stress_result()
        MockStress.return_value = mock

        adapter = StressHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("test-round")

        assert result.harness_type == "stress"
        assert result.round_id == "test-round"
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.duration_s >= 0
        assert "resilience_score" in result.metrics

    @patch("maref.execution.harness.adapters.stress_adapter.StressHarness")
    def test_run_without_config(self, MockStress):
        """无配置时也应正常运行。"""
        mock = MagicMock()
        mock.run.return_value = _mock_stress_result()
        MockStress.return_value = mock

        adapter = StressHarnessAdapter()
        result = adapter.run("no-config")
        assert result.status == HarnessStatus.SUCCEEDED

    @patch("maref.execution.harness.adapters.stress_adapter.StressHarness")
    def test_run_handles_exception(self, MockStress):
        """内部异常应返回 FAILED 状态而非崩溃。"""
        mock = MagicMock()
        mock.run.side_effect = RuntimeError("stress test failed")
        MockStress.return_value = mock

        adapter = StressHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("fail-round")

        assert result.status == HarnessStatus.FAILED
        assert len(result.errors) == 1
        assert "stress test failed" in result.errors[0]

    def test_preflight_warns_without_config(self):
        adapter = StressHarnessAdapter()
        warnings = adapter.preflight()
        assert len(warnings) == 1
        assert "no configuration" in warnings[0]

    def test_preflight_ok_with_config(self):
        adapter = StressHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        warnings = adapter.preflight()
        assert len(warnings) == 0

    def test_list_presets_returns_dict(self):
        adapter = StressHarnessAdapter()
        presets = adapter.list_presets()
        assert isinstance(presets, dict)
        assert len(presets) > 0


# =============================================================================
# DistributedHarnessAdapter
# =============================================================================

class TestDistributedHarnessAdapter:
    def test_configure_sets_workers(self):
        adapter = DistributedHarnessAdapter()
        cfg = HarnessConfig(level="L2", extra={"workers": 8, "rounds": 5})
        adapter.configure(cfg)
        assert adapter._num_workers == 8
        assert adapter._rounds_per_worker == 5

    def test_configure_defaults(self):
        adapter = DistributedHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        assert adapter._num_workers == 4
        assert adapter._rounds_per_worker == 3

    @patch("maref.execution.harness.adapters.distributed_adapter.DistributedStressHarness")
    def test_run_returns_harness_result(self, MockDist):
        mock = MagicMock()
        mock.run_concurrent.return_value = [_mock_stress_result() for _ in range(3)]
        mock.aggregate.return_value = {"total_runs": 3, "avg_resilience": 0.85}
        MockDist.return_value = mock

        adapter = DistributedHarnessAdapter()
        adapter.configure(HarnessConfig(level="L2", extra={"workers": 2}))
        result = adapter.run("dist-round")

        assert result.harness_type == "distributed"
        assert result.status == HarnessStatus.SUCCEEDED
        assert result.metrics.get("total_runs") == 3

    @patch("maref.execution.harness.adapters.distributed_adapter.DistributedStressHarness")
    def test_run_handles_exception(self, MockDist):
        mock = MagicMock()
        mock.run_concurrent.side_effect = ValueError("connection lost")
        MockDist.return_value = mock

        adapter = DistributedHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("fail-dist")

        assert result.status == HarnessStatus.FAILED
        assert any("connection lost" in e for e in result.errors)


# =============================================================================
# EmergenceHarnessAdapter
# =============================================================================

class TestEmergenceHarnessAdapter:
    def test_configure_sets_scenario(self):
        adapter = EmergenceHarnessAdapter()
        cfg = HarnessConfig(level="L1", extra={"scenario": "byzantine_tampering", "runs": 20})
        adapter.configure(cfg)
        assert adapter._scenario_name == "byzantine_tampering"
        assert adapter._run_count == 20

    def test_configure_defaults(self):
        adapter = EmergenceHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        assert adapter._scenario_name == "temporal_perturbation"
        assert adapter._run_count == 10

    @patch("maref.execution.harness.adapters.emergence_adapter.EmergenceTestHarness")
    def test_run_high_consistency_succeeds(self, MockEmergence):
        mock = MagicMock()
        report = _mock_emergence_report(consistency_rate=0.9)
        mock.temporal_perturbation.return_value = report
        MockEmergence.return_value = mock

        adapter = EmergenceHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("emerge-round")

        assert result.status == HarnessStatus.SUCCEEDED

    @patch("maref.execution.harness.adapters.emergence_adapter.EmergenceTestHarness")
    def test_run_low_consistency_fails(self, MockEmergence):
        """一致性率 ≤0.5 时报告 FAILED。"""
        mock = MagicMock()
        report = _mock_emergence_report(consistency_rate=0.3)
        mock.temporal_perturbation.return_value = report
        MockEmergence.return_value = mock

        adapter = EmergenceHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("emerge-low")

        assert result.status == HarnessStatus.FAILED
        assert len(result.errors) > 0
        assert "inconsistency" in result.errors[0]

    @patch("maref.execution.harness.adapters.emergence_adapter.EmergenceTestHarness")
    def test_run_handles_exception(self, MockEmergence):
        mock = MagicMock()
        mock.temporal_perturbation.side_effect = RuntimeError("emergence crash")
        MockEmergence.return_value = mock

        adapter = EmergenceHarnessAdapter()
        adapter.configure(HarnessConfig(level="L1"))
        result = adapter.run("fail-emerge")

        assert result.status == HarnessStatus.FAILED
        assert any("emergence crash" in e for e in result.errors)


# =============================================================================
# 辅助 - mock 工厂
# =============================================================================

def _mock_stress_result():
    """创建模拟的 StressResult 对象（鸭子类型）。"""
    r = MagicMock()
    r.errors = []
    r.resilience_score = 0.85
    r.stress_level = "L1"
    r.latency_p50 = 45.0
    r.latency_p99 = 120.0
    r.latency_p99_9 = 200.0
    r.cb_state = "closed"
    r.healer_success_rate = 1.0
    r.oscillation_detected = False
    r.oscillation_resolved = True
    r.revert_rate = 0.0
    r.ab_test_pass_rate = 1.0
    r.axes_applied = 6
    r.healer_strategy_rates = {}
    r.degradation_plans = 0
    return r


def _mock_emergence_report(consistency_rate: float = 1.0):
    """创建模拟的 EmergenceReport 对象。"""
    r = MagicMock()
    r.scenario_name = "temporal_perturbation"
    r.run_count = 10
    r.consistent_runs = int(consistency_rate * 10)
    r.inconsistent_runs = 10 - int(consistency_rate * 10)
    r.consistency_rate = consistency_rate
    r.p99_latency_ms = 150.0
    return r
