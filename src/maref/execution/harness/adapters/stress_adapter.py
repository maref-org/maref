from __future__ import annotations

import time

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.stress.stress_harness import StressHarness
from maref.stress.stress_level import STRESS_PRESETS, StressLevel


class StressHarnessAdapter(BaseHarness):
    def __init__(self) -> None:
        super().__init__()
        self._harness = StressHarness()

    def configure(self, config: HarnessConfig) -> None:
        super().configure(config)
        level = _parse_level(config.level)
        self._harness.set_level(level)
        if config.duration_minutes > 0:
            self._harness.set_duration(config.duration_minutes)
        for k, v in config.extra.items():
            if k in (
                "agent_concurrency",
                "churn_rate",
                "fault_rate",
                "recursion_depth",
                "oscillation_rate",
                "data_volume",
            ):
                self._harness.set_axis(k, float(v))

    def run(self, round_id: str = "") -> HarnessResult:
        config = HarnessConfig() if self._config is None else self._config
        rid = round_id or config.round_id or f"stress-{int(time.time())}"
        start = time.time()
        try:
            raw = self._harness.run(rid)
            elapsed = time.time() - start
            return HarnessResult(
                harness_type="stress",
                round_id=rid,
                status=HarnessStatus.SUCCEEDED,
                duration_s=round(elapsed, 2),
                errors=list(raw.errors),
                metrics={
                    "resilience_score": raw.resilience_score,
                    "stress_level": raw.stress_level,
                    "latency_p50": raw.latency_p50,
                    "latency_p99": raw.latency_p99,
                    "latency_p99_9": raw.latency_p99_9,
                    "cb_state": raw.cb_state,
                    "healer_success_rate": raw.healer_success_rate,
                    "oscillation_detected": raw.oscillation_detected,
                    "oscillation_resolved": raw.oscillation_resolved,
                    "revert_rate": raw.revert_rate,
                    "ab_test_pass_rate": raw.ab_test_pass_rate,
                    "axes_applied": raw.axes_applied,
                    "healer_strategy_rates": raw.healer_strategy_rates,
                    "degradation_plans": raw.degradation_plans,
                },
                raw=raw,
            )
        except Exception as e:
            return HarnessResult(
                harness_type="stress",
                round_id=rid,
                status=HarnessStatus.FAILED,
                duration_s=round(time.time() - start, 2),
                errors=[str(e)],
            )

    def list_presets(self) -> dict[str, dict[str, float]]:
        return {str(level): dict(STRESS_PRESETS[level]) for level in StressLevel}


def _parse_level(s: str) -> StressLevel:
    try:
        return StressLevel[s.upper()]
    except KeyError:
        pass
    try:
        return StressLevel.from_numeric(int(s.replace("L", "")))
    except (ValueError, AttributeError):
        return StressLevel.L1
