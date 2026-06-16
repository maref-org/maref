from __future__ import annotations

import pytest

from maref.recursive.self_diagnostician import (
    DiagnosisReport,
    SelfDiagnostician,
)
from maref.recursive.self_healer import (
    HEALING_STRATEGIES,
    HealAction,
    HealingRecord,
    SelfHealer,
)
from maref.recursive.self_observer import SystemSnapshot


def _mock_executor(strategy: str, problem_type: str) -> HealAction:
    return HealAction(
        problem_type=problem_type,
        strategy=strategy,
        applied=True,
        result="mock_recovery",
        iteration=0,
        exit_code=0,
        detail=f"mock: {strategy}",
    )


def _mock_executor_failing(strategy: str, problem_type: str) -> HealAction:
    return HealAction(
        problem_type=problem_type,
        strategy=strategy,
        applied=True,
        result="mock_failure",
        iteration=0,
        exit_code=1,
        detail=f"mock fail: {strategy}",
    )


class TestSelfHealer:
    @pytest.fixture
    def healer(self) -> SelfHealer:
        return SelfHealer(strategy_executor=_mock_executor)

    @pytest.fixture
    def healer_real(self) -> SelfHealer:
        return SelfHealer()

    @pytest.fixture
    def healer_failing(self) -> SelfHealer:
        return SelfHealer(strategy_executor=_mock_executor_failing)

    @pytest.fixture
    def critical_report(self) -> DiagnosisReport:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 0, "failed": 100},
            module_graph={"a": [], "b": [], "c": [], "d": [], "e": []},
            git_stats={"tags": []},
            source_file_count=20,
            total_lines=5000,
        )
        d = SelfDiagnostician()
        return d.diagnose(snapshot)

    @pytest.fixture
    def normal_report(self) -> DiagnosisReport:
        snapshot = SystemSnapshot(
            test_stats={"total": 100, "passed": 100, "failed": 0},
            module_graph={"a": []},
            git_stats={"tags": []},
            source_file_count=1,
            total_lines=100,
        )
        d = SelfDiagnostician()
        return d.diagnose(snapshot)

    def test_triage_test_failure(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        problem_types = healer.triage(critical_report)
        assert "test_failure" in problem_types

    def test_triage_normal_report(self, healer: SelfHealer, normal_report: DiagnosisReport) -> None:
        problem_types = healer.triage(normal_report)
        assert "unknown" in problem_types

    def test_heal_returns_actions(self, healer: SelfHealer) -> None:
        actions = healer.heal(["test_failure", "coverage_drop"])
        assert len(actions) == 2
        assert actions[0].problem_type == "test_failure"
        assert actions[0].strategy == HEALING_STRATEGIES["test_failure"]
        assert actions[0].applied is True
        assert actions[0].success is True

    def test_heal_actions_have_exit_code(self, healer: SelfHealer) -> None:
        actions = healer.heal(["test_failure"])
        assert actions[0].exit_code == 0

    def test_heal_cycle_converges(self, healer: SelfHealer, normal_report: DiagnosisReport) -> None:
        healing = healer.heal_cycle(normal_report)
        assert healing.converged is True
        assert healing.final_state == "HEALTHY"
        assert healing.iterations == 0

    def test_heal_cycle_critical_max_iterations(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healing = healer.heal_cycle(critical_report)
        assert healing.iterations >= 1
        assert len(healing.actions) >= 1

    def test_heal_cycle_stores_history(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healer.heal_cycle(critical_report)
        assert len(healer.history) == 1

    def test_heal_cycle_with_re_diagnose(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        re_diagnose_calls = []

        def re_diagnose() -> DiagnosisReport:
            re_diagnose_calls.append(1)
            snapshot = SystemSnapshot(
                test_stats={"total": 100, "passed": 100, "failed": 0},
                module_graph={"a": []},
                git_stats={"tags": []},
                source_file_count=1,
                total_lines=100,
            )
            d = SelfDiagnostician()
            return d.diagnose(snapshot)

        healing = healer.heal_cycle(critical_report, re_diagnose=re_diagnose)
        assert len(re_diagnose_calls) >= 1
        assert healing.converged is True
        assert healing.final_state == "RECOVERED"

    def test_heal_cycle_failing_all_strategies(
        self, healer_failing: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healing = healer_failing.heal_cycle(critical_report)
        assert healing.converged is False
        assert healing.final_state == "DEGRADED"

    def test_healing_strategies_complete(self) -> None:
        assert len(HEALING_STRATEGIES) >= 6
        assert "test_failure" in HEALING_STRATEGIES
        assert "dependency_conflict" in HEALING_STRATEGIES
        assert "coverage_drop" in HEALING_STRATEGIES
        assert "performance_regression" in HEALING_STRATEGIES
        assert "import_error" in HEALING_STRATEGIES

    def test_heal_action_dataclass(self) -> None:
        action = HealAction(
            problem_type="test_failure", strategy="rerun", applied=True, result="passed"
        )
        assert action.problem_type == "test_failure"
        assert action.applied is True

    def test_heal_action_success_property(self) -> None:
        good = HealAction(problem_type="t", strategy="s", exit_code=0)
        assert good.success is True
        bad = HealAction(problem_type="t", strategy="s", exit_code=1)
        assert bad.success is False

    def test_healing_record_to_unified(self) -> None:
        record = HealingRecord(
            actions=[
                HealAction(problem_type="test_failure", strategy="rerun", exit_code=0, detail="ok"),
                HealAction(
                    problem_type="coverage_drop", strategy="stubs", exit_code=1, detail="fail"
                ),
            ],
            final_state="RECOVERED",
            iterations=1,
            converged=True,
        )
        unified = record.to_unified(round_num=51)
        assert len(unified) == 2
        assert unified[0].outcome == "success"
        assert unified[1].outcome == "failure"

    def test_real_executor_rerun_tests(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["test_failure"])
        assert len(actions) == 1
        assert actions[0].applied is True
        assert isinstance(actions[0].exit_code, int)

    def test_real_executor_pip_check(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["dependency_conflict"])
        assert len(actions) == 1
        assert isinstance(actions[0].exit_code, int)

    def test_real_executor_full_scan(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["unknown"])
        assert len(actions) == 1
        assert actions[0].applied is True

    def test_real_executor_missing_dependency(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["import_error"])
        assert len(actions) == 1
        assert actions[0].exit_code == 0
