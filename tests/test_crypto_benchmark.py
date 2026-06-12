"""国密基准测试模块单元测试.

覆盖 benchmark.py 的 BenchmarkResult、run_all_benchmarks、format_results。
"""
from __future__ import annotations

import pytest

from maref.crypto.benchmark import BenchmarkResult, format_results, run_all_benchmarks
from maref.crypto.sm2 import SM2KeyPair


class TestBenchmarkResult:
    def test_dataclass_fields(self) -> None:
        r = BenchmarkResult(
            algorithm="SM3",
            operation="hash",
            iterations=10,
            total_seconds=0.1,
            ops_per_second=100.0,
            throughput_mbps=1.0,
        )
        assert r.algorithm == "SM3"
        assert r.operation == "hash"
        assert r.iterations == 10
        assert r.total_seconds == 0.1
        assert r.ops_per_second == 100.0
        assert r.throughput_mbps == 1.0

    def test_optional_throughput_none(self) -> None:
        r = BenchmarkResult(
            algorithm="SM2",
            operation="sign",
            iterations=5,
            total_seconds=0.05,
            ops_per_second=100.0,
        )
        assert r.throughput_mbps is None


class TestRunAllBenchmarks:
    def test_run_all_defaults(self) -> None:
        kp = SM2KeyPair.generate()
        results = run_all_benchmarks(kp, data_size_bytes=64, iterations=2)
        assert len(results) >= 8
        names = {r.algorithm for r in results}
        assert "SM3" in names
        assert "SM4-CBC" in names
        assert "SM4-GCM" in names
        assert "SM2" in names

    def test_run_all_without_keypair(self) -> None:
        results = run_all_benchmarks(None, data_size_bytes=32, iterations=1)
        assert len(results) >= 8

    def test_result_values_positive(self) -> None:
        kp = SM2KeyPair.generate()
        results = run_all_benchmarks(kp, data_size_bytes=32, iterations=2)
        for r in results:
            assert r.iterations > 0
            assert r.total_seconds >= 0
            assert r.ops_per_second >= 0


class TestFormatResults:
    def test_format_includes_header(self) -> None:
        results = [
            BenchmarkResult("SM3", "hash", 10, 0.1, 100.0, 1.0),
        ]
        text = format_results(results)
        assert "Algorithm" in text
        assert "SM3" in text
        assert "hash" in text
        assert "100.0" in text

    def test_format_no_throughput(self) -> None:
        results = [
            BenchmarkResult("SM2", "sign", 5, 0.05, 100.0),
        ]
        text = format_results(results)
        assert "N/A" in text

    def test_format_empty(self) -> None:
        text = format_results([])
        assert "Algorithm" in text
