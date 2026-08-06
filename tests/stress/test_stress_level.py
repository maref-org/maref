from __future__ import annotations

import pytest

from maref.stress.stress_level import STRESS_AXIS_NAMES, STRESS_PRESETS, StressLevel


class TestStressLevel:
    def test_enum_values(self):
        assert StressLevel.L1.numeric == 1
        assert StressLevel.L2.numeric == 2
        assert StressLevel.L3.numeric == 3
        assert StressLevel.L4.numeric == 4
        assert StressLevel.L5.numeric == 5

    def test_labels(self):
        assert StressLevel.L1.label == "安全区"
        assert StressLevel.L2.label == "中度区"
        assert StressLevel.L3.label == "降级边界"
        assert StressLevel.L4.label == "降级区"
        assert StressLevel.L5.label == "崩溃边界"

    def test_descriptions_nonempty(self):
        for level in StressLevel:
            assert len(level.description) > 0

    def test_from_numeric_exact(self):
        assert StressLevel.from_numeric(1) == StressLevel.L1
        assert StressLevel.from_numeric(3) == StressLevel.L3
        assert StressLevel.from_numeric(5) == StressLevel.L5

    def test_from_numeric_unknown_returns_L3(self):
        assert StressLevel.from_numeric(0) == StressLevel.L3
        assert StressLevel.from_numeric(99) == StressLevel.L3
        assert StressLevel.from_numeric(-1) == StressLevel.L3

    def test_str_presets_all_levels_present(self):
        assert set(STRESS_PRESETS.keys()) == {
            StressLevel.L1, StressLevel.L2, StressLevel.L3,
            StressLevel.L4, StressLevel.L5,
        }

    def test_presets_monotonic(self):
        axes = ["agent_concurrency", "churn_rate", "fault_rate",
                "recursion_depth", "oscillation_rate", "data_volume"]
        for axis in axes:
            values = [STRESS_PRESETS[l][axis] for l in StressLevel]
            assert values == sorted(values), f"{axis} not monotonic: {values}"

    def test_axis_names_all_present(self):
        expected = {"agent_concurrency", "churn_rate", "fault_rate",
                    "recursion_depth", "oscillation_rate", "data_volume"}
        assert set(STRESS_AXIS_NAMES.keys()) == expected

    def test_axis_names_are_chinese(self):
        for name in STRESS_AXIS_NAMES.values():
            assert isinstance(name, str)
            assert len(name) > 0
