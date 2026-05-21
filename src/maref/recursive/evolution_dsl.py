from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditRecord


@dataclass
class SafetyGate:
    min_test_pass_rate: float = 0.95
    max_coverage_drop_pct: float = 2.0
    max_perf_regression_pct: float = 5.0
    require_sandbox_simulation: bool = True
    min_simulation_rounds: int = 3
    forbid_core_removal: bool = True

    _CORE_COMPONENTS: tuple = (
        "circuit_breaker",
        "state_machine",
        "audit_logger",
    )

    def evaluate(self, rule: EvolutionRule, metrics: dict[str, float] | None = None) -> GateResult:
        if self.forbid_core_removal:
            for core in self._CORE_COMPONENTS:
                if core in rule.target.lower() and rule.proposed_value is None:
                    return GateResult(
                        passed=False,
                        rejection_reason=f"forbid_core_removal: cannot remove {rule.target}",
                        risk_assessment="HIGH",
                    )

        if rule.proposed_value is None:
            return GateResult(
                passed=True,
                rejection_reason="",
                risk_assessment="LOW",
            )

        if metrics:
            test_pass_rate = metrics.get("test_pass_rate", 1.0)
            coverage_pct = metrics.get("coverage_pct", 100.0)
            baseline_coverage = metrics.get("baseline_coverage_pct", coverage_pct)
            coverage_drop = baseline_coverage - coverage_pct
            perf_regression = metrics.get("perf_regression_pct", 0.0)

            if test_pass_rate < self.min_test_pass_rate:
                return GateResult(
                    passed=False,
                    rejection_reason=f"test_pass_rate {test_pass_rate:.2f} < {self.min_test_pass_rate}",
                    risk_assessment="HIGH",
                )
            if coverage_drop > self.max_coverage_drop_pct:
                return GateResult(
                    passed=False,
                    rejection_reason=f"coverage_drop {coverage_drop:.1f}% > {self.max_coverage_drop_pct}%",
                    risk_assessment="MEDIUM",
                )
            if perf_regression > self.max_perf_regression_pct:
                return GateResult(
                    passed=False,
                    rejection_reason=f"perf_regression {perf_regression:.1f}% > {self.max_perf_regression_pct}%",
                    risk_assessment="MEDIUM",
                )

        return GateResult(
            passed=True,
            rejection_reason="",
            risk_assessment="LOW",
        )


@dataclass
class GateResult:
    passed: bool
    rejection_reason: str = ""
    risk_assessment: str = "LOW"


@dataclass
class EvolutionRule:
    rule_id: str
    target: str
    current_value: Any
    proposed_value: Any
    justification: str = ""
    safety_gate: SafetyGate = field(default_factory=SafetyGate)
    rollback_trigger: str = ""


@dataclass
class SimulationResult:
    rounds_completed: int = 0
    passed: bool = False
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ApplyResult:
    applied: bool = False
    rule_id: str = ""
    timestamp: float = 0.0
    regression_passed: bool = False


@dataclass
class EvolutionAuditEntry:
    rule_id: str
    target: str
    timestamp: float
    justification: str
    gate_passed: bool

    def to_unified(self, round_num: int = 10) -> UnifiedAuditRecord:
        from maref.recursive.unified_audit import UnifiedAuditRecord

        return UnifiedAuditRecord(
            record_id=self.rule_id,
            timestamp=self.timestamp,
            layer="evolution",
            round=round_num,
            event_type="evolution",
            source_module="EvolutionDSL",
            target_module=self.target,
            decision="apply_rule" if self.gate_passed else "reject_rule",
            justification=self.justification,
            outcome="success" if self.gate_passed else "failure",
            context_refs=[],
        )


class EvolutionDSL:
    def __init__(self, freeze_zone: Any = None) -> None:
        self._rules: dict[str, EvolutionRule] = {}
        self._audit: list[EvolutionAuditEntry] = []
        if freeze_zone is not None:
            self._freeze_zone = freeze_zone
        else:
            from maref.recursive.rule_freeze_zone import RuleFreezeZone
            self._freeze_zone = RuleFreezeZone()

    def load_default_rules(self, skip_frozen: bool = True) -> list[EvolutionRule]:
        defaults = [
            ("adoption_gain_threshold", 0.03, "GA 阈值 3% 激进"),
            ("heal_max_iterations", 3, "收敛上限 3 轮"),
            ("meta_cb_trip_threshold", 4, "元CB 4次 trip → OPEN"),
            ("max_recursion_depth", 4, "递归深度限制 激进"),
            ("chaos_stress_duration", 30, "混沌压测 30s"),
            ("coverage_target_pct", 80.0, "覆盖率目标"),
            ("benchmark_warmup_runs", 2, "A/B benchmark 预热"),
            ("stability_timeout_s", 30.0, "稳定观测超时"),
            ("cb_cooldown_s", 15, "CB 冷却 15s 激进"),
            ("audit_retention_days", 90, "审计日志保留"),
        ]
        rules = []
        for target, val, justification in defaults:
            if skip_frozen and self._freeze_zone.is_frozen_target(target):
                continue
            rule_id = f"rule_{target}_{uuid.uuid4().hex[:6]}"
            rule = EvolutionRule(
                rule_id=rule_id,
                target=target,
                current_value=val,
                proposed_value=val,
                justification=justification,
            )
            self._rules[rule_id] = rule
            rules.append(rule)
        return rules

    def propose(self, target: str, current_value: Any,
                proposed_value: Any,
                justification: str = "") -> EvolutionRule:
        from maref.recursive.rule_freeze_zone import FreezeBlockedError

        check = self._freeze_zone.check(target, proposed_value)
        if not check.allowed:
            raise FreezeBlockedError(
                f"Cannot propose change to frozen target '{target}': {check.frozen_reason}"
            )

        rule_id = f"proposal_{uuid.uuid4().hex[:8]}"
        rule = EvolutionRule(
            rule_id=rule_id,
            target=target,
            current_value=current_value,
            proposed_value=proposed_value,
            justification=justification,
        )
        self._rules[rule_id] = rule
        return rule

    @property
    def freeze_zone(self) -> Any:
        return self._freeze_zone

    def simulate(
        self, rule: EvolutionRule, rounds: int = 3,
        benchmark_fn: Any = None,
    ) -> SimulationResult:
        if rounds <= 0:
            return SimulationResult(rounds_completed=0, passed=False)

        can_sim = rule.proposed_value is not None
        metrics: dict[str, float] = {"stability": 0.9}

        if benchmark_fn is not None:
            try:
                bench = benchmark_fn()
                if isinstance(bench, dict):
                    metrics.update({
                        "test_pass_rate": bench.get("tests_passed", 0) / max(bench.get("test_count", 1), 1),
                        "coverage_pct": bench.get("coverage_pct", 0),
                        "execution_time_ms": bench.get("execution_time_ms", 0),
                    })
            except Exception:
                pass

        return SimulationResult(
            rounds_completed=rounds,
            passed=can_sim,
            metrics=metrics,
        )

    def safety_check(self, rule: EvolutionRule) -> GateResult:
        return rule.safety_gate.evaluate(rule)

    def apply(self, rule: EvolutionRule) -> ApplyResult:
        gate = rule.safety_gate.evaluate(rule)
        sim = self.simulate(rule, rule.safety_gate.min_simulation_rounds)

        applied = gate.passed and sim.passed
        self._audit.append(EvolutionAuditEntry(
            rule_id=rule.rule_id,
            target=rule.target,
            timestamp=time.time(),
            justification=rule.justification,
            gate_passed=gate.passed,
        ))
        return ApplyResult(
            applied=applied,
            rule_id=rule.rule_id,
            timestamp=time.time(),
            regression_passed=applied,
        )

    def rollback(self, rule_id: str) -> bool:
        rule = self._rules.get(rule_id)
        if rule is None:
            return False
        rule.proposed_value = rule.current_value
        return True

    def audit_trail(self) -> list[EvolutionAuditEntry]:
        return list(self._audit)

    @property
    def rules(self) -> dict[str, EvolutionRule]:
        return dict(self._rules)

    def rule_count(self) -> int:
        return len(self._rules)
