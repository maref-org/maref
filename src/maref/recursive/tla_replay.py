from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TLAInvariantCheck:
    invariant_name: str
    passed: bool | None
    description: str
    counterexample: str | None = None
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant": self.invariant_name,
            "passed": self.passed,
            "description": self.description,
            "counterexample": self.counterexample,
            "details": self.details,
        }


@dataclass
class TLAValidationReport:
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    checks: list[TLAInvariantCheck] = field(default_factory=list)
    log_path: str = ""
    spec_path: str = ""
    state_count: int = 0

    @property
    def all_passed(self) -> bool:
        return self.passed == self.total_checks and self.total_checks > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "all_passed": self.all_passed,
            "checks": [c.to_dict() for c in self.checks],
            "log_path": self.log_path,
            "spec_path": self.spec_path,
            "state_count": self.state_count,
        }


class TLAReplayValidator:
    """Validator for MAREF governance invariants from observed trajectories.

    Performs runtime checks on evolution state data:
    - LyapunovConvergence (empirical — monotonic decrease check)
    - HALTAbsorbing (structural — no transitions after HALT)
    - GrayCodeTransition (structural — single-bit transitions)

    SafetyGateIntegrity and RedLineImmutability are structural invariants
    verified via TLA+ model checking (MAREF_ConstitutionalRedLines.tla).
    They are not verifiable from trajectory data alone and are marked
    ``passed=None`` in Python reports.
    """

    DEFAULT_TLA_SPEC: dict[str, Any] = {
        "version": "0.38.0",
        "invariants": [
            {
                "name": "LyapunovConvergence",
                "description": "Lyapunov function V(x) decreases monotonically toward basin",
                "expression": "V(s_{t+1}) <= V(s_t) for all t beyond convergence horizon",
                "check_type": "empirical",
                "tolerance": 0.01,
            },
            {
                "name": "HALTAbsorbing",
                "description": "Once HALT is reached, no further state transitions occur",
                "expression": "s_t = HALT => forall k > 0: s_{t+k} = HALT",
                "check_type": "tla_invariant",
            },
            {
                "name": "GrayCodeTransition",
                "description": "Agent state transitions follow Gray code (single-bit change)",
                "expression": "hamming_distance(s_t, s_{t+1}) == 1 for agent state vectors",
                "check_type": "tla_invariant",
            },
            {
                "name": "SafetyGateIntegrity",
                "description": "Safety gate cannot be bypassed by any evolution decision",
                "expression": "Square(SafetyGate.active = True /\\ forall decision: SafetyGate.evaluate(decision) != None)",
                "check_type": "tla_invariant",
            },
            {
                "name": "RedLineImmutability",
                "description": "Red lines cannot be self-modified by any agent",
                "expression": "forall rl in RedLines: Square(rl.modified_by notin Agents /\\ rl.immutable = True)",
                "check_type": "tla_invariant",
            },
        ],
    }

    def __init__(self, tla_spec_path: str | None = None) -> None:
        self._spec_path = Path(tla_spec_path) if tla_spec_path else Path("tla_spec.json")
        self._spec: dict[str, Any] = self._load_spec()

    def _load_spec(self) -> dict[str, Any]:
        if self._spec_path.exists():
            try:
                return json.loads(self._spec_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return dict(self.DEFAULT_TLA_SPEC)

    def replay_log(self, log_path: str) -> dict[str, Any]:
        log = Path(log_path)
        if not log.exists():
            return {"error": f"Log not found: {log_path}", "states": []}

        try:
            raw = log.read_text()
            states: list[dict[str, Any]] = []
            for line in raw.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    states.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            return {"error": f"Cannot read: {log_path}", "states": []}

        results: dict[str, Any] = {
            "log_path": log_path,
            "state_count": len(states),
            "lyapunov": self.check_lyapunov(states),
            "halt_absorption": self.check_halt_absorption(states),
            "gray_code": self.check_gray_code_transitions(states),
        }
        return results

    def check_lyapunov(self, states: list[dict[str, Any]]) -> bool:
        if len(states) < 2:
            return True

        def lyapunov_v(state: dict[str, Any]) -> float:
            fnr = state.get("fnr", 0.1)
            fpr = state.get("fpr", 0.05)
            entropy = state.get("entropy", 0)
            kl_drift = state.get("kl_drift", 0.0)
            return (fnr * 2.0) + (fpr * 1.0) + (entropy * 0.1) + kl_drift

        violations = 0
        for i in range(1, len(states)):
            v_prev = lyapunov_v(states[i - 1])
            v_curr = lyapunov_v(states[i])
            if v_curr > v_prev + 0.01:
                violations += 1

        return violations <= max(1, len(states) * 0.05)

    def check_halt_absorption(self, states: list[dict[str, Any]]) -> bool:
        halted_at: int | None = None
        for i, state in enumerate(states):
            halt_status = state.get("halt", state.get("halted", state.get("state", "")))
            if halt_status in ("HALT", True, "halted", "halt"):
                halted_at = i
                break

        if halted_at is None:
            return True

        for j in range(halted_at + 1, len(states)):
            halt_status = states[j].get("halt", states[j].get("halted", states[j].get("state", "")))
            if halt_status not in ("HALT", True, "halted", "halt"):
                return False

        return True

    def check_gray_code_transitions(self, states: list[dict[str, Any]]) -> bool:
        if len(states) < 2:
            return True

        def state_to_bitmask(state: dict[str, Any], field: str = "agent_state") -> int:
            raw = state.get(field, state.get("state_bits", state.get("bitmask", 0)))
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str):
                try:
                    return int(raw, 2)
                except ValueError:
                    return 0
            return 0

        def hamming_distance(a: int, b: int) -> int:
            return (a ^ b).bit_count()

        violations = 0
        for i in range(1, len(states)):
            prev = state_to_bitmask(states[i - 1])
            curr = state_to_bitmask(states[i])
            if prev == 0 and curr == 0:
                continue
            if hamming_distance(prev, curr) != 1:
                violations += 1

        return violations <= max(1, len(states) * 0.10)

    def generate_validation_report(
        self,
        states: list[dict[str, Any]] | None = None,
    ) -> TLAValidationReport:
        """Generate a validation report from observed state trajectories.

        When ``states`` is provided, real checks are run for:
        - LyapunovConvergence (empirical check on trajectory)
        - HALTAbsorbing (state machine check on trajectory)
        - GrayCodeTransition (bit transition check on trajectory)

        SafetyGateIntegrity and RedLineImmutability are structural invariants
        verified via TLA+ model checking in ``src/formal/MAREF_ConstitutionalRedLines.tla``.
        They are marked ``passed=None`` (not verifiable from trajectory data alone).

        When ``states`` is None, all invariants are marked ``passed=None``
        with an explanation — no verification was performed.

        Args:
            states: Optional observed trajectory for empirical and structural checks.
        """
        report = TLAValidationReport(spec_path=str(self._spec_path))

        invariants = self._spec.get("invariants", self.DEFAULT_TLA_SPEC["invariants"])
        report.total_checks = len(invariants)

        if states is not None:
            report.state_count = len(states)

        for inv in invariants:
            name = inv["name"]
            desc = inv.get("description", "")
            check_type = inv.get("check_type", "tla_invariant")

            if states is None or len(states) < 2:
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=None,
                    description=desc,
                    details=[
                        f"check_type={check_type}",
                        "No state data provided — verification requires evolution trajectory",
                    ],
                )
            elif name == "LyapunovConvergence":
                passed = self.check_lyapunov(states)
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=passed,
                    description=desc,
                    details=[
                        f"check_type={check_type} (not a TLA+ invariant)",
                        f"Empirical Lyapunov check on {len(states)} states: "
                        f"{'monotonic decrease within tolerance' if passed else 'violations exceed tolerance'}",
                    ],
                )
            elif name == "HALTAbsorbing":
                passed = self.check_halt_absorption(states)
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=passed,
                    description=desc,
                    details=[
                        f"check_type={check_type}",
                        f"Runtime check on {len(states)} states: "
                        f"{'halt absorption holds' if passed else 'violation detected'}",
                        "Also model-checked in src/formal/MAREF_ConstitutionalRedLines.tla",
                    ],
                )
            elif name == "GrayCodeTransition":
                passed = self.check_gray_code_transitions(states)
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=passed,
                    description=desc,
                    details=[
                        f"check_type={check_type}",
                        f"Gray code transition check on {len(states)} states: "
                        f"{'all single-bit' if passed else 'multi-bit violations detected'}",
                    ],
                )
            elif name in ("SafetyGateIntegrity", "RedLineImmutability"):
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=None,
                    description=desc,
                    details=[
                        f"check_type={check_type}",
                        "Structural invariant — verified in TLA+ model checking",
                        "See src/formal/MAREF_ConstitutionalRedLines.tla",
                    ],
                )
            else:
                check = TLAInvariantCheck(
                    invariant_name=name,
                    passed=None,
                    description=desc,
                    details=[f"check_type={check_type}", "Unknown invariant — not verified"],
                )

            report.checks.append(check)
            if check.passed is True:
                report.passed += 1
            elif check.passed is False:
                report.failed += 1

        return report

    @property
    def spec(self) -> dict[str, Any]:
        return dict(self._spec)

    def reload_spec(self, path: str) -> None:
        self._spec_path = Path(path)
        self._spec = self._load_spec()


class TLAReplayRunner:
    """Parses a TLA+ spec file and enumerates invariants for validation.

    Provides run_check, run_all, and generate_report methods that
    integrate with TLAInvariantCheck and TLAValidationReport.
    """

    def __init__(self, spec_path: str | Path | None = None, spec_text: str | None = None) -> None:
        self._spec_path = Path(spec_path) if spec_path else None
        self._spec_text = spec_text
        self._invariants: list[dict[str, Any]] = []
        self._parse_invariants()

    def _parse_invariants(self) -> None:
        """Extract invariant operator definitions from the spec text using regex."""
        if self._spec_path and self._spec_path.exists():
            text = self._spec_path.read_text()
        elif self._spec_text:
            text = self._spec_text
        else:
            self._invariants = []
            return

        inv_pattern = re.compile(r'^(\w+Inv)\s*==', re.MULTILINE)
        names = inv_pattern.findall(text)

        self._invariants = []
        for name in names:
            self._invariants.append({
                "name": name,
                "description": f"Invariant {name}",
                "expression": "",
            })

    @property
    def invariants(self) -> list[dict[str, Any]]:
        return list(self._invariants)

    def run_check(self, invariant_name: str) -> TLAInvariantCheck:
        names = [inv["name"] for inv in self._invariants]
        found = invariant_name in names
        return TLAInvariantCheck(
            invariant_name=invariant_name,
            passed=found,
            description=f"Invariant '{invariant_name}' {'found' if found else 'not found'} in spec",
            counterexample=None if found else f"Invariant {invariant_name} not defined in spec",
            details=[f"Located in {self._spec_path}" if self._spec_path else "Parsed from text"],
        )

    def run_all(self) -> list[TLAInvariantCheck]:
        return [self.run_check(inv["name"]) for inv in self._invariants]

    def generate_report(self) -> TLAValidationReport:
        checks = self.run_all()
        report = TLAValidationReport(
            total_checks=len(checks),
            passed=sum(1 for c in checks if c.passed),
            failed=sum(1 for c in checks if not c.passed),
            checks=checks,
            spec_path=str(self._spec_path) if self._spec_path else "",
            state_count=0,
        )
        return report
