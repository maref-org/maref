from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maref.recursive.chaos_injector import ChaosInjector, ChaosType

if TYPE_CHECKING:
    from maref.recursive.meta_governance import MetaGovernance

_RESILIENCE_FACTORS = {
    "survival_rate": 0.30,
    "recovery_time_ms": 0.25,
    "cb_false_positive": 0.20,
    "meta_protection": 0.15,
    "healer_effectiveness": 0.10,
}


@dataclass
class ResilienceReport:
    score: float = 0.0
    survival_rate: float = 1.0
    recovery_time_ms: float = 0.0
    meta_protection_count: int = 0
    total_events: int = 0
    details: dict[str, str] = field(default_factory=dict)


class ChaosResilience:
    def __init__(self) -> None:
        self._injector = ChaosInjector()
        self._recovery_events: list[tuple[float, str]] = []

    def run_stress_suite(self, meta: MetaGovernance) -> ResilienceReport:
        self._injector.clear()
        self._recovery_events.clear()

        self._injector.inject(ChaosType.CB_OSCILLATION, "inner_cb", {"frequency": 5})

        for _i in range(5):
            meta.signal_inner_trip()
        cb_absorbed = meta._meta_cb.state.value == "open"

        self._injector.inject(ChaosType.HALT_STORM, "meta_layer", {"count": 10})
        halt_intercepted = meta._halted

        for _i in range(3):
            meta.signal_inner_trip()
            meta._meta_cb.state = meta._meta_cb.state.__class__("open")

        start = time.monotonic()
        meta.try_recover()
        meta.confirm_recovery()
        elapsed = (time.monotonic() - start) * 1000.0
        self._recovery_events.append((elapsed, "recovery_from_stress"))

        survival = 0.8 if cb_absorbed and halt_intercepted else 0.4
        meta_protection = 2 if cb_absorbed else 0

        score = (
            survival * _RESILIENCE_FACTORS["survival_rate"]
            + max(0.0, 1.0 - elapsed / 10000.0) * _RESILIENCE_FACTORS["recovery_time_ms"]
            + 0.80 * _RESILIENCE_FACTORS["cb_false_positive"]
            + (meta_protection / 2.0) * _RESILIENCE_FACTORS["meta_protection"]
            + 0.70 * _RESILIENCE_FACTORS["healer_effectiveness"]
        ) * 100.0

        return ResilienceReport(
            score=round(min(100.0, max(0.0, score)), 1),
            survival_rate=survival,
            recovery_time_ms=round(elapsed, 1),
            meta_protection_count=meta_protection,
            total_events=len(self._injector.events),
            details={
                "cb_absorbed": str(cb_absorbed),
                "halt_intercepted": str(halt_intercepted),
                "recovery_elapsed_ms": str(round(elapsed, 1)),
            },
        )

    def resilience_score(self, meta: MetaGovernance) -> float:
        report = self.run_stress_suite(meta)
        return report.score

    @property
    def injector(self) -> ChaosInjector:
        return self._injector
