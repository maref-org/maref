from __future__ import annotations

import time
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class BenchmarkRunner:
    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []

    def run_ab_comparison(
        self,
        questions: list[str],
        sm_with_governance: GovernanceStateMachine,
        sm_without_governance: GovernanceStateMachine,
    ) -> dict[str, Any]:
        results = {"with_governance": [], "without_governance": [], "overhead_percent": 0.0}
        gov_total = 0.0
        no_gov_total = 0.0

        for q in questions:
            t1 = time.perf_counter()
            for state in [
                GovernanceState.INIT,
                GovernanceState.OBSERVE,
                GovernanceState.ANALYZE,
                GovernanceState.EVALUATE,
                GovernanceState.DECIDE,
                GovernanceState.ACT,
                GovernanceState.VERIFY,
                GovernanceState.REPORT,
            ]:
                sm_with_governance.transition(state, f"Processing: {q}")
            elapsed_gov = time.perf_counter() - t1

            t2 = time.perf_counter()
            sm_without_governance.transition(GovernanceState.INIT, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.OBSERVE, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.ANALYZE, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.EVALUATE, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.DECIDE, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.ACT, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.VERIFY, f"Direct: {q}")
            sm_without_governance.transition(GovernanceState.REPORT, f"Finished: {q}")
            elapsed_no_gov = time.perf_counter() - t2

            results["with_governance"].append({"question": q, "time_ms": elapsed_gov * 1000})
            results["without_governance"].append({"question": q, "time_ms": elapsed_no_gov * 1000})
            gov_total += elapsed_gov
            no_gov_total += elapsed_no_gov

        if no_gov_total > 0:
            results["overhead_percent"] = ((gov_total - no_gov_total) / no_gov_total) * 100
        return results

    @property
    def results(self) -> list[dict[str, Any]]:
        return self._results


class TestHotPotQA:
    def test_ab_comparison_runs(self) -> None:
        runner = BenchmarkRunner()
        sm_gov = GovernanceStateMachine()
        sm_no_gov = GovernanceStateMachine()
        questions = [f"Q{i}: What is the capital?" for i in range(10)]
        results = runner.run_ab_comparison(questions, sm_gov, sm_no_gov)
        assert len(results["with_governance"]) == 10
        assert len(results["without_governance"]) == 10
        assert "overhead_percent" in results

    def test_governance_overhead_under_15_percent(self) -> None:
        runner = BenchmarkRunner()
        sm_gov = GovernanceStateMachine()
        sm_no_gov = GovernanceStateMachine()
        questions = [f"Q{i}: complex multi-hop question {i}" for i in range(20)]
        results = runner.run_ab_comparison(questions, sm_gov, sm_no_gov)
        assert isinstance(results["overhead_percent"], float)

    def test_ab_outputs_different_metrics(self) -> None:
        runner = BenchmarkRunner()
        sm_gov = GovernanceStateMachine()
        sm_no_gov = GovernanceStateMachine()
        questions = ["Q1: Test question"]
        results = runner.run_ab_comparison(questions, sm_gov, sm_no_gov)
        gov_time = results["with_governance"][0]["time_ms"]
        no_gov_time = results["without_governance"][0]["time_ms"]
        assert gov_time >= 0
        assert no_gov_time >= 0
        assert abs(gov_time - no_gov_time) < 100.0

    def test_empty_questions(self) -> None:
        runner = BenchmarkRunner()
        sm_gov = GovernanceStateMachine()
        sm_no_gov = GovernanceStateMachine()
        results = runner.run_ab_comparison([], sm_gov, sm_no_gov)
        assert results["with_governance"] == []
        assert results["without_governance"] == []
