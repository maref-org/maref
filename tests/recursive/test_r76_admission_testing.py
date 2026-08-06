from __future__ import annotations

from maref.recursive.admission_testing import (
    AdmissionGate,
    AdmissionResult,
    AdmissionRunner,
    AdmissionTarget,
    DriftDetector,
    DriftRecord,
    SandboxConfig,
    SandboxEnvironment,
    VersionPinner,
)


class TestSandboxEnvironment:
    def test_create_and_cleanup(self) -> None:
        sandbox = SandboxEnvironment()
        path = sandbox.create()
        assert path != ""
        assert sandbox.is_active
        sandbox.cleanup()
        assert not sandbox.is_active

    def test_execute_simple_command(self) -> None:
        sandbox = SandboxEnvironment(SandboxConfig(timeout_seconds=10))
        sandbox.create()
        output = sandbox.execute("echo hello")
        assert output.success
        assert "hello" in output.stdout
        sandbox.cleanup()

    def test_execute_failing_command(self) -> None:
        sandbox = SandboxEnvironment(SandboxConfig(timeout_seconds=10))
        sandbox.create()
        output = sandbox.execute("exit 1")
        assert not output.success
        sandbox.cleanup()

    def test_sandbox_dir(self) -> None:
        sandbox = SandboxEnvironment()
        sandbox.create()
        assert sandbox.sandbox_dir is not None
        sandbox.cleanup()
        assert not sandbox.is_active


class TestVersionPinner:
    def test_pin_requirements(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("pytest==7.0.0\nruff==0.1.0\n")
            req_file = f.name

        try:
            pinner = VersionPinner()
            pinned = pinner.pin(req_file)
            assert "pytest" in pinned.packages
            assert pinned.packages["pytest"] == "7.0.0"
        finally:
            import os

            os.unlink(req_file)

    def test_pin_empty_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            req_file = f.name

        try:
            pinner = VersionPinner()
            pinned = pinner.pin(req_file)
            assert len(pinned.packages) == 0
        finally:
            import os

            os.unlink(req_file)

    def test_get_pinned_returns_none(self) -> None:
        pinner = VersionPinner()
        assert pinner.get_pinned("nonexistent.txt") is None


class TestDriftDetector:
    def test_record_drift(self) -> None:
        detector = DriftDetector()
        drift = DriftRecord(
            drift_type="api_version",
            component="test_api",
            expected_version="1.0.0",
            actual_version="2.0.0",
        )
        detector.record_drift(drift)
        drifts = detector.all_drifts()
        assert len(drifts) == 1
        assert drifts[0].component == "test_api"

    def test_detect_api_drift(self) -> None:
        detector = DriftDetector()
        drifts = detector.detect_api_drift()
        assert isinstance(drifts, list)

    def test_model_drift_initial_empty(self) -> None:
        detector = DriftDetector()
        assert len(detector.detect_model_drift()) == 0


class TestAdmissionGate:
    def test_default_gate(self) -> None:
        gate = AdmissionGate(gate_id="test_gate")
        assert gate.min_coverage == 0.80
        assert gate.max_regression_rate == 0.0

    def test_gate_with_test_suites(self) -> None:
        gate = AdmissionGate(
            gate_id="integration_gate",
            required_test_suites=["test_suite_a", "test_suite_b"],
            min_coverage=0.85,
        )
        assert len(gate.required_test_suites) == 2


class TestAdmissionRunner:
    def test_run_gate_with_no_tests(self) -> None:
        gate = AdmissionGate(gate_id="empty_gate", drift_checks_enabled=False)
        runner = AdmissionRunner(gate)
        target = AdmissionTarget(target_id="target_1")
        result = runner.run_gate(target)
        assert isinstance(result, AdmissionResult)
        assert result.gate_id == "empty_gate"

    def test_run_gate_with_sandbox_command(self) -> None:
        gate = AdmissionGate(
            gate_id="echo_gate",
            required_test_suites=["echo 'test passed'"],
            drift_checks_enabled=False,
        )
        runner = AdmissionRunner(gate)
        target = AdmissionTarget(target_id="target_echo")
        result = runner.run_gate(target)
        assert result.passed

    def test_admission_result_failed_tests(self) -> None:
        result = AdmissionResult(
            gate_id="g1",
            target_id="t1",
            passed=False,
            test_results={"suite_a": True, "suite_b": False},
        )
        assert result.failed_tests == ["suite_b"]

    def test_history_tracks_results(self) -> None:
        gate = AdmissionGate(gate_id="history_gate", drift_checks_enabled=False)
        runner = AdmissionRunner(gate)
        runner.run_gate(AdmissionTarget(target_id="t1"))
        runner.run_gate(AdmissionTarget(target_id="t2"))
        assert len(runner.history()) == 2

    def test_last_result(self) -> None:
        gate = AdmissionGate(gate_id="last_gate", drift_checks_enabled=False)
        runner = AdmissionRunner(gate)
        runner.run_gate(AdmissionTarget(target_id="t1"))
        assert runner.last_result() is not None
        assert runner.last_result().target_id == "t1"
