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


@pytest.fixture(autouse=True)
def _mock_env_heavy_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """desktop/gui_build 是环境相关 heavy probe,真实测量在无 pnpm/桌面环境的
    CI 上会把正常快照误判为 CRITICAL。mock 成 NORMAL 让诊断测试跨环境确定。

    替换后的 measure 是无 __func__ 的闭包,SelfDiagnostician._heavy_measure
    会走直接调用分支并绕过类级 _heavy_probe_cache,避免跨测试缓存污染。
    """
    from maref.observation.probes import ProbeReading, ProbeSeverity

    def _normal(name: str):
        def _measure(context: dict | None = None) -> ProbeReading:
            return ProbeReading(
                probe_name=name,
                severity=ProbeSeverity.NORMAL,
                value=1.0,
                threshold=0.3,
            )

        return _measure

    monkeypatch.setattr(
        "maref.recursive.self_diagnostician.DesktopProbe.measure",
        _normal("desktop"),
    )
    monkeypatch.setattr(
        "maref.recursive.self_diagnostician.GUIBuildProbe.measure",
        _normal("gui_build"),
    )


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

    @pytest.mark.slow
    def test_triage_test_failure(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        problem_types = healer.triage(critical_report)
        assert "test_failure" in problem_types

    @pytest.mark.slow
    def test_triage_normal_report(self, healer: SelfHealer, normal_report: DiagnosisReport) -> None:
        problem_types = healer.triage(normal_report)
        assert "unknown" in problem_types

    @pytest.mark.slow
    def test_heal_returns_actions(self, healer: SelfHealer) -> None:
        actions = healer.heal(["test_failure", "coverage_drop"])
        assert len(actions) == 2
        assert actions[0].problem_type == "test_failure"
        assert actions[0].strategy == HEALING_STRATEGIES["test_failure"]
        assert actions[0].applied is True
        assert actions[0].success is True

    @pytest.mark.slow
    def test_heal_actions_have_exit_code(self, healer: SelfHealer) -> None:
        actions = healer.heal(["test_failure"])
        assert actions[0].exit_code == 0

    @pytest.mark.slow
    def test_heal_cycle_converges(self, healer: SelfHealer, normal_report: DiagnosisReport) -> None:
        healing = healer.heal_cycle(normal_report)
        assert healing.converged is True
        assert healing.final_state == "HEALTHY"
        assert healing.iterations == 0

    @pytest.mark.slow
    def test_heal_cycle_critical_max_iterations(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healing = healer.heal_cycle(critical_report)
        assert healing.iterations >= 1
        assert len(healing.actions) >= 1

    @pytest.mark.slow
    def test_heal_cycle_stores_history(
        self, healer: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healer.heal_cycle(critical_report)
        assert len(healer.history) == 1

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_heal_cycle_failing_all_strategies(
        self, healer_failing: SelfHealer, critical_report: DiagnosisReport
    ) -> None:
        healing = healer_failing.heal_cycle(critical_report)
        assert healing.converged is False
        assert healing.final_state == "DEGRADED"

    @pytest.mark.slow
    def test_healing_strategies_complete(self) -> None:
        assert len(HEALING_STRATEGIES) >= 6
        assert "test_failure" in HEALING_STRATEGIES
        assert "dependency_conflict" in HEALING_STRATEGIES
        assert "coverage_drop" in HEALING_STRATEGIES
        assert "performance_regression" in HEALING_STRATEGIES
        assert "import_error" in HEALING_STRATEGIES

    @pytest.mark.slow
    def test_heal_action_dataclass(self) -> None:
        action = HealAction(
            problem_type="test_failure", strategy="rerun", applied=True, result="passed"
        )
        assert action.problem_type == "test_failure"
        assert action.applied is True

    @pytest.mark.slow
    def test_heal_action_success_property(self) -> None:
        good = HealAction(problem_type="t", strategy="s", exit_code=0)
        assert good.success is True
        bad = HealAction(problem_type="t", strategy="s", exit_code=1)
        assert bad.success is False

    @pytest.mark.slow
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

    @pytest.mark.slow
    @pytest.mark.real
    def test_real_executor_rerun_tests(self, healer_real: SelfHealer) -> None:
        # 真实 executor 会在仓库根跑全仓 `pytest -v`(timeout=120s),
        # 15000+ 测试必然超时,归入 `real` 由 CI 的 `-m "not real"` 排除。
        actions = healer_real.heal(["test_failure"])
        assert len(actions) == 1
        assert actions[0].applied is True
        assert isinstance(actions[0].exit_code, int)

    @pytest.mark.slow
    @pytest.mark.real
    def test_real_executor_pip_check(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["dependency_conflict"])
        assert len(actions) == 1
        assert isinstance(actions[0].exit_code, int)

    @pytest.mark.slow
    @pytest.mark.real
    def test_real_executor_full_scan(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["unknown"])
        assert len(actions) == 1
        assert actions[0].applied is True

    @pytest.mark.slow
    def test_real_executor_missing_dependency(self, healer_real: SelfHealer) -> None:
        actions = healer_real.heal(["import_error"])
        assert len(actions) == 1
        assert actions[0].exit_code == 0
