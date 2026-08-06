from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConvergenceSnapshot:
    round_num: int
    cycle_id: str
    fnr: float
    fpr: float
    kl_drift: float
    perf_score: float
    gain_pct: float
    saturated: bool
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConvergenceSnapshot:
        return cls(
            round_num=data.get("round", data.get("round_num", 0)),
            cycle_id=data.get("cycle_id", "unknown"),
            fnr=data.get("fnr", 0.0),
            fpr=data.get("fpr", 0.0),
            kl_drift=data.get("kl_drift", 0.0),
            perf_score=data.get("perf_score", 1.0),
            gain_pct=data.get("gain_pct", 0.0),
            saturated=data.get("saturated", False),
            timestamp=data.get("timestamp", time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_num,
            "cycle_id": self.cycle_id,
            "fnr": self.fnr,
            "fpr": self.fpr,
            "kl_drift": self.kl_drift,
            "perf_score": self.perf_score,
            "gain_pct": self.gain_pct,
            "saturated": self.saturated,
            "timestamp": self.timestamp,
        }


class ConvergenceDashboard:
    def __init__(self, history_path: str = "convergence_history.jsonl") -> None:
        self._history_path = Path(history_path)
        self._snapshots: list[ConvergenceSnapshot] = []
        self._load_history()

    def _load_history(self) -> None:
        if self._history_path.exists():
            with open(self._history_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._snapshots.append(ConvergenceSnapshot.from_dict(json.loads(line)))
                        except (json.JSONDecodeError, KeyError):
                            continue

    def record(self, snapshot: ConvergenceSnapshot) -> None:
        self._snapshots.append(snapshot)
        with open(self._history_path, "a") as f:
            f.write(json.dumps(snapshot.to_dict()) + "\n")

    def compute_convergence_curves(self) -> dict[str, dict[str, list[float]]]:
        by_cycle: dict[str, list[ConvergenceSnapshot]] = defaultdict(list)
        for snap in self._snapshots:
            by_cycle[snap.cycle_id].append(snap)

        curves: dict[str, dict[str, list[float]]] = {}
        for cycle_id, snaps in by_cycle.items():
            snaps_sorted = sorted(snaps, key=lambda s: s.round_num)
            curves[cycle_id] = {
                "rounds": [s.round_num for s in snaps_sorted],
                "fnr": [s.fnr for s in snaps_sorted],
                "fpr": [s.fpr for s in snaps_sorted],
                "kl_drift": [s.kl_drift for s in snaps_sorted],
                "perf_score": [s.perf_score for s in snaps_sorted],
                "gain_pct": [s.gain_pct for s in snaps_sorted],
            }
        return curves

    def detect_saturation(self, sensitivity: float = 0.003, windows: int = 5) -> dict[str, Any]:
        curves = self.compute_convergence_curves()
        result: dict[str, Any] = {"saturated_cycles": [], "details": {}}

        for cycle_id, data in curves.items():
            gains = data.get("gain_pct", [])
            if len(gains) < windows:
                continue

            is_saturated = all(abs(g) < sensitivity for g in gains[-windows:])
            result["details"][cycle_id] = {
                "saturated": is_saturated,
                "recent_gains": gains[-windows:],
                "mean_recent_gain": statistics.mean(gains[-windows:]) if gains[-windows:] else 0.0,
                "total_rounds": len(data["rounds"]),
            }
            if is_saturated:
                result["saturated_cycles"].append(cycle_id)

        result["overall_saturated"] = len(result["saturated_cycles"]) > 0
        return result

    def compute_pareto_front(self) -> list[dict[str, Any]]:
        if not self._snapshots:
            return []

        by_cycle: dict[str, list[ConvergenceSnapshot]] = defaultdict(list)
        for snap in self._snapshots:
            by_cycle[snap.cycle_id].append(snap)

        pareto_points: list[dict[str, Any]] = []
        for cycle_id, snaps in by_cycle.items():
            last = snaps[-1]
            pareto_points.append(
                {
                    "cycle_id": cycle_id,
                    "fnr": last.fnr,
                    "fpr": last.fpr,
                    "kl_drift": last.kl_drift,
                    "perf_score": last.perf_score,
                    "round": last.round_num,
                }
            )

        pareto_front: list[dict[str, Any]] = []
        for i, p1 in enumerate(pareto_points):
            dominated = False
            for j, p2 in enumerate(pareto_points):
                if i == j:
                    continue
                if (
                    p2["fnr"] <= p1["fnr"]
                    and p2["fpr"] <= p1["fpr"]
                    and p2["kl_drift"] <= p1["kl_drift"]
                    and p2["perf_score"] >= p1["perf_score"]
                    and (
                        p2["fnr"] < p1["fnr"]
                        or p2["fpr"] < p1["fpr"]
                        or p2["kl_drift"] < p1["kl_drift"]
                        or p2["perf_score"] > p1["perf_score"]
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                pareto_front.append(p1)

        return pareto_front

    def export_report(self, format: str = "markdown") -> str:
        curves = self.compute_convergence_curves()
        saturation = self.detect_saturation()
        pareto = self.compute_pareto_front()

        if format == "json":
            return json.dumps(
                {
                    "curves": {
                        k: {mk: mv[-10:] for k, v in curves.items() for mk, mv in v.items()}
                        for k, v in curves.items()
                    },
                    "saturation": saturation,
                    "pareto_front": pareto,
                },
                indent=2,
            )

        lines = [
            "# MAREF Convergence Report",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total snapshots: {len(self._snapshots)}",
            f"Cycles tracked: {len(curves)}",
            "",
            "## Convergence Curves",
        ]

        for cycle_id, data in curves.items():
            lines.append(f"\n### Cycle: {cycle_id}")
            rounds = data["rounds"]
            fnr_last = data["fnr"][-1] if data["fnr"] else float("nan")
            fpr_last = data["fpr"][-1] if data["fpr"] else float("nan")
            kl_last = data["kl_drift"][-1] if data["kl_drift"] else float("nan")
            perf_last = data["perf_score"][-1] if data["perf_score"] else float("nan")

            lines.append(
                f"- Rounds: {min(rounds) if rounds else 0} → {max(rounds) if rounds else 0} ({len(rounds)} total)"
            )
            lines.append(f"- Final FNR: {fnr_last:.4f}")
            lines.append(f"- Final FPR: {fpr_last:.4f}")
            lines.append(f"- Final KL-drift: {kl_last:.4f}")
            lines.append(f"- Final Perf Score: {perf_last:.4f}")

        lines.append("\n## Saturation Analysis")
        lines.append(f"Overall saturated: {saturation['overall_saturated']}")
        for cycle_id, detail in saturation["details"].items():
            status = "SATURATED" if detail["saturated"] else "ACTIVE"
            lines.append(f"- {cycle_id}: {status} (mean gain: {detail['mean_recent_gain']:.6f})")

        lines.append("\n## Pareto Front")
        for point in pareto:
            lines.append(
                f"- {point['cycle_id']}: "
                f"FNR={point['fnr']:.4f}, FPR={point['fpr']:.4f}, "
                f"KL={point['kl_drift']:.4f}, Perf={point['perf_score']:.4f}"
            )

        return "\n".join(lines)

    def plot_convergence(self) -> str:
        curves = self.compute_convergence_curves()
        if not curves:
            return "No data to plot."

        lines: list[str] = []
        lines.append("=" * 68)
        lines.append("  MAREF Convergence Dashboard — Terminal Plot")
        lines.append("=" * 68)

        for cycle_id, data in curves.items():
            lines.append(f"\n  ── {cycle_id} ──")
            for metric_name, color_char in [
                ("fnr", "F"),
                ("fpr", "P"),
                ("kl_drift", "K"),
                ("perf_score", "S"),
                ("gain_pct", "G"),
            ]:
                values = data.get(metric_name, [])
                if len(values) < 2:
                    continue

                min_val = min(values)
                max_val = max(values)
                val_range = max_val - min_val if max_val != min_val else 1.0
                last_val = values[-1]
                trend = (
                    "↗"
                    if len(values) >= 2 and values[-1] > values[-2]
                    else ("↘" if len(values) >= 2 and values[-1] < values[-2] else "→")
                )

                bar_width = 40
                normalized = (last_val - min_val) / val_range
                filled = int(normalized * bar_width)

                bar = f"  {color_char} [{trend}] "
                bar += "█" * filled + "░" * (bar_width - filled)
                bar += f" {last_val:8.4f}"
                lines.append(bar)

        lines.append("\n" + "=" * 68)
        lines.append(
            f"  Total snapshots: {len(self._snapshots)}  |  Saturated: {self.detect_saturation()['overall_saturated']}"
        )
        lines.append("=" * 68)

        return "\n".join(lines)

    @property
    def snapshots(self) -> list[ConvergenceSnapshot]:
        return list(self._snapshots)

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def clear(self) -> None:
        self._snapshots.clear()
        if self._history_path.exists():
            self._history_path.unlink()
