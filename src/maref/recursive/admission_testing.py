from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxConfig:
    isolated_fs: bool = True
    network_disabled: bool = False
    max_memory_mb: int = 512
    timeout_seconds: float = 120.0
    read_only_volumes: list[str] = field(default_factory=list)


@dataclass
class AdmissionGate:
    gate_id: str
    required_test_suites: list[str] = field(default_factory=list)
    sandbox_config: SandboxConfig = field(default_factory=SandboxConfig)
    min_coverage: float = 0.80
    max_regression_rate: float = 0.0
    version_lock_file: str = ""
    drift_checks_enabled: bool = True


@dataclass
class AdmissionTarget:
    target_id: str
    source_path: str = ""
    entry_point: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdmissionResult:
    gate_id: str
    target_id: str
    passed: bool
    test_results: dict[str, bool] = field(default_factory=dict)
    coverage_pct: float = 0.0
    regression_count: int = 0
    drift_records: list[DriftRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def failed_tests(self) -> list[str]:
        return [k for k, v in self.test_results.items() if not v]


@dataclass
class DriftRecord:
    drift_type: str
    component: str
    expected_version: str
    actual_version: str
    severity: str = "WARNING"


@dataclass
class PinnedRequirements:
    packages: dict[str, str] = field(default_factory=dict)
    python_version: str = ""
    pinned_at: float = field(default_factory=time.time)


class SandboxEnvironment:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()
        self._temp_dir: str | None = None
        self._active = False

    def create(self) -> str:
        self._temp_dir = tempfile.mkdtemp(prefix="maref_sandbox_")
        self._active = True
        return self._temp_dir

    def execute(self, command: str) -> ExecutionOutput:
        if not self._active:
            return ExecutionOutput(
                success=False,
                stdout="",
                stderr="Sandbox not active",
                return_code=-1,
            )
        import subprocess
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._config.timeout_seconds,
                cwd=self._temp_dir,
            )
            return ExecutionOutput(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionOutput(
                success=False,
                stdout="",
                stderr="Command timed out",
                return_code=-1,
            )
        except Exception as e:
            return ExecutionOutput(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
            )

    def cleanup(self) -> None:
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def sandbox_dir(self) -> str | None:
        return self._temp_dir


@dataclass
class ExecutionOutput:
    success: bool
    stdout: str
    stderr: str
    return_code: int


class VersionPinner:
    def __init__(self) -> None:
        self._pinned: dict[str, PinnedRequirements] = {}

    def pin(self, requirements_file: str) -> PinnedRequirements:
        packages: dict[str, str] = {}
        if os.path.exists(requirements_file):
            with open(requirements_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("==", 1) if "==" in line else [line, "latest"]
                        packages[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "latest"

        pinned = PinnedRequirements(
            packages=packages,
            python_version="",
        )
        self._pinned[requirements_file] = pinned
        return pinned

    def verify(self, pinned: PinnedRequirements) -> bool:
        for pkg, version in pinned.packages.items():
            try:
                import importlib.metadata
                installed = importlib.metadata.version(pkg)
                if version != "latest" and installed != version:
                    return False
            except importlib.metadata.PackageNotFoundError:
                return False
        return True

    def get_pinned(self, requirements_file: str) -> PinnedRequirements | None:
        return self._pinned.get(requirements_file)


class DriftDetector:
    def __init__(self) -> None:
        self._api_drift_records: list[DriftRecord] = []
        self._model_drift_records: list[DriftRecord] = []

    def detect_api_drift(self) -> list[DriftRecord]:
        records: list[DriftRecord] = []
        api_markers = {
            "openai": "1.0.0",
            "anthropic": "0.30.0",
            "pydantic": "2.0.0",
            "fastapi": "0.100.0",
        }
        for pkg, expected in api_markers.items():
            try:
                import importlib.metadata
                actual = importlib.metadata.version(pkg)
                if actual != expected:
                    records.append(DriftRecord(
                        drift_type="api_version",
                        component=pkg,
                        expected_version=expected,
                        actual_version=actual,
                        severity="WARNING",
                    ))
            except importlib.metadata.PackageNotFoundError:
                pass

        self._api_drift_records.extend(records)
        return records

    def detect_model_drift(self) -> list[DriftRecord]:
        return list(self._model_drift_records)

    def record_drift(self, drift: DriftRecord) -> None:
        if drift.drift_type == "api_version":
            self._api_drift_records.append(drift)
        elif drift.drift_type == "model_version":
            self._model_drift_records.append(drift)

    def all_drifts(self) -> list[DriftRecord]:
        return self._api_drift_records + self._model_drift_records


class AdmissionRunner:
    def __init__(self, gate: AdmissionGate | None = None) -> None:
        self._gate = gate or AdmissionGate(gate_id="default")
        self._sandbox = SandboxEnvironment(self._gate.sandbox_config)
        self._pinner = VersionPinner()
        self._drift_detector = DriftDetector()
        self._results: list[AdmissionResult] = []

    def run_gate(self, target: AdmissionTarget) -> AdmissionResult:
        start_time = time.time()
        errors: list[str] = []

        result = AdmissionResult(
            gate_id=self._gate.gate_id,
            target_id=target.target_id,
            passed=False,
        )

        self._sandbox.create()
        try:
            tests_passed: dict[str, bool] = {}
            for suite in self._gate.required_test_suites:
                try:
                    output = self._sandbox.execute(suite)
                    tests_passed[suite] = output.success
                    if not output.success:
                        errors.append(f"Test suite '{suite}' failed: {output.stderr[:200]}")
                except Exception as e:
                    tests_passed[suite] = False
                    errors.append(f"Test suite '{suite}' error: {e}")
            result.test_results = tests_passed

            if self._gate.version_lock_file:
                pinned = self._pinner.pin(self._gate.version_lock_file)
                if not self._pinner.verify(pinned):
                    errors.append("Version pinning verification failed")
                    result.passed = False

            if self._gate.drift_checks_enabled:
                api_drifts = self._drift_detector.detect_api_drift()
                result.drift_records = api_drifts
                if api_drifts:
                    result.passed = False
                    errors.extend(f"API drift: {d.component} {d.expected_version} -> {d.actual_version}"
                                  for d in api_drifts)

            all_tests_pass = all(tests_passed.values()) if tests_passed else len(errors) == 0
            result.passed = all_tests_pass and not self._gate.drift_checks_enabled or (
                all_tests_pass and len(api_drifts) == 0
            )
        finally:
            self._sandbox.cleanup()

        result.errors = errors
        result.duration_ms = (time.time() - start_time) * 1000
        self._results.append(result)
        return result

    def history(self) -> list[AdmissionResult]:
        return list(self._results)

    def last_result(self) -> AdmissionResult | None:
        return self._results[-1] if self._results else None
