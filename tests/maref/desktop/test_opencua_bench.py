"""Smoke tests for maref.desktop.opencua_bench."""
from __future__ import annotations

import pytest

from maref.desktop.opencua_bench import OpenCUABenchmarkResult, OpenCUAResult, OpenCUASample


class TestOpenCUASample:
    def test_init_default(self) -> None:
        sample = OpenCUASample(sample_id="s1", task_description="Test task")
        assert sample.sample_id == "s1"
        assert sample.task_description == "Test task"
        assert sample.expected_actions == []
        assert sample.ground_truth == {}

    def test_init_custom(self) -> None:
        sample = OpenCUASample(
            sample_id="s2", task_description="Another task",
            expected_actions=[{"action": "click"}], ground_truth={"result": "ok"},
        )
        assert len(sample.expected_actions) == 1
        assert sample.ground_truth["result"] == "ok"

    def test_to_dict(self) -> None:
        sample = OpenCUASample(sample_id="s1", task_description="Test")
        d = sample.to_dict()
        assert d["sample_id"] == "s1"
        assert d["task_description"] == "Test"


class TestOpenCUAResult:
    def test_init_default(self) -> None:
        result = OpenCUAResult(sample_id="s1")
        assert result.sample_id == "s1"
        assert result.action_match is False
        assert result.action_accuracy == 0.0

    def test_action_accuracy_with_steps(self) -> None:
        result = OpenCUAResult(sample_id="s1", step_correct=3, step_total=4)
        assert result.action_accuracy == 0.75
        assert result.ActionAccuracy == 0.75
        assert result.StepAccuracy == 0.75

    def test_action_accuracy_zero_total(self) -> None:
        result = OpenCUAResult(sample_id="s1")
        assert result.action_accuracy == 0.0

    def test_to_dict(self) -> None:
        result = OpenCUAResult(sample_id="s1", step_correct=3, step_total=4)
        d = result.to_dict()
        assert d["sample_id"] == "s1"
        assert d["ActionAccuracy"] == 0.75


class TestOpenCUABenchmarkResult:
    def test_init_default(self) -> None:
        result = OpenCUABenchmarkResult(
            total_samples=10, action_accuracy=0.8, step_accuracy=0.75, avg_latency_ms=100.0, p99_latency_ms=500.0,
        )
        assert result.total_samples == 10
        assert result.action_accuracy == 0.8
        assert result.step_accuracy == 0.75
        assert result.ActionAccuracy == 0.8

    def test_init_with_samples(self) -> None:
        samples = [OpenCUAResult(sample_id="s1")]
        result = OpenCUABenchmarkResult(
            total_samples=1, action_accuracy=1.0, step_accuracy=1.0,
            avg_latency_ms=50.0, p99_latency_ms=100.0,
            per_sample_results=samples,
        )
        assert len(result.per_sample_results) == 1
