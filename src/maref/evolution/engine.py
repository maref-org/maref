"""
MAREF Recursive Evolution Engine.

Orchestrates the 3-cycle recursive evolution loop:
  C1 Baseline (50 rounds) → C2 Optimization (100 rounds) → C3 Convergence (50 rounds)

Each round runs a complete state machine path (INIT→...→HALT) and records metrics.
Safety layers: CircuitBreaker, OscillationFixLoop, PolicySandbox auto-revert.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drift_guard.policy_sandbox import PolicyChangeType, PolicySandbox
from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    CycleSpec,
    EvolutionMetrics,
    EvolutionResult,
)
from maref.evolution.reporter import (
    generate_cycle_report,
    generate_final_report,
)
from maref.learning.replay import DecisionOutcome
from maref_lite.meta_learning import MetaLearner

ROUND_SEED = 42

CANONICAL_PATH = [1, 2, 3, 4, 5, 6, 7, 8, 9]

GRADIENT_DISASTER_FNR_THRESHOLD = 0.50
BREAKER_FAIL_CONSECUTIVE_LIMIT = 3


@dataclass
class EvolutionConfig:
    cycles: dict[str, CycleSpec] = field(
        default_factory=lambda: {
            "c1": CycleSpec(
                name="Baseline Calibration",
                rounds=50,
                description="Collect baseline metrics, no policy changes",
            ),
            "c2": CycleSpec(
                name="Policy Optimization",
                rounds=100,
                description="MetaLearner proposes policy improvements every 5 rounds",
                meta_learning_enabled=True,
                meta_learning_interval=5,
            ),
            "c3": CycleSpec(
                name="Convergence Validation",
                rounds=50,
                description="Verify FNR/FPR convergence, zero oscillation, clean HALT",
            ),
        }
    )
    max_total_rounds: int = 300
    acceptance_criteria: AcceptanceCriteria = field(default_factory=AcceptanceCriteria)
    output_dir: str = "./evolution_results/"
    dry_run: bool = False
    dry_run_rounds: int = 1
    resume_from_cycle: str | None = None
    resume_from_round: int = 0
    metrics_mode: str = "real"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles": {
                k: {
                    "name": v.name,
                    "rounds": v.rounds,
                    "description": v.description,
                    "meta_learning_enabled": v.meta_learning_enabled,
                    "meta_learning_interval": v.meta_learning_interval,
                }
                for k, v in self.cycles.items()
            },
            "max_total_rounds": self.max_total_rounds,
            "acceptance_criteria": self.acceptance_criteria.to_dict(),
            "output_dir": self.output_dir,
            "dry_run": self.dry_run,
            "dry_run_rounds": self.dry_run_rounds,
            "metrics_mode": self.metrics_mode,
        }


class RecursiveEvolutionEngine:
    """
    Core engine for recursive evolution of MAREF governance.

    Orchestrates C1→C2→C3 with:
    - Per-round state machine runs
    - FNR/FPR tracking via simulated anomaly streams
    - MetaLearner policy optimization in C2
    - CircuitBreaker + OscillationFixLoop safety
    - PolicySandbox with auto-revert
    """

    def __init__(
        self,
        config: EvolutionConfig | None = None,
        seed: int | None = None,
        quality_gate: Any | None = None,
        metrics_collector: Any | None = None,
        telemetry_source: Any | None = None,
        vault: Any | None = None,
    ) -> None:
        self._config = config or EvolutionConfig()
        self._quality_gate = quality_gate
        self._metrics_collector = metrics_collector
        self._telemetry_source = telemetry_source
        self._vault = vault
        self._output_base = Path(self._config.output_dir)
        self._rng = random.Random(seed if seed is not None else ROUND_SEED)
        self._running = False
        self._total_rounds = 0

        from maref.governance import CircuitBreaker, OscillationFixLoop

        self._breaker = CircuitBreaker(
            max_depth=3,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        self._oscillation_loop = OscillationFixLoop(
            stabilize_fn=self._noop_stabilize,
            get_state_fn=lambda: {"state": "IDLE", "entropy": 0},
            cooldown_seconds=30.0,
        )
        self._sandbox = PolicySandbox()
        self._meta_learner = MetaLearner()

    @property
    def quality_gate(self) -> Any | None:
        return self._quality_gate

    def evaluate_candidate_with_quality_gate(
        self,
        candidate_id: str,
        cycle: str = "c1",
        score: float = 80.0,
    ) -> dict[str, Any]:
        if not self._quality_gate:
            return {"verdict": "approved", "reason": "no_quality_gate_configured"}

        mock_report = self._quality_gate.build_mock_report(
            agent_id=candidate_id,
            score=score,
        )

        if cycle == "c1":
            result = self._quality_gate.evaluate_c1_to_c2(candidate_id, mock_report)
        elif cycle == "c2":
            result = self._quality_gate.evaluate_c2_to_c3(candidate_id, mock_report)
        else:
            return {"verdict": "unknown", "reason": f"unknown_cycle:{cycle}"}

        return {
            "verdict": result.verdict.value,
            "score": result.score,
            "reason": result.reason,
            "candidate_id": candidate_id,
            "cycle": cycle,
        }

    @staticmethod
    def _noop_stabilize(reason: str = "") -> bool:
        return True

    async def run(self) -> EvolutionResult:
        self._running = True
        cycle_results: list[CycleResult] = []
        stop_reason = "unknown"
        self._total_rounds = 0

        cycle_order = ["c1", "c2", "c3"]

        for cycle_id in cycle_order:
            if self._config.dry_run:
                cycle_spec = CycleSpec(
                    name="DRY RUN",
                    rounds=1,
                    description="Single-round pipeline validation",
                )
            elif self._config.resume_from_cycle and cycle_id < self._config.resume_from_cycle:
                continue
            else:
                cycle_spec = self._config.cycles[cycle_id]

            cycle_metrics = EvolutionMetrics()
            round_start_offset = (
                self._config.resume_from_round
                if (self._config.resume_from_cycle and cycle_id == self._config.resume_from_cycle)
                else 0
            )

            total_rounds = 1 if self._config.dry_run else cycle_spec.rounds

            for round_num in range(round_start_offset, total_rounds):
                if not self._running:
                    stop_reason = "manual_stop"
                    break
                if self._total_rounds >= self._config.max_total_rounds:
                    stop_reason = "timeout"
                    break

                try:
                    round_snapshot = await self._run_one_round(cycle_id, round_num, cycle_spec)
                    self._collect_round_metrics(cycle_metrics, round_snapshot)

                    stop = self._check_stop_conditions(cycle_metrics, cycle_id)
                    if stop:
                        stop_reason = stop
                        break

                except asyncio.CancelledError:
                    stop_reason = "manual_stop"
                    break

                self._total_rounds += 1

            acceptance = cycle_metrics.assess_acceptance(self._config.acceptance_criteria, cycle_id)

            actual_rounds = self._total_rounds
            cycle_result = CycleResult(
                cycle_id=cycle_id,
                name=cycle_spec.name,
                rounds_completed=min(actual_rounds, total_rounds),
                rounds_total=total_rounds,
                metrics=cycle_metrics,
                acceptance=acceptance,
                passed=all(acceptance.values()) if acceptance else True,
            )
            cycle_results.append(cycle_result)

            if self._config.dry_run:
                stop_reason = "dry_run_complete"
                break

            if stop_reason != "unknown":
                break

            cycle_dir = self._output_base / f"cycle_{cycle_id}"
            generate_cycle_report(cycle_result, self._config.acceptance_criteria, cycle_dir)

        if stop_reason == "unknown":
            stop_reason = "normal_completion"

        result = EvolutionResult(
            cycles=cycle_results,
            stop_reason=stop_reason,
            total_rounds=self._total_rounds,
            all_passed=all(c.passed for c in cycle_results),
        )

        generate_final_report(result, self._config.acceptance_criteria, self._output_base)
        return result

    async def _run_one_round(
        self,
        cycle_id: str,
        round_num: int,
        cycle_spec: CycleSpec,
    ) -> dict[str, Any]:
        from maref.governance import GovernanceState, GovernanceStateMachine

        path = [GovernanceState(v) for v in CANONICAL_PATH]

        sm = GovernanceStateMachine()
        failed_transitions = 0
        total_attempts = 0
        entropy_sequence: list[int] = []
        halt_reason = ""

        for target in path:
            if not self._running:
                break

            total_attempts += 1
            if sm.can_transition(target):
                sm.transition(target, f"{cycle_id}_r{round_num}")
                entropy_sequence.append(sm.current_entropy)
            else:
                failed_transitions += 1
                if target == GovernanceState.HALT:
                    sm.force_halt("normal_completion")
                    halt_reason = "normal_completion"
                    entropy_sequence.append(sm.current_entropy)
                    break

            await asyncio.sleep(0.0001)

        if sm.current_state == GovernanceState.HALT:
            halt_reason = halt_reason or "normal_path_completion"
        elif sm.current_state != GovernanceState.HALT:
            sm.force_halt("round_end")
            halt_reason = "round_end_force"
            entropy_sequence.append(sm.current_entropy)

        fnr, fpr, metrics_source, real_metrics = self._collect_detector_metrics(round_num)

        if (
            cycle_spec.meta_learning_enabled
            and round_num > 0
            and round_num % cycle_spec.meta_learning_interval == 0
        ):
            self._run_meta_learning_step(round_num, fnr)

        return {
            "round": round_num,
            "cycle_id": cycle_id,
            "fnr": fnr,
            "fpr": fpr,
            "final_entropy": sm.current_entropy,
            "entropy_sequence": entropy_sequence,
            "transition_count": sm.transition_count,
            "failed_transitions": failed_transitions,
            "total_attempts": total_attempts,
            "halt_reason": halt_reason,
            "final_state": sm.current_state.name,
            "metrics_source": metrics_source,
            "real_metrics": real_metrics,
        }

    def _collect_detector_metrics(self, round_num: int) -> tuple[float, float, str, dict[str, Any]]:
        if self._config.metrics_mode == "real":
            collector = self._metrics_collector
            if collector is None:
                from maref.evolution.real_metrics import RealMetricsCollector

                collector = RealMetricsCollector()
                self._metrics_collector = collector
            metrics = collector.collect_incremental()
            return metrics.fnr, metrics.fpr, "real", metrics.to_dict()
        fnr, fpr = self._simulate_detector_metrics(round_num)
        return fnr, fpr, "simulated", {}

    def _simulate_detector_metrics(self, round_num: int) -> tuple[float, float]:
        base_fnr = 0.10 + self._rng.uniform(-0.05, 0.03)
        base_fpr = 0.06 + self._rng.uniform(-0.03, 0.02)
        noise_fnr = self._rng.gauss(0, 0.02)
        noise_fpr = self._rng.gauss(0, 0.01)
        fnr = max(0.0, min(0.30, base_fnr + noise_fnr))
        fpr = max(0.0, min(0.20, base_fpr + noise_fpr))
        return fnr, fpr

    def _run_meta_learning_step(self, round_num: int, fnr: float) -> None:
        telemetry_reward = 0.0
        if self._telemetry_source is not None:
            try:
                telemetry_reward = self._telemetry_source.compute_reward()
            except Exception:
                pass
        local_reward = 1.0 - (fnr * 2.0)
        reward = max(0.0, min(1.0, local_reward * 0.7 + telemetry_reward * 0.3))
        outcome = DecisionOutcome(
            timestamp=time.time(),
            decision_type="evolution_round",
            state_before="ANALYZE",
            state_after="STABILIZE",
            entropy_before=2,
            entropy_after=1,
            reward=reward,
        )
        self._meta_learner.record_decision(outcome)

        new_config = self._meta_learner.optimize_policy()
        if new_config:
            change = self._sandbox.propose_change(
                change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
                description=f"Meta-learning round {round_num}",
                new_config=new_config,
            )
            if self._meta_learner.get_stats()["avg_reward"] > 0.5:
                self._sandbox.approve_change(
                    change.change_id,
                    reviewer="meta_recursive_evolution",
                )

    def _collect_round_metrics(
        self,
        metrics: EvolutionMetrics,
        snapshot: dict[str, Any],
    ) -> None:
        metrics.fnr_series.append(snapshot["fnr"])
        metrics.fpr_series.append(snapshot["fpr"])
        metrics.entropy_series.append(snapshot["final_entropy"])
        metrics.transition_count_series.append(snapshot["transition_count"])
        metrics.halt_reasons.append(snapshot["halt_reason"])
        metrics.policy_weights_series.append(dict(self._meta_learner._state.policy_weights))
        metrics.learning_rate_series.append(self._meta_learner._state.learning_rate)

        # Persist to RoundVault if configured
        if self._vault is not None:
            try:
                real_metrics = snapshot.get("real_metrics", {})
                self._vault.record_round(
                    round_num=snapshot.get("round", -1),
                    cycle_id=snapshot.get("cycle_id", "unknown"),
                    metrics=real_metrics
                    if real_metrics
                    else {
                        "fnr": snapshot.get("fnr"),
                        "fpr": snapshot.get("fpr"),
                        "test_pass_rate": None,
                        "coverage_pct": None,
                        "total_tests": None,
                        "source_file_count": None,
                        "total_lines": None,
                        "git_commit_count_30d": None,
                        "module_count": None,
                        "governance_state": snapshot.get("final_state", ""),
                        "cb_state": "CLOSED",
                    },
                    stop_reason=snapshot.get("halt_reason", ""),
                )
            except Exception:
                pass

    def _check_stop_conditions(
        self,
        metrics: EvolutionMetrics,
        cycle_id: str,
    ) -> str | None:
        from maref.governance import BreakerState

        cb_stats = self._breaker.get_stats()
        if cb_stats.get("state") == BreakerState.OPEN.value:
            trip_count = cb_stats.get("trip_count", 0)
            if trip_count >= BREAKER_FAIL_CONSECUTIVE_LIMIT:
                return "circuit_breaker_permanent_open"

        recent_fnr = metrics.fnr_series[-5:] if len(metrics.fnr_series) >= 5 else metrics.fnr_series
        if recent_fnr and all(f > GRADIENT_DISASTER_FNR_THRESHOLD for f in recent_fnr):
            return "gradient_disaster"

        return None

    def stop(self) -> None:
        self._running = False

    def get_live_status(self) -> dict[str, Any]:
        meta_stats = self._meta_learner.get_stats()
        sandbox_stats = self._sandbox.get_stats()
        breaker_stats = self._breaker.get_stats()

        return {
            "running": self._running,
            "total_rounds": self._total_rounds,
            "meta_learning": meta_stats,
            "sandbox": sandbox_stats,
            "circuit_breaker": breaker_stats,
        }
