import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.self_architect import SelfArchitect
from maref.recursive.self_diagnostician import SelfDiagnostician
from maref.recursive.self_executor import SelfExecutor
from maref.recursive.self_healer import SelfHealer
from maref.recursive.self_observer import SelfObserver
from maref.recursive.unified_audit import UnifiedAudit

logger = logging.getLogger(__name__)


@dataclass
class SelfHealingConfig:
    max_cycles: int = 10
    healing_threshold: float = 0.8
    auto_heal: bool = True
    check_interval_seconds: float = 300.0
    proposal_dry_run: bool = True
    max_heal_iterations: int = 3
    enable_architecture_proposals: bool = True
    enable_proposal_execution: bool = True
    max_proposals_per_cycle: int = 3
    arch_proposal_interval_cycles: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cycles": self.max_cycles,
            "healing_threshold": self.healing_threshold,
            "auto_heal": self.auto_heal,
            "check_interval_seconds": self.check_interval_seconds,
            "proposal_dry_run": self.proposal_dry_run,
            "max_heal_iterations": self.max_heal_iterations,
            "enable_architecture_proposals": self.enable_architecture_proposals,
            "enable_proposal_execution": self.enable_proposal_execution,
            "max_proposals_per_cycle": self.max_proposals_per_cycle,
            "arch_proposal_interval_cycles": self.arch_proposal_interval_cycles,
        }


@dataclass
class HealingCycleReport:
    cycle_id: int
    timestamp: float
    risk_level: str = "low"
    risk_matrix: dict[str, Any] = field(default_factory=dict)
    problems_found: list[str] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    converged: bool = True
    final_state: str = "HEALTHY"
    duration_ms: float = 0.0
    proposals_generated: int = 0
    proposals_executed: int = 0
    proposals_succeeded: int = 0
    proposals_failed: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_matrix": self.risk_matrix,
            "problems_found": self.problems_found,
            "actions_taken": self.actions_taken,
            "converged": self.converged,
            "final_state": self.final_state,
            "duration_ms": self.duration_ms,
            "proposals_generated": self.proposals_generated,
            "proposals_executed": self.proposals_executed,
            "proposals_succeeded": self.proposals_succeeded,
            "proposals_failed": self.proposals_failed,
            "details": self.details,
            "status": self.status,
        }


class SelfHealingLoop:
    def __init__(self, config: SelfHealingConfig | None = None) -> None:
        self._config: SelfHealingConfig = config or SelfHealingConfig()
        self._running: bool = False
        self._history: list[HealingCycleReport] = []
        self._cycle_count: int = 0
        self._audit = UnifiedAudit()
        self._architect = SelfArchitect(audit_store=self._audit.store)
        self._diagnostician = SelfDiagnostician()
        self._executor = SelfExecutor()
        self._healer = SelfHealer()
        self._observer = SelfObserver()

    @property
    def config(self) -> SelfHealingConfig:
        return self._config

    @property
    def running(self) -> bool:
        return self._running

    @property
    def history(self) -> list[HealingCycleReport]:
        return self._history.copy()

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._run_one_cycle()
            except Exception as exc:
                self._cycle_count += 1
                self._history.append(
                    HealingCycleReport(
                        cycle_id=self._cycle_count,
                        timestamp=time.time(),
                        status="cycle_error",
                        final_state="CYCLE_ERROR",
                        converged=False,
                        risk_level="high",
                        problems_found=[str(exc)],
                        duration_ms=0.0,
                    )
                )
            await asyncio.sleep(self.config.check_interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _lazy_init(self) -> None:
        if self._observer is not None:
            return
        from maref.recursive.self_observer import SelfObserver

        self._observer = SelfObserver()

    async def _run_one_cycle(self) -> HealingCycleReport:
        """Execute one observe -> diagnose -> heal -> verify cycle (P5.5)."""
        self._cycle_count += 1
        cycle_id = self._cycle_count
        start = time.time()

        # 1. Observe - snapshot the system state
        try:
            snapshot = self._observer.snapshot()
        except Exception as exc:
            report = HealingCycleReport(
                cycle_id=cycle_id,
                timestamp=start,
                status="observe_failed",
                final_state="OBSERVE_FAILED",
                converged=False,
                risk_level="high",
                problems_found=[f"observe error: {exc}"],
                duration_ms=(time.time() - start) * 1000,
            )
            self._history.append(report)
            return report

        # 2. Diagnose - assess risk from snapshot
        try:
            diagnosis = self._diagnostician.diagnose(snapshot)
        except Exception as exc:
            report = HealingCycleReport(
                cycle_id=cycle_id,
                timestamp=start,
                status="diagnose_failed",
                final_state="DIAGNOSE_FAILED",
                converged=False,
                risk_level="high",
                problems_found=[f"diagnose error: {exc}"],
                duration_ms=(time.time() - start) * 1000,
            )
            self._history.append(report)
            return report

        # 3. Triage + 4. Heal
        try:
            problems = self._healer.triage(diagnosis)
            healing = self._healer.heal_cycle(
                diagnosis,
                auto_re_diagnose=True,
                _observer=self._observer,
                _diagnostician=self._diagnostician,
            )
        except Exception as exc:
            report = HealingCycleReport(
                cycle_id=cycle_id,
                timestamp=start,
                status="heal_failed",
                final_state="HEAL_FAILED",
                converged=False,
                risk_level="high",
                problems_found=[f"heal error: {exc}"],
                duration_ms=(time.time() - start) * 1000,
            )
            self._history.append(report)
            return report

        # 5. Map final state to risk level
        _RISK_MAP = {
            "HEALTHY": "low",
            "RECOVERED": "low",
            "STABLE_WITH_RISK": "medium",
            "DEGRADED": "high",
        }
        risk_level = _RISK_MAP.get(healing.final_state, "medium")

        # 6. Build actions summary
        actions_taken = [
            {
                "strategy": a.strategy,
                "problem_type": a.problem_type,
                "success": a.success,
                "detail": a.detail,
            }
            for a in healing.actions
        ]

        # 7. Record to unified audit (best-effort)
        try:
            audit_records = healing.to_unified(round_num=cycle_id)
            for record in audit_records:
                self._audit.log(record)
        except Exception:
            pass

        cycle_report = HealingCycleReport(
            cycle_id=cycle_id,
            timestamp=start,
            status=healing.final_state.lower(),
            final_state=healing.final_state,
            details={
                "overall_risk": diagnosis.overall_risk.value,
                "iterations": healing.iterations,
                "actions_count": len(healing.actions),
                "cb_state": diagnosis.cb_status,
            },
            converged=healing.converged,
            risk_level=risk_level,
            problems_found=problems,
            actions_taken=actions_taken,
            duration_ms=(time.time() - start) * 1000,
        )
        self._history.append(cycle_report)
        return cycle_report

    def get_status_summary(self) -> dict[str, Any]:
        recent = self._history[-5:]
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "config": self._config.to_dict(),
            "recent_cycles": [r.to_dict() for r in recent],
        }

    def _log_cycle_result(self, report: HealingCycleReport) -> None:
        try:
            logger.info("heal cycle %s finished with status %s", report.cycle_id, report.status)
        except Exception:
            pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "history": [
                {"cycle_id": r.cycle_id, "status": r.status, "details": r.details}
                for r in self._history
            ],
        }
