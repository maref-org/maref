"""SafetyMetrics 单元测试 — SR/SSR/USR 三元组 + 合规替代动作(P0-1)."""

from __future__ import annotations

import pytest

from maref.governance.core_pipeline import GovernancePipeline, Verdict
from maref.governance.decorators import (
    GovernanceAlternativeError,
    GovernanceDeniedError,
    governed,
    set_default_pipeline,
)
from maref.governance.safety_metrics import (
    SafetyMetricsRecorder,
    SafetyOutcome,
    SanctionedAlternative,
    default_alternatives_for,
    summarize,
)


def _outcome(task_id: str, success: bool, violations: int = 0) -> SafetyOutcome:
    return SafetyOutcome(task_id=task_id, success=success, violations=violations)


class TestSummarize:
    def test_empty_batch(self) -> None:
        assert summarize([]) == {"count": 0.0, "sr": 0.0, "ssr": 0.0, "usr": 0.0}

    def test_all_clean_success(self) -> None:
        summary = summarize([_outcome("a", True), _outcome("b", True)])
        assert summary["sr"] == 1.0
        assert summary["ssr"] == 1.0
        assert summary["usr"] == 0.0

    def test_unsafe_success_counts_as_usr_not_ssr(self) -> None:
        summary = summarize([_outcome("a", True, violations=2), _outcome("b", True)])
        assert summary["sr"] == 1.0
        assert summary["ssr"] == 0.5
        assert summary["usr"] == 0.5

    def test_failure_excluded_from_ssr_and_usr(self) -> None:
        summary = summarize([_outcome("a", False, violations=1), _outcome("b", True)])
        assert summary["sr"] == 0.5
        assert summary["ssr"] == 0.5
        assert summary["usr"] == 0.0

    def test_verifier_tax_scenario(self) -> None:
        # 动作被逐次拦截(violations>0)但任务仍完成 -> SSR=0, USR=1
        outcomes = [_outcome(f"t{i}", True, violations=1) for i in range(5)]
        summary = summarize(outcomes)
        assert summary["sr"] == 1.0
        assert summary["ssr"] == 0.0
        assert summary["usr"] == 1.0


class TestRecorder:
    def test_record_and_summary(self) -> None:
        recorder = SafetyMetricsRecorder()
        recorder.record(_outcome("a", True))
        recorder.record(_outcome("b", False))
        assert recorder.count == 2
        assert recorder.summary()["sr"] == 0.5
        assert len(recorder.outcomes) == 2

    def test_reset(self) -> None:
        recorder = SafetyMetricsRecorder()
        recorder.record(_outcome("a", True))
        recorder.reset()
        assert recorder.count == 0
        assert recorder.summary()["count"] == 0.0

    def test_to_dict(self) -> None:
        recorder = SafetyMetricsRecorder()
        recorder.record(_outcome("a", True, violations=1))
        payload = recorder.to_dict()
        assert payload["summary"]["usr"] == 1.0
        assert payload["outcomes"][0]["task_id"] == "a"


class TestDefaultAlternatives:
    def test_known_action_has_alternative(self) -> None:
        alternatives = default_alternatives_for("file.delete")
        assert alternatives
        assert alternatives[0].action_id == "file.trash"

    def test_unknown_action_is_empty(self) -> None:
        assert default_alternatives_for("unknown.action") == []

    def test_to_dict_shape(self) -> None:
        payload = default_alternatives_for("shell.exec")[0].to_dict()
        assert set(payload) == {"action_id", "reason", "risk_level"}


class TestGovernedAlternatives:
    @pytest.fixture(autouse=True)
    def _reset_pipeline(self) -> None:
        yield
        set_default_pipeline(None)

    def _deny_pipeline(self, **kwargs: object) -> GovernancePipeline:
        return GovernancePipeline(
            policy_rules=[(999, lambda req: (Verdict.DENY, "blocked", None))],
            **kwargs,  # type: ignore[arg-type]
        )

    def test_dangerous_action_deny_carries_alternative(self) -> None:
        set_default_pipeline(self._deny_pipeline())

        @governed(require="file.delete")
        def delete() -> str:
            return "deleted"

        with pytest.raises(GovernanceAlternativeError) as exc:
            delete()
        assert exc.value.alternatives
        assert exc.value.alternatives[0].action_id == "file.trash"

    def test_alternative_error_is_denied_subclass(self) -> None:
        set_default_pipeline(self._deny_pipeline())

        @governed(require="file.delete")
        def delete() -> str:
            return "deleted"

        with pytest.raises(GovernanceDeniedError):
            delete()

    def test_unknown_action_plain_denied(self) -> None:
        set_default_pipeline(self._deny_pipeline())

        @governed(require="mystery.action")
        def act() -> str:
            return "done"

        with pytest.raises(GovernanceDeniedError) as exc:
            act()
        assert not isinstance(exc.value, GovernanceAlternativeError)

    def test_custom_alternative_provider(self) -> None:
        set_default_pipeline(
            self._deny_pipeline(
                alternative_provider=lambda req, result: [
                    SanctionedAlternative("custom.retry", "custom", "low")
                ]
            )
        )

        @governed(require="mystery.action")
        def act() -> str:
            return "done"

        with pytest.raises(GovernanceAlternativeError) as exc:
            act()
        assert exc.value.alternatives[0].action_id == "custom.retry"

    def test_allowed_action_not_affected(self) -> None:
        set_default_pipeline(GovernancePipeline())

        @governed(require="file.read")
        def read() -> str:
            return "content"

        assert read() == "content"
