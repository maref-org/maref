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
    check_interval_seconds: int = 300
    proposal_dry_run: bool = True
    max_heal_iterations: int = 5
    enable_architecture_proposals: bool = False
    arch_proposal_interval_cycles: int = 10


@dataclass
class HealingCycleReport:
    cycle_id: int
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    converged: bool = True
    risk_level: str = "low"
    problems_found: list[str] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


class SelfHealingLoop:
    def __init__(self, config: SelfHealingConfig | None = None) -> None:
        self.config = config or SelfHealingConfig()
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
            await self._run_one_cycle()
            await asyncio.sleep(self.config.check_interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _lazy_init(self) -> None:
        pass

    async def _run_one_cycle(self) -> HealingCycleReport:
        """Execute one observe -> diagnose -> heal -> verify cycle (P5.5)."""
        cycle_id = self._cycle_count + 1
        self._cycle_count = cycle_id
        start = time.time()

        # 1. Observe - snapshot the system state
        try:
            snapshot = self._observer.snapshot()
        except Exception as exc:
            report = HealingCycleReport(
                cycle_id=cycle_id,
                status="observe_failed",
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
                status="diagnose_failed",
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
                status="heal_failed",
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
            status=healing.final_state.lower(),
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "history": [
                {"cycle_id": r.cycle_id, "status": r.status, "details": r.details}
                for r in self._history
            ],
        }
