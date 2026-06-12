from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.self_observer import SelfObserver, SystemSnapshot
from maref.recursive.self_diagnostician import SelfDiagnostician, DiagnosisReport, RiskLevel
from maref.recursive.self_healer import SelfHealer, HealingRecord
from maref.recursive.self_architect import SelfArchitect, ArchitectureProposal
from maref.recursive.self_executor import SelfExecutor, ExecutionPipelineRecord
from maref.recursive.self_optimizer import SelfOptimizer, OptimizationHypothesis
from maref.recursive.unified_audit import UnifiedAuditStore, UnifiedAuditRecord, make_record_id
from maref.recursive.meta_governance import MetaGovernance, RecursionDepthExceededError


@dataclass
class LoopConfig:
    max_iterations: int = 5
    convergence_threshold: float = 0.05
    heal_after_diagnosis: bool = True
    optimize_enabled: bool = True
    architect_enabled: bool = True
    execute_enabled: bool = False
    audit_round: int = 0


@dataclass
class IterationResult:
    iteration: int
    steps_completed: list[str]
    snapshot: SystemSnapshot | None = None
    diagnosis: DiagnosisReport | None = None
    healing: HealingRecord | None = None
    optimizations: list[OptimizationHypothesis] | None = None
    proposals: list[ArchitectureProposal] | None = None
    execution: ExecutionPipelineRecord | None = None
    duration: float = 0.0


@dataclass
class LoopResult:
    iterations_completed: int
    converged: bool
    final_convergence_metric: float
    iteration_results: list[IterationResult] = field(default_factory=list)
    total_duration: float = 0.0


class SelfLoopRunner:
    def __init__(
        self,
        config: LoopConfig | None = None,
        observer: SelfObserver | None = None,
        diagnostician: SelfDiagnostician | None = None,
        healer: SelfHealer | None = None,
        optimizer: SelfOptimizer | None = None,
        architect: SelfArchitect | None = None,
        executor: SelfExecutor | None = None,
        audit_store: UnifiedAuditStore | None = None,
        meta_governance: MetaGovernance | None = None,
    ) -> None:
        self.config = config or LoopConfig()
        self._observer = observer or SelfObserver()
        self._diagnostician = diagnostician or SelfDiagnostician()
        self._healer = healer or SelfHealer()
        self._optimizer = optimizer or SelfOptimizer()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._executor = executor or SelfExecutor(audit_store=self._audit_store)
        self._architect = architect or SelfArchitect(audit_store=self._audit_store)
        self._meta_governance = meta_governance or MetaGovernance()
        self.current_iteration: int = 0
        self.is_running: bool = False
        self._previous_snapshots: list[SystemSnapshot] = []

    def _audit_log(self, event_type: str, source: str, target: str, decision: str, justification: str) -> None:
        record = UnifiedAuditRecord(
            record_id=make_record_id("loop", self.current_iteration),
            timestamp=time.time(),
            layer="self_loop",
            round=self.config.audit_round,
            event_type=event_type,
            source_module=source,
            target_module=target,
            decision=decision,
            justification=justification,
        )
        self._audit_store.append(record)

    def _observe(self) -> SystemSnapshot:
        self._audit_log("observe_start", "SelfLoopRunner", "SelfObserver", "start", "Beginning observation")
        snapshot = self._observer.snapshot()
        self._audit_log("observe_complete", "SelfObserver", "SelfLoopRunner", "complete", f"Observed {snapshot.source_file_count} files")
        return snapshot

    def _diagnose(self, snapshot: SystemSnapshot) -> DiagnosisReport:
        self._audit_log("diagnose_start", "SelfLoopRunner", "SelfDiagnostician", "start", "Beginning diagnosis")
        report = self._diagnostician.diagnose(snapshot)
        self._audit_log("diagnose_complete", "SelfDiagnostician", "SelfLoopRunner", "complete", f"Risk: {report.overall_risk.value}")
        return report

    def _heal(self, report: DiagnosisReport) -> HealingRecord | None:
        if not self.config.heal_after_diagnosis:
            return None
        if report.overall_risk == RiskLevel.NORMAL:
            self._audit_log("heal_skipped", "SelfLoopRunner", "SelfHealer", "skip", "No healing needed")
            return None
        self._audit_log("heal_start", "SelfLoopRunner", "SelfHealer", "start", "Beginning healing")
        result = self._healer.heal_cycle(report)
        state = result.final_state if result else "no_result"
        self._audit_log("heal_complete", "SelfHealer", "SelfLoopRunner", "complete", f"State: {state}")
        return result

    def _optimize(self, snapshot: SystemSnapshot) -> list[OptimizationHypothesis]:
        if not self.config.optimize_enabled:
            return []
        self._audit_log("optimize_start", "SelfLoopRunner", "SelfOptimizer", "start", "Beginning optimization")
        hypotheses = self._optimizer.propose_optimizations(snapshot)
        self._audit_log("optimize_complete", "SelfOptimizer", "SelfLoopRunner", "complete", f"Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def _plan(self) -> list[ArchitectureProposal]:
        if not self.config.architect_enabled:
            return []
        self._audit_log("architect_start", "SelfLoopRunner", "SelfArchitect", "start", "Beginning architecture analysis")
        proposals = self._architect.propose_all()
        self._audit_log("architect_complete", "SelfArchitect", "SelfLoopRunner", "complete", f"Generated {len(proposals)} proposals")
        return proposals

    def _execute(self, proposals: list[ArchitectureProposal]) -> ExecutionPipelineRecord | None:
        if not self.config.execute_enabled or not proposals:
            return None
        self._audit_log("execute_start", "SelfLoopRunner", "SelfExecutor", "start", "Beginning execution")
        record = self._executor.execute(proposals[0])
        self._audit_log("execute_complete", "SelfExecutor", "SelfLoopRunner", "complete", f"State: {record.final_state}")
        return record

    def _check_convergence(self, snapshot: SystemSnapshot) -> float:
        if not self._previous_snapshots:
            return 1.0
        prev = self._previous_snapshots[-1]
        diff = abs(snapshot.source_file_count - prev.source_file_count)
        diff += abs(len(snapshot.test_stats) - len(prev.test_stats))
        max_val = max(snapshot.source_file_count, 1)
        return max(0.0, 1.0 - diff / max_val)

    def run_one_iteration(self) -> IterationResult:
        start = time.time()
        steps: list[str] = []
        snapshot = self._observe()
        steps.append("observe")
        report = self._diagnose(snapshot)
        steps.append("diagnose")
        healing = self._heal(report)
        if healing:
            steps.append("heal")
        hypotheses = self._optimize(snapshot)
        if self.config.optimize_enabled:
            steps.append("optimize")
        proposals = self._plan()
        if self.config.architect_enabled:
            steps.append("architect")
        record = self._execute(proposals)
        if record:
            steps.append("execute")
        self._previous_snapshots.append(snapshot)
        self.current_iteration += 1
        return IterationResult(
            iteration=self.current_iteration,
            steps_completed=steps,
            snapshot=snapshot,
            diagnosis=report,
            healing=healing,
            optimizations=hypotheses,
            proposals=proposals,
            execution=record,
            duration=time.time() - start,
        )

    def dry_run(self) -> LoopResult:
        old_exec = self.config.execute_enabled
        old_audit = self.config.audit_round
        self.config.execute_enabled = False
        self.config.audit_round = 0
        result = self.run()
        self.config.execute_enabled = old_exec
        self.config.audit_round = old_audit
        return result

    def run(self) -> LoopResult:
        if self.is_running:
            raise RuntimeError("Loop is already running")
        self.is_running = True
        start = time.time()
        results: list[IterationResult] = []
        try:
            for i in range(self.config.max_iterations):
                result = self.run_one_iteration()
                results.append(result)
                if result.snapshot is not None:
                    convergence = self._check_convergence(result.snapshot)
                    if convergence >= (1.0 - self.config.convergence_threshold):
                        return LoopResult(
                            iterations_completed=i + 1,
                            converged=True,
                            final_convergence_metric=convergence,
                            iteration_results=results,
                            total_duration=time.time() - start,
                        )
        except RecursionDepthExceededError:
            self._audit_log("loop_halted", "MetaGovernance", "SelfLoopRunner", "halt", "Recursion depth exceeded")
        finally:
            self.is_running = False
        return LoopResult(
            iterations_completed=len(results),
            converged=False,
            final_convergence_metric=0.0,
            iteration_results=results,
            total_duration=time.time() - start,
        )
