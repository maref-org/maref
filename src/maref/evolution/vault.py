"""EvolutionVault — cross-round persistence for recursive evolution snapshots."""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


class TrendDirection(Enum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class EvolutionSnapshot:
    """Single round snapshot persisted to vault."""
    timestamp: float
    round_num: int
    cycle_id: str
    fnr: float
    fpr: float
    test_pass_rate: float | None = None
    coverage_pct: float | None = None
    entropy: float | None = None
    transition_count: int | None = None
    meta_stats: dict[str, Any] = field(default_factory=dict)
    real_metrics: dict[str, Any] = field(default_factory=dict)
    halt_reason: str = ""
    final_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "round_num": self.round_num,
            "cycle_id": self.cycle_id,
            "fnr": self.fnr,
            "fpr": self.fpr,
            "test_pass_rate": self.test_pass_rate,
            "coverage_pct": self.coverage_pct,
            "entropy": self.entropy,
            "transition_count": self.transition_count,
            "meta_stats": self.meta_stats,
            "real_metrics": self.real_metrics,
            "halt_reason": self.halt_reason,
            "final_state": self.final_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvolutionSnapshot:
        return cls(
            timestamp=data["timestamp"],
            round_num=data["round_num"],
            cycle_id=data["cycle_id"],
            fnr=data["fnr"],
            fpr=data["fpr"],
            test_pass_rate=data.get("test_pass_rate"),
            coverage_pct=data.get("coverage_pct"),
            entropy=data.get("entropy"),
            transition_count=data.get("transition_count"),
            meta_stats=data.get("meta_stats", {}),
            real_metrics=data.get("real_metrics", {}),
            halt_reason=data.get("halt_reason", ""),
            final_state=data.get("final_state", ""),
        )


@dataclass
class TrendResult:
    metric_name: str
    direction: TrendDirection
    slope: float
    mean: float
    std: float
    window_size: int
    values: list[float] = field(default_factory=list)


@dataclass
class DailyReport:
    """Aggregated daily evolution report."""
    date: str
    total_rounds: int
    cycles_completed: list[str]
    avg_fnr: float
    avg_fpr: float
    best_fnr: float
    best_fpr: float
    trends: dict[str, TrendResult] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)
    real_metrics_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total_rounds": self.total_rounds,
            "cycles_completed": self.cycles_completed,
            "avg_fnr": round(self.avg_fnr, 4),
            "avg_fpr": round(self.avg_fpr, 4),
            "best_fnr": round(self.best_fnr, 4),
            "best_fpr": round(self.best_fpr, 4),
            "trends": {k: {
                "direction": v.direction.value,
                "slope": round(v.slope, 4),
                "mean": round(v.mean, 4),
                "std": round(v.std, 4),
            } for k, v in self.trends.items()},
            "anomalies": self.anomalies,
            "real_metrics_summary": self.real_metrics_summary,
        }


class EvolutionVault:
    """Cross-round evolution persistence store.

    Stores JSONL snapshots under vault/evolution/YYYY-MM-DD/rounds.jsonl
    and provides trend analysis across historical data.
    Automatically prunes snapshots older than 90 days.
    """

    DEFAULT_RETENTION_DAYS = 90

    def __init__(self, vault_dir: str | Path | None = None) -> None:
        self._vault = Path(vault_dir) if vault_dir else Path("vault") / "evolution"
        self._vault.mkdir(parents=True, exist_ok=True)

    @property
    def vault_dir(self) -> Path:
        return self._vault

    def _today_dir(self) -> Path:
        today = date.today().isoformat()
        day_dir = self._vault / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _rounds_file(self, day: str | None = None) -> Path:
        target = day or date.today().isoformat()
        day_dir = self._vault / target
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / "rounds.jsonl"

    def save_snapshot(self, snapshot: EvolutionSnapshot) -> str:
        """Append a snapshot to today's JSONL file. Returns the file path."""
        file_path = self._rounds_file()
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot.to_dict(), default=str) + "\n")
        return str(file_path)

    def save_round_direct(
        self,
        round_num: int,
        cycle_id: str,
        fnr: float,
        fpr: float,
        **kwargs: Any,
    ) -> str:
        """Convenience: create and save a snapshot from raw values."""
        snapshot = EvolutionSnapshot(
            timestamp=time.time(),
            round_num=round_num,
            cycle_id=cycle_id,
            fnr=fnr,
            fpr=fpr,
            **kwargs,
        )
        return self.save_snapshot(snapshot)

    def load_history(self, last_n: int = 100) -> list[EvolutionSnapshot]:
        """Load the most recent N snapshots across all days."""
        all_snapshots: list[tuple[float, EvolutionSnapshot]] = []

        for day_dir in sorted(self._vault.iterdir()):
            if not day_dir.is_dir():
                continue
            rounds_file = day_dir / "rounds.jsonl"
            if not rounds_file.exists():
                continue
            with open(rounds_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    snap = EvolutionSnapshot.from_dict(data)
                    all_snapshots.append((snap.timestamp, snap))

        all_snapshots.sort(key=lambda x: x[0])
        return [s for _, s in all_snapshots[-last_n:]]

    def load_by_date(self, day: str) -> list[EvolutionSnapshot]:
        """Load all snapshots for a specific date (YYYY-MM-DD)."""
        file_path = self._rounds_file(day)
        if not file_path.exists():
            return []
        snapshots: list[EvolutionSnapshot] = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                snapshots.append(EvolutionSnapshot.from_dict(data))
        return snapshots

    def get_trend(self, metric_name: str, window: int = 7) -> TrendResult:
        """Calculate trend for a metric over the last N snapshots."""
        history = self.load_history(last_n=window)
        if len(history) < 2:
            return TrendResult(
                metric_name=metric_name,
                direction=TrendDirection.INSUFFICIENT_DATA,
                slope=0.0,
                mean=0.0,
                std=0.0,
                window_size=len(history),
            )

        values = [getattr(s, metric_name, 0.0) or 0.0 for s in history]
        n = len(values)
        mean = statistics.mean(values)
        std = statistics.stdev(values) if n >= 2 else 0.0

        # Simple linear regression slope
        x_mean = (n - 1) / 2.0
        y_mean = mean
        num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0.0

        # Determine direction
        if abs(slope) < 0.001:
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.RISING
        else:
            direction = TrendDirection.FALLING

        return TrendResult(
            metric_name=metric_name,
            direction=direction,
            slope=round(slope, 4),
            mean=round(mean, 4),
            std=round(std, 4),
            window_size=n,
            values=values,
        )

    def generate_daily_report(self, day: str | None = None) -> DailyReport | None:
        """Generate an aggregated daily evolution report."""
        target = day or date.today().isoformat()
        snapshots = self.load_by_date(target)
        if not snapshots:
            return None

        fnrs = [s.fnr for s in snapshots]
        fprs = [s.fpr for s in snapshots]
        cycles = sorted({s.cycle_id for s in snapshots})

        trends = {
            "fnr": self.get_trend("fnr", window=len(snapshots)),
            "fpr": self.get_trend("fpr", window=len(snapshots)),
        }

        anomalies: list[str] = []
        for _i, s in enumerate(snapshots):
            if s.fnr > 0.5:
                anomalies.append(f"Round {s.round_num}: FNR={s.fnr:.3f} > 0.5 threshold")
            if s.fpr > 0.3:
                anomalies.append(f"Round {s.round_num}: FPR={s.fpr:.3f} > 0.3 threshold")

        real_metrics_summary: dict[str, Any] = {}
        real_data = [s.real_metrics for s in snapshots if s.real_metrics]
        if real_data:
            real_metrics_summary = {
                "count": len(real_data),
                "latest": real_data[-1],
            }

        return DailyReport(
            date=target,
            total_rounds=len(snapshots),
            cycles_completed=cycles,
            avg_fnr=statistics.mean(fnrs),
            avg_fpr=statistics.mean(fprs),
            best_fnr=min(fnrs),
            best_fpr=min(fprs),
            trends=trends,
            anomalies=anomalies,
            real_metrics_summary=real_metrics_summary,
        )

    def cleanup_old_snapshots(self, retention_days: int | None = None) -> int:
        """Remove snapshot files older than retention_days. Returns count of removed files."""
        from datetime import timedelta

        days = retention_days or self.DEFAULT_RETENTION_DAYS
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        removed = 0
        for day_dir in sorted(self._vault.iterdir()):
            if not day_dir.is_dir():
                continue
            if day_dir.name < cutoff:
                import shutil
                shutil.rmtree(day_dir)
                removed += 1

        return removed
