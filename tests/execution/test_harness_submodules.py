from __future__ import annotations

import pytest

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.exceptions import HarnessAbortedError, HarnessExecutionError
from maref.execution.harness.lifecycle import HarnessLifecycleState, _VALID_TRANSITIONS
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus


class TestHarnessBase:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            BaseHarness()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class ConcreteHarness(BaseHarness):
            def run(self, round_id: str = "") -> HarnessResult:
                return HarnessResult()

        h = ConcreteHarness()
        assert h._config is None

    def test_configure(self) -> None:
        class ConcreteHarness(BaseHarness):
            def run(self, round_id: str = "") -> HarnessResult:
                return HarnessResult()

        h = ConcreteHarness()
        config = HarnessConfig(level="L5")
        h.configure(config)
        assert h._config is not None
        assert h._config.level == "L5"

    def test_preflight_default(self) -> None:
        class ConcreteHarness(BaseHarness):
            def run(self, round_id: str = "") -> HarnessResult:
                return HarnessResult()

        h = ConcreteHarness()
        assert h.preflight() == []

    def test_validate_delegate(self) -> None:
        class ConcreteHarness(BaseHarness):
            def run(self, round_id: str = "") -> HarnessResult:
                return HarnessResult()

        h = ConcreteHarness()
        assert h.validate(HarnessResult(passed=True))
        assert not h.validate(HarnessResult(passed=False))


class TestHarnessExceptions:
    def test_harness_execution_error(self) -> None:
        e = HarnessExecutionError("test error")
        assert str(e) == "test error"
        assert isinstance(e, Exception)

    def test_harness_aborted_error(self) -> None:
        e = HarnessAbortedError("aborted")
        assert str(e) == "aborted"
        assert isinstance(e, Exception)


class TestHarnessLifecycleState:
    def test_values(self) -> None:
        assert HarnessLifecycleState.INIT.value == "init"
        assert HarnessLifecycleState.PREFLIGHT.value == "preflight"
        assert HarnessLifecycleState.READY.value == "ready"
        assert HarnessLifecycleState.RUNNING.value == "running"
        assert HarnessLifecycleState.VALIDATING.value == "validating"
        assert HarnessLifecycleState.REPORTING.value == "reporting"
        assert HarnessLifecycleState.DONE.value == "done"
        assert HarnessLifecycleState.FAILED.value == "failed"
        assert len(HarnessLifecycleState) == 8

    def test_valid_transitions_init(self) -> None:
        transitions = _VALID_TRANSITIONS[HarnessLifecycleState.INIT]
        assert HarnessLifecycleState.PREFLIGHT in transitions
        assert HarnessLifecycleState.FAILED in transitions

    def test_valid_transitions_done(self) -> None:
        assert _VALID_TRANSITIONS[HarnessLifecycleState.DONE] == []

    def test_valid_transitions_failed(self) -> None:
        assert _VALID_TRANSITIONS[HarnessLifecycleState.FAILED] == []


class TestHarnessStatus:
    def test_values(self) -> None:
        assert HarnessStatus.SUCCEEDED.value == "succeeded"
        assert HarnessStatus.FAILED.value == "failed"
        assert HarnessStatus.ABORTED.value == "aborted"
        assert len(HarnessStatus) == 3


class TestHarnessConfig:
    def test_defaults(self) -> None:
        c = HarnessConfig()
        assert c.harness_type == "unified"
        assert c.level == "L1"
        assert c.token_budget == 0
        assert c.max_workers == 4
        assert c.timeout_seconds == 300
        assert c.retry_count == 0
        assert c.extra == {}

    def test_custom_values(self) -> None:
        c = HarnessConfig(
            harness_type="stress",
            level="L5",
            round_id="round-1",
            duration_minutes=10.0,
            token_budget=4096,
            extra={"key": "val"},
        )
        assert c.harness_type == "stress"
        assert c.level == "L5"
        assert c.token_budget == 4096
        assert c.extra == {"key": "val"}


class TestHarnessResult:
    def test_defaults(self) -> None:
        r = HarnessResult()
        assert r.harness_type == "unified"
        assert r.status == HarnessStatus.SUCCEEDED
        assert r.passed
        assert r.duration_s == 0.0
        assert r.errors == []
        assert r.metrics == {}
        assert r.raw is None

    def test_failed_result(self) -> None:
        r = HarnessResult(
            harness_type="stress",
            status=HarnessStatus.FAILED,
            passed=False,
            duration_s=5.5,
            errors=["timeout"],
        )
        assert not r.passed
        assert r.status == HarnessStatus.FAILED
        assert "timeout" in r.errors
