"""E4: 稳定性验证测试 — E-07 熔断器 + E-08 多轮不退化的验收标准。"""

from __future__ import annotations

from maref.evolution.evolution_vault import RoundVault
from maref.governance import CircuitBreaker


class TestCircuitBreakerThreshold:
    """E-07: 熔断器在连续 3 轮演进失败时自动停止。"""

    def test_breaker_opens_after_3_consecutive(self) -> None:
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        assert cb.get_stats()["state"].upper() == "CLOSED"
        for _ in range(3):
            cb.record_failure()
        assert cb.get_stats()["state"].upper() == "OPEN"

    def test_breaker_stays_closed_under_threshold(self) -> None:
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.get_stats()["state"].upper() == "CLOSED"

    def test_breaker_resets_after_cooldown(self) -> None:
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.get_stats()["state"].upper() == "OPEN"
        import time
        time.sleep(0.15)
        cb.reset()
        assert cb.get_stats()["state"].upper() == "CLOSED"

    def test_breaker_blocks_after_limit(self) -> None:
        """RecursiveEvolutionEngine._check_stop_conditions checks breaker."""
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        for _ in range(5):
            cb.record_failure()
        stats = cb.get_stats()
        assert stats["state"].upper() == "OPEN"
        assert stats.get("trip_count", 0) >= 1

    def test_breaker_success_resets_count(self) -> None:
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        stats = cb.get_stats()
        assert stats["state"].upper() != "OPEN"


class TestRoundVaultStability:
    """E-08: 多轮连续演进不导致系统退化。"""

    def test_vault_tracks_trend(self) -> None:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "stability.db")
            v = RoundVault(db)

            for i in range(5):
                v.record_round(
                    round_num=i,
                    cycle_id="c1",
                    metrics={
                        "fnr": 0.05 - i * 0.005,
                        "fpr": 0.02,
                        "test_pass_rate": 0.95 + i * 0.005,
                        "coverage_pct": 36.1 + i * 0.5,
                        "total_tests": 100,
                        "source_file_count": 200 + i,
                        "total_lines": 50000 + i * 100,
                        "git_commit_count_30d": 15 + i,
                        "module_count": 80,
                        "governance_state": "STABILIZE",
                        "cb_state": "CLOSED",
                    },
                )

            cov_trend = v.get_trend("coverage_pct", last_n=5)
            assert len(cov_trend) == 5
            values = [t["value"] for t in cov_trend]
            assert values == sorted(values), f"Coverage trend not monotonically improving: {values}"

            fnr_trend = v.get_trend("fnr", last_n=5)
            fnr_values = [round(t["value"], 4) for t in fnr_trend]
            assert fnr_values == sorted(fnr_values, reverse=True), \
                f"FNR trend not monotonically decreasing: {fnr_values}"

    def test_vault_detects_degradation(self) -> None:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "degradation.db")
            v = RoundVault(db)

            for i in range(5):
                v.record_round(
                    round_num=i,
                    cycle_id="c1",
                    metrics={
                        "fnr": 0.05 + i * 0.02,
                        "fpr": 0.02 + i * 0.01,
                        "test_pass_rate": 0.95 - i * 0.03,
                        "coverage_pct": 36.1 - i * 0.5,
                        "total_tests": 100,
                        "source_file_count": 200,
                        "total_lines": 50000,
                        "git_commit_count_30d": 15,
                        "module_count": 80,
                        "governance_state": "DEGRADE",
                        "cb_state": "CLOSED",
                    },
                )

            pass_trend = v.get_trend("test_pass_rate", last_n=5)
            pass_values = [round(t["value"], 4) for t in pass_trend]
            assert pass_values == sorted(pass_values, reverse=True), \
                f"test_pass_rate should be degrading (decreasing): {pass_values}"

    def test_round_equivalence(self) -> None:
        """Verify that storing and reloading gives consistent results."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "equiv.db")
            v1 = RoundVault(db)
            v1.record_round(0, "c1", {"fnr": 0.05, "coverage_pct": 36.1})
            v1.record_round(1, "c1", {"fnr": 0.04, "coverage_pct": 37.0})

            v2 = RoundVault(db)
            latest = v2.get_latest_round()
            assert latest["round_num"] == 1
            assert latest["coverage_pct"] == 37.0
            all_r = v2.get_all_rounds()
            assert len(all_r) == 2
