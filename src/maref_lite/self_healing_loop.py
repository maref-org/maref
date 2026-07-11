from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
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

@dataclass
class HealingCycleReport:
    cycle_id: int
    status: str
    details: Dict[str, Any]

class SelfHealingLoop:
    def __init__(self, config: Optional[SelfHealingConfig] = None) -> None:
        self.config = config or SelfHealingConfig()
        self._running: bool = False
        self._history: List[HealingCycleReport] = []
        self._cycle_count: int = 0
        self._architect = SelfArchitect()
        self._diagnostician = SelfDiagnostician()
        self._executor = SelfExecutor()
        self._healer = SelfHealer()
        self._observer = SelfObserver()
        self._audit = UnifiedAudit()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def history(self) -> List[HealingCycleReport]:
        return self._history.copy()

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "history": [
                {"cycle_id": r.cycle_id, "status": r.status, "details": r.details}
                for r in self._history
            ],
        }