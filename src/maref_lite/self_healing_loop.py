import asyncio
import logging
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

    def __init__(self, config: SelfHealingConfig | None=None) -> None:
        self.config = config or SelfHealingConfig()
        self._running: bool = False
        self._history: list[HealingCycleReport] = []
        self._cycle_count: int = 0
        self._architect = SelfArchitect()  # type: ignore[call-arg]
        self._diagnostician = SelfDiagnostician()
        self._executor = SelfExecutor()
        self._healer = SelfHealer()
        self._observer = SelfObserver()
        self._audit = UnifiedAudit()

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
        cycle_id = self._cycle_count + 1
        self._cycle_count = cycle_id
        report = HealingCycleReport(cycle_id=cycle_id, status="completed")
        self._history.append(report)
        return report

    def to_dict(self) -> dict[str, Any]:
        return {'running': self._running, 'cycle_count': self._cycle_count, 'history': [{'cycle_id': r.cycle_id, 'status': r.status, 'details': r.details} for r in self._history]}
